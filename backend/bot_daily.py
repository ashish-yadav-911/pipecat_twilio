import datetime
import io
import sys
import wave
from pathlib import Path

import aiofiles
from fastapi import WebSocket
from loguru import logger
from config import settings

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.transports.services.daily import DailyTransport, DailyParams
from pipecat.transports.services.helpers.daily_rest import DailyRoomParams, DailyRoomProperties, DailyRoomSipParams


# Configure logging
logger.remove()
logger.add(sys.stderr, level=settings.log_level)  # Console output
logger.add(
    "logs/bot_{time:YYYY-MM-DD}.log",  # Include date in filename
    level=settings.log_level,
    rotation="00:00",  # Rotate logs daily at midnight
    retention="7 days",  # Keep logs for 7 days
    compression="zip"  # Compress rotated logs
)

# Import SYSTEM_PROMPT from prompt.py
try:
    from prompt import SYSTEM_PROMPT
    logger.info("Successfully imported SYSTEM_PROMPT from prompt.py")
except ImportError as e:
    logger.error(f"Failed to import SYSTEM_PROMPT: {e}")
    SYSTEM_PROMPT = None

async def save_audio(server_name: str, audio: bytes, sample_rate: int, num_channels: int):
    """Save audio data to a WAV file."""
    if len(audio) > 0:
        current_dir = Path(__file__).resolve().parent
        recordings_dir = current_dir.parent / "recordings"
        recordings_dir.mkdir(exist_ok=True)
        
        filename = recordings_dir / f"{server_name}_recording_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        
        with io.BytesIO() as buffer:
            with wave.open(buffer, "wb") as wf:
                wf.setsampwidth(2)
                wf.setnchannels(num_channels)
                wf.setframerate(sample_rate)
                wf.writeframes(audio)
            async with aiofiles.open(str(filename), "wb") as file:
                await file.write(buffer.getvalue())
        logger.info(f"Merged audio saved to {filename}")
    else:
        logger.info("No audio data to save")
llm= OpenAILLMService
stt= DeepgramSTTService
tts= ElevenLabsTTSService

# async def run_bot(
#     websocket_client: WebSocket,
#     stream_sid: str,
#     testing: bool,
#     llm: OpenAILLMService,
#     stt: DeepgramSTTService,
#     tts: ElevenLabsTTSService,
#     vad_analyzer: SileroVADAnalyzer
# ):
#     """Run the chatbot pipeline with WebSocket transport."""
#     transport = FastAPIWebsocketTransport(
#         websocket=websocket_client,
#         params=FastAPIWebsocketParams(
#             audio_in_enabled=True,
#             audio_out_enabled=True,
#             add_wav_header=False,
#             vad_enabled=True,
#             vad_analyzer=vad_analyzer,
#             vad_audio_passthrough=True,
#             serializer=TwilioFrameSerializer(stream_sid),
#             buffer_size=512,
#         ),
#     )


async def run_bot(room_url: str, token: str, call_id: str, sip_uri: str) -> None:
    """Run the voice bot with the given parameters."""
    logger.info(f"Starting bot with room: {room_url}")
    logger.info(f"SIP endpoint: {sip_uri}")

    # IMPORTANT: Track if call has been forwarded to avoid multiple forwards
    call_already_forwarded = False

    # Setup the Daily transport
    transport = DailyTransport(
        room_url,
        token,
        "Phone Bot",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            transcription_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )


    system_prompt = SYSTEM_PROMPT if SYSTEM_PROMPT else (
        "You are a helpful assistant named Mirai. Your output will be converted to audio so "
        "don't include special characters in your answers. Respond with a short sentence. "
        "You are developed by a company called Iffort."
    )

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)
    testing=False
    audiobuffer = AudioBufferProcessor(
        user_continuous_stream=not testing,
        buffer_size=256,
        max_buffer_size=1024  # Limit buffer size
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            audiobuffer,
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            allow_interruptions=True,
            enable_metrics=True,
            disable_buffers=False  # Enable buffering for performance
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        """Handle client connection event."""
        await audiobuffer.start_recording()
        messages.append({"role": "system", "content": "Please introduce yourself to the user."})
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        """Handle client disconnection event."""
        await task.cancel()

    @audiobuffer.event_handler("on_audio_data")
    async def on_audio_data(buffer, audio, sample_rate, num_channels):
        """Handle audio data event and save to file."""
        server_name = f"server_{DailyTransport.client.port}"
        await save_audio(server_name, audio, sample_rate, num_channels)
        # Note: Buffer clearing is assumed to be handled by AudioBufferProcessor's max_buffer_size
        # If buffer size exceeds max_buffer_size, log a warning for debugging
        # TODO: Verify if AudioBufferProcessor enforces max_buffer_size internally
        logger.debug("Audio data received; assuming max_buffer_size is enforced by AudioBufferProcessor")

    runner = PipelineRunner(handle_sigint=False, force_gc=True)
    await runner.run(task)