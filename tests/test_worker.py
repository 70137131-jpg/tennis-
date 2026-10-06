import importlib
from datetime import datetime, timedelta, timezone

from courtside.schemas import Report, VideoInfo
from worker.run import cleanup, process_next


def test_worker_claim_completion_and_retention(client, video_file, upload_options, monkeypatch):
    value = client.post(
        "/api/uploads",
        json={"filename": "session.mp4", "size": video_file.stat().st_size, "options": upload_options},
    ).json()
    client.put(f"/api/uploads/{value['id']}?offset=0", content=video_file.read_bytes())
    sid = client.post(f"/api/uploads/{value['id']}/complete").json()["id"]
    module = importlib.import_module("worker.run")

    def fake_analyze(original, out, options, progress):
        progress(90, "Finishing")
        return Report(
            feedback_rules_version="test",
            video=VideoInfo(width=320, height=240, fps=30, frames=90, duration=3),
            shots=[],
        )

    monkeypatch.setattr(module, "analyze", fake_analyze)
    store = client.app.state.store
    assert process_next(store)
    assert store.get(sid)["status"] == "completed"
    assert not process_next(store)
    with store.connection() as db:
        db.execute(
            "UPDATE sessions SET created_at=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(days=40)).isoformat(), sid),
        )
    assert cleanup(store) == 1
    assert store.get(sid) is None
    assert not (store.root / "sessions" / sid).exists()


def queue_session(client, video_file, upload_options):
    value = client.post(
        "/api/uploads",
        json={"filename": "session.mp4", "size": video_file.stat().st_size, "options": upload_options},
    ).json()
    client.put(f"/api/uploads/{value['id']}?offset=0", content=video_file.read_bytes())
    return client.post(f"/api/uploads/{value['id']}/complete").json()["id"]


def test_worker_failure_retry_and_cancellation(client, video_file, upload_options, monkeypatch):
    module = importlib.import_module("worker.run")
    store = client.app.state.store
    sid = queue_session(client, video_file, upload_options)

    def fail(*args):
        raise RuntimeError("Model unavailable")

    monkeypatch.setattr(module, "analyze", fail)
    assert process_next(store)
    assert store.get(sid)["status"] == "failed"
    assert client.post(f"/api/sessions/{sid}/retry").status_code == 200
    assert store.get(sid)["status"] == "queued"

    def cancel(original, directory, options, progress):
        client.delete(f"/api/sessions/{sid}")
        progress(20, "Tracking")

    monkeypatch.setattr(module, "analyze", cancel)
    assert process_next(store) and store.get(sid) is None
    assert not (store.root / "sessions" / sid).exists()


def test_worker_restart_recovers_job_and_removes_abandoned_upload(
    client, video_file, upload_options, monkeypatch
):
    import threading

    module = importlib.import_module("worker.run")
    store = client.app.state.store
    sid = queue_session(client, video_file, upload_options)
    store.claim()
    upload = client.post(
        "/api/uploads",
        json={"filename": "session.mp4", "size": video_file.stat().st_size, "options": upload_options},
    ).json()
    client.put(f"/api/uploads/{upload['id']}?offset=0", content=b"partial")
    with store.connection() as db:
        db.execute(
            "UPDATE uploads SET created_at=?", ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),)
        )
    stop = threading.Event()

    def once(current):
        assert current.get(sid)["status"] == "queued"
        stop.set()
        return False

    monkeypatch.setattr(module, "process_next", once)
    module.run(store, stop)
    assert not (store.root / "uploads" / f"{upload['id']}.part").exists()
