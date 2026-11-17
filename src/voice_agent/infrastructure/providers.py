"""Builds speech / model plugins from settings. The only place model names live."""
from __future__ import annotations

from google import genai
from google.genai import types
from livekit.plugins import google, openai
from livekit.agents import TurnHandlingOptions, inference, tokenize, tts as agents_tts
from livekit.agents.tokenize import token_stream

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


def split_lines(text: str) -> list[str]:
    """Complete lines, then whatever follows the last line break (maybe "")."""
    *lines, rest = text.split("\n")
    return [line for line in lines if line.strip()] + [rest]


class LineTokenizer(tokenize.SentenceTokenizer):
    """One line is one thing to say, released the moment its line break arrives.

    The stock sentence tokenizer holds a sentence back until the next one
    starts, to be sure it has ended. DarAI already sends whole sentences, so
    in darai mode each is written as a line and spoken at once: a short "one
    moment" is heard while the answer is still being written.
    """

    def tokenize(self, text: str, *, language: str | None = None) -> list[str]:
        return [line for line in text.split("\n") if line.strip()]

    def stream(self, *, language: str | None = None) -> tokenize.SentenceStream:
        return token_stream.BufferedSentenceStream(tokenizer=split_lines, min_token_len=1, min_ctx_len=1)


def spoken_by_line(tts):
    """Make ``tts`` speak each line as soon as it is complete.

    A streaming TTS already speaks while text arrives and is returned as is;
    a non-streaming one is wrapped so it synthesizes line by line.
    """
    if tts.capabilities.streaming:
        return tts
    return agents_tts.StreamAdapter(tts=tts, sentence_tokenizer=LineTokenizer())


def elevenlabs_tts(m: ModelSettings):
    from livekit.plugins import elevenlabs  # imported on use: optional provider

    return elevenlabs.TTS(voice_id=m.elevenlabs_voice_id, model=m.elevenlabs_model,
                          api_key=m.elevenlabs_api_key, language="ar", auto_mode=True)


def call_voice(m: ModelSettings, base_tts):
    """The voice of a call: ElevenLabs when chosen, with ``base_tts`` behind it
    so an outage or an exhausted quota changes the voice instead of ending the call."""
    if m.tts_provider != "elevenlabs":
        return spoken_by_line(base_tts)
    return agents_tts.FallbackAdapter([elevenlabs_tts(m), spoken_by_line(base_tts)],
                                      max_retry_per_tts=0)


def pipeline_speech(m: ModelSettings, stt_prompt: str = STT_PROMPT, *, realtime_stt: bool = False):
    if m.voice_provider == "openai":
        return (openai.STT(model=m.openai_stt_model, language="ar", prompt=stt_prompt,
                           api_key=m.openai_api_key,
                           # Realtime transcription streams while the caller speaks,
                           # so the turn ends sooner; it takes no temperature.
                           **({"use_realtime": True} if realtime_stt else {"temperature": 0})),
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
