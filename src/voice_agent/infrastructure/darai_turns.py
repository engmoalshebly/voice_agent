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
import re
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import aiohttp

from ..config import GatewaySettings

log = logging.getLogger(__name__)
# ElevenLabs ids, or OpenAI/Gemini voice names ("marin", "Kore").
_VOICE_ID = re.compile(r"[A-Za-z0-9_-]{2,64}")
_PROVIDERS = ("elevenlabs", "openai", "gemini")


@dataclass(frozen=True)
class TurnEvent:
    kind: str            # sentence | replace | end
    text: str = ""
    reason: str = ""     # for end: answered | no_reply | silent | timeout


@dataclass(frozen=True)
class CallSession:
    """Who a call speaks for. Every field may be empty."""
    organization: str = ""
    greeting: str = ""
    stt_hints: tuple[str, ...] = ()
    #: The assistant's voice and limits, already within the platform's policy.
    voice_provider: str = ""
    voice_id: str = ""
    max_call_seconds: float | None = None
    filler_enabled: bool = True


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

    async def measurement(self, visitor_token: str, body: dict) -> None:
        async with self._http().post(self._settings.url + "/ws/voice/measurements", json=body,
                headers={"Authorization": f"Bearer {visitor_token}", "X-Voice-Worker-Key": self._settings.worker_key},
                timeout=aiohttp.ClientTimeout(total=8)) as response:
            if response.status != 200:
                raise DaraiTurnError("Voice measurement refused", response.status)

    async def session(self, visitor_token: str) -> CallSession:
        """Fetch the call's greeting and listening hints once, at the start.

        Reject unavailable runtime so calls cannot bypass admission policy.
        """
        headers = {"Authorization": f"Bearer {visitor_token}", "X-Voice-Worker-Key": self._settings.worker_key}
        try:
            async with self._http().post(
                self._settings.url + "/ws/voice/session", headers=headers,
                timeout=aiohttp.ClientTimeout(total=3.0, connect=self._settings.connect_timeout),
            ) as response:
                if response.status != 200:
                    raise DaraiTurnError("Voice session refused", response.status)
                data = await response.json()
        except DaraiTurnError:
            raise
        except Exception as exc:
            raise DaraiTurnError("Voice session unavailable") from exc
        if not isinstance(data, dict):
            return CallSession()
        hints = data.get("stt_hints") if isinstance(data.get("stt_hints"), list) else []
        voice = data.get("voice") if isinstance(data.get("voice"), dict) else {}
        voice_id = str(voice.get("voice_id") or "").strip()
        provider = str(voice.get("provider") or "").strip()
        valid_voice = bool(_VOICE_ID.fullmatch(voice_id)) and provider in _PROVIDERS
        seconds = voice.get("max_call_seconds")
        return CallSession(
            organization=str(data.get("organization") or "").strip(),
            greeting=str(data.get("greeting") or "").strip(),
            stt_hints=tuple(str(h).strip() for h in hints if str(h).strip())[:24],
            voice_provider=provider if valid_voice else "",
            voice_id=voice_id if valid_voice else "",
            max_call_seconds=float(seconds) if isinstance(seconds, (int, float)) and seconds >= 30 else None,
            filler_enabled=voice.get("filler_enabled") is not False,
        )

    async def call_event(self, visitor_token: str, event: str, reason: str = "") -> None:
        headers={"Authorization":f"Bearer {visitor_token}","X-Voice-Worker-Key":self._settings.worker_key}
        async with self._http().post(self._settings.url+"/ws/voice/call-event",
                json={"event":event,"reason":reason},headers=headers,
                timeout=aiohttp.ClientTimeout(total=8)) as response:
            if response.status != 200:
                raise DaraiTurnError("Call lifecycle could not be recorded",response.status)

    async def close(self) -> None:
        if self._session is not None and self._owns_session:
            await self._session.close()
        self._session = None
