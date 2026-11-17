"""Boundaries the domain depends on; infrastructure provides the adapters."""
from __future__ import annotations

from typing import Callable, Protocol


class KnowledgeBase(Protocol):
    """Answers a customer question. One instance == one isolated conversation."""

    async def ask(self, question: str) -> str: ...

    async def close(self) -> None: ...


class SpeechHandle(Protocol):
    def done(self) -> bool: ...

    def interrupt(self) -> None: ...

    async def wait_for_playout(self) -> None: ...


class Say(Protocol):
    def __call__(self, text: str, *, allow_interruptions: bool = True) -> SpeechHandle: ...


KnowledgeFactory = Callable[[], KnowledgeBase]
