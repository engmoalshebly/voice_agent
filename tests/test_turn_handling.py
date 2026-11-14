from livekit.agents import AgentSession

from voice_agent.config import TurnSettings
from voice_agent.infrastructure.providers import turn_handling


def test_session_accepts_dynamic_endpointing_and_non_speculative_tools():
    options = turn_handling(TurnSettings(detector="vad"))
    assert options["endpointing"]["mode"] == "dynamic"
    assert options["interruption"]["resume_false_interruption"]
    assert options["preemptive_generation"] == {"enabled": False, "preemptive_tts": False}
    session = AgentSession(turn_handling=options)
    assert session is not None


def test_local_turn_detector_is_explicit():
    options = turn_handling(TurnSettings())
    assert options["turn_detection"].__class__.__name__ == "TurnDetector"
    assert options["interruption"]["mode"] == "vad"
