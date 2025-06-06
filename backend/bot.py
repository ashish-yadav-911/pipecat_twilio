# import datetime
# import io
# import os
# import sys
# import wave
# from pathlib import Path

# import aiofiles
# from dotenv import load_dotenv
# from fastapi import WebSocket
# from logger import logger
# from loguru import logger
# from pipecat.audio.vad.silero import SileroVADAnalyzer
# from pipecat.pipeline.pipeline import Pipeline
# from pipecat.pipeline.runner import PipelineRunner
# from pipecat.pipeline.task import PipelineParams, PipelineTask
# from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
# from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
# from plivo_serial import PlivoFrameSerializer

# from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
# from pipecat.services.deepgram.stt import DeepgramSTTService
# from pipecat.services.openai.llm import OpenAILLMService
# from pipecat.transports.network.fastapi_websocket import (
#     FastAPIWebsocketParams,
#     FastAPIWebsocketTransport,
# )

# # Import SYSTEM_PROMPT from prompt.py
# try:
#     from prompt import SYSTEM_PROMPT
#     logger.info("Successfully imported SYSTEM_PROMPT from prompt.py")
# except ImportError as e:
#     logger.error(f"Failed to import SYSTEM_PROMPT: {e}")
#     SYSTEM_PROMPT = None

# load_dotenv(override=True)

# logger.remove(0)
# logger.add(sys.stderr, level="DEBUG")

# async def run_bot(websocket_client: WebSocket, call_uuid: str, testing: bool):
#     logger.info("Initializing bot with call_uuid: {}", call_uuid)
#     transport = FastAPIWebsocketTransport(
#         websocket=websocket_client,
#         params=FastAPIWebsocketParams(
#             audio_in_enabled=True,
#             audio_out_enabled=True,
#             add_wav_header=False,
#             vad_enabled=False,
#             vad_analyzer=SileroVADAnalyzer(),
#             serializer=PlivoFrameSerializer(
#                 call_uuid,
#                 params=PlivoFrameSerializer.InputParams(plivo_sample_rate=8000)
#             ),
#         ),
#     )

#     llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o-mini")

#     stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"), audio_passthrough=True)

#     tts = ElevenLabsTTSService(
#         api_key=os.getenv("ELEVENLABS_API_KEY"),
#         voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
#         push_silence_after_stop=True,
#     )

#     # Use imported SYSTEM_PROMPT or fallback to default
#     system_prompt = SYSTEM_PROMPT if SYSTEM_PROMPT else (
#         "You are a helpful assistant named Mirai. Your output will be converted to audio, "
#         "so avoid special characters. Respond concisely. Developed by Iffort."
#     )

#     messages = [
#         {
#             "role": "system",
#             "content": system_prompt,
#         },
#     ]

#     context = OpenAILLMContext(messages)
#     context_aggregator = llm.create_context_aggregator(context)

#     audiobuffer = AudioBufferProcessor(user_continuous_stream=not testing)

#     pipeline = Pipeline(
#         [
#             transport.input(),  # Websocket input from client
#             stt,  # Speech-To-Text
#             context_aggregator.user(),
#             llm,  # LLM
#             tts,  # Text-To-Speech
#             transport.output(),  # Websocket output to client
#             audiobuffer,  # Used to buffer the audio in the pipeline
#             context_aggregator.assistant(),
#         ]
#     )

#     task = PipelineTask(
#         pipeline,
#         params=PipelineParams(
#             audio_in_sample_rate=8000,
#             audio_out_sample_rate=8000,
#             allow_interruptions=True,
#             enable_metrics=True,
#             disable_buffers=True
#         ),
#     )

#     logger.debug("Pipeline and services initialized successfully.")

#     @transport.event_handler("on_client_connected")
#     async def on_client_connected(transport, client):
#         logger.info("Client connected: {}", client)
#         try:
#             messages.append({"role": "system", "content": "Please introduce yourself to the user."})
#             await task.queue_frames([context_aggregator.user().get_context_frame()])
#         except Exception as e:
#             logger.error("Error during client connection handling: {}", e)

#     @transport.event_handler("on_client_disconnected")
#     async def on_client_disconnected(transport, client):
#         logger.info("Client disconnected: {}", client)
#         try:
#             await task.cancel()
#         except Exception as e:
#             logger.error("Error during client disconnection handling: {}", e)

#     # @audiobuffer.event_handler("on_audio_data")
#     # async def on_audio_data(buffer, audio, sample_rate, num_channels):
#     #     logger.debug("Audio data received: sample_rate={}, num_channels={}", sample_rate, num_channels)
#     #     try:
#     #         server_name = f"server_{websocket_client.client.port}"
#     #         # await save_audio(server_name, audio, sample_rate, num_channels)
#     #     except Exception as e:
#     #         logger.error("Error while saving audio data: {}", e)

#     runner = PipelineRunner(handle_sigint=False, force_gc=True)

#     try:
#         await runner.run(task)
#         logger.info("Pipeline runner executed successfully.")
#     except Exception as e:
#         logger.error("Error during pipeline execution: {}", e)























# # bot.py #2

# import datetime
# import io
# import os
# import sys
# import wave
# from pathlib import Path
# import asyncio # Import asyncio

# import aiofiles
# from dotenv import load_dotenv
# from fastapi import WebSocket
# # Consolidate logging - using standard logging configuration from server.py
# # from logger import logger # Remove ambiguous import
# # from loguru import logger # Remove loguru import here if using standard logging

# # Use standard logging module
# import logging
# logger = logging.getLogger(__name__) # Get logger configured in server.py/app.py

# from pipecat.audio.vad.silero import SileroVADAnalyzer
# from pipecat.pipeline.pipeline import Pipeline
# from pipecat.pipeline.runner import PipelineRunner
# from pipecat.pipeline.task import PipelineParams, PipelineTask
# from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
# from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
# # Ensure this import path is correct
# try:
#     from plivo_serial import PlivoFrameSerializer # Assuming in same dir, use relative import
#     logger.info("Successfully imported PlivoFrameSerializer in bot.py")
# except ImportError:
#      logger.error("Failed to import PlivoFrameSerializer in bot.py. Check import path.")
#      PlivoFrameSerializer = None # Handle gracefully

# from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
# from pipecat.services.deepgram.stt import DeepgramSTTService
# from pipecat.services.openai.llm import OpenAILLMService
# from pipecat.transports.network.fastapi_websocket import (
#     FastAPIWebsocketParams,
#     FastAPIWebsocketTransport,
# )

# # Import SYSTEM_PROMPT from prompt.py
# try:
#     from prompt import SYSTEM_PROMPT
#     logger.info("Successfully imported SYSTEM_PROMPT from prompt.py")
# except ImportError as e:
#     logger.warning(f"Failed to import SYSTEM_PROMPT: {e}. Using default.")
#     SYSTEM_PROMPT = None

# # Load environment variables (redundant if server.py does this and passes config,
# # but keep if bot.py needs direct access)
# # load_dotenv(override=True)

# # Configure logging here ONLY if not configured in server.py
# # logger.remove(0) # Remove loguru specific config if using standard logging
# # logger.add(sys.stderr, level="DEBUG") # Configure standard logging if needed

# # --- Modify run_bot signature to accept start_immediately flag ---
# async def run_bot(
#     websocket_client: WebSocket,
#     call_uuid: str, # Renamed stream_sid to call_uuid for Plivo context
#     testing: bool,
#     start_immediately: bool # New parameter
# ):
#     logger.info("Initializing bot for CallUUID: {}. Testing: {}. Start Immediately: {}".format(call_uuid, testing, start_immediately))

#     if PlivoFrameSerializer is None:
#          logger.error("PlivoFrameSerializer not available. Cannot initialize transport.")
#          return # Exit early

#     # --- Get configuration (API keys, etc.) ---
#     # Get from environment variables (assuming dotenv is loaded globally or here)
#     openai_api_key = os.getenv("OPENAI_API_KEY")
#     deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")
#     elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
#     elevenlabs_voice_id = os.getenv("ELEVENLABS_VOICE_ID")
#     # Get Sample Rate from environment or assume default (match Plivo XML/serializer)
#     # The /plivo/stream endpoint could pass the sample rate from the 'start' event if needed.
#     # For now, hardcode to 8000 assuming Plivo XML is rate=8000
#     audio_sample_rate = 8000


#     # --- Instantiate services and pipeline components ---
#     # Kept instantiation inside bot.py as per your current structure
#     transport = FastAPIWebsocketTransport(
#         websocket=websocket_client,
#         params=FastAPIWebsocketParams(
#             audio_in_enabled=True,
#             audio_out_enabled=True,
#             add_wav_header=False, # Raw audio
#             vad_enabled=True, # Enable VAD
#             vad_analyzer=SileroVADAnalyzer(), # Instantiate VAD
#             serializer=PlivoFrameSerializer(
#                 call_uuid, # Use call_uuid for serializer init if needed
#                 params=PlivoFrameSerializer.InputParams(sample_rate=audio_sample_rate) # Pass sample rate
#             ),
#             buffer_size=512,
#             vad_audio_passthrough=True, # Pass audio through VAD
#         ),
#     )
#     logger.debug("FastAPIWebsocketTransport initialized.")


#     if not openai_api_key: logger.warning("OpenAI API key not set.")
#     llm = OpenAILLMService(api_key=openai_api_key, model=os.getenv("OPENAI_MODEL", "gpt-4o-mini")) # Default model

#     if not deepgram_api_key: logger.warning("Deepgram API key not set.")
#     stt = DeepgramSTTService(api_key=deepgram_api_key, audio_passthrough=True)

#     if not elevenlabs_api_key or not elevenlabs_voice_id: logger.warning("Eleven Labs API key or voice ID not set.")
#     tts = ElevenLabsTTSService(
#         api_key=elevenlabs_api_key,
#         voice_id=elevenlabs_voice_id,
#         push_silence_after_stop=True,
#     )
#     logger.debug("Services initialized.")


#     # Use imported SYSTEM_PROMPT or fallback to default (kept here for self-containment)
#     system_prompt = SYSTEM_PROMPT if SYSTEM_PROMPT else (
#         "You are a helpful assistant named Mirai. Your output will be converted to audio, "
#         "so avoid special characters. Respond concisely. Developed by Iffort."
#     )
#     logger.debug("System Prompt: {}".format(system_prompt))

#     messages = [
#         {"role": "system", "content": system_prompt},
#         # Initial "user" message to prime the bot for the intro might be added later
#         # or triggered by maybe_send_greeting queueing the context frame.
#     ]

#     context = OpenAILLMContext(messages)
#     context_aggregator = llm.create_context_aggregator(context)
#     logger.debug("OpenAILLMContext and aggregator created.")

#     # Audio Buffer (for saving audio, not typically in the main processing path)
#     # If you don't need to save audio, you can remove this and its event handler
#     audiobuffer = AudioBufferProcessor(user_continuous_stream=not testing)
#     logger.debug("AudioBufferProcessor created.")


#     pipeline = Pipeline(
#         [
#             transport.input(),  # Websocket input from client (receives raw audio frames)
#             # Wire audiobuffer to transport input if saving audio
#             # transport.input() >> audiobuffer # Example connection outside main path

#             stt,  # Speech-To-Text (gets raw audio frames from transport)
#             context_aggregator.user(), # Aggregates STT results into user context
#             llm,  # LLM (gets user context, outputs assistant text)
#             tts,  # Text-To-Speech (gets assistant text, outputs audio)
#             transport.output(),  # Websocket output to client (sends raw audio frames from TTS)
#             context_aggregator.assistant(), # Aggregates assistant text responses into context
#         ]
#     )
#     logger.debug("Pipeline created.")

#     task = PipelineTask(
#         pipeline,
#         params=PipelineParams(
#             audio_in_sample_rate=audio_sample_rate, # Match Plivo stream/serializer rate
#             audio_out_sample_rate=audio_sample_rate, # Output at the same rate
#             allow_interruptions=True,
#             enable_metrics=True,
#             disable_buffers=False # Keep buffering enabled for performance
#         ),
#     )
#     logger.debug("PipelineTask created.")

#     # --- Define and Set up Event Handlers ---
#     # These handlers live within the scope of run_bot

#     sent_initial_greeting = False # Flag to ensure greeting is sent only once

#     async def maybe_send_greeting():
#         nonlocal sent_initial_greeting
#         # Ensure this is only called once
#         if not sent_initial_greeting:
#             logger.info(f"[{call_uuid}] Queueing initial bot greeting...")
#             # Add a specific intro message *or* rely on system prompt + initial context frame
#             # Option 1: Add a specific intro message to context
#             # messages.append({"role": "system", "content": "Please introduce yourself."})
#             # Option 2: Just queue the initial context frame (relies on LLM/System Prompt)
#             initial_context_frame = context_aggregator.user().get_context_frame() # This frame signals the bot to start/generate first turn
#             await task.queue_frames([initial_context_frame]) # Queue it on the pipeline task
#             sent_initial_greeting = True
#             logger.info(f"[{call_uuid}] Initial greeting queued.")

#     # --- Event Handler: Listen for the first user speech ---
#     # This handler is crucial for the 'wait for user speech' scenario
#     # It fires when STT detects speech and the ContextAggregator processes it.
#     # It also fires for subsequent user speeches.
#     @context_aggregator.user().event_handler("on_user_message_created")
#     async def on_user_context_created(context_agg):
#          # This handler fires after *any* user speech is processed by STT -> LLMContextAggregator.
#          # We only use it to trigger the greeting IF we are waiting
#          # (i.e., not start_immediately) AND the greeting hasn't been sent yet.
#          if not sent_initial_greeting and not start_immediately:
#              # This is the first time we've received user context AND we were waiting
#              logger.info(f"[{call_uuid}] First user speech detected (unprepared call). Triggering initial bot greeting.")
#              await maybe_send_greeting()
#          else:
#              # This branch handles subsequent user inputs *after* the greeting has been sent
#              # or user inputs on prepared calls where greeting is sent immediately.
#              logger.debug(f"[{call_uuid}] User context created (subsequent speech or prepared call initial speech).")
#              # The main pipeline flow (context_aggregator.user() -> llm -> tts) handles subsequent responses automatically.
#              pass # No explicit action needed here to *start* the conversation


#     # --- Optional: Event handler for saving audio ---
#     # If AudioBufferProcessor is used just for saving, uncomment this block
#     # @audiobuffer.event_handler("on_audio_data")
#     # async def on_audio_data(buffer, audio, sample_rate, num_channels):
#     #     """Handle audio data event and save to file."""
#     #     # Use the call_uuid passed to run_bot for naming
#     #     server_name = f"plivo_{call_uuid}" # Example using call_uuid
#     #     output_dir = Path("recordings") # Ensure this directory exists
#     #     output_dir.mkdir(parents=True, exist_ok=True)
#     #     # Use a unique filename per chunk (timestamp + random) or append to a single file
#     #     filename = f"{output_dir}/{server_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.wav"

#     #     try:
#     #         # Save as WAV (Assuming 16-bit PCM, Plivo L16 is Little Endian)
#     #         with wave.open(str(filename), 'wb') as wf:
#     #             wf.setnchannels(num_channels)
#     #             wf.setsampwidth(2) # 16-bit PCM = 2 bytes
#     #             wf.setframerate(sample_rate)
#     #             wf.writeframes(audio) # audio is bytes
#     #         # logger.debug(f"[{call_uuid}] Saved audio chunk to {filename}") # Too noisy
#     #     except Exception as e:
#     #         logger.error(f"[{call_uuid}] Error saving audio chunk: {e}")


#     # --- Start the conversation logic based on preparation status ---
#     # Queue the greeting immediately if start_immediately is True
#     # Otherwise, the on_user_context_created handler will trigger it on first speech.
#     if start_immediately:
#         logger.info(f"[{call_uuid}] Call was prepared. Queuing conversation start immediately.")
#         # Using asyncio.create_task to queue the greeting immediately
#         # allows the runner.run to start without waiting for queue_frames.
#         asyncio.create_task(maybe_send_greeting())
#     else:
#         logger.info(f"[{call_uuid}] Call was NOT prepared. Waiting for first user speech.")
#         # The on_user_context_created handler is already set up to trigger the greeting

#     # --- Instantiate Pipeline Runner ---
#     runner = PipelineRunner(handle_sigint=False, force_gc=True)
#     logger.debug(f"[{call_uuid}] PipelineRunner created.")

#     # --- Run the Pipeline Task (This blocks until the task is done/cancelled) ---
#     # The event handlers set up above will manage the flow based on events
#     logger.info(f"[{call_uuid}] Starting Pipeline Runner...")
#     try:
#         await runner.run(task)
#         logger.info(f"[{call_uuid}] Pipeline Runner finished.")
#     except Exception as e:
#         logger.error(f"[{call_uuid}] Error during pipeline execution: {e}")
#         #logger.error(traceback.format_exc())

#     finally:
#         # Optional: Add cleanup logic here if needed
#         logger.info(f"[{call_uuid}] run_bot exiting.")








# bot.py

import datetime
import io
import os
import sys
import wave
from pathlib import Path
import asyncio # Import asyncio

import aiofiles
from dotenv import load_dotenv
from fastapi import WebSocket
# Consolidate logging - using standard logging configuration from server.py
# from logger import logger # Remove ambiguous import
# from loguru import logger # Remove loguru import here if using standard logging

# Use standard logging module
import logging
logger = logging.getLogger(__name__) # Get logger configured in server.py/app.py

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
# Ensure this import path is correct
try:
    from plivo_serial import PlivoFrameSerializer # Assuming in same dir, use relative import
    logger.info("Successfully imported PlivoFrameSerializer in bot.py")
except ImportError:
     logger.error("Failed to import PlivoFrameSerializer in bot.py. Check import path.")
     PlivoFrameSerializer = None # Handle gracefully

from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

# Import TextFrame to use in event handler signature
from pipecat.frames.frames import TextFrame

# Import SYSTEM_PROMPT from prompt.py
try:
    from prompt import SYSTEM_PROMPT
    logger.info("Successfully imported SYSTEM_PROMPT from prompt.py")
except ImportError as e:
    logger.warning(f"Failed to import SYSTEM_PROMPT: {e}. Using default.")
    SYSTEM_PROMPT = None

# Load environment variables (redundant if server.py does this and passes config,
# but keep if bot.py needs direct access)
# load_dotenv(override=True)

# Configure logging here ONLY if not configured in server.py
# logger.remove(0) # Remove loguru specific config if using standard logging
# logger.add(sys.stderr, level="DEBUG") # Configure standard logging if needed

# --- Modify run_bot signature to accept start_immediately flag ---
async def run_bot(
    websocket_client: WebSocket,
    call_uuid: str, # Renamed stream_sid to call_uuid for Plivo context
    testing: bool,
    start_immediately: bool # New parameter passed from server.py
):
    logger.info("Initializing bot for CallUUID: {}. Testing: {}. Start Immediately: {}".format(call_uuid, testing, start_immediately))

    if PlivoFrameSerializer is None:
         logger.error(f"[{call_uuid}] PlivoFrameSerializer not available. Cannot initialize transport.")
         return # Exit early

    # --- Get configuration (API keys, etc.) ---
    # Get from environment variables (assuming dotenv is loaded globally or here)
    # It's better to load config once in server.py and pass it, but keeping here
    # to match your current bot.py structure.
    openai_api_key = os.getenv("OPENAI_API_KEY")
    deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")
    elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
    elevenlabs_voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    # Get Sample Rate from environment or assume default (match Plivo XML/serializer)
    # The /plivo/stream endpoint should pass the sample rate from the 'start' event if needed.
    # For now, hardcode to 8000 assuming Plivo XML is rate=8000 and serializer is set up for it
    audio_sample_rate = 8000


    # --- Instantiate services and pipeline components ---
    # Kept instantiation inside bot.py as per your current structure
    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False, # Raw audio
            vad_enabled=True, # Enable VAD
            vad_analyzer=SileroVADAnalyzer(), # Instantiate VAD
            serializer=PlivoFrameSerializer(
                call_uuid, # Use call_uuid for serializer init if needed
                params=PlivoFrameSerializer.InputParams(sample_rate=audio_sample_rate) # Pass sample rate
            ),
            buffer_size=512,
            vad_audio_passthrough=True, # Pass audio through VAD
        ),
    )
    logger.debug(f"[{call_uuid}] FastAPIWebsocketTransport initialized.")


    if not openai_api_key: logger.warning(f"[{call_uuid}] OpenAI API key not set.")
    llm = OpenAILLMService(api_key=openai_api_key, model=os.getenv("OPENAI_MODEL", "gpt-4o-mini")) # Default model

    if not deepgram_api_key: logger.warning(f"[{call_uuid}] Deepgram API key not set.")
    stt = DeepgramSTTService(api_key=deepgram_api_key, audio_passthrough=True)

    if not elevenlabs_api_key or not elevenlabs_voice_id: logger.warning(f"[{call_uuid}] Eleven Labs API key or voice ID not set.")
    tts = ElevenLabsTTSService(
        api_key=elevenlabs_api_key,
        voice_id=elevenlabs_voice_id,
        push_silence_after_stop=True,
    )
    logger.debug(f"[{call_uuid}] Services initialized.")


    # Use imported SYSTEM_PROMPT or fallback to default (kept here for self-containment)
    system_prompt = SYSTEM_PROMPT if SYSTEM_PROMPT else (
        "You are a helpful assistant named Mirai. Your output will be converted to audio, "
        "so avoid special characters. Respond concisely. Developed by Iffort."
    )
    #logger.debug(f"[{call_uuid}] System Prompt: {}".format(system_prompt))

    messages = [
        {"role": "system", "content": system_prompt},
        # Initial "user" message to prime the bot for the intro might be added later
        # or triggered by maybe_send_greeting queueing the context frame.
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)
    logger.debug(f"[{call_uuid}] OpenAILLMContext and aggregator created.")

    # Audio Buffer (for saving audio, not typically in the main processing path)
    # If you don't need to save audio, you can remove this and its event handler
    audiobuffer = AudioBufferProcessor(user_continuous_stream=not testing)
    logger.debug(f"[{call_uuid}] AudioBufferProcessor created.")


    # --- Define the PipeCat Pipeline ---
    # This is the standard ASR -> LLM -> TTS flow
    # audiobuffer is typically connected separately for saving, not in the main flow.
    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client (receives raw audio frames)
            # Wire audiobuffer to transport input if saving audio
            # transport.input() >> audiobuffer # Example connection outside main path

            stt,  # Speech-To-Text (gets raw audio frames from transport)
            context_aggregator.user(), # Aggregates STT results into user context
            llm,  # LLM (gets user context, outputs assistant text)
            tts,  # Text-To-Speech (gets assistant text, outputs audio)
            transport.output(),  # Websocket output to client (sends raw audio frames from TTS)
            context_aggregator.assistant(), # Aggregates assistant text responses into context
        ]
    )
    logger.debug(f"[{call_uuid}] Pipeline created.")

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=audio_sample_rate, # Match Plivo stream/serializer rate
            audio_out_sample_rate=audio_sample_rate, # Output at the same rate
            allow_interruptions=True,
            enable_metrics=True,
            disable_buffers=False # Keep buffering enabled for performance
        ),
    )
    logger.debug(f"[{call_uuid}] PipelineTask created.")


    # --- Define and Set up Event Handlers ---
    # These handlers live within the scope of run_bot

    sent_initial_greeting = False # Flag to ensure greeting is sent only once

    async def maybe_send_greeting():
        nonlocal sent_initial_greeting
        # Ensure this is only called once
        if not sent_initial_greeting:
            logger.info(f"[{call_uuid}] Queueing initial bot greeting...")
            # This frame triggers the LLM/TTS pipeline for the intro
            # It should use the context_aggregator instance created in this run_bot call
            initial_context_frame = context_aggregator.user().get_context_frame() # Get the initial context frame
            await task.queue_frames([initial_context_frame]) # Queue it on the pipeline task
            sent_initial_greeting = True
            logger.info(f"[{call_uuid}] Initial greeting queued.")

    # --- Event Handler: Listen for the first final text from STT ---
    # We use this event because it's reliably emitted by the STT component
    # and signifies that the user's speech has been processed into text.
    @stt.event_handler("on_text_final") # <-- Register handler on the STT component
    async def handle_final_user_text(frame: TextFrame): # <-- Handler receives the TextFrame
        logger.debug(f"[{call_uuid}] STT produced final text: {frame.text}")

        nonlocal sent_initial_greeting # Ensure nonlocal access

        # This handler fires for *every* final text segment from STT.
        # We only want to trigger the greeting IF:
        # 1. We are in the 'wait for speech' mode (not start_immediately)
        # 2. The greeting hasn't been sent yet.
        if not sent_initial_greeting and not start_immediately:
            # This is the first time we've received final user text AND we were waiting
            logger.info(f"[{call_uuid}] First final user text detected from STT (unprepared call). Triggering initial bot greeting.")
            # Call the greeting function
            await maybe_send_greeting()
        else:
             # This handles subsequent speech after greeting, or speech on prepared calls
             logger.debug(f"[{call_uuid}] Subsequent final user text from STT or prepared call. (start_immediately={start_immediately}, sent_initial_greeting={sent_initial_greeting})")
             # The pipeline handles feeding this text to the LLM via context_aggregator.user()
             pass # No explicit action needed here to *start* the conversation


    # --- Optional: Event handler for saving audio ---
    # If AudioBufferProcessor is used just for saving, uncomment this block
    # and ensure you have Path and wave imported at the top
    # @audiobuffer.event_handler("on_audio_data")
    # async def on_audio_data(buffer, audio, sample_rate, num_channels):
    #     """Handle audio data event and save to file."""
    #     # Use the call_uuid passed to run_bot for naming
    #     server_name = f"plivo_{call_uuid}" # Example using call_uuid
    #     output_dir = Path("recordings") # Ensure this directory exists relative to where the script is run
    #     output_dir.mkdir(parents=True, exist_ok=True)
    #     # Use a unique filename per chunk (timestamp + random) or append to a single file
    #     filename = f"{output_dir}/{server_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.wav"

    #     try:
    #         # Save as WAV (Assuming 16-bit PCM, Plivo L16 is Little Endian)
    #         with wave.open(str(filename), 'wb') as wf:
    #             wf.setnchannels(num_channels)
    #             wf.setsampwidth(2) # 16-bit PCM = 2 bytes
    #             wf.setframerate(sample_rate)
    #             wf.writeframes(audio) # audio is bytes
    #         # logger.debug(f"[{call_uuid}] Saved audio chunk to {filename}") # Too noisy
    #     except Exception as e:
    #         logger.error(f"[{call_uuid}] Error saving audio chunk: {e}")

    # --- Wire audiobuffer to transport input if saving audio ---
    # If audiobuffer is only for saving, connect it like this:
    # transport.input() >> audiobuffer # Connect the output of transport.input() to audiobuffer input


    # --- Start the conversation logic based on preparation status ---
    # Queue the greeting immediately if start_immediately is True
    # Otherwise, the @stt.event_handler("on_text_final") handler will trigger it on first speech.
    if start_immediately:
        logger.info(f"[{call_uuid}] Call was prepared (from ring webhook). Queuing conversation start immediately.")
        # Using asyncio.create_task to queue the greeting immediately
        # allows the runner.run to start without waiting for queue_frames.
        asyncio.create_task(maybe_send_greeting())
    else:
        logger.info(f"[{call_uuid}] Call was NOT prepared. Waiting for first final user text from STT.")
        # The @stt.event_handler("on_text_final") will handle the trigger when user speaks


    # --- Instantiate Pipeline Runner ---
    runner = PipelineRunner(handle_sigint=False, force_gc=True)
    logger.debug(f"[{call_uuid}] PipelineRunner created.")

    # --- Run the Pipeline Task (This blocks until the task is done/cancelled) ---
    # The event handlers set up above will manage the flow based on events
    logger.info(f"[{call_uuid}] Starting Pipeline Runner...")
    try:
        await runner.run(task)
        logger.info(f"[{call_uuid}] Pipeline Runner finished.")
    except Exception as e:
        logger.error(f"[{call_uuid}] Error during pipeline execution: {e}")
        #logger.error(traceback.format_exc())

    finally:
        # Optional: Add cleanup logic here if needed
        logger.info(f"[{call_uuid}] run_bot exiting.")