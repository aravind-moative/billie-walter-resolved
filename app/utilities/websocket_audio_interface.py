import asyncio
import base64
import json
import queue
import logging
from typing import Optional, Any, Callable
from elevenlabs.conversational_ai.conversation import AudioInterface

logger = logging.getLogger(__name__)


class WebSocketAudioInterface(AudioInterface):
    """
    Custom audio interface for ElevenLabs that works with WebSocket connections.
    This replaces the DefaultAudioInterface which requires server-side audio hardware.
    """

    def __init__(self):
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.websocket = None
        self.is_running = False
        self.audio_callback = None
        logger.info("WebSocketAudioInterface initialized")

    def set_websocket(self, websocket):
        """Set the WebSocket connection for this audio interface"""
        self.websocket = websocket
        logger.info("WebSocket connection set for audio interface")

    def set_audio_callback(self, callback: Callable[[bytes], None]):
        """Set callback for handling audio output from ElevenLabs"""
        self.audio_callback = callback
        logger.info("Audio callback set")

    def start(self, input_callback: Callable[[bytes], None]) -> None:
        """Start the audio interface"""
        self.is_running = True
        logger.info("WebSocketAudioInterface started")
        
        # Start a thread to handle input audio
        import threading
        self.input_thread = threading.Thread(target=self._handle_input, args=(input_callback,))
        self.input_thread.daemon = True
        self.input_thread.start()

    def stop(self) -> None:
        """Stop the audio interface"""
        self.is_running = False
        logger.info("WebSocketAudioInterface stopped")

    def _handle_input(self, input_callback: Callable[[bytes], None]):
        """Handle input audio from the queue"""
        while self.is_running:
            try:
                audio_data = self.input_queue.get(timeout=0.1)
                if audio_data and input_callback:
                    input_callback(audio_data)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error handling input audio: {e}")

    def output(self, audio: bytes) -> None:
        """Handle output audio from ElevenLabs"""
        logger.info(f"WebSocketAudioInterface.output() called with {len(audio)} bytes of audio")
        
        if self.audio_callback:
            try:
                # Create a task to run the async callback
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Schedule the callback to run
                        asyncio.create_task(self.audio_callback(audio))
                        logger.info("Audio callback scheduled successfully")
                    else:
                        # Run in the current loop
                        loop.run_until_complete(self.audio_callback(audio))
                        logger.info("Audio callback executed in current loop")
                except RuntimeError:
                    # No event loop, queue for later
                    self.output_queue.put(audio)
                    logger.info("Audio queued due to no event loop")
            except Exception as e:
                logger.error(f"Error in audio callback: {e}")
                # Fallback to queue
                self.output_queue.put(audio)
        else:
            # Queue the output for later retrieval
            self.output_queue.put(audio)
            logger.info("Audio queued (no callback set)")

    def interrupt(self) -> None:
        """Interrupt the current audio playback"""
        # Clear output queue
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break
        logger.info("Audio playback interrupted")

    def add_audio_input(self, audio_data: bytes):
        """Add audio input from the browser to the queue"""
        self.input_queue.put(audio_data)

    def get_audio_output(self, timeout: float = 0.1) -> Optional[bytes]:
        """Get audio output from the queue"""
        try:
            return self.output_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    async def send_audio_to_websocket(self, audio_data: bytes):
        """Send audio output to the WebSocket client"""
        if self.websocket:
            try:
                # Convert audio to base64 for WebSocket transmission
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                await self.websocket.send_text(json.dumps({
                    "type": "audio_stream",
                    "audio": f"data:audio/mpeg;base64,{audio_base64}"
                }))
            except Exception as e:
                logger.error(f"Error sending audio to WebSocket: {e}")


class NoOpAudioInterface(AudioInterface):
    """
    No-operation audio interface for when audio is not needed.
    This prevents errors when DefaultAudioInterface would fail on servers.
    """

    def __init__(self):
        logger.info("NoOpAudioInterface initialized (audio disabled)")

    def start(self, input_callback: Callable[[bytes], None]) -> None:
        """Start the audio interface (no-op)"""
        logger.info("NoOpAudioInterface started (no-op)")

    def stop(self) -> None:
        """Stop the audio interface (no-op)"""
        logger.info("NoOpAudioInterface stopped (no-op)")

    def output(self, audio: bytes) -> None:
        """Handle output audio (no-op)"""
        pass

    def interrupt(self) -> None:
        """Interrupt audio playback (no-op)"""
        pass