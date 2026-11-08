"""Experimental Gemini Live conversation with DarAI lookup and scripted TTS."""
import asyncio
import logging

from dotenv import load_dotenv
from google.genai import types
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, RunContext, StopResponse, function_tool
from livekit.plugins import google

from darai import DaraiClient
from dialogue_flow import DialogueFlow
from persona import bank_instructions, GREETING, VOICE_STYLE

load_dotenv('.env.local')
logger = logging.getLogger(__name__)


class LiveAssistant(Agent):
    def __init__(self):
        super().__init__(instructions=bank_instructions())
        self.flow = DialogueFlow(DaraiClient, lambda text, **kw: self.session.say(text, **kw))

    async def on_exit(self):
        await self.flow.close()

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
        return 'Waiting stopped. Briefly acknowledge; do not claim remote processing was cancelled.'

    @function_tool()
    async def lookup_status(self):
        """Check status when the user asks if you are still there. Do not start another lookup."""
        return 'Still checking; acknowledge briefly.' if self.flow.pending else 'No pending lookup.'


server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: agents.JobContext):
    session = AgentSession(
        llm=google.realtime.RealtimeModel(
            model='gemini-2.5-flash-native-audio-preview-12-2025', voice='Kore',
            tool_behavior=types.Behavior.NON_BLOCKING,
        ),
        tts=google.beta.GeminiTTS(model='gemini-2.5-flash-preview-tts', voice_name='Kore', instructions=VOICE_STYLE),
    )
    assistant = LiveAssistant()
    @session.on('user_state_changed')
    def user_state(event):
        assistant.flow.user_speaking(event.new_state == 'speaking')
    ctx.add_shutdown_callback(assistant.flow.close)
    await session.start(room=ctx.room, agent=assistant)
    session.say('مرحباً، كيف يمكنني مساعدتك؟', allow_interruptions=True)


if __name__ == '__main__':
    agents.cli.run_app(server)
