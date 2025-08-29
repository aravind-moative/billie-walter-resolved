import json
import base64
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.utilities.conversational_ai import convo_ai

websocket_router = APIRouter()
logger = logging.getLogger(__name__)


@websocket_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("WebSocket connection established")
    await websocket.accept()
    logger.info("WebSocket connection accepted")
    
    # Always initialize a fresh conversation for each WebSocket connection
    logger.info("Initializing conversation...")
    if not convo_ai.initialize_conversation():
        logger.error("Failed to initialize conversation")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "ElevenLabs credentials not configured. Please set ELEVENLABS_API_KEY and AGENT_ID in .env file"
        }))
        # Don't return, allow the connection to continue for testing
    else:
        logger.info("Conversation initialized successfully")
    
    # Note: We're now using DefaultAudioInterface which handles audio output directly
    # The WebSocket will receive text responses and generate audio via TTS
    logger.info("Using DefaultAudioInterface - audio will be handled by system audio")
    
    try:
        while True:
            # Receive data from client
            logger.info("Waiting for WebSocket message...")
            data = await websocket.receive_text()
            logger.info(f"Received WebSocket message: {data[:100]}...")
            message = json.loads(data)
            logger.info(f"Message type: {message.get('type', 'unknown')}")
            
            if message["type"] == "text_question":
                # Handle text questions (for suggestion buttons)
                question = message["question"]
                
                try:
                    # Check if ElevenLabs is available
                    if not convo_ai.is_initialized():
                        # Fallback response when ElevenLabs is not configured
                        fallback_response = f"I received your message: '{question}'. ElevenLabs AI is not configured yet. Please set up your API credentials to enable full conversational AI."
                        await websocket.send_text(json.dumps({
                            "type": "response",
                            "text": fallback_response,
                            "audio": None
                        }))
                    else:
                        # For text-based interactions, we'll use TTS to generate audio
                        # since Conversational AI is designed for voice conversations
                        logger.info(f"Processing text question: '{question}'")
                        if convo_ai.send_text_to_conversation(question):
                            logger.info("Text sent to conversation, waiting for response...")
                            # Wait for response from the agent
                            response = convo_ai.get_response(timeout=10)
                            
                            if response:
                                logger.info(f"Received response: {response}")
                                if response["type"] == "agent_response":
                                    response_text = response["text"]
                                    logger.info(f"Agent response text: '{response_text[:100]}...'")
                                    
                                    # Generate speech response using TTS
                                    logger.info("Generating speech for response...")
                                    audio_data = convo_ai.generate_speech(response_text)
                                    logger.info(f"Audio data generated: {'Yes' if audio_data else 'No'}")
                                    
                                    await websocket.send_text(json.dumps({
                                        "type": "response",
                                        "text": response_text,
                                        "audio": audio_data
                                    }))
                                    logger.info("Response sent to WebSocket client")
                                    
                                elif response["type"] == "user_transcript":
                                    # Display user's transcript
                                    await websocket.send_text(json.dumps({
                                        "type": "transcript",
                                        "text": response["text"]
                                    }))
                            else:
                                await websocket.send_text(json.dumps({
                                    "type": "error",
                                    "message": "No response from agent within timeout"
                                }))
                        else:
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "message": "Failed to send message to agent"
                            }))
                            
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Error processing text question: {str(e)}"
                    }))
                    
            elif message["type"] == "audio_message":
                # Handle audio messages from browser
                audio_data = message["audio"]
                
                try:
                    # Acknowledge the audio
                    await websocket.send_text(json.dumps({
                        "type": "audio_received",
                        "message": "Audio received successfully"
                    }))
                    
                    # Check if ElevenLabs is available
                    if not convo_ai.is_initialized():
                        # Fallback response for audio when ElevenLabs is not configured
                        fallback_response = "I received your voice message! ElevenLabs AI is not configured yet. Please set up your API credentials to enable voice processing."
                        await websocket.send_text(json.dumps({
                            "type": "response",
                            "text": fallback_response,
                            "audio": None
                        }))
                    else:
                        # Process browser audio through our WebSocket audio interface
                        if hasattr(convo_ai, 'audio_interface') and hasattr(convo_ai.audio_interface, 'add_audio_input'):
                            # Convert base64 audio to bytes if needed
                            if isinstance(audio_data, str) and audio_data.startswith('data:'):
                                # Extract base64 part from data URL
                                base64_data = audio_data.split(',')[1]
                                audio_bytes = base64.b64decode(base64_data)
                            else:
                                audio_bytes = audio_data
                            
                            # Feed audio to the conversation through our interface
                            # This should trigger the Conversational AI to process the audio
                            convo_ai.audio_interface.add_audio_input(audio_bytes)
                            
                            # Get response from the conversation
                            response = convo_ai.get_response(timeout=10)
                            
                            if response:
                                if response["type"] == "agent_response":
                                    response_text = response["text"]
                                    
                                    # For voice conversations, the audio should come from the conversation
                                    # Check if we have audio from the conversation
                                    audio_output = None
                                    if hasattr(convo_ai, 'audio_interface') and hasattr(convo_ai.audio_interface, 'get_audio_output'):
                                        audio_output = convo_ai.audio_interface.get_audio_output(timeout=1.0)
                                    
                                    if audio_output:
                                        # Use audio from conversation
                                        import base64
                                        audio_base64 = base64.b64encode(audio_output).decode('utf-8')
                                        audio_data = f"data:audio/mpeg;base64,{audio_base64}"
                                    else:
                                        # Fallback to TTS
                                        audio_data = convo_ai.generate_speech(response_text)
                                    
                                    await websocket.send_text(json.dumps({
                                        "type": "response",
                                        "text": response_text,
                                        "audio": audio_data
                                    }))
                                elif response["type"] == "user_transcript":
                                    await websocket.send_text(json.dumps({
                                        "type": "transcript",
                                        "text": response["text"]
                                    }))
                            else:
                                await websocket.send_text(json.dumps({
                                    "type": "error",
                                    "message": "No response from agent for audio message"
                                }))
                        else:
                            # Fallback to text-based processing
                            logger.warning("WebSocket audio interface not available, using text fallback")
                            placeholder_text = "I received your audio message"
                            
                            if convo_ai.send_text_to_conversation(placeholder_text):
                                response = convo_ai.get_response(timeout=10)
                                
                                if response and response["type"] == "agent_response":
                                    response_text = response["text"]
                                    audio_data = convo_ai.generate_speech(response_text)
                                    
                                    await websocket.send_text(json.dumps({
                                        "type": "response",
                                        "text": response_text,
                                        "audio": audio_data
                                    }))
                                else:
                                    await websocket.send_text(json.dumps({
                                        "type": "error",
                                        "message": "Failed to get response"
                                    }))
                            else:
                                await websocket.send_text(json.dumps({
                                    "type": "error",
                                    "message": "Failed to process audio message"
                                }))
                    
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Error processing audio: {str(e)}"
                    }))
                    
    except WebSocketDisconnect:
        logger.info("Client disconnected")
        if convo_ai.conversation:
            convo_ai.end_conversation()
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if convo_ai.conversation:
            convo_ai.end_conversation()
