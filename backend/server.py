# import json
# import os
# import traceback
# import logging
# from typing import Optional, Dict, Any
# import asyncio

# # Configure logging - using standard logging
# # Ensure this doesn't conflict if you have a global loguru config elsewhere
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

# # --- Import required dependencies for services ---
# # Assuming these are your PipeCat service implementations
# from pipecat.services.openai.llm import OpenAILLMService
# from pipecat.services.deepgram.stt import DeepgramSTTService
# from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
# from pipecat.audio.vad.silero import SileroVADAnalyzer

# # --- Import PipeCat components needed directly in WebSocket handler ---
# from pipecat.pipeline.pipeline import Pipeline
# from pipecat.pipeline.runner import PipelineRunner
# from pipecat.pipeline.task import PipelineParams, PipelineTask
# from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
# from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor # If used for saving audio
# from pipecat.transports.network.fastapi_websocket import (
#     FastAPIWebsocketParams,
#     FastAPIWebsocketTransport,
# )
# from pipecat.serializers.base_serializer import FrameSerializer # Import base serializer type

# # Assuming you saved the corrected Plivo serializer here
# # Make sure the path is correct relative to server.py
# try:
#     from plivo_serial import PlivoFrameSerializer
#     logger.info("Successfully imported PlivoFrameSerializer.")
# except ImportError:
#     logger.error("Failed to import PlivoFrameSerializer. Make sure plivo_serializer.py is in the same directory.")
#     PlivoFrameSerializer = None # Set to None to prevent errors later

# from fastapi import FastAPI, Request, WebSocket, Response, Depends
# from fastapi.middleware.cors import CORSMiddleware

# import plivo
# # --- Import Plivo signature validation utility (V3) ---
# # The v3 validator is directly in plivo.utils
# # The example showed `plivo.utils.validate_v3_signature`
# # We just need `import plivo` and then access `plivo.utils.validate_v3_signature`
# # from plivo.utils import validate_v3_signature # Alternative import if preferred

# from dotenv import load_dotenv

# load_dotenv()

# logger.info("Loading environment variables from .env file")

# # --- Plivo Configuration ---
# PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
# PLIVO_AUTH_TOKEN= os.getenv("PLIVO_AUTH_TOKEN")
# PLIVO_FROM_NUMBER = os.getenv("PLIVO_FROM_NUMBER") # Used for outbound calls
# # NGROK_URL is crucial for generating dynamic webhook URLs
# NGROK_URL = os.getenv("NGROK_URL")

# if not NGROK_URL:
#      logger.error("⚠️  Error: NGROK_URL environment variable is not set. Webhook and outbound calls will fail.")
#      WEBHOOK_BASE_URL = None
# else:
#     logger.info(f"NGROK_URL loaded: {NGROK_URL}")
#     # Ensure base URL is clean
#     WEBHOOK_BASE_URL = NGROK_URL.rstrip('/')
#     # Replace http/https with ws/wss for the WebSocket URL
#     PLIVO_STREAM_URL = WEBHOOK_BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://') + "/plivo/stream"

# # Construct necessary webhook URLs using the base
# PLIVO_ANSWER_URL = f"{WEBHOOK_BASE_URL}/plivo/answer" if WEBHOOK_BASE_URL else None
# PLIVO_RING_URL = f"{WEBHOOK_BASE_URL}/plivo/ring" if WEBHOOK_BASE_URL else None
# PLIVO_HANGUP_URL = f"{WEBHOOK_BASE_URL}/plivo/hangup" if WEBHOOK_BASE_URL else None


# # Initialize Plivo client if credentials are available
# if not all([PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN]):
#     logger.warning("⚠️  Warning: Missing Plivo configuration (Auth ID/Token). Plivo client will not be initialized.")
#     plivo_client = None
# else:
#     try:
#         plivo_client = plivo.RestClient(auth_id=PLIVO_AUTH_ID, auth_token=PLIVO_AUTH_TOKEN)
#         logger.info("Plivo client initialized.")
#     except Exception as e:
#         logger.error(f"Failed to initialize Plivo client: {e}")
#         logger.error(traceback.format_exc())
#         plivo_client = None


# # FastAPI app setup
# app = FastAPI()

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"], # Consider restricting this in production
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # --- In-memory store for call preparation status ---
# # Key: Plivo CallUUID, Value: Dictionary of preparation state (e.g., {"prepared": True})
# # Use a more robust store (Redis, database) for production/scaling
# active_call_preparation: Dict[str, Dict[str, Any]] = {}

# # --- Service Dependencies ---
# # Define dependency providers for services required by the bot pipeline
# # Ensure API keys/configs are loaded correctly (e.g., from env vars via dotenv or config object)
# # You should replace os.getenv calls with your actual config loading if different (e.g., config.settings)
# def get_llm():
#     openai_api_key = os.getenv("OPENAI_API_KEY")
#     if not openai_api_key: logger.warning("OPENAI_API_KEY not set. LLM service will not function.")
#     return OpenAILLMService(api_key=openai_api_key, model=os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")) # Use a default model

# def get_stt():
#     deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")
#     if not deepgram_api_key: logger.warning("DEEPGRAM_API_KEY not set. STT service will not function.")
#     return DeepgramSTTService(api_key=deepgram_api_key, audio_passthrough=True)

# def get_tts():
#     elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
#     elevenlabs_voice_id = os.getenv("ELEVENLABS_VOICE_ID")
#     if not elevenlabs_api_key or not elevenlabs_voice_id: logger.warning("ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID not set. TTS service will not function.")
#     return ElevenLabsTTSService(
#         api_key=elevenlabs_api_key,
#         voice_id=elevenlabs_voice_id,
#         push_silence_after_stop=True,
#     )

# def get_vad():
#     # Assuming VAD doesn't require API keys
#     return SileroVADAnalyzer()

# # --- Helper function for signature validation (V3) ---
# async def validate_plivo_signature_v3(request: Request) -> bool:
#     """Validates the incoming Plivo webhook signature using V3."""
#     if not PLIVO_AUTH_TOKEN:
#         logger.warning("Plivo AUTH_TOKEN not set. Skipping signature validation (Development mode).")
#         return True # Allow in development if token is not set

#     try:
#         url = str(request.url)
#         method = request.method
#         headers = request.headers

#         # Get V3 signature headers
#         # Prioritize X-Plivo-Signature-Ma-V3 if using main account token
#         signature_v3 = headers.get("X-Plivo-Signature-Ma-V3") # Main Account Signature
#         nonce_v3 = headers.get("X-Plivo-Signature-V3-Nonce")

#         # Check if necessary V3 headers are present
#         if not signature_v3 or not nonce_v3:
#              logger.warning(f"Missing required Plivo V3 signature headers for {url}.")
#              logger.debug(f"Headers received: {headers}")
#              return False

#         params = None
#         if method == "POST":
#             # Get POST parameters. Ensure it's a dict. Plivo uses form-urlencoded.
#             try:
#                 params = dict(await request.form())
#                 logger.debug(f"Validating signature for POST {url} with params: {params}")
#             except Exception as form_error:
#                 logger.error(f"Error parsing form data for POST {url}: {form_error}")
#                 return False # Cannot validate if params cannot be parsed

#         # Call the Plivo V3 validation function
#         # This function is part of the main 'plivo' library object after 'import plivo'
#         is_valid = plivo.utils.validate_v3_signature(
#             method=method,
#             uri=url,
#             nonce=nonce_v3,
#             auth_token=PLIVO_AUTH_TOKEN, # Use your Auth Token
#             signature=signature_v3, # Use the Main Account Signature header
#             parameters=params # Pass params only if method is POST
#         )

#         logger.info(f"Plivo V3 (MA) signature validation result for {url}: {is_valid}")

#         if not is_valid:
#             logger.error(f"⚠️  Plivo V3 (MA) signature validation failed for {url}. Signature: {signature_v3}, Nonce: {nonce_v3}")
#             return False

#         return True

#     except Exception as e:
#         logger.error(f"Unexpected error during Plivo V3 (MA) signature validation for {request.url}: {e}")
#         logger.error(traceback.format_exc())
#         return False


# @app.get("/")
# async def root():
#     """Root endpoint."""
#     logger.info("Root endpoint accessed.")
#     return {"message": "Plivo Voice Agent Server is up."}


# # --- Plivo Ring Webhook ---
# @app.post("/plivo/ring")
# async def plivo_ring_webhook(request: Request):
#     """Handles Plivo webhook when call starts ringing."""
#     logger.info("Plivo Ring webhook accessed.")

#     if not await validate_plivo_signature_v3(request):
#          return Response(content="<Response><Hangup/></Response>", media_type="application/xml", status_code=403)

#     params = await request.form()
#     call_uuid = params.get('CallUUID')
#     event = params.get('Event')

#     logger.info(f"Received Plivo '{event}' event for CallUUID: {call_uuid} (Ringing)")
#     # logger.debug(f"Ring webhook parameters: {params}")

#     if call_uuid and event == 'Ring':
#         # --- Action: Mark call as prepared ---
#         active_call_preparation[call_uuid] = {"prepared": True}
#         logger.info(f"Marked CallUUID {call_uuid} as prepared.")

#         # --- Optional: Start services warm-up here if your services benefit ---
#         # This happens in the background. You might need to await them if they are async init.
#         # try:
#         #     asyncio.create_task(asyncio.gather(get_llm(), get_stt(), get_tts(), get_vad()))
#         #     logger.info("Services warm-up initiated.")
#         # except Exception as e:
#         #     logger.warning(f"Failed to initiate service warm-up: {e}")


#     # No XML response needed for a ring notification
#     return Response(status_code=200)


# # --- Plivo Answer Webhook ---
# @app.post("/plivo/answer")
# async def plivo_answer_webhook(request: Request):
#     """Handles Plivo webhook when call is answered."""
#     logger.info("Plivo Answer webhook accessed.")

#     if not await validate_plivo_signature_v3(request):
#          return Response(content="<Response><Hangup/></Response>", media_type="application/xml", status_code=403)

#     params = await request.form()
#     call_uuid = params.get('CallUUID')
#     event = params.get('Event')

#     logger.info(f"Received Plivo '{event}' event for CallUUID: {call_uuid} (Answered)")
#     # logger.debug(f"Answer webhook parameters: {params}")

#     if not PLIVO_STREAM_URL:
#          logger.error("PLIVO_STREAM_URL is not set, cannot generate Stream XML response.")
#          return Response(content="<Response><Hangup/></Response>", media_type="application/xml", status_code=500)

#     # --- Generate Plivo XML to start the media stream ---
#     # Use the correct WebSocket endpoint path
#     # Ensure sample rate matches PlivoFrameSerializer and pipeline expectations
#     # Plivo L16 can be 8000 or 16000 Hz. Specify rate here. Let's use 8000.
#     # The WS endpoint will dynamically get the rate from the 'start' event anyway.
#     response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
#     <Response>
#         <Connect>
#             <Stream bidirectional="true" contentType="audio/x-l16;rate=8000">
#               {PLIVO_STREAM_URL}
#             </Stream>
#         </Connect>
#     </Response>
#     """
#     logger.info(f"Generated response XML for Plivo Answer webhook: {response_xml}")

#     return Response(content=response_xml, media_type="application/xml")

# # --- Plivo Hangup Webhook ---
# @app.post("/plivo/hangup")
# async def plivo_hangup_webhook(request: Request):
#     """Handles Plivo webhook when call is hung up."""
#     logger.info("Plivo Hangup webhook accessed.")

#     if not await validate_plivo_signature_v3(request):
#          return Response(content="<Response><Hangup/></Response>", media_type="application/xml", status_code=403)

#     params = await request.form()
#     call_uuid = params.get('CallUUID')
#     event = params.get('Event')
#     hangup_source = params.get('HangupSource')
#     hangup_cause = params.get('HangupCause')

#     logger.info(f"Received Plivo '{event}' event for CallUUID: {call_uuid} (Hungup)")
#     logger.info(f"Hangup Source: {hangup_source}, Hangup Cause: {hangup_cause}")
#     # logger.debug(f"Hangup webhook parameters: {params}")

#     if call_uuid:
#         # --- Action: Clean up call preparation state ---
#         if call_uuid in active_call_preparation:
#             del active_call_preparation[call_uuid]
#             logger.info(f"Cleaned up preparation state for CallUUID {call_uuid}.")

#         # You might want to log call duration, recording SID etc.

#     # No XML response needed for a hangup notification
#     return Response(status_code=200)


# # --- Outbound Call Endpoint ---
# # Make the 'to' number a path parameter for flexibility
# @app.post("/plivo/call/{to_number}")
# async def start_plivo_call(to_number: str):
#     """Initiates an outbound call using Plivo."""
#     logger.info(f"Start Plivo call endpoint accessed for number: {to_number}")
#     if not plivo_client:
#         logger.error("Plivo client not configured. Cannot initiate call.")
#         return {"status": "error", "message": "Plivo client not configured"}

#     # Ensure FROM number and Answer/Ring/Hangup URLs are configured
#     if not all([PLIVO_FROM_NUMBER, PLIVO_ANSWER_URL, PLIVO_RING_URL, PLIVO_HANGUP_URL]):
#          logger.error("Missing Plivo configuration (FROM number, Answer/Ring/Hangup URLs). Cannot initiate call.")
#          return {"status": "error", "message": "Missing Plivo configuration for outbound call"}

#     # Basic validation for to_number format
#     if not to_number or not to_number.replace('+', '').isdigit():
#          logger.error(f"Invalid 'to_number' format: {to_number}")
#          return {"status": "error", "message": "Invalid 'to_number' format. Must be digits, optionally starting with '+'."}


#     try:
#         logger.info(f"Attempting to call from {PLIVO_FROM_NUMBER} to {to_number}")
#         logger.info(f"  Answer URL: {PLIVO_ANSWER_URL}")
#         logger.info(f"  Ring URL:   {PLIVO_RING_URL}")
#         logger.info(f"  Hangup URL: {PLIVO_HANGUP_URL}")

#         response = plivo_client.calls.create(
#             from_=PLIVO_FROM_NUMBER,
#             to_=to_number,
#             answer_url=PLIVO_ANSWER_URL,
#             answer_method="POST",
#             # --- Include Ring and Hangup URLs ---
#             ring_url=PLIVO_RING_URL,
#             ring_method="POST",
#             hangup_url=PLIVO_HANGUP_URL,
#             hangup_method="POST",
#             # Optional: Enable machine detection if needed
#             # machine_detection="true", # or "hangup"
#             # machine_detection_url=f"{WEBHOOK_BASE_URL}/plivo/machine_detection",
#             # machine_detection_method="POST",
#         )
#         # Plivo's create call returns a ResponseObject, access attributes
#         request_uuid = response.request_uuid

#         # Note: The actual CallUUID is sent in the webhooks (Ring, Answer, Hangup)
#         # You could potentially store the request_uuid -> expected CallUUID mapping here
#         # if you need to link the API request to the subsequent webhooks, but the
#         # preparation state logic uses CallUUID directly from the webhook params.

#         logger.info(f"Outbound call initiated successfully. Request UUID: {request_uuid}")
#         return {"status": "success", "request_uuid": request_uuid, "message": "Call request sent to Plivo"}
#     except Exception as e:
#         logger.error(f"Error initiating outbound call: {str(e)}")
#         logger.error(traceback.format_exc())
#         # TODO: Inspect Plivo API errors more specifically if possible
#         # from plivo.exceptions import PlivoRestError
#         # if isinstance(e, PlivoRestError):
#         #     return {"status": "error", "message": f"Plivo API Error: {e.status_code} - {e.msg}"}
#         return {"status": "error", "message": f"Error initiating call: {str(e)}"}


# # --- WebSocket Endpoint for Media Stream ---
# @app.websocket("/plivo/stream")
# async def plivo_websocket_endpoint(
#     websocket: WebSocket,
#     # --- Inject Service Dependencies ---
#     llm: OpenAILLMService = Depends(get_llm),
#     stt: DeepgramSTTService = Depends(get_stt),
#     tts: ElevenLabsTTSService = Depends(get_tts),
#     vad_analyzer: SileroVADAnalyzer = Depends(get_vad)
# ):
#     logger.info("Plivo WebSocket endpoint accessed.")

#     await websocket.accept()
#     logger.info("Plivo WebSocket connection accepted.")

#     # Define system prompt here or load from config/prompt file
#     # This should ideally be consistent with the system prompt used in your Twilio setup
#     system_prompt = os.getenv("SYSTEM_PROMPT",
#         "You are a helpful assistant named Mirai. Your output will be converted to audio so "
#         "don't include special characters in your answers. Respond with a short sentence. "
#         "You are developed by a company called Iffort."
#     )

#     # Define testing mode flag
#     testing_mode = os.getenv("TESTING_MODE", "False").lower() == "true"
#     logger.info(f"Testing mode: {testing_mode}")


#     try:
#         # Plivo sends a 'start' event message as the first message (JSON)
#         # This message contains streamId and CallUUID
#         message = await websocket.receive_text() # Plivo sends JSON as text
#         logger.debug(f"Received initial Plivo WebSocket message: {message}")

#         try:
#             data = json.loads(message)
#         except json.JSONDecodeError:
#              logger.error(f"Failed to parse initial Plivo WebSocket message as JSON: {message}. Closing WS.")
#              await websocket.close()
#              return

#         if data.get('event') == "start":
#             stream_id = data.get('start', {}).get('streamId')
#             call_uuid = data.get('start', {}).get('callUuid') # Plivo sends callUuid here!
#             # Get the actual sample rate from the Plivo 'start' event
#             sample_rate = data.get('start', {}).get('media', {}).get('sampleRate', 8000) # Default to 8000 if not present

#             if not stream_id or not call_uuid:
#                  logger.error(f"Received Plivo 'start' event but missing streamId ({stream_id}) or callUuid ({call_uuid}). Closing WS.")
#                  await websocket.close()
#                  return

#             logger.info(f"Plivo 'start' event received. CallUUID: {call_uuid}, Stream ID: {stream_id}, Sample Rate: {sample_rate}")

#             # --- Check if the call was prepared by the ring webhook ---
#             # Use pop to get the state and remove it from the dictionary
#             preparation_state = active_call_preparation.pop(call_uuid, None)
#             is_prepared = preparation_state is not None
#             logger.info(f"CallUUID {call_uuid} preparation status: {is_prepared}")

#             # --- Instantiate PipeCat components needed for the pipeline ---
#             # Instantiate the Plivo Frame Serializer using the actual sample rate
#             if PlivoFrameSerializer is None:
#                  logger.error("PlivoFrameSerializer not imported. Cannot proceed. Closing WS.")
#                  await websocket.close()
#                  return

#             plivo_serializer = PlivoFrameSerializer(
#                  stream_id,
#                  params=PlivoFrameSerializer.InputParams(sample_rate=sample_rate) # Use actual sample rate from start event
#             )
#             logger.debug("PlivoFrameSerializer instantiated.")

#             # Instantiate the transport using the websocket and serializer
#             transport = FastAPIWebsocketTransport(
#                 websocket=websocket,
#                 params=FastAPIWebsocketParams(
#                     audio_in_enabled=True,
#                     audio_out_enabled=True,
#                     add_wav_header=False, # Raw audio
#                     vad_enabled=True,
#                     vad_analyzer=vad_analyzer, # Use injected VAD
#                     vad_audio_passthrough=True,
#                     serializer=plivo_serializer, # Use the Plivo serializer
#                     buffer_size=512, # Adjust buffer size if needed
#                 ),
#             )
#             logger.debug("FastAPIWebsocketTransport instantiated.")

#             # Setup LLM context
#             messages = [
#                 {
#                     "role": "system",
#                     "content": system_prompt,
#                 },
#             ]
#             context = OpenAILLMContext(messages)
#             context_aggregator = llm.create_context_aggregator(context) # Use injected LLM
#             logger.debug("OpenAILLMContext and aggregator created.")

#             # Setup Audio Buffer (used for saving audio, not core pipeline logic typically)
#             # If you need to save audio, ensure save_audio function is available
#             audiobuffer = AudioBufferProcessor(
#                 user_continuous_stream=not testing_mode, # Capture continuous stream unless in testing mode
#                 buffer_size=256,
#                 max_buffer_size=1024
#             )
#             logger.debug("AudioBufferProcessor created.")


#             # --- Define the PipeCat Pipeline ---
#             # This is the standard ASR -> LLM -> TTS flow
#             # audiobuffer is typically connected separately for saving, not in the main flow.
#             pipeline = Pipeline(
#                 [
#                     transport.input(),
#                     stt, # Use injected STT
#                     context_aggregator.user(), # Feed STT results to context
#                     llm, # Use injected LLM
#                     tts, # Use injected TTS
#                     transport.output(), # Output TTS to transport
#                     context_aggregator.assistant(), # Add assistant responses to context
#                 ]
#             )
#             logger.debug("Pipeline created.")

#             # --- Create Pipeline Task ---
#             # Ensure sample rates match the Plivo stream and expected pipeline rates
#             pipeline_task = PipelineTask(
#                 pipeline,
#                 params=PipelineParams(
#                     audio_in_sample_rate=sample_rate, # Use actual sample rate from Plivo
#                     audio_out_sample_rate=sample_rate, # Output at the same rate
#                     allow_interruptions=True, # Keep interruptions enabled
#                     enable_metrics=True,
#                     disable_buffers=False # Enable buffering for performance
#                 ),
#             )
#             logger.debug("PipelineTask created.")

#             # --- Instantiate Pipeline Runner ---
#             runner = PipelineRunner(handle_sigint=False, force_gc=True)
#             logger.debug("PipelineRunner created.")

#             # --- Define and Set up Event Handlers ---
#             # These handlers must be defined *within* the scope where the components exist
#             # The logic for the initial greeting now lives here, controlled by 'is_prepared'

#             sent_initial_greeting = False # Flag to ensure greeting is sent only once

#             async def maybe_send_greeting():
#                 nonlocal sent_initial_greeting
#                 if not sent_initial_greeting:
#                     logger.info("Queueing initial bot greeting...")
#                     # This frame triggers the LLM/TTS pipeline for the intro
#                     # Assuming the system prompt and initial context are enough
#                     initial_context_frame = context_aggregator.user().get_context_frame() # This frame signals the bot to start/generate first turn
#                     await pipeline_task.queue_frames([initial_context_frame])
#                     sent_initial_greeting = True
#                     logger.info("Initial greeting queued.")

#             # --- Event Handler: Listen for the first user speech ---
#             # This handler is crucial for the 'wait for user speech' scenario
#             # It fires when STT detects speech and the ContextAggregator processes it.
#             @context_aggregator.event_handler("on_user_context_created")
#             async def on_user_context_created(context_agg):
#                  # This handler fires after *any* user speech is processed.
#                  # We only use it to trigger the greeting IF we are waiting
#                  # (i.e., not prepared) AND the greeting hasn't been sent yet.
#                  if not sent_initial_greeting and not is_prepared:
#                      logger.info("First user speech detected (unprepared call). Triggering initial bot greeting.")
#                      await maybe_send_greeting()
#                  else:
#                      # This branch handles subsequent user inputs *after* the greeting
#                      # or user inputs on prepared calls where greeting is sent immediately.
#                      logger.debug("User context created (subsequent speech or prepared call initial speech).")
#                      # The main pipeline already handles responding to user input
#                      # (context_aggregator.user() -> llm -> tts etc.)
#                      pass # No explicit action needed here to *start* the conversation

#             # --- Optional: Event handler for saving audio ---
#             # If AudioBufferProcessor is used just for saving, connect its input:
#             transport.input() >> audiobuffer # Wire transport input frames to audiobuffer input

#             # Assuming save_audio is defined/imported elsewhere
#             # async def save_audio(server_name, audio, sample_rate, num_channels):
#             #      # Your existing save_audio logic
#             #      pass # Placeholder

#             # @audiobuffer.event_handler("on_audio_data")
#             # async def on_audio_data(buffer, audio, sample_rate, num_channels):
#             #     """Handle audio data event and save to file."""
#             #     # Need access to the websocket client info if server_name depends on it
#             #     # This handler needs access to the websocket context or other ID for naming
#             #     server_name = f"plivo_{call_uuid}" # Example using call_uuid
#             #     output_dir = Path("recordings") # Ensure this directory exists
#             #     output_dir.mkdir(parents=True, exist_ok=True)
#             #     filename = f"{output_dir}/{server_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"

#             #     try:
#             #         # Save as WAV
#             #         with wave.open(str(filename), 'wb') as wf:
#             #             wf.setnchannels(num_channels)
#             #             wf.setsampwidth(2) # L16 is 16-bit PCM (2 bytes)
#             #             wf.setframerate(sample_rate)
#             #             wf.writeframes(audio)
#             #         logger.debug(f"Saved audio chunk to {filename}")
#             #     except Exception as e:
#             #         logger.error(f"Error saving audio chunk: {e}")

#             # (Uncomment and adapt audio saving if needed, ensuring necessary imports like datetime, wave, Path)


#             # --- Start the conversation logic based on preparation status ---
#             # Run this logic as a background task so the main handler can proceed to run the pipeline
#             asyncio.create_task(maybe_send_greeting() if is_prepared else asyncio.sleep(0.1)) # Queue immediately if prepared, otherwise add a tiny delay before starting runner

#             # --- Run the Pipeline Task (This blocks until the task is done/cancelled) ---
#             # The event handlers set up above will trigger based on pipeline events
#             logger.info("Starting Pipeline Runner...")
#             await runner.run(pipeline_task)
#             logger.info("Pipeline Runner finished.")


#         elif data.get('event') == "media":
#             # This should not happen as the first message, but handle subsequent media if not processed by transport
#             logger.warning("Received 'media' event before 'start'. This is unexpected. Ignoring.")
#             # The transport's deserialize method will handle subsequent media frames

#         elif data.get('event') in ["stop", "clearAudioAck", "dtmf", "mark"]:
#              # Log other expected events from Plivo
#              logger.debug(f"Received Plivo WebSocket event: {data.get('event')} for CallUUID {data.get('callUuid')}")

#         else:
#             logger.warning(f"Received unhandled Plivo WebSocket message event: {data.get('event', 'Unknown Event')}. Data: {data}. Closing connection.")
#             await websocket.close()

#     except Exception as e:
#         logger.error(f"Error in Plivo WebSocket communication: {str(e)}")
#         logger.error(traceback.format_exc())
#         # Ensure the websocket is closed in case of error
#         try:
#             await websocket.close()
#         except RuntimeError:
#             # Ignore if websocket is already closed during error handling
#             pass
#     finally:
#         logger.info("Plivo WebSocket connection handler finished.")
#         # Note: WebSocket disconnection might be handled by runner.run exiting


# # Standard entry point to run the FastAPI application using uvicorn
# if __name__ == "__main__":
#     logger.info("Starting FastAPI server.")
#     import uvicorn
#     # You might want to load configuration for host/port from settings/env vars
#     # Ensure app name is correct if file is not named server.py (e.g. "main:app")
#     uvicorn.run("server:app", host="0.0.0.0", port=8765, reload=True)















# server.py

import json
import os
import traceback
import logging
from typing import Optional, Dict, Any
import asyncio
from datetime import datetime # Import datetime for potential audio saving


# Configure logging - using standard logging
# You might want to configure this more extensively or use loguru here
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Import required components ---
# Import run_bot from your bot.py
from bot import run_bot

# Import the Plivo Frame Serializer
# Ensure this import path is correct
try:
    from plivo_serial import PlivoFrameSerializer
    logger.info("Successfully imported PlivoFrameSerializer in server.py.")
except ImportError:
    logger.error("Failed to import PlivoFrameSerializer in server.py. Make sure plivo_serializer.py is in the same directory.")
    PlivoFrameSerializer = None # Set to None to handle gracefully

from fastapi import FastAPI, Request, WebSocket, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles # Uncomment if you need to serve static files

import plivo
# --- Import Plivo signature validation utility (V3) ---
# The v3 validator is directly in plivo.utils
# from plivo.utils import validate_v3_signature # Alternative import if preferred


from dotenv import load_dotenv

load_dotenv()

logger.info("Loading environment variables from .env file")

# --- Plivo Configuration ---
PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN= os.getenv("PLIVO_AUTH_TOKEN")
PLIVO_FROM_NUMBER = os.getenv("PLIVO_FROM_NUMBER") # Used for outbound calls
# NGROK_URL is crucial for generating dynamic webhook URLs
NGROK_URL = os.getenv("NGROK_URL")

# Optional: Testing mode flag
TESTING_MODE = os.getenv("TESTING_MODE", "False").lower() == "true"
logger.info(f"Server Testing Mode: {TESTING_MODE}")


if not NGROK_URL:
     logger.error("⚠️  Error: NGROK_URL environment variable is not set. Webhook and outbound calls will fail.")
     WEBHOOK_BASE_URL = None
else:
    logger.info(f"NGROK_URL loaded: {NGROK_URL}")
    # Ensure base URL is clean and contains scheme (http/https)
    WEBHOOK_BASE_URL = NGROK_URL.rstrip('/')
    # Replace http/https with ws/wss for the WebSocket URL
    # The actual sample rate will be taken from Plivo's 'start' event in the WS endpoint
    PLIVO_STREAM_URL = WEBHOOK_BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://') + "/plivo/stream"

# Construct necessary webhook URLs using the base
PLIVO_ANSWER_URL = f"{WEBHOOK_BASE_URL}/plivo/answer" if WEBHOOK_BASE_URL else None
PLIVO_RING_URL = f"{WEBHOOK_BASE_URL}/plivo/ring" if WEBHOOK_BASE_URL else None
PLIVO_HANGUP_URL = f"{WEBHOOK_BASE_URL}/plivo/hangup" if WEBHOOK_BASE_URL else None


# Initialize Plivo client if credentials are available
if not all([PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN]):
    logger.warning("⚠️  Warning: Missing Plivo configuration (Auth ID/Token). Plivo client will not be initialized.")
    plivo_client = None
else:
    try:
        plivo_client = plivo.RestClient(auth_id=PLIVO_AUTH_ID, auth_token=PLIVO_AUTH_TOKEN)
        logger.info("Plivo client initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize Plivo client: {e}")
        logger.error(traceback.format_exc())
        plivo_client = None


# FastAPI app setup
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Consider restricting this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory store for call preparation status ---
# Key: Plivo CallUUID, Value: Dictionary of preparation state (e.g., {"prepared": True})
# Use a more robust store (Redis, database) for production/scaling
active_call_preparation: Dict[str, Dict[str, Any]] = {}

# --- Helper function for signature validation (V3) ---

async def validate_plivo_signature_v3(request: Request) -> bool:
    """Validates the incoming Plivo webhook signature using V3."""
    if not PLIVO_AUTH_TOKEN:
        logger.warning("Plivo AUTH_TOKEN not set. Skipping signature validation (Development mode).")
        return True # Allow in development if token is not set

    try:
        url = str(request.url)
        method = request.method
        headers = request.headers

        # Get V3 signature headers
        # Prioritize X-Plivo-Signature-Ma-V3 if using main account token
        signature_v3 = headers.get("X-Plivo-Signature-Ma-V3") # Main Account Signature header value
        nonce_v3 = headers.get("X-Plivo-Signature-V3-Nonce") # Nonce header value

        # Check if necessary V3 headers are present
        if not signature_v3 or not nonce_v3:
             logger.warning(f"Missing required Plivo V3 signature headers (X-Plivo-Signature-Ma-V3 or X-Plivo-Signature-V3-Nonce) for {url}. Headers received: {dict(headers)}")
             return False

        params = None
        if method == "POST":
            # Get POST parameters. Ensure it's a dict. Plivo uses form-urlencoded.
            try:
                # Use request.form() for application/x-www-form-urlencoded
                form_data = await request.form()
                # Convert ImmutableMultiDict to dict
                params = dict(form_data)
                #logger.debug(f"Validating signature for POST {url} with params: {params}")
            except Exception as form_error:
                logger.error(f"Error parsing form data for POST {url}: {form_error}")
                # If form parsing fails, we cannot validate. Return False.
                return False

        # Call the Plivo V3 validation function
        # Pass the signature using the keyword 'v3_signature' (as per previous error)
        # Pass the parameters dictionary using the keyword 'params' (as per doc snippet's variable name)
        # If 'params' keyword still fails, try passing the dict positionally after v3_signature.
        try:
            is_valid = plivo.utils.validate_v3_signature(
                method=method,
                uri=url,
                nonce=nonce_v3,
                auth_token=PLIVO_AUTH_TOKEN, # Use your Auth Token
                v3_signature=signature_v3, # Use the Main Account Signature header value here
                # --- FIX: Use 'params' as the keyword argument name for parameters ---
                # If this still fails, try: ..., signature_v3, params) # Pass params positionally
                params=params if method == "POST" else None # Pass params dict if POST, None otherwise
            )
        except TypeError as te:
             # Catch TypeErrors specifically from the validation call itself
             logger.error(f"TypeError when calling validate_v3_signature for {url}: {te}")
             logger.error("This might indicate a mismatch with the Plivo SDK version's function signature.")
             return False # Validation failed due to SDK call error
        except Exception as e:
             # Catch other potential errors during validation calculation
             logger.error(f"Unexpected error during Plivo V3 validation calculation for {url}: {e}")
             return False # Validation failed due to unexpected error


        logger.info(f"Plivo V3 (MA) signature validation result for {url}: {is_valid}")

        if not is_valid:
            logger.error(f"⚠️  Plivo V3 (MA) signature validation failed for {url}. Signature: {signature_v3[:10]}..., Nonce: {nonce_v3[:10]}...") # Mask info
            # Optionally log the assembled string used for validation if you need to debug manually
            # logger.debug(f"Validation string parts: {method}, {url}, {nonce_v3}, {PLIVO_AUTH_TOKEN}, {signature_v3}, {params}")
            return False

        return True

    except Exception as e:
        # Catch errors happening *before* the validate_v3_signature call (e.g. header retrieval, initial form parsing)
        logger.error(f"Error before calling validate_v3_signature for {request.url}: {e}")
        logger.error(traceback.format_exc())
        return False


@app.get("/")
async def root():
    """Root endpoint."""
    logger.info("Root endpoint accessed.")
    return {"message": "Plivo Voice Agent Server is up."}


# --- Plivo Ring Webhook ---
@app.post("/plivo/ring")
async def plivo_ring_webhook(request: Request):
    """Handles Plivo webhook when call starts ringing."""
    logger.info("Plivo Ring webhook accessed.")

    if not await validate_plivo_signature_v3(request):
         return Response(content="<Response><Hangup/></Response>", media_type="application/xml", status_code=403)

    params = await request.form()
    call_uuid = params.get('CallUUID')
    event = params.get('Event')

    logger.info(f"Received Plivo '{event}' event for CallUUID: {call_uuid} (Ringing)")
    # logger.debug(f"Ring webhook parameters: {params}")

    if call_uuid and event == 'Ring':
        # --- Action: Mark call as prepared ---
        active_call_preparation[call_uuid] = {"prepared": True}
        logger.info(f"Marked CallUUID {call_uuid} as prepared.")

        # --- Optional: Start services warm-up here if your services benefit ---
        # You could potentially instantiate services here in background tasks
        # if their __init__ methods are slow but async.
        # This requires moving get_* functions back and adjusting them.
        # Example (requires get_* to be async or return awaitables):
        # try:
        #     asyncio.create_task(asyncio.gather(get_llm(), get_stt(), get_tts(), get_vad()))
        #     logger.info("Services warm-up initiated.")
        # except Exception as e:
        #     logger.warning(f"Failed to initiate service warm-up: {e}")


    # No XML response needed for a ring notification
    return Response(status_code=200)


# --- Plivo Answer Webhook ---
@app.post("/plivo/answer")
async def plivo_answer_webhook(request: Request):
    """Handles Plivo webhook when call is answered."""
    logger.info("Plivo Answer webhook accessed.")

    if not await validate_plivo_signature_v3(request):
         return Response(content="<Response><Hangup/></Response>", media_type="application/xml", status_code=403)

    params = await request.form()
    call_uuid = params.get('CallUUID')
    event = params.get('Event')

    logger.info(f"Received Plivo '{event}' event for CallUUID: {call_uuid} (Answered)")
    # logger.debug(f"Answer webhook parameters: {params}")

    if not PLIVO_STREAM_URL:
         logger.error("PLIVO_STREAM_URL is not set, cannot generate Stream XML response.")
         return Response(content="<Response><Hangup/></Response>", media_type="application/xml", status_code=500)

    # --- Generate Plivo XML to start the media stream ---
    # Use the correct WebSocket endpoint path
    # Ensure sample rate matches PlivoFrameSerializer and pipeline expectations (8000 Hz L16)
    response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        
        <Stream bidirectional="true" audioTrack="inbound" contentType="audio/x-l16;rate=8000" keepCallAlive="true">
          {PLIVO_STREAM_URL}
        </Stream>

    </Response>
    """
    logger.info(f"Generated response XML for Plivo Answer webhook: {response_xml}")

    return Response(content=response_xml, media_type="application/xml")

# --- Plivo Hangup Webhook ---
@app.post("/plivo/hangup")
async def plivo_hangup_webhook(request: Request):
    """Handles Plivo webhook when call is hung up."""
    logger.info("Plivo Hangup webhook accessed.")

    if not await validate_plivo_signature_v3(request):
         return Response(content="<Response><Hangup/></Response>", media_type="application/xml", status_code=403)

    params = await request.form()
    call_uuid = params.get('CallUUID')
    event = params.get('Event')
    hangup_source = params.get('HangupSource')
    hangup_cause = params.get('HangupCause')

    logger.info(f"Received Plivo '{event}' event for CallUUID: {call_uuid} (Hungup)")
    logger.info(f"Hangup Source: {hangup_source}, Hangup Cause: {hangup_cause}")
    # logger.debug(f"Hangup webhook parameters: {params}")

    if call_uuid:
        # --- Action: Clean up call preparation state ---
        if call_uuid in active_call_preparation:
            del active_call_preparation[call_uuid]
            logger.info(f"Cleaned up preparation state for CallUUID {call_uuid}.")

        # You might want to log call duration, recording SID etc.

    # No XML response needed for a hangup notification
    return Response(status_code=200)


# --- Outbound Call Endpoint ---
# Defined at /plivo/call/{to_number} as recommended
@app.post("/start-call")
async def start_plivo_call():
    """Initiates an outbound call using Plivo."""
    logger.info(f"Start Plivo call endpoint accessed for number: +919671454088")
    if not plivo_client:
        logger.error("Plivo client not configured. Cannot initiate call.")
        return {"status": "error", "message": "Plivo client not configured"}, 500

    # Ensure FROM number and Answer/Ring/Hangup URLs are configured
    if not all([PLIVO_FROM_NUMBER, PLIVO_ANSWER_URL, PLIVO_RING_URL, PLIVO_HANGUP_URL]):
         logger.error("Missing Plivo configuration (FROM number, Answer/Ring/Hangup URLs). Cannot initiate call.")
         return {"status": "error", "message": "Missing Plivo configuration for outbound call"}, 500

    # # Basic validation for to_number format
    # if not to_number or not to_number.replace('+', '').isdigit():
    #      logger.error(f"Invalid 'to_number' format: {to_number}")
    #      return {"status": "error", "message": "Invalid 'to_number' format. Must be digits, optionally starting with '+'."}, 400

    try:
        logger.info(f"Attempting to call from {PLIVO_FROM_NUMBER} to +919671454088")
        logger.info(f"  Answer URL: {PLIVO_ANSWER_URL}")
        logger.info(f"  Ring URL:   {PLIVO_RING_URL}")
        logger.info(f"  Hangup URL: {PLIVO_HANGUP_URL}")

        response = plivo_client.calls.create(
            from_=PLIVO_FROM_NUMBER,
            to_="+919671454088",
            answer_url=PLIVO_ANSWER_URL,
            answer_method="POST",
            # --- Include Ring and Hangup URLs ---
            ring_url=PLIVO_RING_URL,
            ring_method="POST",
            hangup_url=PLIVO_HANGUP_URL,
            hangup_method="POST",
            # Optional: Enable recording if needed
            # record="true", # boolean string
            # record_url=f"{WEBHOOK_BASE_URL}/plivo/record", # Add a record webhook handler
            # Optional: Enable machine detection if needed
            # machine_detection="true", # or "hangup"
            # machine_detection_url=f"{WEBHOOK_BASE_URL}/plivo/machine_detection", # Add MD webhook handler
            # machine_detection_method="POST",
        )
        # Plivo's create call returns a ResponseObject, access attributes
        request_uuid = response.request_uuid

        logger.info(f"Outbound call initiated successfully. Request UUID: {request_uuid}")
        return {"status": "success", "request_uuid": request_uuid, "message": "Call request sent to Plivo"}
    except Exception as e:
        logger.error(f"Error initiating outbound call: {str(e)}")
        logger.error(traceback.format_exc())
        # TODO: Inspect Plivo API errors more specifically if possible
        # from plivo.exceptions import PlivoRestError
        # if isinstance(e, PlivoRestError):
        #     return {"status": "error", "message": f"Plivo API Error: {e.status_code} - {e.msg}"}, e.status_code
        return {"status": "error", "message": f"Error initiating call: {str(e)}"}, 500


# --- WebSocket Endpoint for Media Stream ---
@app.websocket("/plivo/stream")
async def plivo_websocket_endpoint(
    websocket: WebSocket,
    # --- Removed Service Dependencies Injection ---
    # Services are now instantiated inside run_bot again, matching your bot.py structure
    # llm: OpenAILLMService = Depends(get_llm), # REMOVED
    # stt: DeepgramSTTService = Depends(get_stt), # REMOVED
    # tts: ElevenLabsTTSService = Depends(get_tts), # REMOVED
    # vad_analyzer: SileroVADAnalyzer = Depends(get_vad) # REMOVED
):
    logger.info("Plivo WebSocket endpoint accessed.")

    await websocket.accept()
    logger.info("Plivo WebSocket connection accepted.")

    # Get testing mode flag (or pass from config)
    testing_mode = os.getenv("TESTING_MODE", "False").lower() == "true"

    try:
        # Plivo sends a 'start' event message as the first message (JSON)
        # This message contains streamId and CallUUID
        message = await websocket.receive_text() # Plivo sends JSON as text
        logger.debug(f"Received initial Plivo WebSocket message: {message}")

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
             logger.error(f"Failed to parse initial Plivo WebSocket message as JSON: {message}. Closing WS.")
             await websocket.close()
             return
        logger.info(f"Data You were looking for: {data}")
        if data.get('event') == "start":
            stream_id = data['start']['streamId']
            call_uuid = data['start']['callId'] # Plivo sends callUuid here!
            logger.info(f"call id you were looking for, : {call_uuid}")
            # Get the actual sample rate from the Plivo 'start' event
            sample_rate = data.get('start', {}).get('media', {}).get('sampleRate', 8000) # Default to 8000 if not present

            if not stream_id or not call_uuid:
                 logger.error(f"Received Plivo 'start' event but missing streamId ({stream_id}) or callUuid ({call_uuid}). Closing WS.")
                 await websocket.close()
                 return

            logger.info(f"Plivo 'start' event received. CallUUID: {call_uuid}, Stream ID: {stream_id}, Sample Rate: {sample_rate}")

            # --- Check if the call was prepared by the ring webhook ---
            # Use pop to get the state and remove it from the dictionary
            preparation_state = active_call_preparation.pop(call_uuid, None)
            is_prepared = preparation_state is not None
            logger.info(f"CallUUID {call_uuid} preparation status: {is_prepared} (from ring webhook)")

            # --- Call run_bot with the necessary parameters ---
            # Pass the websocket, call_uuid, testing mode, and the new start_immediately flag
            await run_bot(websocket, stream_id,
                testing=testing_mode,
                start_immediately=is_prepared # Pass the flag based on ring webhook
            )
            #await run_bot(websocket, stream_id, True)

            logger.info(f"run_bot finished for CallUUID.")


        elif data.get('event') == "media":
            # This should not happen as the first message, but handle subsequent media if not processed by transport
            logger.warning("Received 'media' event before 'start'. This is unexpected. Ignoring.")
            # The transport's deserialize method will handle subsequent media frames

        elif data.get('event') in ["stop", "clearAudioAck", "dtmf", "mark"]:
             # Log other expected events from Plivo
             logger.debug(f"Received Plivo WebSocket event: {data.get('event')} for CallUUID {data.get('callUuid')}")

        else:
            logger.warning(f"Received unhandled Plivo WebSocket message event: {data.get('event', 'Unknown Event')}. Data: {data}. Closing connection.")
            await websocket.close()

    except Exception as e:
        logger.error(f"Error in Plivo WebSocket communication for CallUUID {call_uuid}: {str(e)}")
        logger.error(traceback.format_exc())
        # Ensure the websocket is closed in case of error
        try:
            await websocket.close()
        except RuntimeError:
            # Ignore if websocket is already closed during error handling
            pass
    finally:
        logger.info(f"Plivo WebSocket connection handler finished for CallUUID {call_uuid}.")
        # Clean up state just in case hangup webhook wasn't hit or processed first
        if call_uuid in active_call_preparation:
             del active_call_preparation[call_uuid]
             logger.info(f"Cleaned up preparation state for CallUUID {call_uuid} in finally block.")


# Standard entry point to run the FastAPI application using uvicorn
if __name__ == "__main__":
    logger.info("Starting FastAPI server.")
    import uvicorn
    # Ensure app name is correct if file is not named server.py (e.g. "main:app")
    uvicorn.run("server:app", host="0.0.0.0", port=8765, reload=True)