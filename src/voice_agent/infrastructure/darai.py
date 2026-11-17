"""DarAI developer-channel client (ticket + WebSocket v2).

One instance is one isolated DarAI conversation. The WebSocket is opened on
the first question and reused for later ones; if it drops, the next question
reconnects once transparently. A failure never poisons the instance.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from ..config import DaraiSettings

log = logging.getLogger(__name__)


class DaraiError(RuntimeError):
    pass


class DaraiClient:
    def __init__(self, settings: DaraiSettings, session: aiohttp.ClientSession | None = None):
        self._settings = settings
        self._external_session = session
        self._http: aiohttp.ClientSession | None = session
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ping: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._closed = False
        self._cursor: str | None = None
        self.conversation_id = "voice-" + uuid.uuid4().hex
        parts = urlsplit(settings.base_url)
        self._ws_url = urlunsplit(("wss", parts.netloc, parts.path.rstrip("/") + "/ws/developer/v2/connect", "", ""))

    # -- public ---------------------------------------------------------
    async def ask(self, question: str) -> str:
        async with self._lock, asyncio.timeout(self._settings.request_timeout):
            correlation_id = uuid.uuid4().hex
            request_id = uuid.uuid4().hex
            for attempt in (1, 2):
                try:
                    ws = await self._connected(correlation_id)
                    return await self._exchange(ws, question, request_id)
                except (aiohttp.ClientConnectionError, ConnectionResetError, DaraiConnectionLost) as exc:
                    await self._drop()
                    if attempt == 2:
                        raise DaraiError("DarAI connection lost") from exc
                    log.info("DarAI unavailable (%s); retrying once", exc, extra={"correlation_id": correlation_id})
                    await asyncio.sleep(1.0)
                except BaseException:
                    # Timeout/cancel leaves the socket mid-exchange: never reuse it.
                    await self._drop()
                    raise
            raise AssertionError("unreachable")

    async def warm(self) -> None:
        """Open the socket ahead of the first question and keep it open."""
        async with self._lock:
            await self._connected(uuid.uuid4().hex)

    async def close(self) -> None:
        self._closed = True
        await self._drop()
        async with self._lock:
            await self._drop()
            if self._http and not self._external_session:
                await self._http.close()
            self._http = None

    # -- internals --------------------------------------------------------
    async def _connected(self, correlation_id: str) -> aiohttp.ClientWebSocketResponse:
        if self._closed:
            raise DaraiError("DarAI client is closed")
        if self._ws is not None and not self._ws.closed:
            return self._ws
        if self._http is None:
            self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, connect=self._settings.connect_timeout))
        headers = {"Authorization": "Bearer " + self._settings.api_key, "X-Correlation-ID": correlation_id}
        async with self._http.post(
            self._settings.base_url + "/ws/developer/v2/tickets",
            headers=headers,
            json={"customer_id": self.conversation_id, "consumer_id": self.conversation_id},
            timeout=aiohttp.ClientTimeout(total=self._settings.connect_timeout),
        ) as response:
            if response.status >= 500 or response.status == 429:
                # Transient (dependency restart, rate window): one retry is worth it.
                raise DaraiConnectionLost(f"DarAI ticket unavailable ({response.status})")
            if response.status >= 400:
                raise DaraiError(f"DarAI ticket rejected ({response.status})")
            ticket = (await response.json()).get("ticket")
        if not ticket:
            raise DaraiError("DarAI ticket missing")
        ws = await self._http.ws_connect(self._ws_url, heartbeat=20, headers={"X-Correlation-ID": correlation_id})
        try:
            auth = {"type": "authenticate", "ticket": ticket}
            if self._cursor:
                auth["resume_after"] = self._cursor
            await ws.send_json(auth)
            ready = await asyncio.wait_for(ws.receive_json(), self._settings.connect_timeout)
            if not isinstance(ready, dict) or ready.get("type") != "session.ready":
                raise DaraiError("DarAI session was not accepted")
            if self._closed:
                raise DaraiError("DarAI client is closed")
        except BaseException:
            await ws.close()
            raise
        self._ws = ws
        self._ping = asyncio.create_task(self._keepalive(ws))
        return ws

    async def _keepalive(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        lost = False
        try:
            while not ws.closed:
                await asyncio.sleep(15)
                if self._lock.locked():  # a question owns the socket right now
                    continue
                async with self._lock:  # never read concurrently with an exchange
                    if ws.closed:
                        break
                    await ws.send_json({"type": "ping"})
                    # Drain the pong so a server-side close is noticed while idle.
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.receive(), 0.3)
                        except asyncio.TimeoutError:
                            break
                        if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED,
                                        aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
                            lost = True
                            break
                    if lost:
                        break
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        # Closed while idle: reconnect now so the next question skips
        # ticket + connect + authenticate.
        if not self._closed and self._ws is ws:
            log.info("DarAI socket closed while idle; reconnecting ahead of time")
            with contextlib.suppress(Exception):
                await ws.close()
            self._ws = None
            self._ping = None
            with contextlib.suppress(Exception):
                await self.warm()

    async def _exchange(self, ws: aiohttp.ClientWebSocketResponse, question: str, request_id: str) -> str:
        await ws.send_json({
            "type": "message.send",
            "request_id": request_id,
            "conversation_id": self.conversation_id,
            "message": {"type": "text", "text": question},
        })
        async with asyncio.timeout(self._settings.request_timeout):
            while True:
                event = await self._receive(ws)
                kind = event.get("type")
                if kind == "message.accepted" and event.get("request_id") == request_id:
                    log.info("DarAI request accepted", extra={"request_id": request_id,
                                                              "correlation_id": event.get("correlation_id")})
                if kind == "request.error" and event.get("request_id") == request_id:
                    raise DaraiError(f"DarAI rejected the request ({event.get('status')})")
                if kind != "message.created":
                    continue
                answer = _assistant_text(event, self.conversation_id)
                if event.get("cursor"):
                    self._cursor = event["cursor"]
                    with contextlib.suppress(aiohttp.ClientConnectionError, ConnectionResetError):
                        await ws.send_json({"type": "event.ack", "cursor": self._cursor})
                if answer:
                    return answer

    @staticmethod
    async def _receive(ws: aiohttp.ClientWebSocketResponse) -> dict[str, Any]:
        msg = await ws.receive()
        if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
            raise DaraiConnectionLost()
        if msg.type != aiohttp.WSMsgType.TEXT:
            return {}
        data = msg.json()
        return data if isinstance(data, dict) else {}

    async def _drop(self) -> None:
        if self._ping:
            self._ping.cancel()
            await asyncio.gather(self._ping, return_exceptions=True)
            self._ping = None
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None


class DaraiConnectionLost(ConnectionError):
    pass


def _assistant_text(event: dict[str, Any], conversation_id: str) -> str | None:
    if event.get("conversation_id") not in (None, conversation_id):
        return None
    message = event.get("message") or {}
    if not isinstance(message, dict) or message.get("role") not in (None, "assistant"):
        return None
    content = message.get("content") or {}
    text = content.get("text") if isinstance(content, dict) else None
    return text.strip() if isinstance(text, str) and text.strip() else None
