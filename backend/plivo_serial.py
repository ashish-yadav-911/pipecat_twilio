

from loguru import logger
import base64
import json

from pydantic import BaseModel

from pipecat.frames.frames import AudioRawFrame, Frame, InputAudioRawFrame, StartInterruptionFrame
from pipecat.serializers.base_serializer import FrameSerializer, FrameSerializerType


class PlivoFrameSerializer(FrameSerializer):
    class InputParams(BaseModel):
        # Plivo media stream is L16, can be 8kHz or 16kHz
        sample_rate: int = 8000 # Assuming 16kHz L16 based on the serialize method payload sampleRate

    def __init__(self, stream_id: str, params: InputParams = InputParams()):
        self._stream_id = stream_id
        self._params = params
        # Note: The original Plivo serializer didn't have a setup method
        # or handle pipeline sample rate differences, unlike the Twilio one.
        # This might be a point to address later if your pipeline runs at 8kHz.

    @property
    def type(self) -> FrameSerializerType:
        return FrameSerializerType.TEXT

    # FIX: Make serialize async
    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, AudioRawFrame):
            # IMPORTANT NOTE: This serializer assumes the input frame is raw L16
            # at the sample rate expected by Plivo (e.g., 16kHz).
            # If your pipeline outputs audio at a different rate (like 8kHz),
            # you will need to add resampling logic here, similar to the Twilio serializer.
            payload = base64.b64encode(frame.audio).decode("utf-8")
            answer = {
                "event": "playAudio",
                "media": {
                    "contentType": "audio/x-l16",
                    "sampleRate": self._params.sample_rate, # Use the configured sample rate
                    "payload": payload
                },
            }
            return json.dumps(answer)

        if isinstance(frame, StartInterruptionFrame):
            # This matches the 'clearAudio' event documented for Plivo Media Stream.
            # Ensure the streamId matches what Plivo expects.
            answer = {"event": "clearAudio", "streamId": self._stream_id}
            return json.dumps(answer)

        # The Plivo serializer doesn't handle TransportMessageFrame/UrgentFrame.
        # Add handling if needed, similar to the Twilio serializer.

        return None

    # FIX: Make deserialize async
    async def deserialize(self, data: str | bytes) -> Frame | None:
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            # Handle potential errors with invalid JSON
            logger.error(f"Failed to decode JSON from Plivo WebSocket: {data}")
            return None # Or raise an exception

        if message.get("event") == "media":
            payload_base64 = message.get("media", {}).get("payload")
            if not payload_base64:
                 logger.warning(f"Received 'media' event with no payload: {message}")
                 return None

            try:
                payload = base64.b64decode(payload_base64)
            except base64.binascii.Error:
                 logger.error(f"Failed to base64 decode payload from Plivo WebSocket: {payload_base64[:50]}...")
                 return None

            # IMPORTANT NOTE: This serializer assumes the incoming audio is raw L16
            # at the sample rate specified in InputParams (defaulting to 16kHz).
            # If Plivo sends 8kHz, or if your pipeline needs 8kHz, you will
            # need to add format conversion (L16 is easier than u-law) and/or
            # resampling logic here, similar to the Twilio serializer.
            audio_frame = InputAudioRawFrame(
                audio=payload, num_channels=1, sample_rate=self._params.sample_rate
            )
            return audio_frame
        elif message.get("event") in ["connected", "start", "stop", "mark", "dtmf", "clearAudioAck"]:
             # Plivo sends other events. You might want to log them or handle specific ones.
             # The Twilio serializer handled 'dtmf'. You might need to add that for Plivo if needed.
             # Plivo DTMF is typically sent as a separate 'dtmf' event.
             # Example: {"event": "dtmf", "streamId": "...", "dtmf": {"digit": "1", "timestamp": "..."}}
             # You would need to add an elif message.get("event") == "dtmf": ...
             # and create an InputDTMFFrame similar to the Twilio serializer.
            logger.debug(f"Received Plivo WebSocket event: {message.get('event')}")
            return None # Ignore other events for now
        else:
            logger.warning(f"Received unhandled Plivo WebSocket event: {message}")
            return None
