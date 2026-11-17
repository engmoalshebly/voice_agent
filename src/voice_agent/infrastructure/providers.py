"""Builds speech / model plugins from settings. The only place model names live."""
from __future__ import annotations

from google import genai
from google.genai import types
from livekit.plugins import google, openai
from livekit.agents import TurnHandlingOptions, inference

from ..application.persona import VOICE_STYLE, bank_instructions
from ..config import ModelSettings, TurnSettings


def turn_handling(settings: TurnSettings) -> TurnHandlingOptions:
    return TurnHandlingOptions(
        turn_detection=(inference.TurnDetector(version="v1-mini")
                        if settings.detector == "v1-mini" else "vad"),
        endpointing={"mode": "dynamic", "min_delay": settings.min_delay,
                    "max_delay": settings.max_delay},
        interruption={"enabled": True, "mode": settings.interruption,
                      "min_duration": 0.5, "false_interruption_timeout": 2.0,
                      "resume_false_interruption": True},
        preemptive_generation={"enabled": False, "preemptive_tts": False},
    )


def gemini_tts(m: ModelSettings):
    return google.beta.GeminiTTS(model=m.gemini_tts_model, voice_name=m.gemini_voice,
                                 instructions=VOICE_STYLE, api_key=m.google_api_key)


# Domain context sharply improves recognition of names, terms and dialect.
STT_PROMPT = (
    "مكالمة خدمة عملاء صوتية مع كاك بنك (بنك التسليف التعاوني والزراعي) في اليمن، "
    "بلهجة يمنية أو عربية فصحى. مصطلحات شائعة: حساب جاري، حساب توفير، بطاقة صراف، "
    "تحويل، حوالة، فرع، رسوم، قرض، تمويل، كاك موبايل، تطبيق، رقم الحساب. "
    "اكتب كلام المتصل كما قاله بالعربية دون ترجمة أو تلخيص."
)


#: For darai mode, where the worker serves any tenant and knows no domain terms.
NEUTRAL_STT_PROMPT = (
    "مكالمة خدمة عملاء صوتية بالعربية، بلهجة محلية أو فصحى. "
    "اكتب كلام المتصل كما قاله بالعربية دون ترجمة أو تلخيص."
)


def pipeline_speech(m: ModelSettings, stt_prompt: str = STT_PROMPT):
    if m.voice_provider == "openai":
        return (openai.STT(model=m.openai_stt_model, language="ar", prompt=stt_prompt,
                           temperature=0, api_key=m.openai_api_key),
                openai.TTS(model=m.openai_tts_model, voice=m.openai_voice, instructions=VOICE_STYLE,
                           api_key=m.openai_api_key))
    return google.beta.GeminiSTT(language="ar", api_key=m.google_api_key), gemini_tts(m)


def chat_llm(m: ModelSettings):
    return google.LLM(model=m.chat_model, api_key=m.google_api_key, temperature=0.3)


def realtime_model(m: ModelSettings):
    return google.realtime.RealtimeModel(model=m.live_model, voice=m.gemini_voice,
                                         api_key=m.google_api_key,
                                         tool_behavior=types.Behavior.NON_BLOCKING)


def router_generate(m: ModelSettings):
    client = genai.Client(api_key=m.google_api_key)
    config = types.GenerateContentConfig(system_instruction=bank_instructions(),
                                         response_mime_type="application/json", temperature=0)

    async def generate(prompt: str) -> str:
        response = await client.aio.models.generate_content(model=m.router_model, contents=prompt, config=config)
        return response.text or ""

    return generate
