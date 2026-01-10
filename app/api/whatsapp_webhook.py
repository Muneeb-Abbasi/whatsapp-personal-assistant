"""
WhatsApp webhook endpoint for receiving messages from Twilio.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import Response
from twilio.request_validator import RequestValidator
from sqlalchemy import select, delete

from app.config.settings import get_settings
from app.infrastructure.database import DatabaseSession, async_session_factory
from app.infrastructure.twilio_whatsapp import send_whatsapp_message, send_error_message
from app.infrastructure.audio_handler import download_and_transcribe_audio
from app.ai.nlp_parser import parse_user_message
from app.usecases.reminder_service import ReminderService
from app.domain.processed_message import ProcessedMessage

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


async def is_message_processed(message_sid: str) -> bool:
    """
    Check if a message has already been processed using SQLite.
    
    Args:
        message_sid: Twilio message SID
    
    Returns:
        True if message was already processed
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(ProcessedMessage).where(ProcessedMessage.message_sid == message_sid)
        )
        return result.scalar_one_or_none() is not None


async def mark_message_processed(message_sid: str) -> None:
    """
    Mark a message as processed in SQLite.
    
    Args:
        message_sid: Twilio message SID
    """
    async with async_session_factory() as session:
        processed_msg = ProcessedMessage(
            message_sid=message_sid,
            processed_at=datetime.utcnow()
        )
        session.add(processed_msg)
        await session.commit()


async def cleanup_old_processed_messages(days: int = 7) -> None:
    """
    Remove processed messages older than specified days.
    Called periodically to prevent table from growing indefinitely.
    
    Args:
        days: Number of days to retain messages
    """
    async with async_session_factory() as session:
        cutoff = datetime.utcnow() - timedelta(days=days)
        await session.execute(
            delete(ProcessedMessage).where(ProcessedMessage.processed_at < cutoff)
        )
        await session.commit()


def validate_twilio_signature(request: Request, body: Optional[bytes]) -> bool:
    """
    Validate the Twilio webhook signature.
    
    Args:
        request: FastAPI request object
        body: Raw request body
    
    Returns:
        True if signature is valid
    """
    if not settings.validate_twilio_signature:
        return True
    
    validator = RequestValidator(settings.twilio_auth_token)
    
    # Get the signature from headers
    signature = request.headers.get("X-Twilio-Signature", "")
    
    # Build the full URL
    url = str(request.url)
    
    # Parse form data for validation
    from urllib.parse import parse_qs
    params = parse_qs(body.decode("utf-8"))
    # Convert lists to single values
    params = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
    
    return validator.validate(url, params, signature)


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(...),
    MessageSid: str = Form(...),
    NumMedia: str = Form(default="0"),
    MediaUrl0: Optional[str] = Form(default=None),
    MediaContentType0: Optional[str] = Form(default=None),
):
    """
    Handle incoming WhatsApp messages from Twilio.
    
    This endpoint processes both text and audio messages.
    Audio messages are transcribed using OpenAI before processing.
    """
    # Note: Cannot read request.body() here as Form() already consumed the stream
    # Signature validation is skipped when VALIDATE_TWILIO_SIGNATURE=false
    
    # Validate Twilio signature (skip body validation when disabled)
    if not validate_twilio_signature(request, None):
        logger.warning(f"Invalid Twilio signature for message {MessageSid}")
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # Idempotency check - prevent duplicate processing (persisted in SQLite)
    if await is_message_processed(MessageSid):
        logger.info(f"Message {MessageSid} already processed, skipping")
        return Response(content="", media_type="text/xml")
    
    # Mark message as processed immediately to prevent race conditions
    await mark_message_processed(MessageSid)
    
    logger.info(f"Received message from {From}, SID: {MessageSid}")
    
    try:
        message_text = Body.strip()
        
        # Check if this is an audio message
        num_media = int(NumMedia)
        if num_media > 0 and MediaContentType0 and "audio" in MediaContentType0.lower():
            logger.info(f"Processing audio message: {MediaContentType0}")
            # Download and transcribe audio
            message_text = await download_and_transcribe_audio(
                media_url=MediaUrl0,
                content_type=MediaContentType0
            )
            
            if not message_text:
                await send_error_message(
                    "I couldn't understand your voice message. Please try again or send a text message."
                )
                return Response(content="", media_type="text/xml")
            
            logger.info(f"Transcribed audio: {message_text}")
        
        # Skip empty messages
        if not message_text:
            logger.info("Empty message received, skipping")
            return Response(content="", media_type="text/xml")
        
        # Parse the message using NLP
        parsed_intent = await parse_user_message(message_text)
        
        # Process the intent
        async with DatabaseSession() as session:
            service = ReminderService(session)
            response = await service.handle_intent(parsed_intent)
        
        # Send response back to user
        await send_whatsapp_message(response)
        
    except Exception as e:
        logger.exception(f"Error processing message: {e}")
        await send_error_message(str(e))
    
    # Return empty TwiML response (we're sending messages via API)
    return Response(content="", media_type="text/xml")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "whatsapp-assistant"}
