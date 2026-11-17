"""DarAI as the session's language model.

The voice worker has no model of its own in ``darai`` mode: what the visitor
said goes to DarAI as a turn, and DarAI's sentences come back as the "LLM"
output. The LiveKit session then does what it does for any model — streams
the text to TTS, publishes the transcript and handles barge-in — so none of
that is reimplemented here.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import random
import re
import time
import uuid
from typing import Any

from livekit.agents import llm

from ..domain.phrases import Phrases
from .darai_turns import DaraiTurnClient, DaraiTurnError

log = logging.getLogger(__name__)


#: Words a reply may open with that only acknowledge. After a filler they echo it
#: ("أكيد. أكيد، تقدر…"), so they are dropped from the first sentence.
_ACKNOWLEDGEMENT = re.compile(
    r"^\s*(?:أكيد|اكيد|تمام|طيب|حاضر|أبشر|ابشر|بالتأكيد|بالتاكيد|طبعاً|طبعا|حسناً|حسنا|ماشي)\s*[،,.!]+\s*")


def without_acknowledgement(sentence: str) -> str:
    """The sentence minus an opening acknowledgement; unchanged if nothing would be left."""
    trimmed = _ACKNOWLEDGEMENT.sub("", sentence, count=1).strip()
    return trimmed or sentence


#: A welcome at the start of an answer. The call was already welcomed, so it
#: is only kept when the caller greeted first.
_WELCOME = re.compile(
    # A standalone welcome phrase: it must end at punctuation, so "أهلاً
    # بالأبطال في برنامجنا" (not addressed to the caller) is left alone.
    r"^\s*(?:(?:أهلاً|أهلا|اهلاً|اهلا)(?:\s+وسهلاً|\s+وسهلا)?|مرحباً|مرحبا)(?:\s+(?:بك|فيك))?\s*[،,.!]+\s*")
_CALLER_GREETING = re.compile(r"سلام|مرحب|أهل|اهل|صباح|مساء|كيف\s*(?:حالك|الحال|اصبحت|أصبحت)|هلا")
#: "4×6" is read as "four times six" or not at all; a caller hears "أربعة في ستة".
_SIZE = re.compile(r"(\d+)\s*[×xX*]\s*(\d+)")


def spoken_answer(sentence: str, *, first: bool, after_filler: bool, caller_text: str) -> str:
    """What is actually said for a sentence of DarAI's answer.

    The model is asked for all of this; these are the safeguards for when it
    does not comply, because every miss is heard.
    """
    text = _SIZE.sub(r"\1 في \2", sentence)
    if first and not _CALLER_GREETING.search(caller_text or ""):
        text = _WELCOME.sub("", text, count=1).strip() or text
    if first and after_filler:
        text = without_acknowledgement(text)
    return text


def last_user_message(chat_ctx: llm.ChatContext) -> tuple[str, str]:
    """(text, item id) of what the visitor just said, or ("", "")."""
    for item in reversed(chat_ctx.items):
        if getattr(item, "type", None) == "message" and getattr(item, "role", None) == "user":
            return (item.text_content or "").strip(), str(getattr(item, "id", "") or "")
    return "", ""


class DaraiLLM(llm.LLM):
    def __init__(self, client: DaraiTurnClient, visitor_token: str, phrases: Phrases, *,
                 filler_delay: float = 0.0, call_id: str = "") -> None:
        super().__init__()
        self._client = client
        self._visitor_token = visitor_token
        self._phrases = phrases
        self._filler_delay = filler_delay
        self._call_id = call_id or uuid.uuid4().hex[:12]
        self._last_filler: str | None = None
        self._random = random.Random()

    @property
    def model(self) -> str:
        return "darai"

    @property
    def provider(self) -> str:
        return "darai"

    def next_filler(self) -> str:
        """A short acknowledgement, never the one said last: repeating the same
        words every turn is what makes a call sound machine-made."""
        choices = [p for p in self._phrases.fillers if p != self._last_filler] or list(self._phrases.fillers)
        self._last_filler = self._random.choice(choices)
        return self._last_filler

    def chat(self, *, chat_ctx: llm.ChatContext, tools: list[Any] | None = None,
             conn_options: Any = None, **_: Any) -> "DaraiLLMStream":
        options = conn_options if conn_options is not None else llm.llm.DEFAULT_API_CONNECT_OPTIONS
        # Never retried by the framework: a retry would be a second message in
        # the visitor's conversation. Failures are spoken, not raised.
        return DaraiLLMStream(self, chat_ctx=chat_ctx, tools=tools or [],
                              conn_options=dataclasses.replace(options, max_retry=0))


class DaraiLLMStream(llm.LLMStream):
    _llm: DaraiLLM

    def _say(self, request_id: str, text: str) -> None:
        self._event_ch.send_nowait(llm.ChatChunk(
            # One line per sentence: the line tokenizer speaks it immediately.
            id=request_id, delta=llm.ChoiceDelta(role="assistant", content=text.strip() + "\n")))

    async def _run(self) -> None:
        owner = self._llm
        text, item_id = last_user_message(self._chat_ctx)
        if not text:
            return
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        loop = asyncio.get_running_loop()
        filler_at = started + owner._filler_delay if owner._filler_delay > 0 else None
        answered = False
        filler_said = False
        first_ms: float | None = None
        reason = "error"
        events = owner._client.turn(
            owner._visitor_token, text, client_turn_id=f"{owner._call_id}:{item_id}" if item_id else None,
        ).__aiter__()
        pending: asyncio.Future = asyncio.ensure_future(events.__anext__())
        try:
            while True:
                timeout = None if (answered or filler_at is None) else max(0.0, filler_at - loop.time())
                done, _ = await asyncio.wait({pending}, timeout=timeout)
                if not done:
                    # DarAI is still working: say so instead of leaving silence.
                    self._say(request_id, owner.next_filler())
                    filler_said = True
                    filler_at = None
                    continue
                try:
                    event = pending.result()
                except StopAsyncIteration:
                    break
                pending = asyncio.ensure_future(events.__anext__())
                if event.kind == "sentence":
                    first = first_ms is None
                    if first:
                        first_ms = (time.monotonic() - started) * 1000
                    answered = True
                    self._say(request_id, spoken_answer(event.text, first=first, after_filler=filler_said,
                                                        caller_text=text))
                elif event.kind == "replace":
                    answered = True
                    self._say(request_id, f"{owner._phrases.correction} {event.text}")
                elif event.kind == "end":
                    reason = event.reason or "answered"
                    break
            if not answered:
                self._say(request_id, {"no_reply": owner._phrases.with_team,
                                       "silent": owner._phrases.no_reply}.get(reason, owner._phrases.turn_failed))
        except DaraiTurnError as exc:
            reason = f"error:{exc.status or 'transport'}"
            log.warning("DarAI turn failed: %s", exc)
            if not answered:
                self._say(request_id, owner._phrases.turn_failed)
        finally:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            await events.aclose()
            log.info("darai turn reason=%s answered=%s first_sentence_ms=%s total_ms=%.0f",
                     reason, answered, None if first_ms is None else round(first_ms),
                     (time.monotonic() - started) * 1000)
