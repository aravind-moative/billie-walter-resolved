import os
from typing import Optional

from dotenv import load_dotenv
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

load_dotenv()


class TextToSpeech:
    def __init__(self):
        self.client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
        self.default_voice_id = "UgBBYS2sOqTuMpoF3BR0"  # Adam pre-made voice
        self.default_model_id = "eleven_flash_v2_5"

    def convert_text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        stability: float = 0.0,
        similarity_boost: float = 1.0,
        style: float = 0.0,
        use_speaker_boost: bool = True,
    ) -> bytes:
        """
        Convert text to speech using ElevenLabs API.

        Args:
            text: The text to convert to speech
            voice_id: Optional voice ID to use (defaults to Adam voice)
            model_id: Optional model ID to use (defaults to turbo model)
            stability: Voice stability setting (0.0 to 1.0)
            similarity_boost: Voice similarity boost setting (0.0 to 1.0)
            style: Voice style setting (0.0 to 1.0)
            use_speaker_boost: Whether to use speaker boost

        Returns:
            bytes: The audio data in MP3 format
        """
        # Clean text by removing any markdown-style formatting
        cleaned_text = text.replace("**", "")

        # Use default values if not provided
        voice_id = voice_id or self.default_voice_id
        model_id = model_id or self.default_model_id

        # Call text_to_speech API
        print(cleaned_text)
        response = self.client.text_to_speech.convert(
            voice_id=voice_id,
            output_format="mp3_22050_32",
            text=cleaned_text,
            model_id=model_id,
            voice_settings=VoiceSettings(
                stability=stability,
                similarity_boost=similarity_boost,
                style=style,
                use_speaker_boost=use_speaker_boost,
            ),
        )

        return response
