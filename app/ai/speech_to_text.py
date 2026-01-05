"""
OpenAI Speech-to-Text integration for voice message transcription.
"""

import logging
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

# Supported audio formats for Whisper
SUPPORTED_FORMATS = ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm", "ogg"]


async def transcribe_audio(audio_file_path: str) -> Optional[str]:
    """
    Transcribe an audio file using OpenAI Whisper.
    
    Args:
        audio_file_path: Path to the audio file
    
    Returns:
        Transcribed text, or None if transcription fails
    """
    try:
        file_path = Path(audio_file_path)
        
        if not file_path.exists():
            logger.error(f"Audio file not found: {audio_file_path}")
            return None
        
        logger.info(f"Transcribing audio file: {file_path.name}")
        
        with open(file_path, "rb") as audio_file:
            response = await openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en",  # Can be made configurable
                response_format="text"
            )
        
        transcribed_text = response.strip()
        logger.info(f"Transcription successful: {transcribed_text[:100]}...")
        
        return transcribed_text
        
    except Exception as e:
        logger.exception(f"Error transcribing audio: {e}")
        return None


async def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "audio.ogg") -> Optional[str]:
    """
    Transcribe audio from bytes using OpenAI Whisper.
    
    Args:
        audio_bytes: Raw audio bytes
        filename: Filename with extension for format detection
    
    Returns:
        Transcribed text, or None if transcription fails
    """
    try:
        logger.info(f"Transcribing audio bytes ({len(audio_bytes)} bytes)")
        
        # Create a file-like object from bytes
        from io import BytesIO
        audio_buffer = BytesIO(audio_bytes)
        audio_buffer.name = filename
        
        response = await openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_buffer,
            language="en",
            response_format="text"
        )
        
        transcribed_text = response.strip()
        logger.info(f"Transcription successful: {transcribed_text[:100]}...")
        
        return transcribed_text
        
    except Exception as e:
        logger.exception(f"Error transcribing audio bytes: {e}")
        return None
