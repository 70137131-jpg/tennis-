"""Personal-account isolation and Google OAuth transaction boundaries."""

from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from api.auth_mode import configured_mode
from api.gateway import create_accounts_app
from api.google_auth import authorize_url, exchange_code, settings
from api.main import create_app

PASSWORD = "A secure tennis test phrase 29"


def google_state(response):
    assert response.status_code == 302
    return parse_qs(urlsplit(response.headers["location"]).query)["state"][0]


def test_default_personal_mode_protects_every_workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("COURTSIDE_AUTH_MODE", raising=False)
    monkeypatch.delenv("COURTSIDE_ACCOUNTS", raising=False)
    monkeypatch.delenv("COURTSIDE_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("COURTSIDE_GOOGLE_CLIENT_SECRET", raising=False)
    app = create_app(tmp_path, embedded_worker=False, demo=False)
    with TestClient(app) as client:
        assert client.get("/api/auth/config").json()["personal"] is True
        assert client.get("/api/sessions").status_code == 404
        assert client.get("/api/workspaces/other/api/sessions").status_code == 401
        assert client.get("/api/auth/me").status_code == 401
        setup = {"name": "First Player", "email": "first@example.test", "password": PASSWORD}
        assert client.post("/api/auth/setup", json=setup).status_code == 200
        first = client.post("/api/auth/login", json={"email": setup["email"], "password": PASSWORD}).json()
        first_id = first["user"]["id"]
        assert [w["id"] for w in first["workspaces"]] == [first_id]
        assert client.post("/api/admin/users", headers={"X-CSRF-Token": first["csrf"]}, json={
            "name": "Second Player", "email": "second@example.test", "password": PASSWORD, "role": "player",
        }).status_code == 403
        member = app.state.accounts.create_user(
            first["user"]["academy_id"], "second@example.test", "Second Player", "player", PASSWORD,
        )
        first_root = f"/api/workspaces/{first_id}/api"
        second_root = f"/api/workspaces/{member['id']}/api"
        assert client.get(first_root + "/sessions").json() == []
        assert client.get(second_root + "/sessions").status_code == 404
        assert client.get(second_root + "/settings").status_code == 404
        assert client.get(second_root + "/media/demo-1/demo.mp4").status_code == 404
        assert client.get(second_root + "/live").status_code == 404
        assert client.post("/api/auth/logout", headers={"X-CSRF-Token": first["csrf"]}).status_code == 200
        second = client.post("/api/auth/login", json={"email": member["email"], "password": PASSWORD}).json()
        assert [w["id"] for w in second["workspaces"]] == [member["id"]]
        assert client.get(first_root + "/sessions").status_code == 404
        assert client.get(second_root + "/sessions").json() == []


def test_google_login_uses_state_once_and_provisions_isolated_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("COURTSIDE_ORIGIN", "http://localhost:8000")
    monkeypatch.setenv("COURTSIDE_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("COURTSIDE_GOOGLE_CLIENT_SECRET", "test-only-secret")
    monkeypatch.setattr("api.gateway.exchange_code", lambda config, code, verifier: {
        "sub": code, "email": f"{code}@example.test", "name": code.title(), "email_verified": True,
    })
    monkeypatch.setattr("courtside.readiness.installation_status", lambda: {"local_ready": True, "errors": []})
    app = create_accounts_app(tmp_path, embedded_worker=False, personal=True)
    with TestClient(app, base_url="http://localhost:8000") as client:
        assert client.get("/api/ready").status_code == 200
        first_start = client.get("/api/auth/google/start", follow_redirects=False)
        state = google_state(first_start)
        assert first_start.headers["location"].startswith("https://accounts.google.com/")
        assert parse_qs(urlsplit(first_start.headers["location"]).query)["code_challenge_method"] == ["S256"]
        assert client.get("/api/auth/google/callback", params={"state": "wrong", "code": "first"}).status_code == 400
        result = client.get("/api/auth/google/callback", params={"state": state, "code": "first"}, follow_redirects=False)
        assert result.status_code == 303
        first_id = client.get("/api/auth/me").json()["user"]["id"]
        assert client.get(f"/api/workspaces/{first_id}/api/sessions").json() == []
        assert client.get("/api/auth/google/callback", params={"state": state, "code": "first"}).status_code == 400
        first_csrf = client.get("/api/auth/me").json()["csrf"]
        assert client.post("/api/auth/logout", headers={"X-CSRF-Token": first_csrf}).status_code == 200
        state2 = google_state(client.get("/api/auth/google/start", follow_redirects=False))
        assert client.get("/api/auth/google/callback", params={"state": state2, "code": "second"}, follow_redirects=False).status_code == 303
        second_id = client.get("/api/auth/me").json()["user"]["id"]
        assert first_id != second_id
        assert client.get(f"/api/workspaces/{first_id}/api/sessions").status_code == 404
        assert client.get(f"/api/workspaces/{second_id}/api/sessions").json() == []


def test_google_email_does_not_silently_take_over_password_account(tmp_path, monkeypatch):
    monkeypatch.setenv("COURTSIDE_ORIGIN", "http://localhost:8000")
    monkeypatch.setenv("COURTSIDE_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("COURTSIDE_GOOGLE_CLIENT_SECRET", "test-only-secret")
    monkeypatch.setattr("api.gateway.exchange_code", lambda config, code, verifier: {
        "sub": "google-123", "email": "owner@example.test", "name": "Owner", "email_verified": True,
    })
    with TestClient(create_accounts_app(tmp_path, embedded_worker=False, personal=True), base_url="http://localhost:8000") as client:
        assert client.post("/api/auth/setup", json={
            "academy": "Ignored", "name": "Owner", "email": "owner@example.test", "password": PASSWORD,
        }).status_code == 200
        state = google_state(client.get("/api/auth/google/start", follow_redirects=False))
        result = client.get("/api/auth/google/callback", params={"state": state, "code": "valid"}, follow_redirects=False)
        assert "auth_error=account_exists" in result.headers["location"]
        assert client.get("/api/auth/me").status_code == 401
        login = client.post("/api/auth/login", json={"email": "owner@example.test", "password": PASSWORD}).json()
        assert client.post("/api/auth/google/link").status_code == 403
        link = client.post("/api/auth/google/link", headers={"X-CSRF-Token": login["csrf"]})
        assert link.status_code == 200
        linked_state = parse_qs(urlsplit(link.json()["url"]).query)["state"][0]
        assert client.get("/api/auth/google/callback", params={"state": linked_state, "code": "valid"}, follow_redirects=False).status_code == 303
        client.post("/api/auth/logout", headers={"X-CSRF-Token": login["csrf"]})
        repeat_state = google_state(client.get("/api/auth/google/start", follow_redirects=False))
        assert client.get("/api/auth/google/callback", params={"state": repeat_state, "code": "valid"}, follow_redirects=False).status_code == 303
        assert client.get("/api/auth/me").json()["user"]["id"] == login["user"]["id"]


def test_google_claims_and_production_configuration_fail_closed(monkeypatch):
    monkeypatch.setenv("COURTSIDE_GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv("COURTSIDE_GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("COURTSIDE_ORIGIN", "http://public.example")
    with pytest.raises(ValueError, match="HTTPS"):
        settings()
    monkeypatch.setenv("COURTSIDE_ORIGIN", "https://example.test")
    monkeypatch.setenv("COURTSIDE_ENV", "production")
    with pytest.raises(ValueError, match="personal"):
        configured_mode("local")
    assert configured_mode() == "personal"
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {"id_token": "signed-google-token"}
    monkeypatch.setattr("api.google_auth.requests.post", lambda *args, **kwargs: Response())
    monkeypatch.setattr("api.google_auth.id_token.verify_oauth2_token", lambda token, request, audience: {
        "sub": "123", "email": "unverified@example.test", "email_verified": False,
    })
    with pytest.raises(ValueError, match="could not be confirmed"):
        exchange_code(("client", "secret", "https://example.test"), "code", "verifier")
    url = authorize_url(("client", "secret", "https://example.test"), "state", "verifier")
    assert "response_type=code" in url and "code_challenge_method=S256" in url
