"""
OpenAI-powered NLP parser for intent detection and entity extraction.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config.settings import get_settings
from app.domain.reminder import ParsedIntent
from app.utils.time import get_current_time_pkt, parse_natural_time

logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

# System prompt for intent parsing
SYSTEM_PROMPT = """You are an AI assistant that parses WhatsApp messages about reminders.
Your task is to extract the user's intent and relevant entities from their message.

Current date and time in Pakistan (PKT): {current_time}

IMPORTANT RULES:
1. Output ONLY valid JSON, nothing else
2. All times should be in ISO 8601 format with Pakistan timezone (+05:00)
3. For relative times like "tomorrow at 9am", calculate the actual datetime
4. Be flexible with natural language - users may not be precise

Possible intents:
- create_reminder: User wants to create a new reminder
- update_reminder: User wants to modify an existing reminder
- delete_reminder: User wants to remove a reminder
- pause_reminder: User wants to pause a reminder
- resume_reminder: User wants to resume a paused reminder
- list_reminders: User wants to see their reminders
- opt_out_calls: User wants to disable phone calls for reminders
- opt_in_calls: User wants to enable phone calls for reminders
- acknowledge: User is acknowledging/responding to a reminder
- unknown: Cannot determine the intent

Output JSON schema:
{{
  "intent": "string (one of the intents above)",
  "title": "string or null (reminder title)",
  "description": "string or null (additional details)",
  "scheduled_time": "string or null (ISO 8601 datetime)",
  "follow_up_minutes": "integer or null (minutes to wait before follow-up)",
  "call_if_no_response": "boolean or null (whether to call if no response)",
  "target_reminder": "string or null (title/keyword to identify existing reminder for update/delete)",
  "response_message": "string (friendly message to send back to user)"
}}

Examples:
- "Remind me to pay electricity bill tomorrow at 9am" → create_reminder
- "Remind me to call Mark before 7pm. If I don't respond, call me." → create_reminder with call_if_no_response=true
- "Pause my wifi reminder" → pause_reminder with target_reminder="wifi"
- "Delete Mark reminder" → delete_reminder with target_reminder="mark"
- "Do not call me if I don't respond" → opt_out_calls
- "List my reminders" → list_reminders
- "ok" or "done" or "thanks" → acknowledge
"""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((APIError, APITimeoutError, RateLimitError)),
    reraise=True
)
async def _call_openai_chat(messages: list, response_format: dict) -> str:
    """
    Make an OpenAI chat completion call with retry logic.
    
    Args:
        messages: Chat messages
        response_format: Response format specification
    
    Returns:
        Response content string
    """
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        response_format=response_format,
        temperature=0.1,
        max_tokens=500
    )
    return response.choices[0].message.content


async def parse_user_message(message: str) -> ParsedIntent:
    """
    Parse a user message to extract intent and entities.
    
    Args:
        message: The user's message text
    
    Returns:
        ParsedIntent object with extracted information
    """
    current_time = get_current_time_pkt()
    
    try:
        result_text = await _call_openai_chat(
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(
                        current_time=current_time.strftime("%Y-%m-%d %H:%M:%S %Z")
                    )
                },
                {
                    "role": "user",
                    "content": message
                }
            ],
            response_format={"type": "json_object"}
        )
        
        # Parse the JSON response
        result = json.loads(result_text)
        
        logger.info(f"Parsed intent: {result.get('intent')}")
        logger.debug(f"Full parse result: {result}")
        
        # Convert scheduled_time string to datetime if present
        scheduled_time = None
        if result.get("scheduled_time"):
            try:
                scheduled_time = datetime.fromisoformat(result["scheduled_time"])
            except ValueError:
                # Try natural language parsing as fallback
                scheduled_time = parse_natural_time(result["scheduled_time"])
        
        return ParsedIntent(
            intent=result.get("intent", "unknown"),
            title=result.get("title"),
            description=result.get("description"),
            scheduled_time=scheduled_time,
            follow_up_minutes=result.get("follow_up_minutes"),
            call_if_no_response=result.get("call_if_no_response"),
            target_reminder=result.get("target_reminder"),
            response_message=result.get("response_message", "I understood your message.")
        )
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        return ParsedIntent(
            intent="unknown",
            response_message="I'm sorry, I had trouble understanding that. Could you try rephrasing?"
        )
    except (APIError, APITimeoutError, RateLimitError) as e:
        logger.error(f"OpenAI API error after retries: {e}")
        return ParsedIntent(
            intent="unknown",
            response_message="I'm having trouble connecting to my AI service. Please try again in a moment."
        )
    except Exception as e:
        logger.exception(f"Error parsing message: {e}")
        return ParsedIntent(
            intent="unknown",
            response_message="I encountered an error processing your message. Please try again."
        )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((APIError, APITimeoutError, RateLimitError)),
    reraise=True
)
async def _call_openai_generate(messages: list) -> str:
    """
    Make an OpenAI chat completion call for response generation with retry logic.
    
    Args:
        messages: Chat messages
    
    Returns:
        Response content string
    """
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=150
    )
    return response.choices[0].message.content.strip()


async def generate_smart_response(context: str, action_result: str) -> str:
    """
    Generate a natural language response using OpenAI.
    
    Args:
        context: What the user asked for
        action_result: What action was taken
    
    Returns:
        Natural language response string
    """
    try:
        return await _call_openai_generate(
            messages=[
                {
                    "role": "system",
                    "content": "You are a friendly WhatsApp reminder assistant. Generate short, helpful responses. Use emojis sparingly. Be concise."
                },
                {
                    "role": "user",
                    "content": f"User request: {context}\nAction taken: {action_result}\n\nGenerate a brief, friendly confirmation message."
                }
            ]
        )
        
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return action_result  # Fallback to the basic action result
