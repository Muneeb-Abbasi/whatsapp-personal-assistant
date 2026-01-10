"""
Twilio WhatsApp messaging integration with retry logic.
"""

import logging
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize Twilio client
twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(TwilioRestException),
    reraise=True
)
def _send_message_sync(message: str, from_number: str, to_number: str):
    """
    Synchronous Twilio message send with retry logic.
    
    Args:
        message: Text message to send
        from_number: Sender's WhatsApp number
        to_number: Recipient's WhatsApp number
    
    Returns:
        Twilio message object
    """
    return twilio_client.messages.create(
        body=message,
        from_=from_number,
        to=to_number
    )


async def send_whatsapp_message(message: str, to_number: str = None) -> bool:
    """
    Send a WhatsApp text message.
    
    Args:
        message: Text message to send
        to_number: Recipient WhatsApp number (defaults to configured user)
    
    Returns:
        True if message sent successfully, False otherwise
    """
    if to_number is None:
        to_number = settings.user_whatsapp_number
    
    try:
        msg = _send_message_sync(
            message=message,
            from_number=settings.twilio_whatsapp_number,
            to_number=to_number
        )
        logger.info(f"WhatsApp message sent successfully. SID: {msg.sid}")
        return True
    except TwilioRestException as e:
        logger.error(f"Failed to send WhatsApp message after retries: {e}")
        return False


async def send_reminder_notification(
    reminder_title: str,
    reminder_description: str = None,
    to_number: str = None
) -> bool:
    """
    Send a formatted reminder notification.
    
    Args:
        reminder_title: Title of the reminder
        reminder_description: Optional description
        to_number: Recipient WhatsApp number
    
    Returns:
        True if message sent successfully
    """
    message = f"⏰ *Reminder*: {reminder_title}"
    
    if reminder_description:
        message += f"\n\n{reminder_description}"
    
    message += "\n\n_Reply to acknowledge this reminder._"
    
    return await send_whatsapp_message(message, to_number)


async def send_confirmation(action: str, details: str, to_number: str = None) -> bool:
    """
    Send a confirmation message for an action.
    
    Args:
        action: Action that was performed (e.g., "created", "deleted")
        details: Details about the action
        to_number: Recipient WhatsApp number
    
    Returns:
        True if message sent successfully
    """
    message = f"✅ {action}\n\n{details}"
    return await send_whatsapp_message(message, to_number)


async def send_error_message(error: str, to_number: str = None) -> bool:
    """
    Send an error message to the user.
    
    Args:
        error: Error description
        to_number: Recipient WhatsApp number
    
    Returns:
        True if message sent successfully
    """
    message = f"❌ Sorry, something went wrong:\n\n{error}\n\nPlease try again."
    return await send_whatsapp_message(message, to_number)
