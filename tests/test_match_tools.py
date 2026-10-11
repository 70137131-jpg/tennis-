import json

import pytest

from courtside.match import bounce_candidates, detect_rallies, judge_bounce, score_match


def events(winners):
    return [{"winner": winner} for winner in winners]


def test_deuce_advantage_and_game():
    cfg = {"best_of": 3, "first_server": 0}
    sequence = [0, 0, 0, 1, 1, 1]
    assert score_match(events(sequence), cfg)["points"] == ["40", "40"]
    assert score_match(events(sequence + [0]), cfg)["points"] == ["AD", "40"]
    assert score_match(events(sequence + [0, 1]), cfg)["points"] == ["40", "40"]
    state = score_match(events(sequence + [0, 0]), cfg)
    assert state["points"] == ["0", "0"] and state["games"] == [1, 0] and state["server"] == 1
    assert score_match(events(sequence + [1]), {**cfg, "no_ad": True})["games"] == [0, 1]


def test_sets_match_completion_and_undo():
    sequence = [0] * 48
    state = score_match(events(sequence), {"best_of": 3})
    assert state["winner"] == 0 and state["sets"] == [2, 0]
    assert state["set_history"] == [[6, 0], [6, 0]]
    with pytest.raises(ValueError, match="complete"):
        score_match(events(sequence + [1]), {"best_of": 3})
    assert score_match(events(sequence[:-1]), {"best_of": 3})["winner"] is None
    with pytest.raises(ValueError, match="winner"):
        score_match(events([9]), {})


def test_tiebreak_service_rotation_win_by_two_and_next_set_server():
    sequence = sum(([0] * 4 + [1] * 4 for _ in range(6)), [])
    cfg = {"best_of": 3, "first_server": 0}
    assert score_match(events(sequence), cfg)["tiebreak"]
    assert [score_match(events(sequence + [0] * count), cfg)["server"] for count in range(7)] == [
        0,
        1,
        1,
        0,
        0,
        1,
        1,
    ]
    sequence += [0, 1] * 6
    assert score_match(events(sequence + [0]), cfg)["winner"] is None
    result = score_match(events(sequence + [0, 0]), cfg)
    assert result["set_history"] == [[7, 6]] and result["server"] == 1 and not result["tiebreak"]


def test_rally_segmentation_is_ordered_bounded_and_does_not_infer_winners():
    shots = [{"contact": time, "type": "forehand", "confidence": 0.9} for time in [15, 1, 2, 30]]
    rallies = detect_rallies(shots, 20)
    assert len(rallies) == 2 and rallies[0]["shots"] == 2
    assert rallies[0]["start"] == 0 and rallies[-1]["end"] <= 20
    assert all(r["winner"] is None for r in rallies)
    assert detect_rallies([], 20) == []


def test_bounce_candidates_reject_gaps_interpolation_contacts_and_weak_detections():
    samples = [
        {"x": 50, "y": y, "time": i * 0.05, "confidence": 0.9, "interpolated": False}
        for i, y in enumerate([1, 4, 1])
    ]
    assert len(bounce_candidates(samples, [])) == 1
    assert bounce_candidates(samples, [0.05]) == []
    assert bounce_candidates([samples[0], None, samples[2]], []) == []
    for changed in [{"interpolated": True}, {"confidence": 0.3}, {"time": 2}]:
        assert bounce_candidates([samples[0], {**samples[1], **changed}, samples[2]], []) == []
    assert bounce_candidates([{**s, "y": i} for i, s in enumerate(samples)], []) == []


@pytest.mark.parametrize(
    "point,zone,call",
    [
        ([4, 12], "singles", "in"),
        ([9, 12], "singles", "out"),
        ([0, 12], "singles", "uncertain"),
        ([-0.02, 12], "singles", "uncertain"),
        ([9, 12], "doubles", "in"),
        ([2, 8], "far-left-service", "in"),
        ([6, 8], "far-left-service", "out"),
    ],
)
def test_line_geometry_preserves_uncertainty_and_ball_overlap(point, zone, call):
    assert judge_bounce(point, zone)["call"] == call


def test_invalid_line_geometry():
    for point, zone in [([float("nan"), 0], "singles"), ([0], "singles"), ([0, 0], "invalid")]:
        with pytest.raises(ValueError):
            judge_bounce(point, zone)


@pytest.fixture
def completed(client, video_file, upload_options):
    import shutil

    value = client.post(
        "/api/uploads",
        json={"filename": video_file.name, "size": video_file.stat().st_size, "options": upload_options},
    ).json()
    client.put(f"/api/uploads/{value['id']}?offset=0", content=video_file.read_bytes())
    session = client.post(f"/api/uploads/{value['id']}/complete").json()
    sid = session["id"]
    store = client.app.state.store
    directory = store.root / "sessions" / sid
    shutil.copyfile(video_file, directory / "annotated.mp4")
    report = {
        "annotated_video": "annotated.mp4",
        "shots": [
            {"id": "shot-1", "contact": 0.5, "type": "forehand", "confidence": 0.9},
            {"id": "shot-2", "contact": 1, "type": "backhand", "confidence": 0.8},
        ],
    }
    with store.connection() as db:
        db.execute("UPDATE sessions SET status='completed',report=? WHERE id=?", (json.dumps(report), sid))
    return sid, directory, store


def command(client, sid, revision=0, action="point", **fields):
    import uuid

    return client.post(
        f"/api/sessions/{sid}/match/actions",
        json={"request_id": str(uuid.uuid4()), "revision": revision, "action": action, **fields},
    )


def test_match_actions_persist_idempotently_and_reject_conflicts(client, completed):
    sid, _, _ = completed
    url = f"/api/sessions/{sid}/match"
    initial = client.get(url).json()
    assert initial["score"]["points"] == ["0", "0"]
    assert initial["config"]["players"][0] == "Test Player"
    assert len(initial["rallies"]) == 1
    assert command(client, sid, action="undo").status_code == 409
    assert command(client, sid).status_code == 400
    assert command(client, sid, winner=0, rally_id="missing").status_code == 404
    assert command(client, sid, action="configure").status_code == 400
    assert command(client, sid, action="configure", config={"players": [" ", "B"]}).status_code == 400
    assert (
        command(client, sid, action="configure", config={"players": ["A", "B"], "best_of": 1}).status_code
        == 200
    )
    payload = {
        "request_id": "watch-command-001",
        "revision": 1,
        "action": "point",
        "winner": 0,
        "rally_id": "rally-0001",
    }
    first = client.post(url + "/actions", json=payload).json()
    assert first["revision"] == 2 and first["score"]["points"] == ["15", "0"]
    assert client.post(url + "/actions", json=payload).json() == first
    assert client.post(url + "/actions", json={**payload, "winner": 1}).status_code == 409
    assert command(client, sid, 1, winner=1).status_code == 409
    assert command(client, sid, 2, action="configure", config={"players": ["A", "B"]}).status_code == 409
    assert command(client, sid, 2, winner=0, rally_id="rally-0001").status_code == 409
    assert command(client, sid, 2, action="undo").json()["score"]["points"] == ["0", "0"]
    assert client.get(url).json()["revision"] == 3


def test_rally_scoring_rejects_reversing_the_timeline(client, completed):
    sid, _, store = completed
    session = store.get(sid)
    session["report"]["shots"].append({"id": "later", "contact": 10, "type": "serve", "confidence": 0.9})
    with store.connection() as db:
        db.execute(
            "UPDATE sessions SET metadata=?,report=? WHERE id=?",
            (json.dumps({**session["metadata"], "duration": 20}), json.dumps(session["report"]), sid),
        )
    assert command(client, sid, winner=1, rally_id="rally-0002").status_code == 200
    assert command(client, sid, 1, winner=0, rally_id="rally-0001").status_code == 409
    assert command(client, sid, 1, action="undo").status_code == 200
    assert command(client, sid, 2, winner=0, rally_id="rally-0001").status_code == 200


def test_line_review_requires_real_contact_and_valid_calibration(client, completed):
    sid, _, _ = completed
    url = f"/api/sessions/{sid}/line-reviews"
    value = {"time": 0.5, "x": 0.5, "y": 0.5}
    assert client.post(url, json=value).status_code == 400
    value["ground_contact_confirmed"] = True
    assert client.post(url, json=value).status_code == 400
    value["corners"] = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
    result = client.post(url, json=value)
    assert result.status_code == 200, result.text
    assert result.json()["call"] == "in"
    assert result.json()["source"] == "user_confirmed_ground_contact"
    assert client.post(url, json={**value, "x": 0.1}).json()["call"] == "uncertain"
    assert client.post(url, json={**value, "x": 0}).json()["call"] == "out"
    assert client.post(url, json={**value, "time": 3}).status_code == 400
    assert client.post(url, json={**value, "x": 2}).status_code == 422
    assert client.post(url, json={**value, "corners": [[0, 0]] * 4}).status_code == 400
    assert len(client.get(f"/api/sessions/{sid}/match").json()["line_reviews"]) == 3


def test_candidates_only_offer_unverified_review_prompts(client, completed):
    sid, directory, _ = completed
    url = f"/api/sessions/{sid}/bounce-candidates"
    assert client.get(url).json()["candidates"] == []
    samples = [{"time": 2 + i * 0.05, "x": 30, "y": y, "confidence": 0.9} for i, y in enumerate([1, 4, 1])]
    (directory / "ball.json").write_text(json.dumps(samples))
    result = client.get(url).json()
    assert result["status"] == "unverified_image_turns"
    assert result["candidates"][0]["status"] == "needs_review"


def test_highlight_export_is_playable_signed_and_removed_with_session(client, completed):
    from courtside.video import inspect_video

    sid, directory, store = completed
    url = f"/api/sessions/{sid}/highlights"
    assert client.post(url, json={"rally_ids": ["rally-0001", "rally-0001"]}).status_code == 400
    assert client.post(url, json={"rally_ids": ["missing"]}).status_code == 404
    job = client.post(url, json={"rally_ids": ["rally-0001"]}).json()
    status = client.get(f"{url}/{job['id']}").json()
    assert status["status"] == "completed", status
    media = client.get(status["url"])
    assert media.status_code == 200 and len(media.content) > 100
    assert client.get(status["url"], headers={"Range": "bytes=0-99"}).status_code == 206
    assert client.get(status["url"].replace("signature=", "signature=bad")).status_code == 403
    assert 1 < inspect_video(directory / f"highlight-{job['id']}.mp4").duration <= 3
    assert client.get(url + "/invalid").status_code == 404
    assert client.get(url + "/" + "a" * 24).status_code == 404
    command(client, sid, winner=0)
    assert client.delete(f"/api/sessions/{sid}").status_code == 200
    for table in ["match_states", "match_actions", "line_reviews", "highlight_exports"]:
        with store.connection() as db:
            assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE session_id=?", (sid,)).fetchone()[0] == 0
    assert not directory.exists()
    assert client.get(status["url"]).status_code == 404


def test_highlight_failures_leave_no_partial_video_and_allow_retry(client, completed, monkeypatch):
    sid, directory, _ = completed

    def fail(source, target, intervals):
        target.write_bytes(b"partial")
        raise RuntimeError("private encoder details")

    monkeypatch.setattr("api.match.export_highlights", fail)
    url = f"/api/sessions/{sid}/highlights"
    for _ in range(2):
        job = client.post(url, json={"rally_ids": ["rally-0001"]}).json()
        status = client.get(f"{url}/{job['id']}").json()
        assert status["status"] == "failed" and status["url"] is None
        assert "private" not in status["error"]
    assert not list(directory.glob("highlight-*"))


def test_export_rejects_missing_media_unfinished_sessions_and_demo_timestamps(client, completed, monkeypatch):
    sid, directory, store = completed
    url = f"/api/sessions/{sid}/highlights"
    request = {"rally_ids": ["rally-0001"]}
    session = store.get(sid)
    with store.connection() as db:
        db.execute("UPDATE sessions SET status='queued' WHERE id=?", (sid,))
    assert client.post(url, json=request).status_code == 409
    with store.connection() as db:
        db.execute("UPDATE sessions SET status='completed' WHERE id=?", (sid,))
    (directory / "annotated.mp4").rename(directory / "saved.mp4")
    assert client.post(url, json=request).status_code == 404
    (directory / "saved.mp4").rename(directory / "annotated.mp4")
    session["report"]["shots"][0]["contact"] = 19
    session["report"]["shots"][1]["contact"] = 20
    with store.connection() as db:
        db.execute(
            "UPDATE sessions SET metadata=?,report=? WHERE id=?",
            (json.dumps({**session["metadata"], "duration": 30}), json.dumps(session["report"]), sid),
        )
    assert client.post(url, json=request).status_code == 400

    def invalid(path):
        raise ValueError("invalid video")

    monkeypatch.setattr("api.match.inspect_video", invalid)
    assert client.post(url, json=request).status_code == 400


def test_highlight_renderer_enforces_limits_and_concatenates(video_file, tmp_path):
    from courtside.highlights import export_highlights
    from courtside.video import inspect_video

    for intervals in [[], [(0, 1)] * 51, [(0, 301)]]:
        with pytest.raises(ValueError):
            export_highlights(video_file, tmp_path / "invalid.mp4", intervals)
    target = tmp_path / "reel.mp4"
    export_highlights(video_file, target, [(0, 0.75), (2, 2.75)])
    assert inspect_video(target).duration == pytest.approx(1.5, abs=0.1)


def test_match_routes_require_workspace_authorization(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import create_app

    monkeypatch.setenv("COURTSIDE_TOKEN", "secret-token")
    with TestClient(create_app(tmp_path, embedded_worker=False, demo=False)) as secured:
        prefix = "/api/sessions/" + "a" * 24
        for path in ["/match", "/bounce-candidates", "/highlights/" + "b" * 24]:
            assert secured.get(prefix + path).status_code == 401
        for path, payload in [
            ("/match/actions", {"request_id": "command-001", "revision": 0, "action": "point", "winner": 0}),
            ("/line-reviews", {"time": 0, "x": 0.5, "y": 0.5}),
            ("/highlights", {"rally_ids": ["rally-0001"]}),
        ]:
            assert secured.post(prefix + path, json=payload).status_code == 401


def test_retention_removes_saved_match_data_and_export_jobs(client, completed):
    from worker.run import cleanup

    sid, directory, store = completed
    command(client, sid, winner=0)
    with store.connection() as db:
        db.execute("UPDATE sessions SET created_at='2000-01-01T00:00:00+00:00' WHERE id=?", (sid,))
        db.execute("INSERT INTO line_reviews VALUES(?,?,?)", ("review", sid, "{}"))
        db.execute(
            "INSERT INTO highlight_exports VALUES(?,?,'completed',NULL,?,?)",
            ("export", sid, "highlight.mp4", "2000"),
        )
    assert cleanup(store) == 1
    assert not directory.exists()
    for table in ["match_states", "match_actions", "line_reviews", "highlight_exports"]:
        with store.connection() as db:
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
