from types import SimpleNamespace
from voice_agent.infrastructure.usage import speech_measurement

def metric(provider='api.openai.com', model='gpt-4o-mini-tts', **values):
    cls = type('TTSMetrics', (), {})
    result = cls()
    result.request_id = 'request-1'
    result.metadata = SimpleNamespace(model_name=model, model_provider=provider)
    result.audio_duration = 2.0
    result.characters_count = 20
    for key, value in values.items(): setattr(result, key, value)
    return result

def test_vendor_identity_comes_from_actual_metrics_after_fallback():
    event = speech_measurement(metric('elevenlabs', 'eleven_flash_v2_5'))
    assert event['provider']=='elevenlabs' and event['model']=='eleven_flash_v2_5'
    assert event['event_id']==speech_measurement(metric('elevenlabs', 'eleven_flash_v2_5'))['event_id']
    assert event['event_id']!=speech_measurement(metric())['event_id']

def test_unknown_vendor_and_missing_request_are_not_billable_receipts():
    assert speech_measurement(metric('unknown')) is None
    assert speech_measurement(metric(request_id='')) is None
    event = speech_measurement(metric(audio_duration=float('nan')))
    assert event['measurements']=={'characters':20}
