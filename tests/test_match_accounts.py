"""Exercise match tools through the signed-in academy gateway, including isolation."""

import json
import shutil

from fastapi.testclient import TestClient

from api.gateway import create_accounts_app

PASSWORD = "A tennis test passphrase 42"


def test_academy_match_tools_preserve_auth_csrf_and_workspace_isolation(
    tmp_path_factory, video_file, upload_options, monkeypatch
):
    monkeypatch.delenv("COURTSIDE_TOKEN", raising=False)
    app = create_accounts_app(tmp_path_factory.mktemp("academy"), embedded_worker=False)
    with TestClient(app) as client:
        assert client.get("/api/auth/config").json()["setup_available"]
        assert client.get("/api/ready").status_code == 503
        assert client.get("/api/auth/me").status_code == 401
        setup = {
            "academy": "Test academy",
            "name": "Coach",
            "email": "coach@example.test",
            "password": PASSWORD,
        }
        assert client.post("/api/auth/setup", json=setup).status_code == 200
        assert client.post("/api/auth/setup", json=setup).status_code == 409
        assert (
            client.post(
                "/api/auth/login", json={"email": setup["email"], "password": PASSWORD + "wrong"}
            ).status_code
            == 401
        )
        login = client.post("/api/auth/login", json={"email": setup["email"], "password": PASSWORD}).json()
        admin = login["user"]
        headers = {"X-CSRF-Token": login["csrf"]}
        assert not client.get("/api/auth/config").json()["setup_available"]
        assert client.get("/api/auth/me").json()["user"]["id"] == admin["id"]
        assert client.get("/api/health").json()["accounts_enabled"]
        assert client.get("/api/operations/metrics").status_code == 200
        member_data = {
            "name": "Player",
            "email": "player@example.test",
            "password": PASSWORD,
            "role": "player",
        }
        assert client.post("/api/admin/users", json=member_data).status_code == 403
        member = client.post("/api/admin/users", json=member_data, headers=headers).json()
        assert client.post("/api/admin/users", json=member_data, headers=headers).status_code == 400
        assert client.delete("/api/admin/users/" + admin["id"], headers=headers).status_code == 400
        root = f"/api/workspaces/{member['id']}/api"
        assert client.get(root + "/sessions").json() == []
        assert client.get("/api/workspaces/unknown/api/sessions").status_code == 404
        assert client.get(f"/api/workspaces/{member['id']}/not-api").status_code == 404
        assert (
            client.get(root + "/sessions", headers={"Origin": "https://untrusted.example"}).status_code == 403
        )
        request = {"filename": video_file.name, "size": video_file.stat().st_size, "options": upload_options}
        assert client.post(root + "/uploads", json=request).status_code == 403
        upload = client.post(root + "/uploads", json=request, headers=headers).json()
        assert (
            client.put(
                f"{root}/uploads/{upload['id']}?offset=0", content=video_file.read_bytes(), headers=headers
            ).status_code
            == 200
        )
        session = client.post(f"{root}/uploads/{upload['id']}/complete", headers=headers).json()
        sid = session["id"]
        store = app.state.workspaces.apps[member["id"]].state.store
        directory = store.root / "sessions" / sid
        shutil.copyfile(video_file, directory / "annotated.mp4")
        report = {
            "annotated_video": "annotated.mp4",
            "shots": [{"id": "s1", "contact": 0.5, "type": "serve", "confidence": 0.9}],
        }
        with store.connection() as db:
            db.execute(
                "UPDATE sessions SET status='completed',report=? WHERE id=?", (json.dumps(report), sid)
            )
        prefix = f"{root}/sessions/{sid}"
        payload = {"request_id": "watch-command-001", "revision": 0, "action": "point", "winner": 0}
        assert client.post(prefix + "/match/actions", json=payload).status_code == 403
        assert client.post(prefix + "/match/actions", json=payload, headers=headers).json()["score"][
            "points"
        ] == ["15", "0"]
        export = client.post(
            prefix + "/highlights", json={"rally_ids": ["rally-0001"]}, headers=headers
        ).json()
        media = client.get(prefix + "/highlights/" + export["id"]).json()["url"]
        assert media.startswith(root + "/media/")
        assert client.get(media).status_code == 200
        # Even an authorized academy administrator has a distinct personal workspace.
        own = f"/api/workspaces/{admin['id']}/api/sessions/{sid}/match"
        assert client.get(own).status_code == 404
        assert client.post("/api/auth/logout", headers=headers).status_code == 200
        assert client.get(prefix + "/match").status_code == 401
        assert client.get(media).status_code == 401
        login = client.post(
            "/api/auth/login", json={"email": member_data["email"], "password": PASSWORD}
        ).json()
        player_headers = {"X-CSRF-Token": login["csrf"]}
        assert len(login["workspaces"]) == 1
        assert client.get(own).status_code == 404
        assert client.get(root + "/operations/metrics").status_code == 403
        assert client.post(prefix + "/reviews", json={}, headers=player_headers).status_code == 403
        assert client.get("/api/admin/audit").status_code == 403
        assert client.post("/api/admin/users", json=member_data, headers=player_headers).status_code == 403
        assert client.get(prefix + "/match").json()["score"]["points"] == ["15", "0"]
        assert (
            client.post(prefix + "/match/actions", json=payload, headers=player_headers).json()["revision"]
            == 1
        )
        player_cookie = client.cookies.get("courtside-session")
        client.cookies.clear()
        relogin = client.post("/api/auth/login", json={"email": setup["email"], "password": PASSWORD}).json()
        headers = {"X-CSRF-Token": relogin["csrf"]}
        assert client.get("/api/admin/audit").status_code == 200
        assert client.get("/api/admin/audit").json()
        assert client.delete("/api/admin/users/" + member["id"], headers=headers).status_code == 200
        client.cookies.clear()
        client.cookies.set("courtside-session", player_cookie)
        assert client.get(prefix + "/match").status_code == 401
        assert client.get(media).status_code == 401


def test_remote_account_setup_and_untrusted_origins_rejected(tmp_path):
    with TestClient(
        create_accounts_app(tmp_path, embedded_worker=False), base_url="http://remote.example"
    ) as client:
        assert not client.get("/api/auth/config").json()["setup_available"]
        payload = {"academy": "Test", "name": "A", "email": "a@example.test", "password": PASSWORD}
        assert client.post("/api/auth/setup", json=payload).status_code == 403
        assert client.post("/api/auth/login", json=payload).status_code == 403
        assert client.get("/api/auth/me", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert client.get("/api/not-a-route").status_code == 404
