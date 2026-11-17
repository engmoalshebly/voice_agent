import base64
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from voice_agent.entrypoints.token_api import RateLimiter, create_app

ENV = {
    "LIVEKIT_URL": "ws://localhost:17980",
    "LIVEKIT_API_KEY": "test-key",
    "LIVEKIT_API_SECRET": "test-secret-with-more-than-thirty-two-bytes",
    "WEB_ORIGIN": "http://127.0.0.1:8000",
    "TOKENS_PER_MINUTE": "2",
}
ORIGIN = {"Origin": "http://127.0.0.1:8000"}


@pytest.fixture
async def client(tmp_path):
    (tmp_path / "index.html").write_text("<html>المساعد الصوتي</html>", encoding="utf-8")
    c = TestClient(TestServer(create_app({**ENV, "WEB_STATIC_DIR": str(tmp_path)})))
    await c.start_server()
    yield c
    await c.close()


def claims(jwt):
    p = jwt.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))


async def test_token_scoped_to_one_room_and_microphone(client):
    r = await client.post("/api/token", headers=ORIGIN)
    assert r.status == 200 and r.headers["Cache-Control"] == "no-store"
    body = await r.json()
    c = claims(body["participantToken"])
    assert c["video"]["room"] == body["roomName"] and body["roomName"].startswith("voice-")
    assert c["video"]["canPublishSources"] == ["microphone"]
    assert c["sub"].startswith("guest-")


async def test_rejects_foreign_origin_and_rate_limits(client):
    assert (await client.post("/api/token", headers={"Origin": "https://evil.invalid"})).status == 403
    assert (await client.post("/api/token")).status == 403
    await client.post("/api/token", headers=ORIGIN)
    await client.post("/api/token", headers=ORIGIN)
    r = await client.post("/api/token", headers=ORIGIN)
    assert r.status == 429 and (await r.json())["error"]["code"] == "rate_limited"


async def test_spa_health_and_security_headers(client):
    page = await client.get("/")
    assert "المساعد الصوتي" in await page.text()
    assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
    policy = page.headers["Content-Security-Policy"]
    assert "http://localhost:17980" in policy
    assert " http:;" not in policy and " http: " not in policy
    assert await (await client.get("/healthz")).json() == {"status": "ok"}
    assert (await client.get("/readyz")).status == 200


async def test_unconfigured_livekit_is_503():
    c = TestClient(TestServer(create_app({"WEB_ORIGIN": "http://127.0.0.1:8000"})))
    await c.start_server()
    try:
        assert (await c.post("/api/token", headers=ORIGIN)).status == 503
        assert (await c.get("/readyz")).status == 503
    finally:
        await c.close()


def test_rate_limiter_window():
    now = [0.0]
    rl = RateLimiter(1, clock=lambda: now[0])
    assert rl.allow("a") and not rl.allow("a") and rl.allow("b")
    now[0] = 61
    assert rl.allow("a")


async def test_config_tells_the_page_where_calls_are_set_up(client, tmp_path):
    assert await (await client.get("/api/config")).json() == {"gatewayUrl": "", "channelId": ""}   # legacy demo

    env = {**ENV, "WEB_STATIC_DIR": str(tmp_path),
           "VOICE_GATEWAY_PUBLIC_URL": "https://app.example.com/", "VOICE_CHANNEL_ID": "webchat_1"}
    darai = TestClient(TestServer(create_app(env)))
    await darai.start_server()
    try:
        response = await darai.get("/api/config")
        assert await response.json() == {"gatewayUrl": "https://app.example.com", "channelId": "webchat_1"}
        assert response.headers["Cache-Control"] == "no-store"
    finally:
        await darai.close()


def test_the_public_gateway_url_must_be_https(tmp_path):
    from voice_agent.config import ConfigError

    with pytest.raises(ConfigError, match="VOICE_GATEWAY_PUBLIC_URL"):
        create_app({**ENV, "WEB_STATIC_DIR": str(tmp_path), "VOICE_GATEWAY_PUBLIC_URL": "http://app.example.com"})
