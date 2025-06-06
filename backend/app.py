import json
import os
from fastapi import FastAPI, Request, WebSocket, Response, requests
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import plivo
#import requests
from bot import run_bot  # Your voice agent logic
from dotenv import load_dotenv
from logger import logger
import asyncio

load_dotenv()

logger.info("Loading environment variables from .env file")

# Load Plivo credentials from environment
PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN= os.getenv("PLIVO_AUTH_TOKEN")
PLIVO_FROM_NUMBER = os.getenv("PLIVO_FROM_NUMBER",+918035737766)
PLIVO_TO_NUMBER = os.getenv("PLIVO_TO_NUMBER",+919671454088)
NGROK_URL = os.getenv("NGROK_URL")
PLIVO_ANSWER_XML = os.getenv("PLIVO_ANSWER_XML") or f"{NGROK_URL}/webhook"


# Initialize Plivo client if credentials are available
if not all([PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN, PLIVO_FROM_NUMBER, PLIVO_TO_NUMBER, PLIVO_ANSWER_XML]):
    logger.error("⚠️  Warning: Missing Plivo configuration. Outbound call initiation will not work.")
    plivo_client = None
else:
    plivo_client = plivo.RestClient(auth_id=PLIVO_AUTH_ID, auth_token=PLIVO_AUTH_TOKEN)

# FastAPI app setup
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    logger.info("Root endpoint accessed.")
    return {"message": "Voice Agent Server is up."}


@app.post("/webhook")
async def webhook_handler(request: Request):
    logger.info("Webhook endpoint accessed.")
    print("✅ Incoming call received from Plivo.")

    response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        
        <Stream bidirectional="true" audioTrack="inbound" contentType="audio/x-l16;rate=8000" keepCallAlive="true">
          ws://f0d9-49-36-144-48.ngrok-free.app/stream
        </Stream>

    </Response>
    """
    #logger.info("Generated response XML for webhook.", response_xml)
    return Response(content=response_xml, media_type="application/xml")

@app.post("/start-call")
async def start_plivo_call():
    logger.info("Start call endpoint accessed.")
    if not plivo_client:
        logger.error("Plivo client not configured.")
        return {"status": "error", "message": "Plivo client not configured"}

    try:
        response = plivo_client.calls.create(
            from_=PLIVO_FROM_NUMBER,
            to_=PLIVO_TO_NUMBER,
            answer_url=PLIVO_ANSWER_XML,
            answer_method="POST"
        )
        logger.info(f"Outbound call initiated successfully. Call UUID: {response['request_uuid']}")
        return {"status": "success", "call_uuid": response['request_uuid']}
    except Exception as e:
        logger.error(f"Error initiating outbound call: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("WebSocket endpoint accessed.")
    await websocket.accept()
    try:
        message = await websocket.receive()
        textFromWebSocket = message.get('text', None)
        if textFromWebSocket is None:
            logger.warning("No text received from WebSocket.")
            return
        data = json.loads(textFromWebSocket)
        logger.info(f"Received data from WebSocket: {message}")
        if data['event'] == "start":
            stream_id = data['start']['streamId']
            logger.info(f"WebSocket connection accepted. Stream ID: {stream_id}")
            await run_bot(websocket, stream_id, True)
            #asyncio.create_task(run_bot(websocket, stream_id, True))

    except Exception as e:
        logger.error(f"Error in WebSocket communication: {str(e)}")
    finally:
        logger.info("WebSocket connection closed.")

# @app.websocket("/stream")
# async def websocket_endpoint(websocket: WebSocket):
#     logger.info("WebSocket endpoint accessed.")
#     await websocket.accept()
#     try:
#         stream_id = None
#         # start the bot only after receiving a "start" event
#         while True:
#             message = await websocket.receive()
#             textFromWebSocket = message.get('text', None)
#             if textFromWebSocket is None:
#                 logger.warning("No text received from WebSocket.")
#                 continue  # wait for next message
            
#             data = json.loads(textFromWebSocket)
            
#             if data.get('event') == "start":
#                 stream_id = data['start']['streamId']
#                 logger.info(f"WebSocket connection accepted. Stream ID: {stream_id}")
#                 asyncio.create_task(run_bot(websocket, stream_id, True))

#             elif data.get('event') == "stop":
#                 logger.info(f"Stopping stream {stream_id}")
#                 break  # Exit the loop and close connection

#     except Exception as e:
#         logger.error(f"Error in WebSocket communication: {str(e)}")
#     finally:
#         await websocket.close()
#         logger.info("WebSocket connection closed.")


if __name__ == "__main__":
    logger.info("Starting FastAPI server.")
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8765, reload=True)





#     #ws_url = NGROK_URL.replace("https://", "").replace("http://", "")
#     #print("---------------",ws_url) https://81d3-49-36-144-2.ngrok-free.app

#     # <Response>
        
#     #     <Stream bidirectional="true" audioTrack="inbound" contentType="audio/x-l16;rate=8000" keepCallAlive="true">
#     #       ws://81d3-49-36-144-2.ngrok-free.app/stream
#     #     </Stream>

#     # </Response>




#         # <Stream url="wss://{ws_url}/stream" />
#         # <Stream bidirectional="true" audioTrack="inbound" contentType="audio/x-l16;rate=8000" keepCallAlive="true"
#         #   wss://{ws_url}/stream
#         # </Stream>
#         #<Speak>Connecting you to the voice assistant.</Speak>