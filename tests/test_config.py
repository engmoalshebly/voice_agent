import pytest

from voice_agent.config import ConfigError, darai_settings, livekit_settings, model_settings, turn_settings

BASE = {"GOOGLE_API_KEY": "g"}


def test_default_cascade_needs_openai_key_but_live_does_not():
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        model_settings(BASE)
    assert model_settings({**BASE, "OPENAI_API_KEY": "o"}).mode == "cascade"
    assert model_settings({**BASE, "VOICE_MODE": "live"}).mode == "live"
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        model_settings({**BASE, "VOICE_MODE": "pipeline"})
    assert model_settings({**BASE, "VOICE_MODE": "pipeline", "VOICE_PROVIDER": "gemini"}).voice_provider == "gemini"


def test_placeholders_and_schemes_rejected():
    with pytest.raises(ConfigError):
        darai_settings({"DARAI_BASE_URL": "https://x", "DARAI_API_KEY": "replace_me"})
    with pytest.raises(ConfigError, match="HTTPS"):
        darai_settings({"DARAI_BASE_URL": "http://x", "DARAI_API_KEY": "k"})
    with pytest.raises(ConfigError, match="ws://"):
        livekit_settings({"LIVEKIT_URL": "http://x", "LIVEKIT_API_KEY": "k", "LIVEKIT_API_SECRET": "s"})


@pytest.mark.parametrize("env", [
    {"VOICE_MIN_ENDPOINT_DELAY": "nan"},
    {"VOICE_MAX_ENDPOINT_DELAY": "inf"},
    {"VOICE_SETTLE_DELAY": "-1"},
    {"VOICE_AWAY_TIMEOUT": "no"},
    {"VOICE_MIN_ENDPOINT_DELAY": "4", "VOICE_MAX_ENDPOINT_DELAY": "2"},
    {"VOICE_TURN_DETECTOR": "unknown"},
    {"VOICE_INTERRUPTION_MODE": "adaptive"},
])
def test_invalid_turn_configuration_rejected(env):
    with pytest.raises(ConfigError):
        turn_settings(env)


def test_turn_configuration_defaults_and_explicit_cloud_credentials():
    settings = turn_settings({})
    assert settings.detector == "v1-mini" and settings.interruption == "vad"
    assert turn_settings({"VOICE_INTERRUPTION_MODE": "adaptive",
                          "LIVEKIT_INFERENCE_API_KEY": "cloud-key",
                          "LIVEKIT_INFERENCE_API_SECRET": "cloud-secret"}).interruption == "adaptive"
