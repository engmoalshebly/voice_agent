import asyncio
import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import aiohttp


class DaraiClient:
    """One isolated DarAI conversation per voice session."""

    def __init__(self):
        self.base = os.environ['DARAI_BASE_URL'].rstrip('/')
        self.key = os.environ['DARAI_API_KEY']
        self.conversation_id = 'voice-' + uuid.uuid4().hex
        self.lock = asyncio.Lock()
        self.failed = False

    async def ask(self, question: str) -> str:
        async with self.lock:
            if self.failed:
                raise RuntimeError('DarAI conversation ended after an error')
            try:
                return await self._ask(question)
            except Exception:
                self.failed = True
                raise

    async def _ask(self, question: str) -> str:
        parts = urlsplit(self.base)
        if parts.scheme != 'https' or not parts.netloc:
            raise ValueError('DARAI_BASE_URL must be an HTTPS URL')
        ws_url = urlunsplit(('wss', parts.netloc, parts.path.rstrip('/') + '/ws/developer/v2/connect', '', ''))
        timeout = aiohttp.ClientTimeout(total=90)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.post(
                self.base + '/ws/developer/v2/tickets',
                headers={'Authorization': 'Bearer ' + self.key},
                json={'customer_id': self.conversation_id, 'consumer_id': self.conversation_id},
            ) as response:
                response.raise_for_status()
                ticket = (await response.json())['ticket']
            async with http.ws_connect(ws_url, heartbeat=20) as ws:
                await ws.send_json({'type': 'authenticate', 'ticket': ticket})
                ready = await asyncio.wait_for(ws.receive_json(), 15)
                if ready.get('type') != 'session.ready':
                    raise RuntimeError('DarAI session was not accepted')
                await ws.send_json({
                    'type': 'message.send', 'request_id': uuid.uuid4().hex,
                    'conversation_id': self.conversation_id,
                    'message': {'type': 'text', 'text': question},
                })
                async def ping():
                    while True:
                        await asyncio.sleep(25)
                        await ws.send_json({'type': 'ping'})

                ping_task = asyncio.create_task(ping())
                try:
                  async with asyncio.timeout(75):
                    while True:
                        event = await ws.receive_json()
                        if event.get('type') == 'request.error':
                            raise RuntimeError('DarAI rejected the request')
                        if event.get('type') != 'message.created':
                            continue
                        if event.get('conversation_id') not in (None, self.conversation_id):
                            continue
                        message = event.get('message') or {}
                        if message.get('role') not in (None, 'assistant'):
                            continue
                        content = message.get('content') or {}
                        answer = content.get('text') if isinstance(content, dict) else None
                        if not answer:
                            continue
                        if event.get('cursor'):
                            await ws.send_json({'type': 'event.ack', 'cursor': event['cursor']})
                        return answer
                finally:
                    ping_task.cancel()
