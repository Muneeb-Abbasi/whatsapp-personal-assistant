"""
OpenAI-powered NLP parser for intent detection and entity extraction.
Supports conversation history for context-aware responses.
"""

import json
import logging
from datetime import datetime
from typing import Optional, List

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
Current day of week: {current_day}
Today's date: {today_date}

CRITICAL DATE CALCULATION RULES:
When user mentions a day name (Monday, Tuesday, etc.), calculate the date as follows:
1. Find TODAY's day number (Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6)
2. Find TARGET day number
3. Calculate days_ahead = (target_day - today_day) % 7
4. If days_ahead == 0 and time has passed, add 7 days (next week)
5. Add days_ahead to today's date

EXAMPLES (if today is {current_day} {today_date}):
- "Thursday" means the UPCOMING Thursday = {thursday_date}
- "tomorrow" means {tomorrow_date}
- "Monday" means the UPCOMING Monday (could be this week or next)
- "next Thursday" means the Thursday AFTER the upcoming Thursday

IMPORTANT: "Thursday" when said on Wednesday means TOMORROW, not next week!

IMPORTANT RULES:
1. Output ONLY valid JSON, nothing else
2. All times should be in ISO 8601 format with Pakistan timezone (+05:00)
3. For relative times like "tomorrow at 9am", calculate the actual datetime
4. Be flexible with natural language - users may not be precise
5. Use conversation history to understand context and follow-up questions
6. When user refers to "it", "that", "the reminder", look at recent context

NUMBERED REFERENCES:
- When user says "delete 1 and 2" or "delete 1 & 2" after listing reminders, they mean reminders by list position
- Use target_indices array for numbered references: [1, 2] means first and second reminder
- "remind me about 3 later" means snooze/reschedule the 3rd reminder from the list

Possible intents:
- create_reminder: User wants to create a new reminder
- update_reminder: User wants to modify an existing reminder
- delete_reminder: User wants to remove a reminder (single)
- delete_reminders: User wants to remove multiple reminders (use target_indices)
- pause_reminder: User wants to pause a reminder
- resume_reminder: User wants to resume a paused reminder
- list_reminders: User wants to see their reminders
- get_reminder_info: User is asking about a specific reminder's details (time, title, etc.)
- opt_out_calls: User wants to disable phone calls for reminders
- opt_in_calls: User wants to enable phone calls for reminders
- acknowledge: User is acknowledging/responding to a reminder
- snooze_reminder: User wants to be reminded later about something
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
  "target_indices": "array of integers or null (for numbered references like 'delete 1 & 2')",
  "response_message": "string (friendly message to send back to user)"
}}

Examples:
- "Remind me to pay electricity bill tomorrow at 9am" → create_reminder
- "Monday 5pm call mom" (on Sunday) → create_reminder for TOMORROW (upcoming Monday)
- "Remind me to call Mark before 7pm. If I don't respond, call me." → create_reminder with call_if_no_response=true
- "Pause my wifi reminder" → pause_reminder with target_reminder="wifi"
- "Delete Mark reminder" → delete_reminder with target_reminder="mark"
- "Delete 1 and 2" or "delete 1 & 2" → delete_reminders with target_indices=[1,2]
- "What time is the Jds reminder?" → get_reminder_info with target_reminder="Jds"
- "Do not call me if I don't respond" → opt_out_calls
- "List my reminders" → list_reminders
- "ok" or "done" or "thanks" → acknowledge
- "remind me about this later" → snooze_reminder
{quoted_context}"""

# Quoted message context template
QUOTED_CONTEXT_TEMPLATE = """
QUOTED MESSAGE CONTEXT:
The user is replying to this previous message: "{quoted_message}"
Use this context to understand what the user is referring to.
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


async def parse_user_message(
    message: str,
    conversation_history: Optional[List[dict]] = None,
    quoted_message: Optional[str] = None
) -> ParsedIntent:
    """
    Parse a user message to extract intent and entities.
    
    Args:
        message: The user's message text
        conversation_history: Optional list of previous messages for context
        quoted_message: Optional quoted/replied-to message for context
    
    Returns:
        ParsedIntent object with extracted information
    """
    current_time = get_current_time_pkt()
    
    # Pre-calculate dates for the prompt to help GPT
    from datetime import timedelta
    today_date = current_time.strftime("%Y-%m-%d")
    tomorrow_date = (current_time + timedelta(days=1)).strftime("%Y-%m-%d (%A)")
    
    # Calculate upcoming Thursday
    current_weekday = current_time.weekday()  # Monday=0, Sunday=6
    thursday_weekday = 3
    days_until_thursday = (thursday_weekday - current_weekday) % 7
    if days_until_thursday == 0:
        days_until_thursday = 7  # If today is Thursday, next Thursday
    thursday_date = (current_time + timedelta(days=days_until_thursday)).strftime("%Y-%m-%d (%A)")
    
    # Build quoted context section
    quoted_context = ""
    if quoted_message:
        quoted_context = QUOTED_CONTEXT_TEMPLATE.format(quoted_message=quoted_message)
    
    # Build messages array with history
    messages = []
    
    # System prompt
    messages.append({
        "role": "system",
        "content": SYSTEM_PROMPT.format(
            current_time=current_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            current_day=current_time.strftime("%A"),
            today_date=today_date,
            tomorrow_date=tomorrow_date,
            thursday_date=thursday_date,
            quoted_context=quoted_context
        )
    })
    
    # Add conversation history for context (last 10 exchanges)
    if conversation_history:
        messages.extend(conversation_history[-20:])  # 10 exchanges = 20 messages
    
    # Current user message
    messages.append({
        "role": "user",
        "content": message
    })
    
    try:
        result_text = await _call_openai_chat(
            messages=messages,
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
        
        # Parse target_indices
        target_indices = result.get("target_indices")
        if target_indices and not isinstance(target_indices, list):
            target_indices = None
        
        return ParsedIntent(
            intent=result.get("intent", "unknown"),
            title=result.get("title"),
            description=result.get("description"),
            scheduled_time=scheduled_time,
            follow_up_minutes=result.get("follow_up_minutes"),
            call_if_no_response=result.get("call_if_no_response"),
            target_reminder=result.get("target_reminder"),
            target_indices=target_indices,
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
