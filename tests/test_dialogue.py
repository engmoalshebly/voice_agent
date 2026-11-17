import asyncio

import pytest

from voice_agent.domain.dialogue import DialogueFlow, LookupState


class Handle:
    def __init__(self): self.interrupted = False
    def done(self): return self.interrupted
    def interrupt(self): self.interrupted = True
    async def wait_for_playout(self): pass


class Harness:
    def __init__(self):
        self.requests, self.spoken, self.states, self.clients = [], [], [], []
        outer = self

        class Client:
            def __init__(self):
                self.closed = False
                outer.clients.append(self)
            async def ask(self, question):
                fut = asyncio.get_running_loop().create_future()
                outer.requests.append((question, fut))
                return await fut
            async def close(self):
                self.closed = True

        def say(text, **_):
            h = Handle(); self.spoken.append((text, h)); return h

        self.flow = DialogueFlow(Client, say, notice_delay=0.03, settle_delay=0.01, on_state=self.states.append)

    def texts(self):
        return [t for t, _ in self.spoken]


@pytest.fixture
async def h():
    harness = Harness()
    yield harness
    await harness.flow.close()


async def test_duplicate_ignored_and_replacement_isolated(h):
    h.flow.start("old"); await asyncio.sleep(0.005)
    h.flow.start("old  ")
    assert len(h.requests) == 1
    h.flow.start("new"); await asyncio.sleep(0.005)
    assert h.requests[0][1].cancelled()
    assert len(h.clients) == 2 and h.clients[0].closed  # fresh conversation
    h.requests[1][1].set_result("NEW ANSWER")
    await h.flow.task
    assert h.texts()[-1] == "NEW ANSWER"


async def test_user_speech_pauses_answer_not_lookup(h):
    h.flow.start("q"); await asyncio.sleep(0.005)
    h.flow.user_speaking(True)
    assert not h.requests[0][1].cancelled()
    h.requests[0][1].set_result("ANSWER"); await asyncio.sleep(0.05)
    assert "ANSWER" not in h.texts()
    h.flow.user_speaking(False)
    await h.flow.task
    assert h.texts()[-1] == "ANSWER"


async def test_no_acknowledgement_over_the_user(h):
    h.flow.user_speaking(True)
    h.flow.start("q"); await asyncio.sleep(0.005)
    assert h.spoken == []


async def test_notice_then_cancel_stops_everything(h):
    h.flow.start("q"); await asyncio.sleep(0.08)
    assert len(h.spoken) == 2
    h.flow.cancel(); await asyncio.sleep(0.005)
    assert all(handle.interrupted for _, handle in h.spoken)
    assert h.requests[0][1].cancelled()
    assert h.flow.state is LookupState.IDLE


async def test_failure_is_honest_and_recovers(h):
    h.flow.start("q"); await asyncio.sleep(0.005)
    h.requests[0][1].set_exception(RuntimeError("offline"))
    await h.flow.task
    from voice_agent.domain.phrases import DEFAULT_PHRASES
    assert h.texts()[-1] == DEFAULT_PHRASES.lookup_failed
    assert LookupState.FAILED in h.states and h.states[-1] is LookupState.IDLE
    h.flow.start("again"); await asyncio.sleep(0.005)
    assert len(h.clients) == 2 and h.requests[-1][0] == "again"


async def test_states_reported(h):
    h.flow.start("q"); await asyncio.sleep(0.005)
    h.requests[0][1].set_result("A"); await h.flow.task
    assert h.states == [LookupState.SEARCHING, LookupState.ANSWERING, LookupState.IDLE]


async def test_knowledge_is_warmed_and_rewarmed_after_replacement():
    warmed = []

    class Client:
        async def ask(self, q):
            await asyncio.sleep(10)
        async def warm(self):
            warmed.append(self)
        async def close(self):
            pass

    flow = DialogueFlow(Client, lambda t, **k: Handle(), notice_delay=10)
    flow.warm(); await asyncio.sleep(0)
    flow.start("a"); await asyncio.sleep(0)
    flow.start("b"); await asyncio.sleep(0.01)
    assert len(warmed) == 2 and warmed[0] is not warmed[1]
    await flow.close()


async def test_acknowledgements_rotate(h):
    from voice_agent.domain.phrases import DEFAULT_PHRASES
    for q in ("a", "b"):
        h.flow.start(q); await asyncio.sleep(0.005)
        h.requests[-1][1].set_result("ok"); await h.flow.task
    acks = [t for t in h.texts() if t in DEFAULT_PHRASES.acknowledgements]
    assert acks == list(DEFAULT_PHRASES.acknowledgements[:2])


async def test_speech_restarting_during_settle_defers_answer(h):
    h.flow._settle_delay = 0.04
    h.flow.start("q")
    await asyncio.sleep(0.005)
    h.requests[0][1].set_result("ANSWER")
    await asyncio.sleep(0.01)
    h.flow.user_speaking(True)
    await asyncio.sleep(0.06)
    assert "ANSWER" not in h.texts()
    h.flow.user_speaking(False)
    await h.flow.task
    assert h.texts()[-1] == "ANSWER"


async def test_raw_speech_does_not_override_livekit_interruption(h):
    h.flow.start("q")
    await asyncio.sleep(0.005)
    handle = h.spoken[0][1]
    h.flow.user_speaking(True)
    assert not handle.interrupted
    h.flow.cancel()
    assert handle.interrupted


async def test_answering_lasts_until_playout_and_new_question_stops_old_audio(h):
    playback = asyncio.Event()

    class PlayingHandle(Handle):
        async def wait_for_playout(self):
            await playback.wait()

    def say(text, **kwargs):
        handle = PlayingHandle()
        h.spoken.append((text, handle))
        return handle

    h.flow._say = say
    h.flow.start("q")
    await asyncio.sleep(0.005)
    h.requests[0][1].set_result("ANSWER")
    await asyncio.sleep(0.02)
    assert h.flow.state is LookupState.ANSWERING
    answer_handle = h.spoken[-1][1]
    h.flow.start("new question")
    await asyncio.sleep(0.005)
    assert answer_handle.interrupted
    h.requests[-1][1].set_result("NEW")
    playback.set()
    await h.flow.task
    assert h.flow.state is LookupState.IDLE


async def test_close_does_not_create_replacement_client(h):
    h.flow.start("q")
    await asyncio.sleep(0.005)
    await h.flow.close()
    h.flow.start("after close")
    assert len(h.clients) == 1
    assert h.clients[0].closed
    assert not h.flow.pending


async def test_away_reminder_once_and_never_during_lookup(h):
    h.flow.start("q")
    await asyncio.sleep(0.005)
    count = len(h.spoken)
    h.flow.user_away()
    assert len(h.spoken) == count
    h.flow.cancel()
    h.flow.user_away()
    h.flow.user_away()
    assert len(h.spoken) == count + 1


async def test_late_result_from_cancelled_lookup_is_never_spoken():
    started = asyncio.Event()
    release_old = asyncio.Event()
    spoken = []

    class Client:
        async def ask(self, question):
            if question == "old":
                started.set()
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    await release_old.wait()
                return "STALE"
            return "CURRENT"

        async def close(self):
            pass

    def say(text, **kwargs):
        spoken.append(text)
        return Handle()

    flow = DialogueFlow(Client, say, settle_delay=0.001)
    flow.start("old")
    await started.wait()
    flow.start("new")
    release_old.set()
    await flow.task
    await flow.close()
    assert "CURRENT" in spoken
    assert "STALE" not in spoken


async def test_close_cancels_inflight_warmup():
    started = asyncio.Event()
    cancelled = asyncio.Event()
    closed = asyncio.Event()

    class Client:
        async def warm(self):
            started.set()
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()

        async def close(self):
            closed.set()

    flow = DialogueFlow(Client, lambda text, **kwargs: Handle())
    flow.warm()
    await started.wait()
    await asyncio.wait_for(flow.close(), 0.2)
    assert cancelled.is_set() and closed.is_set()
    assert not flow._retired
