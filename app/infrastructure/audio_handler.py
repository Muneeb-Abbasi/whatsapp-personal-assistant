"""
Audio handler for downloading and processing WhatsApp voice messages.
"""

import logging
import tempfile
import os
from typing import Optional

import httpx

from app.config.settings import get_settings
from app.ai.speech_to_text import transcribe_audio, transcribe_audio_bytes

logger = logging.getLogger(__name__)
settings = get_settings()


async def download_and_transcribe_audio(
    media_url: str,
    content_type: str
) -> Optional[str]:
    """
    Download audio from Twilio Media URL and transcribe it.
    
    Args:
        media_url: Twilio media URL
        content_type: MIME type of the audio
    
    Returns:
        Transcribed text, or None if failed
    """
    try:
        # Download the audio file from Twilio
        audio_bytes = await download_twilio_media(media_url)
        
        if audio_bytes is None:
            logger.error("Failed to download audio from Twilio")
            return None
        
        # Determine file extension from content type
        extension = get_extension_from_content_type(content_type)
        filename = f"audio.{extension}"
        
        # Transcribe using OpenAI Whisper
        transcribed_text = await transcribe_audio_bytes(audio_bytes, filename)
        
        return transcribed_text
        
    except Exception as e:
        logger.exception(f"Error processing audio: {e}")
        return None


async def download_twilio_media(media_url: str) -> Optional[bytes]:
    """
    Download media from Twilio URL with authentication.
    
    Args:
        media_url: Twilio media URL
    
    Returns:
        Audio bytes, or None if download failed
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                media_url,
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                follow_redirects=True,
                timeout=30.0
            )
            
            if response.status_code == 200:
                logger.info(f"Downloaded audio: {len(response.content)} bytes")
                return response.content
            else:
                logger.error(f"Failed to download audio: {response.status_code}")
                return None
                
    except Exception as e:
        logger.exception(f"Error downloading audio: {e}")
        return None


def get_extension_from_content_type(content_type: str) -> str:
    """
    Get file extension from MIME content type.
    
    Args:
        content_type: MIME type string
    
    Returns:
        File extension (without dot)
    """
    content_type_map = {
        "audio/ogg": "ogg",
        "audio/ogg; codecs=opus": "ogg",
        "audio/opus": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/mp4": "m4a",
        "audio/m4a": "m4a",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/webm": "webm",
        "audio/amr": "amr",
    }
    
    # Normalize content type
    content_type_lower = content_type.lower().strip()
    
    # Try exact match first
    if content_type_lower in content_type_map:
        return content_type_map[content_type_lower]
    
    # Try prefix match
    for key, value in content_type_map.items():
        if content_type_lower.startswith(key.split(";")[0]):
            return value
    
    # Default to ogg (most common for WhatsApp)
    return "ogg"


async def save_audio_to_temp_file(audio_bytes: bytes, extension: str) -> str:
    """
    Save audio bytes to a temporary file.
    
    Args:
        audio_bytes: Raw audio data
        extension: File extension
    
    Returns:
        Path to the temporary file
    """
    temp_file = tempfile.NamedTemporaryFile(
        suffix=f".{extension}",
        delete=False
    )
    temp_file.write(audio_bytes)
    temp_file.close()
    
    logger.info(f"Saved audio to temp file: {temp_file.name}")
    return temp_file.name


def cleanup_temp_file(file_path: str) -> None:
    """
    Delete a temporary file.
    
    Args:
        file_path: Path to the file to delete
    """
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            logger.info(f"Cleaned up temp file: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to cleanup temp file: {e}")
