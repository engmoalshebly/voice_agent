"""The platform's provider keys, read from DarAI when a call starts.

A key the platform admin saves once in «مفاتيح المزودين» reaches the next call
without restarting the worker. The worker's own environment keys are only the
fallback for when DarAI cannot be asked (or holds no key for a provider).

    GET {DARAI_KEYS_URL}
      X-Voice-Worker-Key: <the worker key>
      -> {"keys": {"openai": "...", "gemini": "...", "elevenlabs": "..."}}

Keys are held in this process's memory only, for ``ttl`` seconds, and never
logged.
"""
from __future__ import annotations

import dataclasses
import logging
import time
from typing import Mapping, Optional

import aiohttp

from ..config import ModelSettings

log = logging.getLogger(__name__)

#: DarAI provider name -> ModelSettings field.
FIELDS = {"openai": "openai_api_key", "gemini": "google_api_key", "elevenlabs": "elevenlabs_api_key"}


class ProviderKeys:
    def __init__(self, url: str, worker_key: str, *, ttl: float = 60.0, timeout: float = 2.0,
                 session_factory=aiohttp.ClientSession) -> None:
        self._url = url
        self._worker_key = worker_key
        self._ttl = ttl
        self._timeout = timeout
        self._session_factory = session_factory
        self._keys: dict[str, str] = {}
        self._fetched_at: Optional[float] = None

    async def current(self) -> dict[str, str]:
        """The latest keys; the last good ones (or none) when DarAI cannot answer."""
        if not self._url:
            return {}
        if self._fetched_at is not None and time.monotonic() - self._fetched_at < self._ttl:
            return dict(self._keys)
        try:
            async with self._session_factory() as http:
                async with http.get(self._url, headers={"X-Voice-Worker-Key": self._worker_key},
                                    timeout=aiohttp.ClientTimeout(total=self._timeout)) as response:
                    if response.status != 200:
                        log.warning("provider keys unavailable (%s)", response.status)
                        return dict(self._keys)
                    data = await response.json()
        except Exception as exc:
            log.warning("provider keys unavailable (%s)", type(exc).__name__)
            return dict(self._keys)
        raw = data.get("keys") if isinstance(data, dict) else None
        self._keys = {name: str(value).strip() for name, value in (raw or {}).items()
                      if name in FIELDS and isinstance(value, str) and value.strip()}
        self._fetched_at = time.monotonic()
        return dict(self._keys)


def with_keys(models: ModelSettings, keys: Mapping[str, str]) -> ModelSettings:
    """``models`` with DarAI's keys in place of the environment's, where DarAI has one."""
    changes = {FIELDS[name]: value for name, value in keys.items() if name in FIELDS and value}
    return dataclasses.replace(models, **changes) if changes else models
