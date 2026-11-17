import pytest

from voice_agent.application.router import TurnRouter
from voice_agent.domain.routing import parse_decision

FB = "fallback?"


@pytest.mark.parametrize("raw,expected", [
    ('{"action":"greeting"}', ("greeting", "", "")),
    ('{"action":"cancel","query":"ignore"}', ("cancel", "", "")),
    ('{"action":"status"}', ("status", "", "")),
    ('{"action":"darai","query":" fees "}', ("darai", "fees", "")),
    ('{"action":"darai","query":""}', ("darai", "orig", "")),
    ('{"action":"clarify","reply":"which card?"}', ("clarify", "", "which card?")),
    ('{"action":"clarify","reply":""}', ("clarify", "", FB)),
    ('{"action":"clarify","reply":"' + "x" * 181 + '"}', ("clarify", "", FB)),
    ('{"action":"hack"}', ("darai", "orig", "")),
    ("not json", ("darai", "orig", "")),
    ("[1]", ("darai", "orig", "")),
])
def test_parse_decision(raw, expected):
    d = parse_decision(raw, "orig", FB)
    assert (d.action, d.query, d.reply) == expected


async def test_router_failure_falls_back_and_history_is_bounded():
    prompts = []

    async def broken(prompt):
        prompts.append(prompt)
        raise RuntimeError("down")

    router = TurnRouter(broken, history_turns=2)
    for i in range(5):
        router.remember(f"u{i}", f"a{i}")
    d = await router.route("hello")
    assert (d.action, d.query) == ("darai", "hello")
    assert "u2" not in prompts[0] and "u4" in prompts[0]
