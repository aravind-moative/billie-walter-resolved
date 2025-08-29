# Audio Interface Fix for Cloud Deployment

## Problem Identified

The application was failing when deployed to EC2 or Lightsail instances with errors related to audio interface creation. After investigation, the root cause was identified in `app/utilities/conversational_ai.py` at line 63:

```python
audio_interface=DefaultAudioInterface()
```

### Why It Failed

1. **Server-Side Audio Dependency**: The `DefaultAudioInterface()` from ElevenLabs SDK attempts to create a server-side audio interface using system audio devices via `sounddevice` and `pyaudio` libraries.

2. **No Audio Hardware in Cloud**: Cloud servers (EC2, Lightsail) don't have:
   - Physical microphones or speakers
   - Audio drivers or subsystems
   - ALSA/PulseAudio services

3. **Architectural Mismatch**: Even if server audio worked, it wouldn't connect to the user's browser - the audio needs to flow from the user's microphone through their browser to the server.

## Solution Implemented

### 1. Created Custom Audio Interface (`app/utilities/websocket_audio_interface.py`)

Created two new audio interface classes:

- **`WebSocketAudioInterface`**: Bridges browser audio to ElevenLabs via WebSocket
  - Receives audio from browser via WebSocket
  - Forwards to ElevenLabs conversation API
  - Returns responses back through WebSocket
  - No server-side audio hardware required

- **`NoOpAudioInterface`**: Fallback interface when audio isn't needed
  - Prevents crashes when audio subsystem unavailable
  - Allows text-only operation

### 2. Updated Conversational AI (`app/utilities/conversational_ai.py`)

- Added environment variable `USE_WEBSOCKET_AUDIO` (defaults to `true` for cloud compatibility)
- Modified `initialize_conversation()` to accept optional WebSocket connection
- Implements intelligent audio interface selection:
  ```python
  if USE_WEBSOCKET_AUDIO and websocket:
      # Use WebSocket-based audio for cloud
      audio_interface = WebSocketAudioInterface()
  elif DEFAULT_AUDIO_AVAILABLE and not USE_WEBSOCKET_AUDIO:
      # Use default audio for local development only
      audio_interface = DefaultAudioInterface()
  else:
      # Fallback to no-op interface
      audio_interface = NoOpAudioInterface()
  ```

### 3. Updated WebSocket Handler (`app/routes/websocket.py`)

- Passes WebSocket connection to conversation initialization
- Properly handles browser audio data (base64 decoding)
- Routes audio through the custom WebSocket interface
- Maintains backward compatibility for text messages

## Configuration Guide

### For Cloud Deployment (EC2, Lightsail, etc.)

Add to your `.env` file:
```bash
# Enable WebSocket audio for cloud deployment
USE_WEBSOCKET_AUDIO=true

# Your ElevenLabs credentials
ELEVENLABS_API_KEY=your_api_key_here
AGENT_ID=your_agent_id_here
```

### For Local Development (Optional)

If you want to use local system audio during development:
```bash
# Use system audio interface locally
USE_WEBSOCKET_AUDIO=false
```

## How It Works Now

1. **Browser Side**: 
   - User clicks microphone button in browser
   - Browser captures audio via `getUserMedia()`
   - Audio encoded as base64 and sent via WebSocket

2. **Server Side**:
   - Receives audio through WebSocket connection
   - Routes to ElevenLabs via `WebSocketAudioInterface`
   - No server audio hardware needed
   - Processes responses and sends back to browser

3. **Cloud Compatible**:
   - No dependency on server audio subsystems
   - Works on headless servers
   - All audio processing happens in browser and ElevenLabs API

## Benefits

- ✅ **Cloud Ready**: Works on EC2, Lightsail, and any headless server
- ✅ **No Audio Dependencies**: Doesn't require ALSA, PulseAudio, or audio drivers
- ✅ **Browser-Based**: Audio capture happens in user's browser
- ✅ **Fallback Support**: Gracefully degrades to text-only if needed
- ✅ **Backward Compatible**: Still supports local audio for development

## Testing Recommendations

1. **Local Testing**:
   ```bash
   # Test with WebSocket audio (cloud mode)
   USE_WEBSOCKET_AUDIO=true python run.py
   ```

2. **Deployment Testing**:
   - Deploy to EC2/Lightsail with `USE_WEBSOCKET_AUDIO=true`
   - Ensure HTTPS is configured (required for `getUserMedia()`)
   - Test microphone permissions in browser

3. **Verify Audio Flow**:
   - Check browser console for audio capture logs
   - Monitor server logs for WebSocket audio routing
   - Confirm ElevenLabs responses are received

## Troubleshooting

If audio still doesn't work after deployment:

1. **Check HTTPS**: Browser microphone access requires HTTPS in production
2. **Verify Environment Variables**: Ensure `USE_WEBSOCKET_AUDIO=true` is set
3. **Check ElevenLabs Credentials**: Confirm API key and Agent ID are correct
4. **Browser Permissions**: User must grant microphone permission
5. **WebSocket Connection**: Ensure WebSocket can connect through any reverse proxy/load balancer

## Future Improvements

Consider implementing:
- Audio compression before transmission to reduce bandwidth
- WebRTC for peer-to-peer audio streaming
- Audio quality indicators in UI
- Automatic reconnection on WebSocket disconnect
- Server-side speech-to-text as fallback