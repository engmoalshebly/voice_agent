"""Public numeric measurements only; never transcripts, keys or provider payloads."""
import hashlib
import math

def speech_measurement(metrics):
    kind = type(metrics).__name__
    if kind not in {'STTMetrics', 'TTSMetrics'}:
        return None
    request_id = getattr(metrics, 'request_id', '')
    if not request_id:
        return None  # No stable receipt identity: do not invent a billable event.
    capability = 'stt' if kind == 'STTMetrics' else 'tts'
    metadata = getattr(metrics, 'metadata', None)
    model = getattr(metadata, 'model_name', None)
    raw_provider = str(getattr(metadata, 'model_provider', '') or '').lower()
    providers = {'api.openai.com': 'openai', 'openai': 'openai', 'elevenlabs': 'elevenlabs',
        'api.elevenlabs.io': 'elevenlabs', 'google': 'gemini', 'gemini': 'gemini',
        'generativelanguage.googleapis.com': 'gemini'}
    provider = providers.get(raw_provider)
    # Fallback adapters may serve another vendor. Configured preferences are
    # not evidence of which request actually ran; omit an unidentifiable receipt.
    if not provider or not isinstance(model, str) or not model:
        return None
    measurements = {}
    duration = getattr(metrics, 'audio_duration', None)
    if isinstance(duration, (int, float)) and not isinstance(duration, bool) and math.isfinite(duration) and 0 <= duration <= 3600:
        measurements['audio_seconds'] = str(duration)
    characters = getattr(metrics, 'characters_count', None)
    if capability == 'tts' and isinstance(characters, int) and 0 <= characters <= 100000:
        measurements['characters'] = characters
    if not measurements:
        return None
    identity = f'{provider}:{model}:{capability}:{request_id}'
    return {'event_id': hashlib.sha256(identity.encode()).hexdigest(), 'provider': provider,
        'model': model, 'capability': capability, 'measurements': measurements}
