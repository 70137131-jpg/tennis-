from fastapi.testclient import TestClient

from api.main import create_app


def start(client, video_file, options):
    return client.post(
        "/api/uploads",
        json={"filename": video_file.name, "size": video_file.stat().st_size, "options": options},
    )


def upload(client, video_file, options):
    value = start(client, video_file, options).json()
    data = video_file.read_bytes()
    assert client.put(f"/api/uploads/{value['id']}?offset=0", content=data).status_code == 200
    return client.post(f"/api/uploads/{value['id']}/complete")


def test_resumable_upload_validates_offsets(client, video_file, upload_options):
    uid = start(client, video_file, upload_options).json()["id"]
    data = video_file.read_bytes()
    assert client.post(f"/api/uploads/{uid}/complete").status_code == 409
    assert client.put(f"/api/uploads/{uid}?offset=0", content=data[:100]).json()["offset"] == 100
    assert client.put(f"/api/uploads/{uid}?offset=0", content=data[:100]).status_code == 409
    assert client.get(f"/api/uploads/{uid}").json()["offset"] == 100
    assert client.put(f"/api/uploads/{uid}?offset=100", content=data[100:]).status_code == 200
    response = client.post(f"/api/uploads/{uid}/complete")
    assert response.status_code == 200
    session = response.json()
    assert session["status"] == "queued" and not session["is_demo"]
    assert session["options"]["consent"]["processing"] and not session["options"]["consent"]["training"]
    assert session["metadata"]["duration"] == 3
    assert client.get(f"/api/uploads/{uid}").status_code == 404


def test_permission_and_junior_consent_are_server_enforced(client, video_file, upload_options):
    assert start(client, video_file, {**upload_options, "processing_consent": False}).status_code == 400
    assert start(client, video_file, {**upload_options, "age_group": "junior"}).status_code == 400
    assert (
        start(
            client,
            video_file,
            {
                **upload_options,
                "age_group": "junior",
                "guardian_consent": True,
                "player_assent": True,
                "guardian_name": "Test guardian",
            },
        ).status_code
        == 200
    )


def test_invalid_video_and_extensions_rejected(client, upload_options):
    assert (
        client.post(
            "/api/uploads", json={"filename": "virus.exe", "size": 12, "options": upload_options}
        ).status_code
        == 400
    )
    uid = client.post(
        "/api/uploads", json={"filename": "bad.mp4", "size": 3, "options": upload_options}
    ).json()["id"]
    client.put(f"/api/uploads/{uid}?offset=0", content=b"bad")
    assert client.post(f"/api/uploads/{uid}/complete").status_code == 400
    assert client.get("/api/sessions").json() == []


def test_media_is_signed_and_deletion_removes_every_artifact(client, video_file, upload_options):
    value = upload(client, video_file, upload_options).json()
    sid = value["id"]
    poster = value["media"]["poster.jpg"]
    assert client.get(poster).status_code == 200
    assert client.get(poster, headers={"Range": "bytes=0-99"}).status_code == 206
    assert client.get(poster.replace("signature=", "signature=bad")).status_code == 403
    assert client.get(f"/api/media/{sid}/poster.jpg?expires=1&signature=no").status_code == 403
    directory = client.app.state.store.root / "sessions" / sid
    assert directory.exists()
    assert client.delete(f"/api/sessions/{sid}").status_code == 200
    assert not directory.exists()
    assert client.get(poster).status_code == 404
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_token_and_origin_access_controls(tmp_path, monkeypatch):
    monkeypatch.setenv("COURTSIDE_TOKEN", "a-test-token-with-32-characters")
    with TestClient(create_app(tmp_path, embedded_worker=False, demo=False, auth_mode="local")) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/sessions").status_code == 401
        assert (
            client.get(
                "/api/sessions", headers={"Authorization": "Bearer a-test-token-with-32-characters"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/api/settings",
                headers={
                    "Authorization": "Bearer a-test-token-with-32-characters",
                    "Origin": "https://untrusted.example",
                },
                json={
                    "display_name": "T",
                    "player_name": "T",
                    "handedness": "right",
                    "backhand_style": "two-handed",
                    "level": "beginner",
                    "retention_days": 30,
                    "blur_faces": True,
                },
            ).status_code
            == 403
        )


def test_settings_and_reviews_validate_input(client, video_file, upload_options):
    settings = client.get("/api/settings").json()
    assert client.put("/api/settings", json={**settings, "retention_days": 0}).status_code == 422
    assert (
        client.put(
            "/api/settings", json={**settings, "display_name": "Taylor", "retention_days": 7}
        ).status_code
        == 200
    )
    sid = upload(client, video_file, upload_options).json()["id"]
    assert (
        client.post(
            f"/api/sessions/{sid}/reviews", json={"shot_id": "fake", "tip_id": "fake", "rating": "correct"}
        ).status_code
        == 404
    )
    assert client.post(f"/api/sessions/{sid}/retry").status_code == 409


def test_cancel_removes_partial_bytes(client, video_file, upload_options):
    uid = start(client, video_file, upload_options).json()["id"]
    client.put(f"/api/uploads/{uid}?offset=0", content=video_file.read_bytes()[:100])
    path = client.app.state.store.root / "uploads" / f"{uid}.part"
    assert path.exists()
    assert client.delete(f"/api/uploads/{uid}").status_code == 200
    assert not path.exists()
