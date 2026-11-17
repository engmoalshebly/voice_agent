import asyncio

import pytest

from voice_agent.config import ConfigError, gateway_settings, model_settings
from voice_agent.infrastructure.provider_keys import ProviderKeys, with_keys


class _Response:
    def __init__(self, status, body):
        self.status, self._body = status, body

    async def json(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    """Stands in for aiohttp.ClientSession; records requests, answers from a script."""

    def __init__(self, script, seen):
        self._script, self._seen = script, seen

    def get(self, url, headers=None, timeout=None):
        self._seen.append((url, dict(headers or {})))
        answer = self._script.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return _Response(*answer)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _keys(script, ttl=60.0):
    seen = []
    return ProviderKeys("http://db/keys", "worker-secret", ttl=ttl,
                        session_factory=lambda: _Session(script, seen)), seen


def test_darai_keys_replace_environment_keys_and_unknown_names_are_ignored():
    models = model_settings({"GOOGLE_API_KEY": "env-g", "OPENAI_API_KEY": "env-o"})
    keys, seen = _keys([(200, {"keys": {"openai": "central-o", "elevenlabs": "central-e", "other": "x"}})])
    current = asyncio.run(keys.current())
    assert current == {"openai": "central-o", "elevenlabs": "central-e"}
    applied = with_keys(models, current)
    assert applied.openai_api_key == "central-o"
    assert applied.elevenlabs_api_key == "central-e"
    assert applied.google_api_key == "env-g"          # DarAI had none: the environment's stays
    assert seen == [("http://db/keys", {"X-Voice-Worker-Key": "worker-secret"})]


def test_keys_are_cached_and_the_last_good_ones_survive_an_outage():
    keys, seen = _keys([(200, {"keys": {"gemini": "g1"}}), (503, {}), OSError("down")], ttl=0.0)
    assert asyncio.run(keys.current()) == {"gemini": "g1"}
    assert asyncio.run(keys.current()) == {"gemini": "g1"}   # 503: keep the last good keys
    assert asyncio.run(keys.current()) == {"gemini": "g1"}   # unreachable: same
    assert len(seen) == 3

    cached, seen = _keys([(200, {"keys": {"gemini": "g1"}})])
    asyncio.run(cached.current())
    asyncio.run(cached.current())
    assert len(seen) == 1                                     # within the ttl: no second request


def test_no_url_means_environment_keys_only():
    keys = ProviderKeys("", "k", session_factory=lambda: pytest.fail("must not call"))
    assert asyncio.run(keys.current()) == {}


def test_darai_mode_with_a_keys_url_starts_without_environment_keys():
    env = {"VOICE_MODE": "darai", "DARAI_KEYS_URL": "http://darai_database_management:5522/api/v1/internal/voice-provider-keys",
           "VOICE_TTS_PROVIDER": "elevenlabs"}
    assert model_settings(env).mode == "darai"
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        model_settings({"VOICE_MODE": "darai"})
    settings = gateway_settings({"DARAI_GATEWAY_URL": "http://gw:5080", "VOICE_WORKER_KEY": "w", **env})
    assert settings.keys_url.endswith("/voice-provider-keys")
    with pytest.raises(ConfigError, match="DARAI_KEYS_URL"):
        gateway_settings({"DARAI_GATEWAY_URL": "http://gw:5080", "VOICE_WORKER_KEY": "w", "DARAI_KEYS_URL": "ftp://x"})
