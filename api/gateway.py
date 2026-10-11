"""Account gateway: separate workspace databases, files, keys and live state."""

import hmac
import os
import secrets
import threading
from contextlib import AsyncExitStack, asynccontextmanager
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.datastructures import Headers

from api.accounts import COOKIE, SESSION_SECONDS, Accounts
from api.google_auth import authorize_url, exchange_code
from api.google_auth import settings as google_settings
from api.security import RateLimiter, SecurityMiddleware, Telemetry


def origins():
    if os.environ.get("COURTSIDE_ENV") == "production":
        return [os.environ["COURTSIDE_ORIGIN"]]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        *filter(None, [os.environ.get("COURTSIDE_ORIGIN")]),
    ]


def check_origin(scope):
    headers = Headers(scope=scope)
    scheme = scope.get("scheme", "http").replace("ws", "http", 1)
    own = f"{scheme}://{headers.get('host', '')}"
    origin = headers.get("origin")
    if headers.get("sec-fetch-site") == "cross-site" or (
        origin and origin not in origins() and origin != own
    ):
        raise HTTPException(403, "This origin is not allowed")


def cookie_from_scope(scope):
    cookie = SimpleCookie()
    try:
        cookie.load(Headers(scope=scope).get("cookie", ""))
        return cookie[COOKIE].value if COOKIE in cookie else ""
    except CookieError:
        return ""


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=15, max_length=128)


class NewAccount(Credentials):
    name: str = Field(min_length=1, max_length=80)
    role: Literal["admin", "coach", "player"] = "player"


class SetupAccount(NewAccount):
    academy: str = Field(default="", max_length=100)


class WorkspaceRouter:
    def __init__(self, accounts, stack, live_capacity, embedded_worker):
        self.accounts, self.stack = accounts, stack
        self.apps = {}
        self.live_capacity, self.embedded_worker = live_capacity, embedded_worker
        import asyncio

        self.lock = asyncio.Lock()

    async def __call__(self, scope, receive, send):
        try:
            check_origin(scope)
            token = cookie_from_scope(scope)
            user = self.accounts.resolve(token)
            if not user:
                raise HTTPException(401, "Sign in to your academy")
            headers = Headers(scope=scope)
            if scope["type"] == "http" and scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
                if not hmac.compare_digest(headers.get("x-csrf-token", ""), user["csrf"]):
                    raise HTTPException(403, "Refresh your sign-in before making changes")
            prefix = "/api/workspaces/"
            tail = scope["path"].split(prefix, 1)[-1]
            uid, separator, remaining = tail.partition("/")
            if not separator or not remaining.startswith("api/"):
                raise HTTPException(404, "Endpoint not found")
            root = self.accounts.workspace(user, uid)
            if user["role"] == "player" and (
                remaining.endswith("/reviews")
                and scope.get("method") == "POST"
                or remaining.startswith("api/operations/metrics")
            ):
                raise HTTPException(403, "A coach or administrator role is required")
            async with self.lock:
                if uid not in self.apps:
                    if len(self.apps) >= 32:
                        raise HTTPException(
                            503, "Workspace capacity reached. Restart the service during maintenance."
                        )
                    from api.main import create_app

                    fresh_workspace = not (root / "courtside.sqlite").exists()
                    child = create_app(
                        root,
                        self.embedded_worker,
                        False,
                        trusted_gateway=True,
                        media_prefix=f"/api/workspaces/{uid}",
                        live_capacity=self.live_capacity,
                    )
                    if fresh_workspace:
                        import json
                        preferences = child.state.store.settings()
                        preferences.update(display_name=user["name"].split()[0], player_name=user["name"])
                        with child.state.store.connection() as db:
                            db.execute("UPDATE settings SET value=? WHERE id=1", (json.dumps(preferences),))
                    await self.stack.enter_async_context(child.router.lifespan_context(child))
                    self.apps[uid] = child
                app = self.apps[uid]
            adjusted = {**scope, "path": "/" + remaining, "root_path": ""}
            adjusted["raw_path"] = adjusted["path"].encode()

            async def guarded_receive():
                message = await receive()
                if (
                    scope["type"] == "websocket"
                    and message["type"] == "websocket.receive"
                    and not self.accounts.resolve(token)
                ):
                    await send({"type": "websocket.close", "code": 1008, "reason": "Sign-in expired"})
                    return {"type": "websocket.disconnect", "code": 1008}
                return message

            if scope["type"] == "websocket":
                self.accounts.audit(user, "live_connection", uid)
            elif scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
                self.accounts.audit(user, "workspace_" + scope["method"].lower(), uid)
            await app(adjusted, guarded_receive, send)
        except ValueError:
            await self.reject(scope, receive, send, 404, "Workspace not found")
        except HTTPException as exc:
            await self.reject(scope, receive, send, exc.status_code, exc.detail)

    @staticmethod
    async def reject(scope, receive, send, code, detail):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008, "reason": detail})
        else:
            await JSONResponse({"detail": detail}, status_code=code)(scope, receive, send)


def create_accounts_app(storage=None, embedded_worker=True, personal=False):
    from courtside.pipeline import ROOT

    accounts = Accounts(Path(storage or os.environ.get("COURTSIDE_STORAGE", "storage")), personal=personal)
    google = google_settings()
    stack = AsyncExitStack()
    limiter, telemetry = RateLimiter(), Telemetry()
    capacity = threading.BoundedSemaphore(int(os.environ.get("COURTSIDE_LIVE_CAPACITY", "2")))

    @asynccontextmanager
    async def lifespan(app):
        from courtside.operations import StorageLock

        with StorageLock(accounts.root):
            async with stack:
                yield

    app = FastAPI(title="Courtside Academy", lifespan=lifespan)
    app.state.accounts = accounts
    app.state.telemetry = telemetry
    router = WorkspaceRouter(accounts, stack, capacity, embedded_worker)
    app.state.workspaces = router
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.add_middleware(SecurityMiddleware, telemetry=telemetry, origins=origins())

    def identity(request, admin=False):
        check_origin(request.scope)
        if personal and admin:
            raise HTTPException(403, "Team administration is unavailable in personal mode")
        user = accounts.resolve(request.cookies.get(COOKIE, ""))
        if not user:
            raise HTTPException(401, "Sign in to your academy")
        if admin and user["role"] != "admin":
            raise HTTPException(403, "Administrator role required")
        if request.method not in {"GET", "HEAD"} and not hmac.compare_digest(
            request.headers.get("x-csrf-token", ""), user["csrf"]
        ):
            raise HTTPException(403, "Refresh your sign-in before making changes")
        return user

    def local(request):
        return (
            request.client
            and request.client.host in {"127.0.0.1", "::1", "testclient"}
            and request.url.hostname in {"127.0.0.1", "localhost", "::1", "testserver"}
        )

    def secure_login(request):
        check_origin(request.scope)
        if request.url.scheme != "https" and not local(request):
            raise HTTPException(403, "Sign-in requires HTTPS on this host")
        host = request.client.host if request.client else "unknown"
        if not limiter.allow("login:" + host, 6, 300) or not limiter.allow("login:global", 30):
            raise HTTPException(429, "Too many sign-in attempts. Wait five minutes.")

    @app.get("/api/auth/config")
    def auth_config(request: Request):
        return {
            "enabled": True,
            "personal": personal,
            "google_enabled": google is not None,
            "setup_available": bool(local(request) and not accounts.has_users()),
        }

    @app.post("/api/auth/setup")
    def setup(value: SetupAccount, request: Request):
        secure_login(request)
        if not local(request):
            raise HTTPException(403, "Complete initial setup on the server's localhost page")
        if not personal and not value.academy.strip():
            raise HTTPException(400, "Academy name is required")
        try:
            user = accounts.create_user(
                secrets.token_hex(16),
                value.email,
                value.name,
                "admin",
                value.password,
                value.academy if not personal else "Personal",
                bootstrap=True,
            )
            accounts.audit(user, "academy_setup", user["id"])
            return {"created": True}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/auth/login")
    def login(value: Credentials, request: Request, response: Response):
        secure_login(request)
        try:
            token, csrf, user = accounts.login(value.email, value.password)
        except ValueError as exc:
            raise HTTPException(401, str(exc)) from exc
        response.set_cookie(
            COOKIE,
            token,
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=request.url.scheme == "https" or os.environ.get("COURTSIDE_ORIGIN", "").startswith("https://"),
            samesite="lax",
            path="/",
        )
        return {"user": user, "csrf": csrf, "workspaces": accounts.workspaces(user)}

    @app.get("/api/auth/google/start")
    def google_start(request: Request):
        if not google:
            raise HTTPException(404, "Google sign-in is not configured")
        secure_login(request)
        if request.headers.get("host", "").lower() != google[2].split("//", 1)[1].lower():
            raise HTTPException(400, "Open Courtside at its configured Google sign-in address")
        state, verifier = accounts.create_google_flow()
        response = RedirectResponse(authorize_url(google, state, verifier), status_code=302)
        response.set_cookie(
            "courtside-google-state", state, max_age=300, httponly=True,
            secure=google[2].startswith("https://"), samesite="lax", path="/api/auth/google",
        )
        return response

    @app.post("/api/auth/google/link")
    def google_link(request: Request):
        if not google:
            raise HTTPException(404, "Google sign-in is not configured")
        user = identity(request)
        if request.headers.get("host", "").lower() != google[2].split("//", 1)[1].lower():
            raise HTTPException(400, "Open Courtside at its configured Google sign-in address")
        state, verifier = accounts.create_google_flow(user["id"])
        response = JSONResponse({"url": authorize_url(google, state, verifier)})
        response.set_cookie(
            "courtside-google-state", state, max_age=300, httponly=True,
            secure=google[2].startswith("https://"), samesite="lax", path="/api/auth/google",
        )
        return response

    @app.get("/api/auth/google/callback")
    def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
        if not google:
            raise HTTPException(404, "Google sign-in is not configured")
        if not state or len(state) > 128 or not hmac.compare_digest(
            state, request.cookies.get("courtside-google-state", "")
        ):
            raise HTTPException(400, "Google sign-in request expired")
        flow = accounts.consume_google_flow(state)
        if not flow:
            raise HTTPException(400, "Google sign-in request expired")
        response = RedirectResponse("/?auth_error=google_denied#sessions" if error else "/#sessions", status_code=303)
        response.delete_cookie(
            "courtside-google-state", path="/api/auth/google",
            secure=google[2].startswith("https://"), httponly=True, samesite="lax",
        )
        if error:
            return response
        if not code or len(code) > 4096:
            raise HTTPException(400, "Google authorization code is missing")
        try:
            claims = exchange_code(google, code, flow["verifier"])
            link_uid = flow["link_user_id"]
            if link_uid:
                existing = accounts.resolve(request.cookies.get(COOKIE, ""))
                if not existing or existing["id"] != link_uid:
                    raise ValueError("Sign in again before linking Google")
            user = accounts.google_user(
                claims["sub"], claims["email"], claims.get("name", ""), link_uid,
            )
        except ValueError as exc:
            response.headers["location"] = (
                "/?auth_error=account_exists#sessions"
                if "email exists" in str(exc) else "/?auth_error=google_invalid#sessions"
            )
            return response
        except Exception:
            response.headers["location"] = "/?auth_error=google_unavailable#sessions"
            return response
        if not link_uid:
            token, _ = accounts.new_session(user["id"])
            response.set_cookie(
                COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                secure=google[2].startswith("https://"), samesite="lax", path="/",
            )
        accounts.audit(user, "google_link" if link_uid else "google_login", user["id"])
        return response

    @app.get("/api/auth/me")
    def me(request: Request):
        user = identity(request)
        return {
            "user": {k: v for k, v in user.items() if k not in {"csrf", "expires"}},
            "csrf": user["csrf"],
            "workspaces": accounts.workspaces(user),
        }

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        user = identity(request)
        accounts.logout(request.cookies.get(COOKIE, ""))
        accounts.audit(user, "logout", user["id"])
        response.delete_cookie(
            COOKIE, path="/", secure=request.url.scheme == "https" or os.environ.get("COURTSIDE_ORIGIN", "").startswith("https://"), httponly=True, samesite="lax"
        )
        return {"signed_out": True}

    @app.post("/api/admin/users")
    def add_user(value: NewAccount, request: Request):
        actor = identity(request, True)
        try:
            user = accounts.create_user(
                actor["academy_id"], value.email, value.name, value.role, value.password
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        accounts.audit(actor, "account_created", user["id"])
        return user

    @app.delete("/api/admin/users/{uid}")
    def disable_user(uid: str, request: Request):
        actor = identity(request, True)
        try:
            accounts.disable(actor, uid)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"disabled": True}

    @app.get("/api/admin/audit")
    def audit(request: Request):
        return accounts.audit_log(identity(request, True))

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "accounts_enabled": True,
            "access_token_required": False,
            "model_ready": Path(
                os.environ.get("COURTSIDE_MODEL", ROOT / "models/pose_landmarker_full.task")
            ).is_file(),
        }

    @app.get("/api/ready")
    def ready():
        from courtside.readiness import installation_status

        status = installation_status()
        if not accounts.has_users() and not (personal and google):
            status["local_ready"] = False
            status["errors"].append("Complete initial account setup on localhost")
        return JSONResponse(status, status_code=200 if status["local_ready"] else 503)

    @app.get("/api/operations/metrics")
    def metrics(request: Request):
        identity(request, True)
        return telemetry.snapshot()

    app.mount("/api/workspaces", router)
    dist = ROOT / "web/dist"

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Endpoint not found")
        target = (dist / path).resolve()
        return FileResponse(
            target if target.is_relative_to(dist.resolve()) and target.is_file() else dist / "index.html"
        )

    return app
