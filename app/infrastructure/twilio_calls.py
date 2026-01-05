"""
Twilio Voice integration for phone call reminders.
"""

import logging
from typing import Optional

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from twilio.twiml.voice_response import VoiceResponse

from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize Twilio client
twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)


async def make_reminder_call(reminder_title: str, to_number: str = None) -> bool:
    """
    Make a phone call to remind the user.
    
    Args:
        reminder_title: Title of the reminder to speak
        to_number: Phone number to call (defaults to configured user)
    
    Returns:
        True if call initiated successfully
    """
    if to_number is None:
        to_number = settings.user_phone_number
    
    try:
        # Generate TwiML for the call
        twiml = generate_reminder_twiml(reminder_title)
        
        call = twilio_client.calls.create(
            twiml=twiml,
            to=to_number,
            from_=settings.twilio_phone_number,
            timeout=30,  # Ring for 30 seconds
        )
        
        logger.info(f"Initiated reminder call. SID: {call.sid}")
        return True
        
    except TwilioRestException as e:
        logger.error(f"Failed to make reminder call: {e}")
        return False
    except Exception as e:
        logger.exception(f"Error making reminder call: {e}")
        return False


def generate_reminder_twiml(reminder_title: str) -> str:
    """
    Generate TwiML for a reminder phone call.
    
    Args:
        reminder_title: Title of the reminder
    
    Returns:
        TwiML string
    """
    response = VoiceResponse()
    
    # Add a pause before speaking
    response.pause(length=1)
    
    # Speak the reminder message
    response.say(
        f"This is your WhatsApp reminder assistant. "
        f"You have a reminder: {reminder_title}. "
        f"Please check your WhatsApp for more details.",
        voice="alice",
        language="en-US"
    )
    
    # Repeat once
    response.pause(length=2)
    response.say(
        f"Again, your reminder is: {reminder_title}. "
        f"Please check your WhatsApp.",
        voice="alice",
        language="en-US"
    )
    
    # Say goodbye
    response.pause(length=1)
    response.say(
        "Goodbye.",
        voice="alice",
        language="en-US"
    )
    
    return str(response)


async def check_call_capability() -> bool:
    """
    Check if the Twilio account can make voice calls.
    
    Returns:
        True if voice calling is available
    """
    try:
        # Try to fetch the phone number to verify it exists and can make calls
        numbers = twilio_client.incoming_phone_numbers.list(
            phone_number=settings.twilio_phone_number,
            limit=1
        )
        
        if numbers:
            logger.info("Voice calling capability verified")
            return True
        else:
            logger.warning("Configured phone number not found in Twilio account")
            return False
            
    except TwilioRestException as e:
        logger.error(f"Error checking call capability: {e}")
        return False
