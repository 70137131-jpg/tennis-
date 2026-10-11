"""Session-scoped match review, optimistic score updates and private exports."""

import hashlib
import json
import re
import secrets
import threading
from typing import Literal

from fastapi import BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.store import now
from courtside.court import CourtCalibration
from courtside.highlights import export_highlights
from courtside.match import bounce_candidates, detect_rallies, judge_bounce, score_match
from courtside.video import inspect_video


class MatchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    players: list[str] = Field(default=["You", "Opponent"], min_length=2, max_length=2)
    best_of: Literal[1, 3, 5] = 3
    first_server: Literal[0, 1] = 0
    no_ad: bool = False


class MatchAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[a-zA-Z0-9-]{8,64}$")
    revision: int = Field(ge=0)
    action: Literal["point", "undo", "configure"]
    winner: Literal[0, 1] | None = None
    rally_id: str | None = Field(default=None, max_length=40)
    config: MatchConfig | None = None


class LineReview(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    time: float = Field(ge=0)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    zone: Literal[
        "singles",
        "doubles",
        "far-left-service",
        "far-right-service",
        "near-left-service",
        "near-right-service",
    ] = "singles"
    uncertainty_m: float = Field(default=0.12, ge=0.05, le=1)
    ground_contact_confirmed: bool = False
    corners: list[list[float]] | None = None


class HighlightRequest(BaseModel):
    rally_ids: list[str] = Field(min_length=1, max_length=50)


def register_match(app, store, authorize, get_session, signed_url):
    with store.connection() as db:
        db.execute(
            "UPDATE highlight_exports SET status='failed',error='Export interrupted. Please try again.' WHERE status='processing'"
        )
    export_slot = threading.BoundedSemaphore(1)

    def initial(sid):
        session = get_session(sid)
        return {
            "session_id": sid,
            "revision": 0,
            "config": {
                "players": [session["options"].get("player_name", "You"), "Opponent"],
                "best_of": 3,
                "first_server": 0,
                "no_ad": False,
            },
            "events": [],
        }

    def read_state(sid, db):
        row = db.execute("SELECT payload FROM match_states WHERE session_id=?", (sid,)).fetchone()
        return json.loads(row[0]) if row else initial(sid)

    def expose(state):
        return {**state, "score": score_match(state["events"], state["config"])}

    def rallies(sid):
        session = get_session(sid)
        report = session.get("report") or {}
        return detect_rallies(report.get("shots", []), session["metadata"]["duration"])

    def safe_asset(sid, filename):
        directory = (store.root / "sessions" / sid).resolve()
        target = (directory / filename).resolve()
        if not target.is_relative_to(directory) or not target.is_file():
            raise HTTPException(404, "Session video is unavailable")
        return target

    @app.get("/api/sessions/{sid}/match", dependencies=[Depends(authorize)])
    def match(sid: str):
        get_session(sid)
        with store.connection() as db:
            state = expose(read_state(sid, db))
            state["line_reviews"] = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT payload FROM line_reviews WHERE session_id=? ORDER BY rowid DESC", (sid,)
                )
            ]
        state["rallies"] = rallies(sid)
        return state

    @app.post("/api/sessions/{sid}/match/actions", dependencies=[Depends(authorize)])
    def action(sid: str, value: MatchAction):
        get_session(sid)
        digest = hashlib.sha256(value.model_dump_json().encode()).hexdigest()
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # A deleted session must never be resurrected by an in-flight command.
            if not db.execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone():
                raise HTTPException(404, "Session not found")
            state = read_state(sid, db)
            prior = db.execute(
                "SELECT digest FROM match_actions WHERE session_id=? AND request_id=?",
                (sid, value.request_id),
            ).fetchone()
            if prior:
                if prior[0] != digest:
                    raise HTTPException(409, "This request identifier was already used for another action")
                return expose(state)
            if state["revision"] != value.revision:
                raise HTTPException(409, "The score changed on another device. Refresh before trying again.")
            if value.action == "configure":
                if state["events"]:
                    raise HTTPException(409, "Match settings are locked after the first point")
                if value.config is None or any(not p.strip() or len(p) > 80 for p in value.config.players):
                    raise HTTPException(400, "Provide two player names of 1–80 characters")
                state["config"] = value.config.model_dump()
            elif value.action == "undo":
                if not state["events"]:
                    raise HTTPException(409, "No points to undo")
                state["events"].pop()
            else:
                if value.winner is None:
                    raise HTTPException(400, "Choose the point winner")
                if len(state["events"]) >= 5000:
                    raise HTTPException(400, "This match has reached its point limit")
                if value.rally_id:
                    rally_order = [r["id"] for r in rallies(sid)]
                    if value.rally_id not in rally_order:
                        raise HTTPException(404, "Rally not found")
                    if any(e.get("rally_id") == value.rally_id for e in state["events"]):
                        raise HTTPException(409, "This rally already has a scored result. Undo it first.")
                    previous = [e["rally_id"] for e in state["events"] if e.get("rally_id") in rally_order]
                    if previous and rally_order.index(value.rally_id) < rally_order.index(previous[-1]):
                        raise HTTPException(409, "Score rallies in video order. Undo later points first.")
                state["events"].append(
                    {
                        "id": value.request_id,
                        "winner": value.winner,
                        "rally_id": value.rally_id,
                        "created_at": now(),
                        "source": "confirmed",
                    }
                )
            try:
                result = expose(state)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            state["revision"] += 1
            result["revision"] = state["revision"]
            db.execute(
                "INSERT INTO match_states VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET payload=excluded.payload",
                (sid, json.dumps(state)),
            )
            db.execute("INSERT INTO match_actions VALUES(?,?,?)", (sid, value.request_id, digest))
        return result

    @app.get("/api/sessions/{sid}/bounce-candidates", dependencies=[Depends(authorize)])
    def candidates(sid: str):
        session = get_session(sid)
        path = store.root / "sessions" / sid / "ball.json"
        samples = json.loads(path.read_text()) if path.is_file() else []
        return {
            "candidates": bounce_candidates(
                samples, [s["contact"] for s in (session.get("report") or {}).get("shots", [])]
            ),
            "status": "unverified_image_turns",
        }

    @app.post("/api/sessions/{sid}/line-reviews", dependencies=[Depends(authorize)])
    def line_review(sid: str, value: LineReview):
        session = get_session(sid)
        if not value.ground_contact_confirmed:
            raise HTTPException(400, "Confirm a visible ground contact before requesting a line estimate")
        if value.time >= session["metadata"]["duration"]:
            raise HTTPException(400, "Review time must be inside the video")
        corners = value.corners or session["options"].get("court_corners")
        if not corners:
            raise HTTPException(400, "Calibrate the four singles corners before line review")
        try:
            calibration = CourtCalibration(corners, 1000, 1000)
            position = calibration.position(value.x * 1000, value.y * 1000)
            result = judge_bounce(position or [], value.zone, value.uncertainty_m)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                400, "Use four valid court corners and a visible ground-contact point"
            ) from exc
        result.update(
            {
                "id": secrets.token_hex(12),
                "time": value.time,
                "x": value.x,
                "y": value.y,
                "corners": corners,
                "source": "user_confirmed_ground_contact",
                "created_at": now(),
                "is_demo": session["is_demo"],
            }
        )
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone():
                raise HTTPException(404, "Session not found")
            if (
                db.execute("SELECT COUNT(*) FROM line_reviews WHERE session_id=?", (sid,)).fetchone()[0]
                >= 1000
            ):
                raise HTTPException(400, "Line review limit reached")
            db.execute("INSERT INTO line_reviews VALUES(?,?,?)", (result["id"], sid, json.dumps(result)))
        return result

    def finish_export(sid, job, source, target, intervals):
        try:
            export_highlights(source, target, intervals)
            with store.connection() as db:
                db.execute("UPDATE highlight_exports SET status='completed' WHERE id=?", (job,))
        except Exception:
            target.unlink(missing_ok=True)
            with store.connection() as db:
                db.execute(
                    "UPDATE highlight_exports SET status='failed',error='Could not render the highlights. Check the session video and try again.' WHERE id=?",
                    (job,),
                )
        finally:
            export_slot.release()

    @app.post("/api/sessions/{sid}/highlights", dependencies=[Depends(authorize)])
    def highlights(sid: str, value: HighlightRequest, background: BackgroundTasks):
        session = get_session(sid)
        report = session.get("report")
        if session["status"] != "completed" or not report:
            raise HTTPException(409, "Wait for session analysis to complete")
        if len(set(value.rally_ids)) != len(value.rally_ids):
            raise HTTPException(400, "Select each rally once")
        selected = [r for r in rallies(sid) if r["id"] in value.rally_ids]
        if len(selected) != len(value.rally_ids):
            raise HTTPException(404, "One of these rallies is unavailable")
        source = safe_asset(sid, report["annotated_video"])
        try:
            duration = inspect_video(source).duration
        except ValueError as exc:
            raise HTTPException(400, "Session media could not be decoded") from exc
        intervals = [(r["start"], r["end"]) for r in selected]
        if any(end > duration + 0.02 for _, end in intervals):
            raise HTTPException(
                400,
                "These timestamps exceed the available video. Synthetic demo timelines cannot be exported as full sessions.",
            )
        if sum(end - start for start, end in intervals) > 300:
            raise HTTPException(400, "Select no more than five minutes of highlights")
        if not export_slot.acquire(blocking=False):
            raise HTTPException(409, "Another highlight export is running. Try again shortly.")
        job = secrets.token_hex(12)
        filename = f"highlight-{job}.mp4"
        try:
            with store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                if not db.execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone():
                    raise HTTPException(404, "Session not found")
                db.execute(
                    "INSERT INTO highlight_exports VALUES(?,?,'processing',NULL,?,?)",
                    (job, sid, filename, now()),
                )
            background.add_task(finish_export, sid, job, source, source.parent / filename, intervals)
        except Exception:
            export_slot.release()
            raise
        return {"id": job, "status": "processing"}

    @app.get("/api/sessions/{sid}/highlights/{job}", dependencies=[Depends(authorize)])
    def export_status(sid: str, job: str):
        get_session(sid)
        if not re.fullmatch(r"[a-f0-9]{24}", job):
            raise HTTPException(404, "Export not found")
        with store.connection() as db:
            row = db.execute(
                "SELECT * FROM highlight_exports WHERE id=? AND session_id=?", (job, sid)
            ).fetchone()
        if not row:
            raise HTTPException(404, "Export not found")
        return {
            "id": job,
            "status": row["status"],
            "error": row["error"],
            "url": signed_url(sid, row["filename"]) if row["status"] == "completed" else None,
        }
