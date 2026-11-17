"""Single, validated source of runtime configuration.

Every entrypoint calls ``load_settings()`` once at start-up so a missing or
malformed value fails fast with a clear message instead of mid-call.
"""
from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping
from urllib.parse import urlsplit

from dotenv import load_dotenv

Mode = Literal["darai", "cascade", "live", "pipeline"]
VoiceProvider = Literal["openai", "gemini"]


class ConfigError(ValueError):
    """Raised when the environment cannot produce a usable configuration."""


@dataclass(frozen=True)
class LiveKitSettings:
    url: str
    api_key: str
    api_secret: str
    agent_name: str = ""


@dataclass(frozen=True)
class DaraiSettings:
    base_url: str
    api_key: str
    request_timeout: float = 75.0
    connect_timeout: float = 15.0


@dataclass(frozen=True)
class GatewaySettings:
    """DarAI's realtime gateway, for ``darai`` mode."""
    url: str
    worker_key: str
    connect_timeout: float = 5.0
    turn_timeout: float = 75.0
    #: Seconds of silence before a short "one moment" is spoken; 0 disables it.
    filler_delay: float = 1.2
    #: Longest call, in seconds. The visitor token is valid for an hour.
    max_call_seconds: float = 1800.0
    #: Transcribe while the caller is still speaking (OpenAI realtime).
    realtime_stt: bool = False
    #: Where the platform's provider keys are read when a call starts
    #: (DarAI «مفاتيح المزودين»). Empty: the environment keys only.
    keys_url: str = ""


@dataclass(frozen=True)
class ModelSettings:
    mode: Mode = "cascade"
    voice_provider: VoiceProvider = "openai"
    google_api_key: str = ""
    openai_api_key: str = ""
    router_model: str = "gemini-2.5-flash"
    chat_model: str = "gemini-2.5-flash"
    live_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    #: GA and streamed: first sound in ~0.5 s on a call (the 2.5 preview took ~2.2 s).
    gemini_tts_model: str = "gemini-3.8-flash-tts"
    gemini_voice: str = "Kore"
    openai_stt_model: str = "gpt-4o-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_voice: str = "marin"
    #: Who speaks. "" = the same provider that listens (voice_provider).
    #: "elevenlabs" streams audio while the text is still arriving, and falls
    #: back to that provider's voice if ElevenLabs fails or its quota runs out.
    tts_provider: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "rpGHcNQJvO8dFNNFNj1v"   # «Fahad», white Saudi dialect: closest to Yemeni callers
    elevenlabs_model: str = "eleven_flash_v2_5"


@dataclass(frozen=True)
class WebSettings:
    host: str = "127.0.0.1"
    port: int = 8000
    origin: str = ""
    token_ttl_minutes: int = 10
    tokens_per_minute: int = 6
    trust_proxy: bool = False
    #: DarAI realtime gateway as browsers reach it, and the webchat channel
    #: (widget id) this page's calls belong to. Both empty = legacy demo.
    gateway_public_url: str = ""
    channel_id: str = ""
    static_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parents[3] / "web" / "dist")


@dataclass(frozen=True)
class TurnSettings:
    detector: str = "v1-mini"
    interruption: str = "vad"
    min_delay: float = 0.3
    max_delay: float = 1.8
    settle_delay: float = 0.3
    notice_delay: float = 6.0
    away_timeout: float = 15.0


def turn_settings(env: Mapping[str, str]) -> TurnSettings:
    def number(name: str, default: float) -> float:
        try:
            value = float(_env(env, name, str(default)))
        except ValueError as exc:
            raise ConfigError(f"{name} must be a number") from exc
        if not math.isfinite(value) or value <= 0:
            raise ConfigError(f"{name} must be finite and positive")
        return value

    detector = _env(env, "VOICE_TURN_DETECTOR", "v1-mini")
    interruption = _env(env, "VOICE_INTERRUPTION_MODE", "vad")
    if detector not in ("v1-mini", "vad"):
        raise ConfigError("VOICE_TURN_DETECTOR must be v1-mini or vad")
    if interruption not in ("vad", "adaptive"):
        raise ConfigError("VOICE_INTERRUPTION_MODE must be vad or adaptive")
    if interruption == "adaptive":
        _require(env, "LIVEKIT_INFERENCE_API_KEY")
        _require(env, "LIVEKIT_INFERENCE_API_SECRET")
    settings = TurnSettings(
        detector=detector, interruption=interruption,
        min_delay=number("VOICE_MIN_ENDPOINT_DELAY", 0.3),
        # The ceiling a caller waits when the turn detector is unsure. 2.5 s
        # was measured on live calls as the slowest part of some turns.
        max_delay=number("VOICE_MAX_ENDPOINT_DELAY", 1.8),
        settle_delay=number("VOICE_SETTLE_DELAY", 0.3),
        notice_delay=number("VOICE_NOTICE_DELAY", 6.0),
        away_timeout=number("VOICE_AWAY_TIMEOUT", 15.0),
    )
    if settings.min_delay > settings.max_delay:
        raise ConfigError("VOICE_MIN_ENDPOINT_DELAY must not exceed VOICE_MAX_ENDPOINT_DELAY")
    return settings


def _env(env: Mapping[str, str], name: str, default: str = "") -> str:
    return (env.get(name) or default).strip()


def _require(env: Mapping[str, str], name: str) -> str:
    value = _env(env, name)
    if not value or value == "replace_me":
        raise ConfigError(f"{name} is required")
    return value


def _int(env: Mapping[str, str], name: str, default: int, minimum: int = 1) -> int:
    raw = _env(env, name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return value


def livekit_settings(env: Mapping[str, str]) -> LiveKitSettings:
    url = _require(env, "LIVEKIT_URL")
    parts = urlsplit(url)
    if parts.scheme not in {"ws", "wss"} or not parts.netloc:
        raise ConfigError("LIVEKIT_URL must be a ws:// or wss:// URL")
    return LiveKitSettings(
        url=url,
        api_key=_require(env, "LIVEKIT_API_KEY"),
        api_secret=_require(env, "LIVEKIT_API_SECRET"),
        agent_name=_env(env, "LIVEKIT_AGENT_NAME"),
    )


def darai_settings(env: Mapping[str, str]) -> DaraiSettings:
    base = _require(env, "DARAI_BASE_URL").rstrip("/")
    parts = urlsplit(base)
    if parts.scheme != "https" or not parts.netloc:
        raise ConfigError("DARAI_BASE_URL must be an HTTPS URL")
    return DaraiSettings(base_url=base, api_key=_require(env, "DARAI_API_KEY"))


def gateway_settings(env: Mapping[str, str]) -> GatewaySettings:
    url = _require(env, "DARAI_GATEWAY_URL").rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ConfigError("DARAI_GATEWAY_URL must be an http(s) URL")
    defaults = GatewaySettings(url=url, worker_key="x")

    def number(name: str, default: float, minimum: float) -> float:
        try:
            value = float(_env(env, name, str(default)))
        except ValueError as exc:
            raise ConfigError(f"{name} must be a number") from exc
        if not math.isfinite(value) or value < minimum:
            raise ConfigError(f"{name} must be >= {minimum}")
        return value

    return GatewaySettings(
        url=url,
        worker_key=_require(env, "VOICE_WORKER_KEY"),
        filler_delay=number("VOICE_FILLER_DELAY", defaults.filler_delay, 0.0),
        max_call_seconds=number("VOICE_MAX_CALL_SECONDS", defaults.max_call_seconds, 30.0),
        realtime_stt=_env(env, "VOICE_STT_REALTIME").lower() in ("1", "true", "yes"),
        keys_url=_keys_url(env),
    )


def _keys_url(env: Mapping[str, str]) -> str:
    url = _env(env, "DARAI_KEYS_URL")
    if url:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ConfigError("DARAI_KEYS_URL must be an http(s) URL")
    return url


def model_settings(env: Mapping[str, str]) -> ModelSettings:
    mode = _env(env, "VOICE_MODE", "cascade").lower()
    if mode not in ("darai", "cascade", "live", "pipeline"):
        raise ConfigError("VOICE_MODE must be darai, cascade, live or pipeline")
    provider = _env(env, "VOICE_PROVIDER", "openai").lower()
    if provider not in ("openai", "gemini"):
        raise ConfigError("VOICE_PROVIDER must be openai or gemini")
    google_key = _env(env, "GOOGLE_API_KEY")
    openai_key = _env(env, "OPENAI_API_KEY")
    # In darai mode with DARAI_KEYS_URL the keys come from DarAI on each call;
    # environment keys are then an optional fallback.
    keys_from_darai = mode == "darai" and bool(_env(env, "DARAI_KEYS_URL"))
    # Live mode and the pipeline router both run on Gemini. In darai mode
    # DarAI is the only model; a key is needed only for the chosen speech provider.
    if not google_key and not keys_from_darai and (mode != "darai" or provider == "gemini"):
        raise ConfigError("GOOGLE_API_KEY is required")
    if (mode in ("darai", "cascade", "pipeline") and provider == "openai" and not keys_from_darai
            and openai_key in ("", "replace_me")):
        raise ConfigError("OPENAI_API_KEY is required when VOICE_PROVIDER=openai")
    defaults = ModelSettings()
    tts_provider = _env(env, "VOICE_TTS_PROVIDER").lower()
    if tts_provider not in ("", "openai", "gemini", "elevenlabs"):
        raise ConfigError("VOICE_TTS_PROVIDER must be openai, gemini or elevenlabs")
    if tts_provider == provider:
        tts_provider = ""
    if tts_provider in ("openai", "gemini"):
        raise ConfigError("VOICE_TTS_PROVIDER can only differ from VOICE_PROVIDER as elevenlabs")
    eleven_key = _env(env, "ELEVEN_API_KEY")
    if tts_provider == "elevenlabs" and not keys_from_darai and eleven_key in ("", "replace_me"):
        raise ConfigError("ELEVEN_API_KEY is required when VOICE_TTS_PROVIDER=elevenlabs")
    return ModelSettings(
        tts_provider=tts_provider,
        elevenlabs_api_key=eleven_key,
        elevenlabs_voice_id=_env(env, "ELEVENLABS_VOICE_ID", defaults.elevenlabs_voice_id),
        elevenlabs_model=_env(env, "ELEVENLABS_MODEL", defaults.elevenlabs_model),
        mode=mode,  # type: ignore[arg-type]
        voice_provider=provider,  # type: ignore[arg-type]
        google_api_key=google_key,
        openai_api_key=openai_key,
        router_model=_env(env, "ROUTER_MODEL", defaults.router_model),
        chat_model=_env(env, "CHAT_MODEL", defaults.chat_model),
        live_model=_env(env, "LIVE_MODEL", defaults.live_model),
        gemini_tts_model=_env(env, "GEMINI_TTS_MODEL", defaults.gemini_tts_model),
        gemini_voice=_env(env, "GEMINI_VOICE", defaults.gemini_voice),
        openai_stt_model=_env(env, "OPENAI_STT_MODEL", defaults.openai_stt_model),
        openai_tts_model=_env(env, "OPENAI_TTS_MODEL", defaults.openai_tts_model),
        openai_voice=_env(env, "OPENAI_VOICE", defaults.openai_voice),
    )


def _public_url(env: Mapping[str, str], name: str) -> str:
    value = _env(env, name).rstrip("/")
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc:
        raise ConfigError(f"{name} must be an HTTPS URL")
    return value


def web_settings(env: Mapping[str, str]) -> WebSettings:
    defaults = WebSettings()
    static = _env(env, "WEB_STATIC_DIR")
    return WebSettings(
        host=_env(env, "WEB_HOST", defaults.host),
        port=_int(env, "WEB_PORT", defaults.port),
        origin=_env(env, "WEB_ORIGIN").rstrip("/"),
        token_ttl_minutes=_int(env, "TOKEN_TTL_MINUTES", defaults.token_ttl_minutes),
        tokens_per_minute=_int(env, "TOKENS_PER_MINUTE", defaults.tokens_per_minute),
        trust_proxy=_env(env, "TRUST_PROXY").lower() in ("1", "true", "yes"),
        gateway_public_url=_public_url(env, "VOICE_GATEWAY_PUBLIC_URL"),
        channel_id=_env(env, "VOICE_CHANNEL_ID"),
        static_dir=Path(static) if static else defaults.static_dir,
    )


def load_env_file() -> None:
    """Load ``.env.local`` from the project root without overriding real env."""
    load_dotenv(Path(__file__).resolve().parents[3] / ".env.local", override=False)


def environ() -> Mapping[str, str]:
    load_env_file()
    return os.environ
