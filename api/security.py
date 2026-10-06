"""Bounded rate limits, security headers and aggregate request telemetry."""

import threading
import time
from collections import OrderedDict, deque


class RateLimiter:
    def __init__(self, maximum=2000):
        self.maximum = maximum
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def allow(self, key, limit, window=60):
        stamp = time.monotonic()
        with self.lock:
            events = self.entries.pop(key, deque())
            while events and events[0] <= stamp - window:
                events.popleft()
            allowed = len(events) < limit
            if allowed:
                events.append(stamp)
            self.entries[key] = events
            while len(self.entries) > self.maximum:
                self.entries.popitem(last=False)
            return allowed


class Telemetry:
    def __init__(self):
        self.lock = threading.Lock()
        self.requests = 0
        self.failures = 0
        self.latencies: deque[float] = deque(maxlen=1000)
        self.began = time.monotonic()

    def record(self, status, elapsed):
        with self.lock:
            self.requests += 1
            self.failures += status >= 500
            self.latencies.append(round(elapsed * 1000, 2))

    def snapshot(self):
        with self.lock:
            ordered = sorted(self.latencies)
            return {
                "uptime_seconds": round(time.monotonic() - self.began),
                "requests": self.requests,
                "server_errors": self.failures,
                "request_p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
                if ordered
                else None,
                "sample_count": len(ordered),
            }


class SecurityMiddleware:
    def __init__(self, app, telemetry, origins):
        self.app, self.telemetry = app, telemetry
        self.limiter = RateLimiter()
        connections = " ".join(origins + [o.replace("http", "ws", 1) for o in origins])
        self.csp = (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; "
            "script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; "
            f"media-src 'self' blob:; connect-src 'self' {connections}"
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        stamp = time.monotonic()
        status = 500

        async def secured(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"permissions-policy", b"camera=(self), microphone=(), geolocation=()"),
                        (b"content-security-policy", self.csp.encode()),
                    ]
                )
                if scope.get("scheme") == "https":
                    headers.append((b"strict-transport-security", b"max-age=31536000"))
                if scope.get("path", "").startswith("/api/"):
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        host = (scope.get("client") or ("unknown",))[0]
        if scope.get("path", "").startswith("/api/") and not self.limiter.allow(host, 600):
            from starlette.responses import JSONResponse

            await JSONResponse(
                {"detail": "Too many requests. Try again shortly."}, 429, headers={"Retry-After": "60"}
            )(scope, receive, secured)
        else:
            try:
                await self.app(scope, receive, secured)
            finally:
                self.telemetry.record(status, time.monotonic() - stamp)
