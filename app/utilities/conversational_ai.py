import os
import json
import base64
import queue
import signal
import asyncio
import logging
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
try:
    from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface
    DEFAULT_AUDIO_AVAILABLE = True
except ImportError:
    DEFAULT_AUDIO_AVAILABLE = False
from app.utilities.websocket_audio_interface import WebSocketAudioInterface, NoOpAudioInterface

load_dotenv()

logger = logging.getLogger(__name__)

class ConversationalAI:
    def __init__(self):
        self.agent_id = os.getenv("AGENT_ID")
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.elevenlabs = None
        self.conversation = None
        self.response_queue = queue.Queue()
        self.audio_interface = None
        self.use_websocket_audio = os.getenv("USE_WEBSOCKET_AUDIO", "true").lower() == "true"
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the ElevenLabs client"""
        logger.info(f"Agent ID loaded: {'Yes' if self.agent_id else 'No'}")
        logger.info(f"API Key loaded: {'Yes' if self.api_key else 'No'}")
        logger.info(f"Agent ID: {self.agent_id}")
        if self.api_key:
            self.elevenlabs = ElevenLabs(api_key=self.api_key)
            logger.info("ElevenLabs client initialized successfully")
        else:
            logger.warning("ElevenLabs client not initialized - no API key")

    def initialize_conversation(self):
        """Initialize the ElevenLabs Conversational AI conversation"""
        if not self.elevenlabs or not self.agent_id:
            return False
        try:
            # End any existing conversation first
            if self.conversation:
                try:
                    self.conversation.end_session()
                    logger.info("Previous conversation session ended")
                except Exception as e:
                    logger.error(f"Error ending previous conversation: {e}")
                self.conversation = None
            
            # Clear any existing responses
            while not self.response_queue.empty():
                try:
                    self.response_queue.get_nowait()
                except queue.Empty:
                    break
            
            # Use DefaultAudioInterface for reliable audio output
            # This is the same approach as the working version
            try:
                self.audio_interface = DefaultAudioInterface()
                logger.info("Using DefaultAudioInterface for audio output")
            except Exception as e:
                logger.warning(f"DefaultAudioInterface failed: {e}")
                # Only fall back to NoOpAudioInterface if DefaultAudioInterface completely fails
                self.audio_interface = NoOpAudioInterface()
                logger.info("Falling back to NoOpAudioInterface (audio disabled)")
            
            # Initialize the Conversation instance according to ElevenLabs documentation
            self.conversation = Conversation(
                # API client and agent ID.
                self.elevenlabs,
                self.agent_id,
                # Assume auth is required when API_KEY is set.
                requires_auth=bool(self.api_key),
                # Use the audio interface.
                audio_interface=self.audio_interface,
                # Simple callbacks that put responses in the queue.
                callback_agent_response=lambda response: self.response_queue.put({
                    "type": "agent_response",
                    "text": response
                }),
                callback_agent_response_correction=lambda original, corrected: self.response_queue.put({
                    "type": "agent_response_correction",
                    "original": original,
                    "corrected": corrected
                }),
                callback_user_transcript=lambda transcript: self.response_queue.put({
                    "type": "user_transcript",
                    "text": transcript
                }),
            )
            
            # Start the conversation session
            self.conversation.start_session()
            logger.info("Conversational AI session started successfully")
            return True
        except Exception as e:
            logger.error(f"Error initializing conversation: {e}")
            return False

    def send_text_to_conversation(self, text):
        """Send text message to the conversation"""
        logger.info(f"Attempting to send text to conversation: '{text[:50]}...'")
        if self.conversation:
            try:
                # For Conversational AI, we should use voice input, not text
                # Text input is only for sending messages in voice conversations
                # We'll use TTS to generate audio for text responses instead
                logger.warning("Text input to Conversational AI - this may not generate audio responses")
                self.conversation.send_text(text)
                logger.info("Text sent to conversation successfully")
                return True
            except Exception as e:
                logger.error(f"Error sending text to conversation: {e}")
                return False
        else:
            logger.error("No conversation available")
            return False

    def get_response(self, timeout=10):
        """Get response from the conversation queue"""
        logger.info(f"Waiting for response from conversation queue (timeout: {timeout}s)")
        try:
            response = self.response_queue.get(timeout=timeout)
            logger.info(f"Received response: {response}")
            return response
        except queue.Empty:
            logger.warning(f"No response received within {timeout} seconds")
            return None

    def generate_speech(self, text, voice_id="21m00Tcm4TlvDq8ikWAM"):
        """Generate speech from text using ElevenLabs TTS"""
        logger.info(f"Generating speech for text: '{text[:50]}...'")
        if not self.elevenlabs:
            logger.error("No ElevenLabs client available for TTS")
            return None
        try:
            audio_generator = self.elevenlabs.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_monolingual_v1"
            )
            audio_chunks = []
            for chunk in audio_generator:
                audio_chunks.append(chunk)
            audio_bytes = b''.join(audio_chunks)
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            logger.info(f"Generated audio: {len(audio_bytes)} bytes")
            return f"data:audio/mpeg;base64,{audio_base64}"
        except Exception as e:
            logger.error(f"Error generating speech: {e}")
            return None

    def end_conversation(self):
        """End the conversation session"""
        if self.conversation:
            try:
                self.conversation.end_session()
                print("Conversation session ended")
            except Exception as e:
                print(f"Error ending conversation: {e}")

    def is_initialized(self):
        """Check if the conversational AI is properly initialized"""
        return self.elevenlabs is not None and self.agent_id is not None

# Global instance
convo_ai = ConversationalAI()

# Signal handler for clean shutdown
def signal_handler(sig, frame):
    convo_ai.end_conversation()
    print("\n👋 Shutting down Billie. Goodbye!")

signal.signal(signal.SIGINT, signal_handler)
