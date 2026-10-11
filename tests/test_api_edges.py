import hashlib
import hmac
import time

from fastapi.testclient import TestClient

from api.main import create_app
from tests_helpers import upload_session


def test_chunk_bounds_and_missing_uploads(client, video_file, upload_options):
    uid = client.post(
        "/api/uploads", json={"filename": "test.mp4", "size": 3, "options": upload_options}
    ).json()["id"]
    assert client.put(f"/api/uploads/{uid}?offset=0", content=b"").status_code == 400
    assert client.put(f"/api/uploads/{uid}?offset=0", content=b"too big").status_code == 400
    assert client.put(f"/api/uploads/{uid}?offset=0", content=b"a" * (4 * 1024 * 1024 + 1)).status_code == 413
    assert client.put("/api/uploads/not-an-id?offset=0", content=b"a").status_code == 404
    assert client.put(f"/api/uploads/{'a' * 24}?offset=0", content=b"a").status_code == 404
    assert client.get(f"/api/uploads/{'a' * 24}").status_code == 404
    assert client.delete("/api/uploads/bad").status_code == 404
    assert client.post(f"/api/uploads/{'a' * 24}/complete").status_code == 404


def test_size_and_court_validation(client, upload_options, monkeypatch):
    monkeypatch.setenv("COURTSIDE_MAX_UPLOAD_MB", "1")
    assert (
        client.post(
            "/api/uploads", json={"filename": "big.mp4", "size": 1024 * 1024 + 1, "options": upload_options}
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/uploads",
            json={
                "filename": "test.mp4",
                "size": 3,
                "options": {**upload_options, "court_corners": [[0, 0]] * 4},
            },
        ).status_code
        == 400
    )


def test_real_review_upsert_and_media_allowlist(client, video_file, upload_options):
    session = upload_session(client, video_file, upload_options)
    sid = session["id"]
    report = {
        "annotated_video": "annotated.mp4",
        "shots": [{"id": "shot-0001", "clip": "shot-0001.mp4", "tips": [{"id": "knee-angle"}]}],
    }
    import json

    store = client.app.state.store
    with store.connection() as db:
        db.execute("UPDATE sessions SET report=? WHERE id=?", (json.dumps(report), sid))
    assert "shot-0001.mp4" in client.get(f"/api/sessions/{sid}").json()["media"]
    body = {"shot_id": "shot-0001", "tip_id": "knee-angle", "rating": "correct"}
    assert client.post(f"/api/sessions/{sid}/reviews", json=body).status_code == 200
    assert (
        client.post(
            f"/api/sessions/{sid}/reviews", json={**body, "rating": "incorrect", "correction": "Review angle"}
        ).status_code
        == 200
    )
    reviews = client.get("/api/reviews").json()
    assert len(reviews) == 1 and reviews[0]["rating"] == "incorrect"
    expires = int(time.time()) + 10
    key = (store.root / ".signing_key").read_text().encode()
    for asset in ["original.mp4", "shot-9999.mp4"]:
        signature = hmac.new(key, f"{sid}/{asset}:{expires}".encode(), hashlib.sha256).hexdigest()
        assert (
            client.get(f"/api/media/{sid}/{asset}?expires={expires}&signature={signature}").status_code == 404
        )


def test_nonlocal_clients_need_token(tmp_path, monkeypatch):
    monkeypatch.delenv("COURTSIDE_TOKEN", raising=False)
    with TestClient(create_app(tmp_path, False, False, auth_mode="local"), client=("192.0.2.5", 1234)) as client:
        assert client.get("/api/sessions").status_code == 403


def test_spa_and_readiness(client):
    assert client.get("/api/ready").json()["local_ready"]
    assert client.get("/").status_code == 200
    assert client.get("/session/example").status_code == 200
    assert client.get("/api/unknown").status_code == 404
    assert client.get("/favicon.svg").headers["content-type"].startswith("image/svg+xml")
