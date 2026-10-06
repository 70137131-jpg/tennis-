import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import cv2
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from api.store import Store, now
from courtside.demo import seed_demo
from courtside.pipeline import ROOT
from courtside.video import inspect_video
from worker.run import run


class UploadOptions(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    player_name: str = Field(min_length=1, max_length=80)
    handedness: Literal["left", "right"] = "right"
    backhand_style: Literal["one-handed", "two-handed"] = "two-handed"
    level: Literal["beginner", "intermediate", "competitive"] = "competitive"
    age_group: Literal["junior", "adult"] = "adult"
    session_type: Literal["Practice", "Match", "Drills"] = "Practice"
    court: str = Field(default="Court 01", max_length=100)
    blur_faces: bool = True
    court_corners: list[list[float]] | None = None
    guardian_consent: bool = False
    guardian_name: str = Field(default="", max_length=100)
    player_assent: bool = False
    processing_consent: bool = False
    training_consent: bool = False


class UploadStart(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    size: int = Field(gt=0)
    options: UploadOptions


class Settings(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)
    player_name: str = Field(min_length=1, max_length=80)
    handedness: Literal["left", "right"]
    backhand_style: Literal["one-handed", "two-handed"]
    level: Literal["beginner", "intermediate", "competitive"]
    retention_days: int = Field(ge=1, le=365)
    blur_faces: bool


class Review(BaseModel):
    shot_id: str = Field(max_length=80)
    tip_id: str = Field(max_length=100)
    rating: Literal["correct", "incorrect", "unhelpful"]
    correction: str = Field(default="", max_length=1000)


def create_app(
    storage=None, embedded_worker=True, demo=True, trusted_gateway=False, media_prefix="", live_capacity=None
):
    if not trusted_gateway and os.environ.get("COURTSIDE_ACCOUNTS", "0") == "1":
        from api.gateway import create_accounts_app

        return create_accounts_app(storage, embedded_worker)
    store = Store(storage)
    token = "" if trusted_gateway else os.environ.get("COURTSIDE_TOKEN", "")
    key_path = store.root / ".signing_key"
    if not key_path.exists():
        key_path.write_text(secrets.token_hex(32))
    signing_key = key_path.read_text().encode()
    stop = threading.Event()
    worker = None

    @asynccontextmanager
    async def lifespan(app):
        nonlocal worker
        from courtside.operations import StorageLock

        with StorageLock(store.root):
            if demo:
                seed_demo(store)
            if embedded_worker:
                stop.clear()
                worker = threading.Thread(target=run, args=(store, stop), daemon=True)
                worker.start()
            try:
                yield
            finally:
                stop.set()
                if worker:
                    worker.join(timeout=10)

    app = FastAPI(title="Courtside", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    from api.security import SecurityMiddleware, Telemetry

    telemetry = Telemetry()
    app.state.telemetry = telemetry
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    extra = os.environ.get("COURTSIDE_ORIGIN")
    if extra:
        allowed_origins.append(extra)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(SecurityMiddleware, telemetry=telemetry, origins=allowed_origins)

    from api.live import register_live

    register_live(app, token, allowed_origins, trusted_gateway, live_capacity)

    def authorize(request: Request):
        if trusted_gateway:
            return
        if token:
            supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
            if not hmac.compare_digest(supplied, token):
                raise HTTPException(401, "Enter your workspace access token in Settings")
        elif request.client and request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(403, "Configure COURTSIDE_TOKEN to enable phone or remote access")
        origin = request.headers.get("origin")
        if origin and origin not in allowed_origins and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "This origin is not allowed")

    def get_session(sid):
        session = store.get(sid)
        if not session:
            raise HTTPException(404, "Session not found")
        return session

    def signed_url(sid, asset):
        expires = int(time.time()) + 3600
        signature = hmac.new(signing_key, f"{sid}/{asset}:{expires}".encode(), hashlib.sha256).hexdigest()
        return f"{media_prefix}/api/media/{sid}/{asset}?expires={expires}&signature={signature}"

    @app.get("/api/auth/config")
    def auth_config():
        return {"enabled": False, "setup_available": False}

    @app.get("/api/operations/metrics", dependencies=[Depends(authorize)])
    def operations_metrics():
        return telemetry.snapshot()

    @app.get("/api/production", dependencies=[Depends(authorize)])
    def production():
        from courtside.release import release_status

        return release_status(ROOT)

    def with_media(session):
        report = session.get("report")
        directory = store.root / "sessions" / session["id"]
        assets = {"poster.jpg"} if (directory / "poster.jpg").exists() else set()
        if report:
            assets.add(report["annotated_video"])
            assets.update(s["clip"] for s in report["shots"] if s.get("clip"))
        session["media"] = {asset: signed_url(session["id"], asset) for asset in assets}
        return session

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "version": "0.1.0",
            "access_token_required": bool(token),
            "model_ready": Path(
                os.environ.get("COURTSIDE_MODEL", ROOT / "models/pose_landmarker_full.task")
            ).is_file(),
        }

    @app.get("/api/ready")
    def ready():
        from courtside.readiness import installation_status

        status = installation_status()
        return JSONResponse(status_code=200 if status["local_ready"] else 503, content=status)

    @app.get("/api/settings", dependencies=[Depends(authorize)])
    def read_settings():
        return store.settings()

    @app.put("/api/settings", dependencies=[Depends(authorize)])
    def save_settings(value: Settings):
        with store.connection() as db:
            db.execute("UPDATE settings SET value=? WHERE id=1", (value.model_dump_json(),))
        return value

    @app.get("/api/sessions", dependencies=[Depends(authorize)])
    def sessions():
        return [with_media(s) for s in store.list_sessions()]

    @app.get("/api/sessions/{sid}", dependencies=[Depends(authorize)])
    def session(sid: str):
        return with_media(get_session(sid))

    @app.delete("/api/sessions/{sid}", dependencies=[Depends(authorize)])
    def delete(sid: str):
        get_session(sid)
        with store.connection() as db:
            db.execute("DELETE FROM reviews WHERE session_id=?", (sid,))
            db.execute("DELETE FROM sessions WHERE id=?", (sid,))
        shutil.rmtree(store.root / "sessions" / sid, ignore_errors=True)
        return {"deleted": sid}

    @app.post("/api/sessions/{sid}/retry", dependencies=[Depends(authorize)])
    def retry(sid: str):
        value = get_session(sid)
        if value["status"] != "failed":
            raise HTTPException(409, "Only failed sessions can be retried")
        with store.connection() as db:
            db.execute(
                "UPDATE sessions SET status='queued',error=NULL,progress=0,stage='Queued' WHERE id=?", (sid,)
            )
        return {"queued": sid}

    @app.post("/api/uploads", dependencies=[Depends(authorize)])
    def start_upload(value: UploadStart):
        suffix = Path(value.filename).suffix.lower()
        if suffix not in {".mp4", ".mov"}:
            raise HTTPException(400, "Choose an MP4 or MOV video")
        if value.size > int(os.environ.get("COURTSIDE_MAX_UPLOAD_MB", "1024")) * 1024**2:
            raise HTTPException(413, "This video exceeds the configured 1 GB upload limit")
        options = value.options
        if not options.processing_consent:
            raise HTTPException(400, "Permission to process everyone in the video is required")
        if options.age_group == "junior" and not (
            options.guardian_consent and options.player_assent and options.guardian_name.strip()
        ):
            raise HTTPException(400, "A junior requires guardian consent, guardian name and player assent")
        if options.court_corners is not None:
            from courtside.court import CourtCalibration

            try:
                CourtCalibration(options.court_corners, 1000, 1000)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        uid = secrets.token_hex(12)
        data = options.model_dump()
        data["consent"] = {
            "processing": True,
            "guardian": options.guardian_consent,
            "guardian_name": options.guardian_name,
            "assent": options.player_assent,
            "training": options.training_consent,
            "recorded_at": now(),
            "method": "uploader attestation",
        }
        with store.connection() as db:
            db.execute(
                "INSERT INTO uploads VALUES(?,?,?,0,?,?)",
                (uid, value.filename, value.size, json.dumps(data), now()),
            )
        return {"id": uid, "offset": 0, "chunk_size": 4 * 1024 * 1024}

    @app.get("/api/uploads/{uid}", dependencies=[Depends(authorize)])
    def upload_status(uid: str):
        with store.connection() as db:
            row = db.execute("SELECT id,size,offset FROM uploads WHERE id=?", (uid,)).fetchone()
        if not row:
            raise HTTPException(404, "Upload not found")
        return dict(row)

    @app.put("/api/uploads/{uid}", dependencies=[Depends(authorize)])
    async def chunk(uid: str, offset: int, request: Request):
        if not re.fullmatch(r"[a-f0-9]{24}", uid):
            raise HTTPException(404, "Upload not found")
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > 4 * 1024 * 1024:
                raise HTTPException(413, "Chunks must be no larger than 4 MB")
        if not body:
            raise HTTPException(400, "Empty chunk")
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM uploads WHERE id=?", (uid,)).fetchone()
            if not row:
                raise HTTPException(404, "Upload not found")
            if offset != row["offset"]:
                raise HTTPException(409, f"Resume from byte {row['offset']}")
            if offset + len(body) > row["size"]:
                raise HTTPException(400, "Chunk exceeds declared file size")
            path = store.root / "uploads" / f"{uid}.part"
            with path.open("r+b" if path.exists() else "w+b") as file:
                file.seek(offset)
                file.write(body)
                file.truncate(offset + len(body))
            db.execute("UPDATE uploads SET offset=? WHERE id=?", (offset + len(body), uid))
        return {"offset": offset + len(body)}

    @app.delete("/api/uploads/{uid}", dependencies=[Depends(authorize)])
    def cancel_upload(uid: str):
        if not re.fullmatch(r"[a-f0-9]{24}", uid):
            raise HTTPException(404, "Upload not found")
        with store.connection() as db:
            db.execute("DELETE FROM uploads WHERE id=?", (uid,))
        (store.root / "uploads" / f"{uid}.part").unlink(missing_ok=True)
        return {"cancelled": uid}

    @app.post("/api/uploads/{uid}/complete", dependencies=[Depends(authorize)])
    def complete(uid: str):
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM uploads WHERE id=?", (uid,)).fetchone()
            if not row:
                raise HTTPException(404, "Upload not found")
            if row["offset"] != row["size"]:
                raise HTTPException(409, "Finish uploading all chunks first")
            source = store.root / "uploads" / f"{uid}.part"
            try:
                metadata = inspect_video(source)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            sid = secrets.token_hex(12)
            directory = store.root / "sessions" / sid
            directory.mkdir()
            source.replace(directory / f"original{Path(row['filename']).suffix.lower()}")
            cap = cv2.VideoCapture(str(next(directory.glob("original.*"))))
            ok, image = cap.read()
            cap.release()
            if ok:
                cv2.imwrite(str(directory / "poster.jpg"), image)
            options = json.loads(row["options"])
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,'queued',0,'Waiting for worker',NULL,?,?,NULL,0,?)",
                (sid, options["title"], now(), row["options"], metadata.model_dump_json(), now()),
            )
            db.execute("DELETE FROM uploads WHERE id=?", (uid,))
        return with_media(get_session(sid))

    @app.get("/api/reviews", dependencies=[Depends(authorize)])
    def reviews():
        with store.connection() as db:
            return [
                dict(row) for row in db.execute("SELECT * FROM reviews ORDER BY created_at DESC").fetchall()
            ]

    @app.post("/api/sessions/{sid}/reviews", dependencies=[Depends(authorize)])
    def review(sid: str, value: Review):
        report = get_session(sid).get("report")
        shot = next((s for s in report["shots"] if s["id"] == value.shot_id), None) if report else None
        if not shot or not any(t["id"] == value.tip_id for t in shot["tips"]):
            raise HTTPException(404, "Shot or tip not found")
        with store.connection() as db:
            db.execute(
                "INSERT INTO reviews(session_id,shot_id,tip_id,rating,correction,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(session_id,shot_id,tip_id) DO UPDATE SET rating=excluded.rating,correction=excluded.correction,created_at=excluded.created_at",
                (sid, value.shot_id, value.tip_id, value.rating, value.correction, now()),
            )
        return {"saved": True}

    @app.get("/api/media/{sid}/{asset}")
    def media(sid: str, asset: str, expires: int, signature: str):
        expected = hmac.new(signing_key, f"{sid}/{asset}:{expires}".encode(), hashlib.sha256).hexdigest()
        if expires < int(time.time()) or not hmac.compare_digest(signature, expected):
            raise HTTPException(403, "This private media link has expired. Refresh the report.")
        get_session(sid)
        if not re.fullmatch(r"(?:[a-f0-9]{24}|demo-[1-6])", sid) or not re.fullmatch(
            r"(?:poster\.jpg|annotated\.mp4|demo\.mp4|shot-\d{4}\.mp4)", asset
        ):
            raise HTTPException(404, "Asset not found")
        path = store.root / "sessions" / sid / asset
        if not path.is_file():
            raise HTTPException(404, "Asset not found")
        return FileResponse(path, headers={"Cache-Control": "private, max-age=300"})

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        import logging

        logging.getLogger("courtside.api").exception("Unhandled request error")
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong. Check the local server log and try again."},
        )

    dist = ROOT / "web/dist"
    if dist.exists():

        @app.get("/{path:path}")
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Endpoint not found")
            target = (dist / path).resolve()
            if target.is_relative_to(dist.resolve()) and target.is_file():
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


app = create_app(
    embedded_worker=os.environ.get("COURTSIDE_EMBEDDED_WORKER", "1") == "1",
    demo=os.environ.get("COURTSIDE_DEMO", "1") == "1",
)
