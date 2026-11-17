"""Serves the built web UI and issues short-lived, room-scoped LiveKit tokens."""
from __future__ import annotations

import logging
import time
import uuid
from urllib.parse import urlsplit
from collections import defaultdict, deque
from datetime import timedelta

from aiohttp import web
from livekit import api

from ..config import ConfigError, LiveKitSettings, WebSettings, environ, livekit_settings, web_settings
from ..infrastructure.logs import configure_logging

log = logging.getLogger(__name__)

SETTINGS = web.AppKey("settings", WebSettings)
LIVEKIT = web.AppKey("livekit", object)
LIMITER = web.AppKey("limiter", object)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; img-src 'self' data:; media-src 'self' blob:; "
        "connect-src 'self' ws: wss: https:; frame-ancestors 'none'"
    ),
}


class RateLimiter:
    """Sliding one-minute window per client key."""

    def __init__(self, per_minute: int, clock=time.monotonic):
        self._limit = per_minute
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= 60:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        if len(self._hits) > 10_000:  # bound memory under abuse
            for stale in [k for k, v in self._hits.items() if not v or now - v[-1] >= 60]:
                del self._hits[stale]
        return True


def _client_key(request: web.Request, settings: WebSettings) -> str:
    if settings.trust_proxy:  # only behind a proxy that overwrites the header
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.remote or "unknown"


def _origin_allowed(request: web.Request, settings: WebSettings) -> bool:
    expected = settings.origin or f"{request.scheme}://{request.host}"
    return request.headers.get("Origin") == expected


def _error(status: int, code: str, message: str) -> web.Response:
    return web.json_response({"error": {"code": code, "message": message}}, status=status,
                             headers={"Cache-Control": "no-store"})


async def issue_token(request: web.Request) -> web.Response:
    settings = request.app[SETTINGS]
    if not _origin_allowed(request, settings):
        return _error(403, "origin_forbidden", "Request origin is not allowed.")
    if not request.app[LIMITER].allow(_client_key(request, settings)):
        return _error(429, "rate_limited", "Too many calls started. Try again in a minute.")
    livekit = request.app[LIVEKIT]
    if not isinstance(livekit, LiveKitSettings):
        return _error(503, "not_configured", "Voice service is not configured.")

    room = f"voice-{uuid.uuid4().hex}"
    identity = f"guest-{uuid.uuid4().hex[:16]}"
    token = (
        api.AccessToken(livekit.api_key, livekit.api_secret)
        .with_identity(identity)
        .with_name("زائر")
        .with_ttl(timedelta(minutes=settings.token_ttl_minutes))
        .with_grants(api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True,
                                     can_publish_data=True, can_publish_sources=["microphone"]))
    )
    if livekit.agent_name:
        token = token.with_room_config(api.RoomConfiguration(
            agents=[api.RoomAgentDispatch(agent_name=livekit.agent_name)]))
    log.info("token issued", extra={"room": room})
    return web.json_response({"serverUrl": livekit.url, "participantToken": token.to_jwt(), "roomName": room},
                             headers={"Cache-Control": "no-store"})


async def client_config(request: web.Request) -> web.Response:
    """Where the page sets a call up. With a gateway and a channel, a call is
    that channel's DarAI conversation; without them, the legacy anonymous demo."""
    settings = request.app[SETTINGS]
    return web.json_response(
        {"gatewayUrl": settings.gateway_public_url, "channelId": settings.channel_id},
        # Read by the embeddable widget from any customer site; it holds no secret.
        headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"},
    )


#: The embeddable voice assistant: the button, and the call it loads on press.
WIDGET_FILES = ("widget.js", "widget-call.js")


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def ready(request: web.Request) -> web.Response:
    ok = isinstance(request.app[LIVEKIT], LiveKitSettings)
    return web.json_response({"status": "ready" if ok else "not_configured"}, status=200 if ok else 503)


@web.middleware
async def security_headers(request: web.Request, handler):
    response = await handler(request)
    response.headers.update(SECURITY_HEADERS)
    livekit = request.app[LIVEKIT]
    if isinstance(livekit, LiveKitSettings):
        parts = urlsplit(livekit.url)
        http_scheme = "https" if parts.scheme == "wss" else "http"
        origin = f"{http_scheme}://{parts.netloc}"
        response.headers["Content-Security-Policy"] = SECURITY_HEADERS["Content-Security-Policy"].replace(
            "connect-src 'self' ws: wss: https:;",
            f"connect-src 'self' ws: wss: https: {origin};",
        )
    return response


def create_app(env=None) -> web.Application:
    env = environ() if env is None else env
    settings = web_settings(env)
    try:
        livekit: object = livekit_settings(env)
    except ConfigError as exc:
        log.error("LiveKit not configured: %s", exc)
        livekit = None
    app = web.Application(client_max_size=1024, middlewares=[security_headers])
    app[SETTINGS] = settings
    app[LIVEKIT] = livekit
    app[LIMITER] = RateLimiter(settings.tokens_per_minute)
    app.router.add_get("/healthz", health)
    app.router.add_get("/readyz", ready)
    app.router.add_post("/api/token", issue_token)
    app.router.add_get("/api/config", client_config)

    index = settings.static_dir / "index.html"

    async def spa(_: web.Request) -> web.StreamResponse:
        if not index.exists():
            return web.Response(status=503, text="Web UI is not built. Run: cd web && npm ci && npm run build")
        return web.FileResponse(index, headers={"Cache-Control": "no-cache"})

    app.router.add_get("/", spa)

    def widget_file(name: str):
        path = settings.static_dir / name

        async def serve(_: web.Request) -> web.StreamResponse:
            if not path.is_file():
                return web.Response(status=404, text="Widget is not built")
            return web.FileResponse(path, headers={
                "Content-Type": "application/javascript; charset=utf-8",
                "Access-Control-Allow-Origin": "*",          # included by customer sites
                "Cache-Control": "public, max-age=300",       # a new build reaches sites within minutes
            })
        return serve

    for name in WIDGET_FILES:
        app.router.add_get(f"/{name}", widget_file(name))
    for folder in ("assets", "brand", "fonts"):
        path = settings.static_dir / folder
        if path.is_dir():
            app.router.add_static(f"/{folder}", path, append_version=False)
    return app


def main() -> None:
    configure_logging()
    settings = web_settings(environ())
    web.run_app(create_app(), host=settings.host, port=settings.port, access_log=None)


if __name__ == "__main__":
    main()
