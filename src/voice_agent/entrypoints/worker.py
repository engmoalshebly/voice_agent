"""LiveKit agent worker. ``VOICE_MODE=darai`` (DarAI answers; the product mode),
``cascade`` (default), ``live`` or ``pipeline`` (the earlier demo modes).

Usage: ``voice-agent dev`` / ``voice-agent start`` / ``voice-agent console``.
"""
from __future__ import annotations

import asyncio
import logging
import os
from functools import partial

from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, JobProcess, MetricsCollectedEvent, RunContext, StopResponse, function_tool, llm

from ..application.persona import bank_instructions
from ..application.router import TurnRouter
from ..config import ConfigError, darai_settings, environ, gateway_settings, model_settings, turn_settings
from ..domain.dialogue import DialogueFlow
from ..domain.phrases import DEFAULT_PHRASES
from ..domain.speech import spoken_text
from ..infrastructure import providers
from ..infrastructure.darai import DaraiClient
from ..infrastructure.darai_llm import DaraiLLM
from ..infrastructure.darai_turns import DaraiTurnClient
from ..infrastructure.provider_keys import ProviderKeys, with_keys
from ..infrastructure.logs import configure_logging
from ..infrastructure.state import StatePublisher

log = logging.getLogger(__name__)


class _FlowAgent(Agent):
    """Shared wiring: one DialogueFlow per call, closed on exit."""

    def __init__(self, flow_factory, **kwargs):
        super().__init__(**kwargs)
        self.flow: DialogueFlow = flow_factory(say=lambda text, **kw: self.speak(text, **kw))

    def speak(self, text: str, *, allow_interruptions: bool = True):
        return self.session.say(spoken_text(text), allow_interruptions=allow_interruptions)

    async def on_exit(self) -> None:
        await self.flow.close()


class LiveAssistant(_FlowAgent):
    """A conversational LLM with tools; facts only come from DarAI.

    In cascade mode (default) every word, including DarAI's answer, goes through
    one TTS voice and is spoken exactly as written."""

    def __init__(self, flow_factory):
        super().__init__(flow_factory, instructions=bank_instructions())


    @function_tool()
    async def ask_darai(self, context: RunContext, question: str):
        """Start a lookup. For a corrected request include full context; it replaces the old lookup.

        Args:
            question: The complete clarified question for DarAI.
        """
        self.flow.start(question)
        raise StopResponse()

    @function_tool()
    async def cancel_lookup(self):
        """Stop waiting when the user explicitly cancels. Remote processing may continue."""
        self.flow.cancel()
        return "Waiting stopped. Briefly acknowledge; do not claim remote processing was cancelled."

    @function_tool()
    async def lookup_status(self):
        """Check status when the user asks if you are still there. Do not start another lookup."""
        return "Still checking; acknowledge briefly." if self.flow.pending else "No pending lookup."


class PipelineAssistant(_FlowAgent):
    """STT -> router -> DarAI -> TTS, without a conversational LLM."""

    def __init__(self, flow_factory, router: TurnRouter):
        super().__init__(flow_factory, instructions="")
        self.router = router

    async def on_user_turn_completed(self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage) -> None:
        text = (new_message.text_content or "").strip()
        if not text:
            raise StopResponse()
        decision = await self.router.route(text)
        if decision.action == "darai":
            self.flow.start(decision.query)
            self.router.remember(text, f"[lookup] {decision.query}")
        else:
            if decision.action == "cancel":
                self.flow.cancel()
                reply = DEFAULT_PHRASES.cancelled
            elif decision.action == "status":
                reply = (DEFAULT_PHRASES.still_working if self.flow.pending
                         else DEFAULT_PHRASES.no_pending_lookup)
            else:
                reply = DEFAULT_PHRASES.small_talk if decision.action == "greeting" else decision.reply
            self.flow.stop_audio()
            self.speak(reply)
            self.router.remember(text, reply)
        raise StopResponse()


def _prewarm(proc: JobProcess) -> None:
    """Pay import/model cost once per process, not on the caller's first second."""
    from livekit.plugins import google, silero  # noqa: F401
    try:  # plugins must register on the main thread
        from livekit.plugins import elevenlabs  # noqa: F401
    except ImportError:
        pass
    bank_instructions()
    proc.userdata["vad"] = silero.VAD.load()


server = AgentServer(
    setup_fnc=_prewarm,
    num_idle_processes=int(os.getenv("AGENT_IDLE_PROCESSES", "1")),
)
# Empty name = automatic dispatch (dev); a name = explicit dispatch via the token's room config.
AGENT_NAME = (environ().get("LIVEKIT_AGENT_NAME") or "").strip()


#: Set on the visitor's LiveKit token by the token service; never by the browser.
VISITOR_TOKEN_ATTRIBUTE = "darai.visitor_token"


def _log_metrics(session: AgentSession, room_name: str) -> None:
    @session.on("metrics_collected")
    def _metrics(event: MetricsCollectedEvent) -> None:
        m = event.metrics
        if type(m).__name__ == "VADMetrics":  # fires constantly; keep the audio loop light
            return
        fields = {k: round(v, 3) for k in ("ttft", "duration", "ttfb", "end_of_utterance_delay", "transcription_delay")
                  if isinstance(v := getattr(m, k, None), (int, float)) and v >= 0}
        log.info("turn metrics %s %s", type(m).__name__, fields, extra={"room": room_name})


#: One per process: the platform's provider keys, refreshed at most once a minute.
_provider_keys: ProviderKeys | None = None


def _keys_for(gateway) -> ProviderKeys:
    global _provider_keys
    if _provider_keys is None:
        _provider_keys = ProviderKeys(gateway.keys_url, gateway.worker_key)
    return _provider_keys


async def _darai_session(ctx: agents.JobContext, env, models, turns) -> None:
    """DarAI answers. The worker only hears, speaks and keeps the turn-taking natural."""
    gateway = gateway_settings(env)
    # The keys saved in «مفاتيح المزودين», read while the room connects.
    keys = asyncio.create_task(_keys_for(gateway).current())
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    visitor_token = (participant.attributes or {}).get(VISITOR_TOKEN_ATTRIBUTE, "").strip()
    if not visitor_token:
        # Without it there is no conversation to speak in; do not improvise one.
        log.error("visitor joined without a DarAI token; ending the call", extra={"room": ctx.room.name})
        ctx.shutdown(reason="missing visitor token")
        keys.cancel()
        return

    phrases = DEFAULT_PHRASES
    client = DaraiTurnClient(gateway)
    try:
        call = await client.session(visitor_token)
    except Exception:
        keys.cancel()
        await client.close()
        ctx.shutdown(reason="voice session unavailable")
        return
    models = with_keys(models, await keys)       # never raises
    stt, tts = providers.pipeline_speech(
        models, stt_prompt=providers.stt_prompt_for(call.organization, call.stt_hints),
        realtime_stt=gateway.realtime_stt)
    session = AgentSession(
        stt=stt, tts=providers.call_voice(models, tts, voice_id=call.voice_id, provider=call.voice_provider),
        vad=ctx.proc.userdata.get("vad"),
        llm=DaraiLLM(client, visitor_token, phrases, call_id=ctx.room.name,
                     filler_delay=gateway.filler_delay if call.filler_enabled else 0.0),
        turn_handling=providers.turn_handling(turns),
        user_away_timeout=turns.away_timeout,
    )
    measurement_tasks: set[asyncio.Task] = set()
    from ..infrastructure.usage import speech_measurement

    async def send_measurement(payload):
        for attempt in range(3):
            try:
                await client.measurement(visitor_token, payload)
                return
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(0.2 * (attempt + 1))
        log.warning("speech measurement unavailable", extra={"room": ctx.room.name})

    @session.on("metrics_collected")
    def collect_measurement(event: MetricsCollectedEvent):
        payload = speech_measurement(event.metrics)
        if payload:
            task = asyncio.create_task(send_measurement(payload))
            measurement_tasks.add(task)
            task.add_done_callback(measurement_tasks.discard)

    away_said = False

    @session.on("user_state_changed")
    def _user_state(event) -> None:
        nonlocal away_said
        if event.new_state == "away" and not away_said:
            away_said = True
            session.say(phrases.away)
        elif event.new_state == "speaking":
            away_said = False

    # The assistant's own limit, never above the worker's.
    max_call_seconds = min(gateway.max_call_seconds, call.max_call_seconds or gateway.max_call_seconds)

    end_reason = "worker_shutdown"

    @ctx.room.on("participant_disconnected")
    def caller_disconnected(left):
        nonlocal end_reason
        if left.identity == participant.identity and end_reason != 'time_limit':
            end_reason = 'caller_hangup'

    async def _limit() -> None:
        nonlocal end_reason
        await asyncio.sleep(max_call_seconds)
        end_reason = "time_limit"
        log.info("call reached its time limit", extra={"room": ctx.room.name})
        await session.say(phrases.call_limit, allow_interruptions=False)
        ctx.shutdown(reason="call time limit")

    limit = asyncio.create_task(_limit())

    async def _cleanup() -> None:
        limit.cancel()
        await asyncio.gather(limit, return_exceptions=True)
        for attempt in range(3):
            try:
                await client.call_event(visitor_token,"ended",end_reason)
                break
            except Exception:
                log.warning("call end ledger update failed", extra={"room":ctx.room.name})
                if attempt < 2: await asyncio.sleep(0.2 * (attempt + 1))
        if measurement_tasks:
            await asyncio.gather(*tuple(measurement_tasks), return_exceptions=True)
        await client.close()

    _log_metrics(session, ctx.room.name)
    ctx.add_shutdown_callback(_cleanup)
    log.info("voice session starting (darai mode)", extra={"room": ctx.room.name})
    try:
        await client.call_event(visitor_token,"connected")
        await session.start(room=ctx.room, agent=Agent(instructions=""))
    except Exception:
        end_reason = "connection_failed"
        ctx.shutdown(reason="voice call startup failed")
        return
    # The welcome message the tenant wrote for this widget, so the call opens
    # the way the chat does.
    session.say(call.greeting or phrases.neutral_greeting)


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: agents.JobContext) -> None:
    env = environ()
    models = model_settings(env)
    turns = turn_settings(env)
    if models.mode == "darai":
        await _darai_session(ctx, env, models, turns)
        return
    darai = darai_settings(env)
    publisher = StatePublisher(lambda: ctx.room.local_participant)
    flow_factory = partial(DialogueFlow, partial(DaraiClient, darai),
                           notice_delay=turns.notice_delay, settle_delay=turns.settle_delay,
                           on_state=publisher.publish)

    if models.mode == "cascade":
        stt, tts = providers.pipeline_speech(models)
        session = AgentSession(
            stt=stt, llm=providers.chat_llm(models), tts=tts, vad=ctx.proc.userdata.get("vad"),
            turn_handling=providers.turn_handling(turns),
            user_away_timeout=turns.away_timeout,
        )
        assistant: _FlowAgent = LiveAssistant(flow_factory)
    elif models.mode == "live":
        # Native-audio model: its own voice for chat, TTS for DarAI answers (two voices).
        session = AgentSession(llm=providers.realtime_model(models), tts=providers.gemini_tts(models))
        assistant = LiveAssistant(flow_factory)
    else:
        stt, tts = providers.pipeline_speech(models)
        session = AgentSession(stt=stt, tts=tts, vad=ctx.proc.userdata.get("vad"),
                               turn_handling=providers.turn_handling(turns),
                               user_away_timeout=turns.away_timeout)
        assistant = PipelineAssistant(flow_factory, TurnRouter(providers.router_generate(models)))

    @session.on("user_state_changed")
    def _user_state(event) -> None:
        assistant.flow.user_speaking(event.new_state == "speaking")
        if event.new_state == "away":
            assistant.flow.user_away()

    _log_metrics(session, ctx.room.name)

    ctx.add_shutdown_callback(assistant.flow.close)
    ctx.add_shutdown_callback(publisher.close)
    log.info("voice session starting", extra={"room": ctx.room.name})
    assistant.flow.warm()  # DarAI socket opens while the caller hears the greeting
    await session.start(room=ctx.room, agent=assistant)
    assistant.speak(DEFAULT_PHRASES.greeting)


def main() -> None:
    configure_logging()
    env = environ()
    try:  # fail at boot, not on the first caller
        if model_settings(env).mode == "darai":
            gateway_settings(env)
        else:
            darai_settings(env)
        turn_settings(env)
    except ConfigError as exc:
        raise SystemExit(f"configuration error: {exc}") from None
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
