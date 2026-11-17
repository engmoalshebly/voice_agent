"""Client for DarAI voice turns (realtime gateway ``POST /ws/voice/turn``).

One call per thing the visitor said. The reply arrives as events while the
model is still writing it:

    sentence  say this now
    replace   say this instead of what was said
    end       the turn is over (answered | no_reply | silent | timeout)

The worker presents two credentials: the visitor's own widget token, which
says whose conversation this is, and the worker key.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import aiohttp

from ..config import GatewaySettings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnEvent:
    kind: str            # sentence | replace | end
    text: str = ""
    reason: str = ""     # for end: answered | no_reply | silent | timeout


class DaraiTurnError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class DaraiTurnClient:
    def __init__(self, settings: GatewaySettings, session: aiohttp.ClientSession | None = None):
        self._settings = settings
        self._owns_session = session is None
        self._session = session

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=None, connect=self._settings.connect_timeout))
        return self._session

    async def turn(self, visitor_token: str, text: str, client_turn_id: str | None = None) -> AsyncIterator[TurnEvent]:
        """Send one utterance; yield the reply's events until ``end``.

        Closing the iterator early (the visitor interrupted) only stops
        listening: DarAI still finishes and stores the turn.
        """
        body = {"text": text}
        if client_turn_id:
            body["client_turn_id"] = client_turn_id[:64]
        headers = {
            "Authorization": f"Bearer {visitor_token}",
            "X-Voice-Worker-Key": self._settings.worker_key,
            "Accept": "text/event-stream",
        }
        try:
            async with self._http().post(
                self._settings.url + "/ws/voice/turn", json=body, headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._settings.turn_timeout,
                                              connect=self._settings.connect_timeout),
            ) as response:
                if response.status != 200:
                    raise DaraiTurnError(f"DarAI refused the turn ({response.status})", response.status)
                event = ""
                async for raw in response.content:
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if line.startswith("event: "):
                        event = line[7:].strip()
                    elif line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                        except ValueError:
                            continue
                        if not isinstance(data, dict):
                            continue
                        if event in ("sentence", "replace"):
                            text_piece = str(data.get("text") or "").strip()
                            if text_piece:
                                yield TurnEvent(event, text=text_piece)
                        elif event == "end":
                            yield TurnEvent("end", reason=str(data.get("reason") or ""))
                            return
        except DaraiTurnError:
            raise
        except aiohttp.ClientError as exc:
            raise DaraiTurnError(f"DarAI is unreachable ({type(exc).__name__})") from exc
        except TimeoutError as exc:
            raise DaraiTurnError("DarAI turn timed out") from exc
        raise DaraiTurnError("DarAI closed the turn without an end")

    async def close(self) -> None:
        if self._session is not None and self._owns_session:
            await self._session.close()
        self._session = None
