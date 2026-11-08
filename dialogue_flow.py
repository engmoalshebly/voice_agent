"""Own the lifetime of lookups and scripted speech, independently of model turns."""
import asyncio
import logging
import time

log = logging.getLogger(__name__)


class DialogueFlow:
    def __init__(self, client_factory, say, notice_delay=12):
        self.client_factory = client_factory
        self.client = client_factory()
        self.say = say
        self.notice_delay = notice_delay
        self.task = None
        self.question = None
        self.generation = 0
        self.handles = []
        self.quiet = asyncio.Event()
        self.quiet.set()

    @property
    def pending(self):
        return self.task is not None and not self.task.done()

    def user_speaking(self, speaking):
        if speaking:
            self.quiet.clear()
            self.stop_audio()
        else:
            self.quiet.set()

    def stop_audio(self):
        for handle in self.handles:
            if not handle.done():
                handle.interrupt()
        self.handles.clear()

    def cancel(self):
        self.generation += 1
        if self.pending:
            self.task.cancel()
            # Remote processing may continue. Isolate subsequent requests.
            self.client = self.client_factory()
        self.question = None
        self.stop_audio()

    def start(self, question):
        question = question.strip()
        if self.pending and question == self.question:
            return
        self.cancel()
        self.question = question
        generation = self.generation
        client = self.client
        self.task = asyncio.create_task(self._run(question, generation, client))

    def speak(self, text):
        self.stop_audio()
        self.handles.append(self.say(text, allow_interruptions=True))

    async def _notice(self, generation):
        await asyncio.sleep(self.notice_delay)
        await self.quiet.wait()
        if generation == self.generation:
            self.speak('الرد أخذ وقتاً أطول قليلاً، شكراً لصبرك.')

    async def _run(self, question, generation, client):
        started = time.monotonic()
        notice = asyncio.create_task(self._notice(generation))
        try:
            self.speak('أكيد، أتحقق لك من التفاصيل.')
            try:
                answer = await client.ask(question)
            except Exception:
                log.warning('DarAI request failed; no generated fallback answer')
                if generation == self.generation:
                    self.client = self.client_factory()
                answer = 'عذراً، تعذر الحصول على الرد. يمكننا المحاولة مرة أخرى.'
            notice.cancel()
            await asyncio.gather(notice, return_exceptions=True)
            log.info('DarAI lookup completed in %.2fs', time.monotonic() - started)
            await self.quiet.wait()
            # Give a correction/cancellation tool time to run after speech ends.
            await asyncio.sleep(0.6)
            if generation == self.generation:
                self.speak(answer)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Dialogue playback failed')
        finally:
            notice.cancel()
            await asyncio.gather(notice, return_exceptions=True)

    async def close(self):
        task = self.task
        self.cancel()
        if task:
            await asyncio.gather(task, return_exceptions=True)
