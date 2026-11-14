import asyncio

from voice_agent.domain.dialogue import LookupState
from voice_agent.infrastructure.state import StatePublisher


async def test_state_publications_remain_ordered():
    values = []

    class Participant:
        async def set_attributes(self, attrs):
            if attrs["darai.lookup"] == "searching":
                await asyncio.sleep(0.01)
            values.append(attrs["darai.lookup"])

    publisher = StatePublisher(lambda: Participant())
    for state in (LookupState.SEARCHING, LookupState.ANSWERING, LookupState.IDLE):
        publisher.publish(state)
    await asyncio.gather(*publisher._tasks)
    assert values == ["searching", "answering", "idle"]
    await publisher.close()
    publisher.publish(LookupState.SEARCHING)
    assert not publisher._tasks


async def test_shutdown_cancels_stalled_publication():
    entered = asyncio.Event()

    class Participant:
        async def set_attributes(self, attrs):
            entered.set()
            await asyncio.sleep(10)

    publisher = StatePublisher(lambda: Participant())
    publisher.publish(LookupState.SEARCHING)
    await entered.wait()
    await asyncio.wait_for(publisher.close(), 0.1)
    assert not publisher._tasks
