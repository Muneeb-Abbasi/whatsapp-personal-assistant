"""
Time utilities for Pakistan Standard Time (PKT) handling.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
import re

from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta

# Pakistan Standard Time
PKT = ZoneInfo("Asia/Karachi")


def get_current_time_pkt() -> datetime:
    """Get the current time in Pakistan timezone."""
    return datetime.now(PKT)


def to_pkt(dt: datetime) -> datetime:
    """
    Convert a datetime to Pakistan timezone.
    
    Args:
        dt: Datetime to convert (can be naive or aware)
    
    Returns:
        Datetime in PKT timezone
    """
    if dt.tzinfo is None:
        # Assume naive datetime is in PKT
        return dt.replace(tzinfo=PKT)
    return dt.astimezone(PKT)


def from_pkt_to_utc(dt: datetime) -> datetime:
    """
    Convert a PKT datetime to UTC.
    
    Args:
        dt: Datetime in PKT
    
    Returns:
        Datetime in UTC
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=PKT)
    return dt.astimezone(ZoneInfo("UTC"))


def parse_natural_time(time_str: str, reference_time: datetime = None) -> Optional[datetime]:
    """
    Parse natural language time expressions into datetime.
    
    Args:
        time_str: Natural language time string (e.g., "tomorrow at 9am")
        reference_time: Reference time for relative expressions (defaults to now in PKT)
    
    Returns:
        Parsed datetime in PKT, or None if parsing fails
    """
    if reference_time is None:
        reference_time = get_current_time_pkt()
    
    time_str = time_str.lower().strip()
    
    # Handle relative day expressions
    day_offset = 0
    time_part = time_str
    
    if "tomorrow" in time_str:
        day_offset = 1
        time_part = time_str.replace("tomorrow", "").strip()
    elif "day after tomorrow" in time_str:
        day_offset = 2
        time_part = time_str.replace("day after tomorrow", "").strip()
    elif "today" in time_str:
        day_offset = 0
        time_part = time_str.replace("today", "").strip()
    elif "next week" in time_str:
        day_offset = 7
        time_part = time_str.replace("next week", "").strip()
    
    # Clean up common words
    time_part = time_part.replace("at", "").replace("on", "").strip()
    
    # Handle "in X minutes/hours" patterns
    in_pattern = r"in\s+(\d+)\s*(minute|min|hour|hr|day)s?"
    in_match = re.search(in_pattern, time_str)
    if in_match:
        amount = int(in_match.group(1))
        unit = in_match.group(2)
        
        if unit in ["minute", "min"]:
            return reference_time + timedelta(minutes=amount)
        elif unit in ["hour", "hr"]:
            return reference_time + timedelta(hours=amount)
        elif unit == "day":
            return reference_time + timedelta(days=amount)
    
    # Handle "before Xpm/am" patterns
    before_pattern = r"before\s+(\d{1,2})\s*(am|pm)"
    before_match = re.search(before_pattern, time_str)
    if before_match:
        hour = int(before_match.group(1))
        ampm = before_match.group(2)
        
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        
        target_date = reference_time.date() + timedelta(days=day_offset)
        return datetime(target_date.year, target_date.month, target_date.day, hour, 0, tzinfo=PKT)
    
    # Try to parse the time part
    if time_part:
        try:
            # Handle simple time formats like "9am", "7pm", "14:30"
            parsed_time = dateutil_parser.parse(time_part, fuzzy=True)
            target_date = reference_time.date() + timedelta(days=day_offset)
            
            result = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                parsed_time.hour,
                parsed_time.minute,
                tzinfo=PKT
            )
            
            # If the time has already passed today and no day offset, assume tomorrow
            if day_offset == 0 and result < reference_time:
                result += timedelta(days=1)
            
            return result
        except (ValueError, TypeError):
            pass
    
    # If only day offset but no time, default to 9:00 AM
    if day_offset > 0:
        target_date = reference_time.date() + timedelta(days=day_offset)
        return datetime(target_date.year, target_date.month, target_date.day, 9, 0, tzinfo=PKT)
    
    # Try dateutil parser as fallback
    try:
        parsed = dateutil_parser.parse(time_str, fuzzy=True)
        return to_pkt(parsed)
    except (ValueError, TypeError):
        return None


def format_time_pkt(dt: datetime, include_date: bool = True) -> str:
    """
    Format a datetime for display in PKT.
    
    Args:
        dt: Datetime to format
        include_date: Whether to include the date
    
    Returns:
        Formatted string
    """
    dt_pkt = to_pkt(dt)
    
    if include_date:
        return dt_pkt.strftime("%B %d, %Y at %I:%M %p PKT")
    else:
        return dt_pkt.strftime("%I:%M %p PKT")


def get_relative_time_description(dt: datetime) -> str:
    """
    Get a human-readable relative time description.
    
    Args:
        dt: Target datetime
    
    Returns:
        Relative description like "in 2 hours" or "tomorrow at 9:00 AM"
    """
    now = get_current_time_pkt()
    dt_pkt = to_pkt(dt)
    
    diff = dt_pkt - now
    
    if diff.total_seconds() < 0:
        return "in the past"
    
    if diff.total_seconds() < 3600:  # Less than an hour
        minutes = int(diff.total_seconds() / 60)
        return f"in {minutes} minute{'s' if minutes != 1 else ''}"
    
    if diff.total_seconds() < 86400:  # Less than a day
        hours = int(diff.total_seconds() / 3600)
        return f"in {hours} hour{'s' if hours != 1 else ''}"
    
    # Check if it's tomorrow
    tomorrow = now.date() + timedelta(days=1)
    if dt_pkt.date() == tomorrow:
        return f"tomorrow at {dt_pkt.strftime('%I:%M %p')}"
    
    # Otherwise, show the full date
    days = diff.days
    return f"in {days} day{'s' if days != 1 else ''} ({dt_pkt.strftime('%B %d at %I:%M %p')})"
