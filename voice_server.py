"""Local web host and short-lived LiveKit token service for the voice UI."""
import logging
import os
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web
from dotenv import load_dotenv
from livekit import api

load_dotenv(Path(__file__).parent / ".env.local")
logger = logging.getLogger(__name__)
WEB_ROOT = Path(__file__).parent / "web"


def _origin_allowed(request: web.Request) -> bool:
    origin = request.headers.get("Origin")
    configured_origin = os.getenv("WEB_ORIGIN")
    expected_origin = configured_origin or f"{request.scheme}://{request.host}"
    return origin == expected_origin


def _livekit_settings() -> tuple[str, str, str]:
    url = os.getenv("LIVEKIT_URL", "").strip()
    key = os.getenv("LIVEKIT_API_KEY", "").strip()
    secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
    if not url or not key or not secret:
        raise ValueError("Configure LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET.")
    if urlsplit(url).scheme not in {"ws", "wss"} or not urlsplit(url).netloc:
        raise ValueError("LIVEKIT_URL must be a ws:// or wss:// URL.")
    return url, key, secret


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB_ROOT / "index.html")


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def issue_token(request: web.Request) -> web.Response:
    if not _origin_allowed(request):
        raise web.HTTPForbidden(text="Request origin is not allowed.")

    try:
        server_url, api_key, api_secret = _livekit_settings()
    except ValueError as exc:
        logger.error("LiveKit token service is not configured: %s", exc)
        raise web.HTTPServiceUnavailable(
            text="Voice service is not configured. Check the LiveKit settings in .env.local."
        ) from exc

    room_name = f"voice-{uuid.uuid4().hex}"
    identity = f"guest-{uuid.uuid4().hex[:16]}"
    access_token = (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name("زائر")
        .with_ttl(timedelta(minutes=10))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_sources=["MICROPHONE"],
            )
        )
    )
    return web.json_response(
        {
            "serverUrl": server_url,
            "participantToken": access_token.to_jwt(),
            "roomName": room_name,
        },
        headers={"Cache-Control": "no-store"},
    )


def create_app() -> web.Application:
    app = web.Application(client_max_size=1024)
    app.router.add_get("/", index)
    app.router.add_get("/healthz", health)
    app.router.add_post("/api/token", issue_token)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    web.run_app(create_app(), host="127.0.0.1", port=int(os.getenv("WEB_PORT", "8000")))
