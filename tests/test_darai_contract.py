"""The gateway validates message.send with extra='forbid'; keep the frame exact."""
from voice_agent.config import DaraiSettings
from voice_agent.infrastructure.darai import DaraiClient
import asyncio
import pytest


class FakeWS:
    def __init__(self):
        self.sent = []
    async def send_json(self, data):
        self.sent.append(data)
    async def receive(self):
        import aiohttp, json
        class M:  # noqa: D401
            type = aiohttp.WSMsgType.TEXT
            def json(self_inner):
                return {"type": "message.created", "conversation_id": None,
                        "message": {"role": "assistant", "content": {"text": " ok "}}}
        return M()


async def test_message_send_has_only_gateway_fields():
    client = DaraiClient(DaraiSettings(base_url="https://x.invalid", api_key="k"))
    ws = FakeWS()
    assert await client._exchange(ws, "سؤال", "cid") == "ok"
    frame = ws.sent[0]
    assert set(frame) == {"type", "request_id", "conversation_id", "message"}
    assert frame["message"] == {"type": "text", "text": "سؤال"}


async def test_transient_ticket_error_is_retried_once(monkeypatch):
    from voice_agent.infrastructure import darai as mod
    client = DaraiClient(DaraiSettings(base_url="https://x.invalid", api_key="k"))
    calls = []

    async def connected(cid):
        calls.append(cid)
        if len(calls) == 1:
            raise mod.DaraiConnectionLost("DarAI ticket unavailable (503)")
        return FakeWS()

    async def no_sleep(_):
        return None

    monkeypatch.setattr(client, "_connected", connected)
    monkeypatch.setattr(mod.asyncio, "sleep", no_sleep)
    assert await client.ask("q") == "ok"
    assert len(calls) == 2


async def test_disconnect_after_send_reuses_idempotency_key(monkeypatch):
    from voice_agent.infrastructure import darai as mod
    client = DaraiClient(DaraiSettings(base_url="https://x.invalid", api_key="k"))
    first, second = FakeWS(), FakeWS()
    connections = iter((first, second))

    async def disconnected():
        raise mod.DaraiConnectionLost()

    first.receive = disconnected

    async def connected(correlation_id):
        return next(connections)

    async def no_sleep(delay):
        return None

    monkeypatch.setattr(client, "_connected", connected)
    monkeypatch.setattr(mod.asyncio, "sleep", no_sleep)
    assert await client.ask("question") == "ok"
    assert first.sent[0] == second.sent[0]
    assert first.sent[0]["request_id"]


async def test_closed_client_cannot_reopen():
    from voice_agent.infrastructure.darai import DaraiError
    client = DaraiClient(DaraiSettings(base_url="https://x.invalid", api_key="k"))
    await client.close()
    with pytest.raises(DaraiError, match="closed"):
        await client.warm()
    assert client._http is None


async def test_timeout_covers_connect_and_cleans_up(monkeypatch):
    client = DaraiClient(DaraiSettings(base_url="https://x.invalid", api_key="k", request_timeout=0.01))
    cancelled = asyncio.Event()

    async def slow(correlation_id):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    monkeypatch.setattr(client, "_connected", slow)
    with pytest.raises(TimeoutError):
        await client.ask("question")
    assert cancelled.is_set()


async def test_resume_cursor_sent_and_failed_auth_socket_closed():
    class Socket:
        def __init__(self, ready):
            self.ready = ready
            self.sent = []
            self.closed = False

        async def send_json(self, data):
            self.sent.append(data)

        async def receive_json(self):
            return self.ready

        async def close(self):
            self.closed = True

    class Ticket:
        status = 200

        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def json(self): return {"ticket": "test-ticket"}

    class HTTP:
        def __init__(self, socket): self.socket = socket
        def post(self, *args, **kwargs): return Ticket()
        async def ws_connect(self, *args, **kwargs): return self.socket

    from voice_agent.infrastructure.darai import DaraiError
    accepted = Socket({"type": "session.ready"})
    client = DaraiClient(DaraiSettings(base_url="https://x.invalid", api_key="k"), HTTP(accepted))
    client._cursor = "123-0"
    await client.warm()
    assert accepted.sent == [{"type": "authenticate", "ticket": "test-ticket", "resume_after": "123-0"}]
    await client.close()
    assert accepted.closed

    rejected = Socket({"type": "session.error"})
    client = DaraiClient(DaraiSettings(base_url="https://x.invalid", api_key="k"), HTTP(rejected))
    with pytest.raises(DaraiError):
        await client.warm()
    assert rejected.closed
    assert client._ws is None
    await client.close()
