import asyncio
import unittest
from dialogue_flow import DialogueFlow


class Handle:
    def __init__(self): self.interrupted = False
    def done(self): return self.interrupted
    def interrupt(self): self.interrupted = True


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.spoken = []
        outer = self
        class Client:
            async def ask(self, question):
                future = asyncio.get_running_loop().create_future()
                outer.requests.append((question, future))
                return await future
        def say(text, **kwargs):
            handle = Handle()
            self.spoken.append((text, handle))
            return handle
        self.flow = DialogueFlow(Client, say, notice_delay=0.03)

    async def asyncTearDown(self):
        await self.flow.close()

    async def test_replacement_and_duplicate(self):
        self.flow.start('old')
        await asyncio.sleep(0.01)
        self.flow.start('old')
        self.assertEqual(len(self.requests), 1)
        self.flow.start('new')
        await asyncio.sleep(0.01)
        self.assertTrue(self.requests[0][1].cancelled())
        self.requests[1][1].set_result('NEW ANSWER')
        await self.flow.task
        self.assertEqual(self.spoken[-1][0], 'NEW ANSWER')

    async def test_user_speaking_preserves_lookup(self):
        self.flow.start('question')
        await asyncio.sleep(0.01)
        self.flow.user_speaking(True)
        self.assertFalse(self.requests[0][1].cancelled())
        self.requests[0][1].set_result('ANSWER')
        await asyncio.sleep(0.05)
        self.assertNotIn('ANSWER', [text for text, _ in self.spoken])
        self.flow.user_speaking(False)
        await self.flow.task
        self.assertEqual(self.spoken[-1][0], 'ANSWER')

    async def test_cancel_and_notice(self):
        self.flow.start('question')
        await asyncio.sleep(0.08)
        self.assertEqual(len(self.spoken), 2)
        self.flow.cancel()
        await asyncio.sleep(0.01)
        self.assertTrue(all(handle.interrupted for _, handle in self.spoken))
        self.assertTrue(self.requests[0][1].cancelled())

    async def test_failure_does_not_invent_answer(self):
        self.flow.start('question')
        await asyncio.sleep(0.01)
        self.requests[0][1].set_exception(RuntimeError('offline'))
        await self.flow.task
        self.assertIn('تعذر', self.spoken[-1][0])


if __name__ == '__main__':
    unittest.main()
