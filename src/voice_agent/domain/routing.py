"""Pure validation of a router model's decision (pipeline mode)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

Action = Literal["greeting", "clarify", "darai", "cancel", "status"]
MAX_CLARIFY_CHARS = 180


@dataclass(frozen=True)
class RouteDecision:
    action: Action
    query: str = ""
    reply: str = ""


def parse_decision(raw: str, original: str, clarify_fallback: str) -> RouteDecision:
    """Turn raw model JSON into a safe decision.

    Anything malformed degrades to asking DarAI the original question, which
    is the only path that can produce a factual answer.
    """
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return RouteDecision("darai", original)
    if not isinstance(data, dict):
        return RouteDecision("darai", original)
    action = data.get("action")
    if action in ("cancel", "status"):
        return RouteDecision(action)
    query = data.get("query") if isinstance(data.get("query"), str) else ""
    reply = data.get("reply") if isinstance(data.get("reply"), str) else ""
    if action == "greeting":
        return RouteDecision("greeting")
    if action == "clarify":
        reply = reply.strip()
        if not reply or len(reply) > MAX_CLARIFY_CHARS:
            reply = clarify_fallback
        return RouteDecision("clarify", reply=reply)
    if action == "darai" and query.strip():
        return RouteDecision("darai", query.strip())
    return RouteDecision("darai", original)
