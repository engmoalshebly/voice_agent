"""Owns the lifetime of one knowledge lookup and the speech around it.

Rules (each one is covered by tests/test_dialogue.py):

* Only one lookup is active. An identical question while waiting is ignored;
  a different one replaces the old lookup.
* A replaced or cancelled lookup gets a fresh knowledge conversation, because
  the remote side may still answer the old question.
* LiveKit owns speech interruption; user speech only gates new playback.
* We never talk over the user: the answer and the "still working" notice wait
  for silence.
* A failed lookup speaks an honest failure sentence, never an invented answer.
"""
from __future__ import annotations

import asyncio
import enum
import logging
import time
from typing import Callable

from .phrases import DEFAULT_PHRASES, Phrases
from .ports import KnowledgeBase, KnowledgeFactory, Say, SpeechHandle

log = logging.getLogger(__name__)


class LookupState(str, enum.Enum):
    IDLE = "idle"
    SEARCHING = "searching"
    ANSWERING = "answering"
    FAILED = "failed"


class DialogueFlow:
    def __init__(
        self,
        knowledge_factory: KnowledgeFactory,
        say: Say,
        *,
        phrases: Phrases = DEFAULT_PHRASES,
        notice_delay: float = 12.0,
        settle_delay: float = 0.6,
        on_state: Callable[[LookupState], None] | None = None,
    ) -> None:
        self._factory = knowledge_factory
        self._knowledge: KnowledgeBase = knowledge_factory()
        self._say = say
        self._phrases = phrases
        self._notice_delay = notice_delay
        self._settle_delay = settle_delay
        self._on_state = on_state
        self._task: asyncio.Task[None] | None = None
        self._question: str | None = None
        self._generation = 0
        self._handles: list[SpeechHandle] = []
        self._quiet = asyncio.Event()
        self._quiet.set()
        self._retired: set[asyncio.Task[None]] = set()
        self._warming: set[asyncio.Task[None]] = set()
        self.state = LookupState.IDLE
        self._ack_index = 0
        self._speech_version = 0
        self._closed = False
        self._away_notified = False

    # -- queries -------------------------------------------------------
    @property
    def pending(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def task(self) -> asyncio.Task[None] | None:
        return self._task

    # -- events from the session --------------------------------------
    def user_speaking(self, speaking: bool) -> None:
        self._speech_version += 1
        if speaking:
            self._away_notified = False
            self._quiet.clear()
        else:
            self._quiet.set()

    def user_away(self) -> None:
        if (self._closed or self._away_notified or self.pending or not self._quiet.is_set()
                or any(not handle.done() for handle in self._handles)):
            return
        self._away_notified = True
        self._speak(self._phrases.away)

    def stop_audio(self) -> None:
        for handle in self._handles:
            if not handle.done():
                handle.interrupt()
        self._handles.clear()

    def start(self, question: str) -> None:
        if self._closed:
            return
        question = question.strip()
        if not question:
            return
        if self.pending and question == self._question:
            return
        self.cancel()
        self._question = question
        self._task = asyncio.create_task(self._run(question, self._generation, self._knowledge))

    def cancel(self) -> None:
        self._generation += 1
        if self.pending:
            assert self._task is not None
            self._task.cancel()
            self._track(self._task)
            if not self._closed and self.state is LookupState.SEARCHING:
                self._replace_knowledge()
        self._question = None
        self._task = None
        self.stop_audio()
        self._set_state(LookupState.IDLE)

    def warm(self) -> None:
        """Best effort: open the knowledge connection before the first question."""
        warm = getattr(self._knowledge, "warm", None)
        if warm is None or self._closed:
            return
        async def run():
            try:
                await warm()
            except Exception:
                log.info("knowledge warm-up failed; will connect on first question", exc_info=True)
        task = asyncio.create_task(run())
        self._warming.add(task)
        task.add_done_callback(self._warming.discard)
        self._track(task)

    def _track(self, task: asyncio.Task[None]) -> None:
        self._retired.add(task)
        def finished(done: asyncio.Task[None]) -> None:
            self._retired.discard(done)
            if not done.cancelled() and done.exception() is not None:
                log.warning("background dialogue operation failed")
        task.add_done_callback(finished)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for warming in tuple(self._warming):
            warming.cancel()
        task = self._task
        self.cancel()
        if task:
            await asyncio.gather(task, return_exceptions=True)
        if self._retired:
            await asyncio.gather(*self._retired, return_exceptions=True)
        await self._knowledge.close()

    # -- internals -----------------------------------------------------
    def _set_state(self, state: LookupState) -> None:
        if state is self.state:
            return
        self.state = state
        log.info("lookup state changed", extra={"response_version": self._generation,
                                                "lookup_state": state.value})
        if self._on_state:
            try:
                self._on_state(state)
            except Exception:  # observers must never break the call
                log.exception("lookup state observer failed")

    def _replace_knowledge(self) -> None:
        old = self._knowledge
        self._knowledge = self._factory()
        self.warm()
        closing = asyncio.create_task(old.close())
        self._track(closing)

    def _speak(self, text: str) -> SpeechHandle:
        self.stop_audio()
        handle = self._say(text, allow_interruptions=True)
        self._handles.append(handle)
        return handle

    async def _wait_for_silence(self) -> None:
        while True:
            await self._quiet.wait()
            version = self._speech_version
            await asyncio.sleep(self._settle_delay)
            if self._quiet.is_set() and version == self._speech_version:
                return

    async def _notice(self, generation: int) -> None:
        await asyncio.sleep(self._notice_delay)
        await self._wait_for_silence()
        if generation == self._generation:
            self._speak(self._phrases.still_working)

    async def _run(self, question: str, generation: int, knowledge: KnowledgeBase) -> None:
        started = time.monotonic()
        self._set_state(LookupState.SEARCHING)
        notice = asyncio.create_task(self._notice(generation))
        try:
            if self._quiet.is_set():
                acks = self._phrases.acknowledgements
                self._speak(acks[self._ack_index % len(acks)])
                self._ack_index += 1
            failed = False
            try:
                answer = await knowledge.ask(question)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("knowledge lookup failed; speaking honest failure", exc_info=True)
                failed = True
                answer = self._phrases.lookup_failed
                if generation == self._generation:
                    self._replace_knowledge()
            log.info("lookup finished", extra={"response_version": generation,
                                                "lookup_ms": round((time.monotonic() - started) * 1000),
                                                "lookup_failed": failed})
            notice.cancel()
            await self._wait_for_silence()
            if generation != self._generation:
                return
            self._set_state(LookupState.FAILED if failed else LookupState.ANSWERING)
            handle = self._speak(answer)
            await handle.wait_for_playout()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("dialogue playback failed")
        finally:
            notice.cancel()
            await asyncio.gather(notice, return_exceptions=True)
            if generation == self._generation:
                self._set_state(LookupState.IDLE)
