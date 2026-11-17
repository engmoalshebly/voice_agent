"""darai mode: the visitor's words go to DarAI, DarAI's sentences are spoken."""
import asyncio
import json

import pytest
from aiohttp import web
from livekit.agents import llm

from voice_agent.config import ConfigError, GatewaySettings, gateway_settings, model_settings
from voice_agent.domain.phrases import DEFAULT_PHRASES as P
from voice_agent.infrastructure.darai_llm import DaraiLLM, last_user_message
from voice_agent.infrastructure.darai_turns import DaraiTurnClient, DaraiTurnError, TurnEvent


def _sse(*events):
    return "".join(f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n" for name, data in events)


@pytest.fixture
async def gateway():
    """A local stand-in for the realtime gateway; ``gateway.reply`` decides the answer."""
    state = type("State", (), {"requests": [], "reply": None})()

    async def turn(request: web.Request) -> web.StreamResponse:
        state.requests.append({"headers": dict(request.headers), "body": await request.json()})
        return await state.reply(request)

    app = web.Application()
    app.router.add_post("/ws/voice/turn", turn)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    state.settings = GatewaySettings(url=f"http://127.0.0.1:{port}", worker_key="wk", turn_timeout=5)
    yield state
    await runner.cleanup()


def _text(body, status=200):
    async def reply(request):
        return web.Response(status=status, text=body, content_type="text/event-stream")
    return reply


async def _collect(client, **kw):
    return [event async for event in client.turn("visitor-jwt", "كم الرسوم؟", **kw)]


async def test_client_sends_both_credentials_and_yields_events_until_end(gateway):
    gateway.reply = _text(": waiting\n\n" + _sse(
        ("sentence", {"text": "أهلاً بك."}), ("replace", {"text": "الرسوم ألف ريال."}),
        ("end", {"reason": "answered", "spoke": True}), ("sentence", {"text": "بعد النهاية"})))
    client = DaraiTurnClient(gateway.settings)
    try:
        events = await _collect(client, client_turn_id="call-1:item_9")
    finally:
        await client.close()

    assert events == [TurnEvent("sentence", text="أهلاً بك."), TurnEvent("replace", text="الرسوم ألف ريال."),
                      TurnEvent("end", reason="answered")]
    sent = gateway.requests[0]
    assert sent["headers"]["Authorization"] == "Bearer visitor-jwt"
    assert sent["headers"]["X-Voice-Worker-Key"] == "wk"
    assert sent["body"] == {"text": "كم الرسوم؟", "client_turn_id": "call-1:item_9"}


@pytest.mark.parametrize("status", [401, 404, 410, 502])
async def test_client_raises_a_refusal_with_its_status(gateway, status):
    gateway.reply = _text("{}", status=status)
    client = DaraiTurnClient(gateway.settings)
    try:
        with pytest.raises(DaraiTurnError) as error:
            await _collect(client)
    finally:
        await client.close()
    assert error.value.status == status


async def test_client_treats_a_stream_cut_before_end_as_a_failure(gateway):
    gateway.reply = _text(_sse(("sentence", {"text": "جزء"})))
    client = DaraiTurnClient(gateway.settings)
    got = []
    try:
        with pytest.raises(DaraiTurnError):
            async for event in client.turn("t", "x"):
                got.append(event)
    finally:
        await client.close()
    assert got == [TurnEvent("sentence", text="جزء")]


async def test_client_reports_an_unreachable_gateway():
    client = DaraiTurnClient(GatewaySettings(url="http://127.0.0.1:9", worker_key="wk", connect_timeout=1))
    try:
        with pytest.raises(DaraiTurnError):
            await _collect(client)
    finally:
        await client.close()


# -- DarAI as the session's language model ------------------------------------

class FakeTurns:
    """Yields scripted (delay, event) pairs; records what it was asked."""

    def __init__(self, script, error=None):
        self.script, self.error, self.calls, self.closed_early = script, error, [], False

    async def turn(self, visitor_token, text, client_turn_id=None):
        self.calls.append((visitor_token, text, client_turn_id))
        try:
            for delay, event in self.script:
                await asyncio.sleep(delay)
                yield event
            if self.error:
                raise self.error
        except (GeneratorExit, asyncio.CancelledError):   # closed, or its read was cancelled
            self.closed_early = True
            raise


def _ctx(*messages):
    ctx = llm.ChatContext.empty()
    for role, content in messages:
        ctx.add_message(role=role, content=content)
    return ctx


async def _speak(turns, ctx=None, filler_delay=0.0):
    model = DaraiLLM(turns, "visitor-jwt", P, filler_delay=filler_delay, call_id="room-1")
    stream = model.chat(chat_ctx=ctx or _ctx(("assistant", "أهلاً"), ("user", "كم الرسوم؟")))
    spoken = []
    async with stream:
        async for chunk in stream:
            if chunk.delta and chunk.delta.content:
                spoken.append(chunk.delta.content.strip())
    return spoken


async def test_sentences_become_the_models_output_in_order():
    turns = FakeTurns([(0, TurnEvent("sentence", text="أهلاً بك.")), (0, TurnEvent("sentence", text="الرسوم ألف ريال.")),
                       (0, TurnEvent("end", reason="answered"))])
    ctx = _ctx(("assistant", "أهلاً"), ("user", "سؤال قديم"), ("assistant", "جواب"), ("user", "كم الرسوم؟"))

    assert await _speak(turns, ctx) == ["أهلاً بك.", "الرسوم ألف ريال."]
    token, text, turn_id = turns.calls[0]
    assert (token, text) == ("visitor-jwt", "كم الرسوم؟")   # only what was just said
    assert turn_id.startswith("room-1:item_")               # stable per utterance


async def test_a_slow_reply_gets_one_short_filler_then_the_answer():
    turns = FakeTurns([(0.15, TurnEvent("sentence", text="الرسوم ألف ريال.")), (0.15, TurnEvent("sentence", text="هل أخدمك بشيء آخر؟")),
                       (0, TurnEvent("end", reason="answered"))])

    assert await _speak(turns, filler_delay=0.05) == [P.fillers[0], "الرسوم ألف ريال.", "هل أخدمك بشيء آخر؟"]


async def test_a_fast_reply_gets_no_filler_and_fillers_rotate_between_turns():
    fast = FakeTurns([(0, TurnEvent("sentence", text="أهلاً.")), (0, TurnEvent("end", reason="answered"))])
    assert await _speak(fast, filler_delay=0.2) == ["أهلاً."]

    slow = [(0.1, TurnEvent("sentence", text="تفضل.")), (0, TurnEvent("end", reason="answered"))]
    model = DaraiLLM(FakeTurns(slow), "t", P, filler_delay=0.02)
    first_fillers = []
    for _ in range(2):
        async with model.chat(chat_ctx=_ctx(("user", "س"))) as stream:
            first_fillers.append([c.delta.content.strip() async for c in stream][0])
    assert first_fillers == [P.fillers[0], P.fillers[1]]


async def test_a_replacement_is_introduced_as_a_correction():
    turns = FakeTurns([(0, TurnEvent("sentence", text="تم الحجز.")), (0, TurnEvent("replace", text="لا أستطيع الحجز من هنا.")),
                       (0, TurnEvent("end", reason="answered"))])

    assert await _speak(turns) == ["تم الحجز.", f"{P.correction} لا أستطيع الحجز من هنا."]


@pytest.mark.parametrize("script, error, expected", [
    ([(0, TurnEvent("end", reason="silent"))], None, P.no_reply),
    ([(0, TurnEvent("end", reason="timeout"))], None, P.turn_failed),
    ([], DaraiTurnError("refused", 502), P.turn_failed),
])
async def test_a_turn_without_an_answer_is_never_silence(script, error, expected):
    assert await _speak(FakeTurns(script, error)) == [expected]


async def test_a_failure_after_speech_adds_nothing():
    turns = FakeTurns([(0, TurnEvent("sentence", text="الرسوم"))], error=DaraiTurnError("cut"))
    assert await _speak(turns) == ["الرسوم"]


async def test_nothing_said_means_no_turn_is_sent():
    turns = FakeTurns([])
    assert await _speak(turns, _ctx(("assistant", "أهلاً"))) == []
    assert turns.calls == []


async def test_barge_in_closes_the_turn_without_waiting_for_it():
    turns = FakeTurns([(0, TurnEvent("sentence", text="جملة أولى.")), (5, TurnEvent("sentence", text="لن تُسمع"))])
    stream = DaraiLLM(turns, "t", P).chat(chat_ctx=_ctx(("user", "س")))
    first = await asyncio.wait_for(stream.__anext__(), 1)
    await asyncio.wait_for(stream.aclose(), 1)   # the visitor interrupted

    assert first.delta.content.strip() == "جملة أولى."
    assert turns.closed_early


def test_last_user_message_ignores_everything_after_it():
    assert last_user_message(_ctx(("user", "أ"), ("assistant", "ب")))[0] == "أ"
    assert last_user_message(_ctx(("assistant", "ب"))) == ("", "")


# -- configuration ------------------------------------------------------------

def test_darai_mode_needs_the_gateway_and_only_the_speech_providers_key():
    env = {"VOICE_MODE": "darai", "VOICE_PROVIDER": "openai", "OPENAI_API_KEY": "sk-x"}
    assert model_settings(env).mode == "darai"            # no GOOGLE_API_KEY, no DARAI_API_KEY
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        model_settings({**env, "OPENAI_API_KEY": ""})
    with pytest.raises(ConfigError, match="GOOGLE_API_KEY"):
        model_settings({"VOICE_MODE": "darai", "VOICE_PROVIDER": "gemini"})

    settings = gateway_settings({"DARAI_GATEWAY_URL": "http://gateway:5080/", "VOICE_WORKER_KEY": "k",
                                 "VOICE_FILLER_DELAY": "0"})
    assert (settings.url, settings.worker_key, settings.filler_delay) == ("http://gateway:5080", "k", 0.0)
    for bad in ({"VOICE_WORKER_KEY": "k"}, {"DARAI_GATEWAY_URL": "http://g"},
                {"DARAI_GATEWAY_URL": "ftp://g", "VOICE_WORKER_KEY": "k"},
                {"DARAI_GATEWAY_URL": "http://g", "VOICE_WORKER_KEY": "k", "VOICE_FILLER_DELAY": "-1"}):
        with pytest.raises(ConfigError):
            gateway_settings(bad)


# -- speaking each sentence the moment it is complete -------------------------

async def test_each_line_is_released_as_soon_as_its_line_break_arrives():
    from voice_agent.infrastructure.providers import LineTokenizer

    stream = LineTokenizer().stream()
    released = []

    async def read():
        async for token in stream:
            released.append(token.token)

    reader = asyncio.create_task(read())
    stream.push_text("لحظة من فضلك.\n")           # the filler: short, and nothing follows yet
    await asyncio.sleep(0.01)
    assert released == ["لحظة من فضلك."]           # the stock tokenizer would still be holding it

    stream.push_text("الرسوم ألف ")                 # a sentence arriving in pieces
    await asyncio.sleep(0.01)
    assert released == ["لحظة من فضلك."]
    stream.push_text("ريال.\nهل أخدمك بشيء آخر؟")
    await asyncio.sleep(0.01)
    assert released == ["لحظة من فضلك.", "الرسوم ألف ريال."]

    stream.end_input()                              # the tail without a line break
    await reader
    assert released == ["لحظة من فضلك.", "الرسوم ألف ريال.", "هل أخدمك بشيء آخر؟"]


def test_line_tokenizer_ignores_blank_lines():
    from voice_agent.infrastructure.providers import LineTokenizer, split_lines

    assert LineTokenizer().tokenize("أ\n\n  \nب") == ["أ", "ب"]
    assert split_lines("أ\n") == ["أ", ""] and split_lines("أ") == ["أ"] and split_lines("") == [""]


async def test_the_model_writes_one_sentence_per_line():
    turns = FakeTurns([(0, TurnEvent("sentence", text="أهلاً.")), (0, TurnEvent("end", reason="answered"))])
    async with DaraiLLM(turns, "t", P).chat(chat_ctx=_ctx(("user", "س"))) as stream:
        assert [c.delta.content async for c in stream] == ["أهلاً.\n"]
