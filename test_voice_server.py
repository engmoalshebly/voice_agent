import base64
import json
import os
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from voice_server import create_app


class VoiceServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings = patch.dict(
            os.environ,
            {
                "LIVEKIT_URL": "ws://localhost:17980",
                "LIVEKIT_API_KEY": "test-key",
                "LIVEKIT_API_SECRET": "test-secret-with-more-than-thirty-two-bytes",
                "WEB_ORIGIN": "http://127.0.0.1:8000",
            },
        )
        self.settings.start()
        self.client = TestClient(TestServer(create_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.settings.stop()

    async def test_token_is_room_scoped_and_limited_to_microphone(self):
        response = await self.client.post(
            "/api/token",
            headers={"Origin": "http://127.0.0.1:8000"},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        body = await response.json()
        self.assertEqual(body["serverUrl"], "ws://localhost:17980")
        self.assertTrue(body["roomName"].startswith("voice-"))

        payload = body["participantToken"].split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        self.assertEqual(claims["video"]["room"], body["roomName"])
        self.assertTrue(claims["video"]["roomJoin"])
        self.assertTrue(claims["video"]["canPublish"])
        self.assertTrue(claims["video"]["canSubscribe"])
        self.assertEqual(claims["video"]["canPublishSources"], ["MICROPHONE"])
        self.assertEqual(claims["sub"].split("-")[0], "guest")

    async def test_token_rejects_other_origins(self):
        response = await self.client.post(
            "/api/token",
            headers={"Origin": "https://example.invalid"},
        )
        self.assertEqual(response.status, 403)

    async def test_homepage_and_health_endpoint(self):
        page = await self.client.get("/")
        self.assertEqual(page.status, 200)
        self.assertIn("المساعد الصوتي", await page.text())
        health = await self.client.get("/healthz")
        self.assertEqual(await health.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
