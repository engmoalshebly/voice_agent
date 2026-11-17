"""Ordered, lifecycle-bound publication of call state to the room."""
from __future__ import annotations

import asyncio
import logging

from ..domain.dialogue import LookupState

log = logging.getLogger(__name__)


class StatePublisher:
    def __init__(self, participant):
        self._participant = participant
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()
        self._closed = False

    def publish(self, state: LookupState) -> None:
        if self._closed:
            return

        async def push() -> None:
            async with self._lock:
                try:
                    async with asyncio.timeout(2):
                        await self._participant().set_attributes({"darai.lookup": state.value})
                except Exception:
                    log.warning("lookup state publication failed")

        task = asyncio.create_task(push())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def close(self) -> None:
        self._closed = True
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
