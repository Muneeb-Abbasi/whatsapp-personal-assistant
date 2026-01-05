"""
Reminder service for handling all reminder-related operations.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import select, update, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.reminder import (
    Reminder, 
    ReminderStatus, 
    ReminderCreate, 
    ReminderUpdate,
    ParsedIntent
)
from app.utils.time import (
    get_current_time_pkt, 
    to_pkt, 
    format_time_pkt, 
    get_relative_time_description
)
from app.infrastructure.scheduler import schedule_reminder, cancel_reminder_jobs

logger = logging.getLogger(__name__)


class ReminderService:
    """Service class for reminder operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def handle_intent(self, intent: ParsedIntent) -> str:
        """
        Handle a parsed intent and return a response message.
        
        Args:
            intent: Parsed intent from NLP
        
        Returns:
            Response message to send to user
        """
        intent_handlers = {
            "create_reminder": self._handle_create,
            "update_reminder": self._handle_update,
            "delete_reminder": self._handle_delete,
            "pause_reminder": self._handle_pause,
            "resume_reminder": self._handle_resume,
            "list_reminders": self._handle_list,
            "opt_out_calls": self._handle_opt_out,
            "opt_in_calls": self._handle_opt_in,
            "acknowledge": self._handle_acknowledge,
        }
        
        handler = intent_handlers.get(intent.intent)
        
        if handler:
            try:
                return await handler(intent)
            except Exception as e:
                logger.exception(f"Error handling intent {intent.intent}: {e}")
                return f"Sorry, I encountered an error: {str(e)}"
        else:
            return intent.response_message or "I'm not sure what you'd like me to do. Try saying something like 'Remind me to...' or 'List my reminders'."
    
    async def _handle_create(self, intent: ParsedIntent) -> str:
        """Handle create reminder intent."""
        if not intent.title:
            return "I need a title for your reminder. What would you like to be reminded about?"
        
        if not intent.scheduled_time:
            return "When would you like to be reminded? Please include a time, like 'tomorrow at 9am'."
        
        # Check for duplicate reminders (same title within 5 minutes)
        existing = await self._find_similar_reminder(intent.title, intent.scheduled_time)
        if existing:
            return f"You already have a similar reminder: *{existing.title}* scheduled for {format_time_pkt(existing.scheduled_time)}."
        
        # Create the reminder
        reminder = Reminder(
            id=str(uuid4()),
            title=intent.title,
            description=intent.description,
            scheduled_time=to_pkt(intent.scheduled_time),
            follow_up_minutes=intent.follow_up_minutes,
            call_if_no_response=intent.call_if_no_response or False,
            call_opt_out=not (intent.call_if_no_response or False),  # Opt-out by default unless explicitly requested
            status=ReminderStatus.ACTIVE,
        )
        
        self.session.add(reminder)
        await self.session.commit()
        
        # Schedule the reminder
        await schedule_reminder(reminder)
        
        logger.info(f"Created reminder: {reminder.id} - {reminder.title}")
        
        # Build response
        response = f"✅ *Reminder created!*\n\n"
        response += f"📌 *{reminder.title}*\n"
        response += f"⏰ {format_time_pkt(reminder.scheduled_time)}\n"
        response += f"📅 ({get_relative_time_description(reminder.scheduled_time)})"
        
        if reminder.follow_up_minutes:
            response += f"\n⏳ Follow-up: {reminder.follow_up_minutes} minutes after"
        
        if reminder.call_if_no_response and not reminder.call_opt_out:
            response += f"\n📞 Will call if no response"
        
        return response
    
    async def _handle_update(self, intent: ParsedIntent) -> str:
        """Handle update reminder intent."""
        if not intent.target_reminder:
            return "Which reminder would you like to update? Please mention its name."
        
        reminder = await self._find_reminder_by_keyword(intent.target_reminder)
        if not reminder:
            return f"I couldn't find a reminder matching '{intent.target_reminder}'. Try 'list my reminders' to see your active reminders."
        
        # Apply updates
        updated_fields = []
        
        if intent.title:
            reminder.title = intent.title
            updated_fields.append("title")
        
        if intent.description:
            reminder.description = intent.description
            updated_fields.append("description")
        
        if intent.scheduled_time:
            reminder.scheduled_time = to_pkt(intent.scheduled_time)
            updated_fields.append("time")
            # Reschedule
            await cancel_reminder_jobs(reminder.id)
            await schedule_reminder(reminder)
        
        if intent.follow_up_minutes is not None:
            reminder.follow_up_minutes = intent.follow_up_minutes
            updated_fields.append("follow-up time")
        
        if intent.call_if_no_response is not None:
            reminder.call_if_no_response = intent.call_if_no_response
            reminder.call_opt_out = not intent.call_if_no_response
            updated_fields.append("call settings")
        
        reminder.updated_at = datetime.utcnow()
        await self.session.commit()
        
        if updated_fields:
            return f"✅ Updated *{reminder.title}*\n\nChanged: {', '.join(updated_fields)}"
        else:
            return f"No changes were made to *{reminder.title}*."
    
    async def _handle_delete(self, intent: ParsedIntent) -> str:
        """Handle delete reminder intent."""
        if not intent.target_reminder:
            return "Which reminder would you like to delete? Please mention its name."
        
        reminder = await self._find_reminder_by_keyword(intent.target_reminder)
        if not reminder:
            return f"I couldn't find a reminder matching '{intent.target_reminder}'."
        
        title = reminder.title
        
        # Cancel scheduled jobs
        await cancel_reminder_jobs(reminder.id)
        
        # Delete the reminder
        await self.session.delete(reminder)
        await self.session.commit()
        
        logger.info(f"Deleted reminder: {title}")
        
        return f"🗑️ Deleted reminder: *{title}*"
    
    async def _handle_pause(self, intent: ParsedIntent) -> str:
        """Handle pause reminder intent."""
        if not intent.target_reminder:
            return "Which reminder would you like to pause? Please mention its name."
        
        reminder = await self._find_reminder_by_keyword(intent.target_reminder)
        if not reminder:
            return f"I couldn't find a reminder matching '{intent.target_reminder}'."
        
        if reminder.status == ReminderStatus.PAUSED:
            return f"*{reminder.title}* is already paused."
        
        reminder.status = ReminderStatus.PAUSED
        reminder.updated_at = datetime.utcnow()
        await self.session.commit()
        
        # Cancel scheduled jobs
        await cancel_reminder_jobs(reminder.id)
        
        return f"⏸️ Paused: *{reminder.title}*\n\nSay 'resume {intent.target_reminder} reminder' to reactivate it."
    
    async def _handle_resume(self, intent: ParsedIntent) -> str:
        """Handle resume reminder intent."""
        if not intent.target_reminder:
            return "Which reminder would you like to resume? Please mention its name."
        
        reminder = await self._find_reminder_by_keyword(intent.target_reminder)
        if not reminder:
            return f"I couldn't find a reminder matching '{intent.target_reminder}'."
        
        if reminder.status == ReminderStatus.ACTIVE:
            return f"*{reminder.title}* is already active."
        
        # Check if the scheduled time has passed
        now = get_current_time_pkt()
        if to_pkt(reminder.scheduled_time) < now:
            return f"*{reminder.title}* was scheduled for the past. Please update the time first."
        
        reminder.status = ReminderStatus.ACTIVE
        reminder.updated_at = datetime.utcnow()
        await self.session.commit()
        
        # Reschedule
        await schedule_reminder(reminder)
        
        return f"▶️ Resumed: *{reminder.title}*\n\nScheduled for {format_time_pkt(reminder.scheduled_time)}"
    
    async def _handle_list(self, intent: ParsedIntent) -> str:
        """Handle list reminders intent."""
        result = await self.session.execute(
            select(Reminder)
            .where(Reminder.status.in_([ReminderStatus.ACTIVE, ReminderStatus.PAUSED]))
            .order_by(Reminder.scheduled_time)
        )
        reminders = result.scalars().all()
        
        if not reminders:
            return "📭 You don't have any active reminders.\n\nSay 'Remind me to...' to create one!"
        
        response = f"📋 *Your Reminders* ({len(reminders)})\n\n"
        
        for i, r in enumerate(reminders, 1):
            status_icon = "⏸️" if r.status == ReminderStatus.PAUSED else "✅"
            call_icon = "📞" if r.call_if_no_response and not r.call_opt_out else ""
            
            response += f"{i}. {status_icon} *{r.title}* {call_icon}\n"
            response += f"    ⏰ {format_time_pkt(r.scheduled_time, include_date=True)}\n"
            
            if r.status == ReminderStatus.ACTIVE:
                response += f"    📅 {get_relative_time_description(r.scheduled_time)}\n"
            
            response += "\n"
        
        return response.strip()
    
    async def _handle_opt_out(self, intent: ParsedIntent) -> str:
        """Handle opt-out from calls intent."""
        # Update all active reminders to opt-out from calls
        result = await self.session.execute(
            update(Reminder)
            .where(Reminder.status == ReminderStatus.ACTIVE)
            .values(call_opt_out=True, call_if_no_response=False)
        )
        await self.session.commit()
        
        return "🔕 *Phone calls disabled*\n\nI won't call you for any reminders. You'll only receive WhatsApp messages."
    
    async def _handle_opt_in(self, intent: ParsedIntent) -> str:
        """Handle opt-in for calls intent."""
        # Note: This doesn't automatically enable calls, just removes the opt-out
        result = await self.session.execute(
            update(Reminder)
            .where(Reminder.status == ReminderStatus.ACTIVE)
            .values(call_opt_out=False)
        )
        await self.session.commit()
        
        return "🔔 *Phone calls enabled*\n\nI can now call you for reminders that have call notifications enabled."
    
    async def _handle_acknowledge(self, intent: ParsedIntent) -> str:
        """Handle acknowledgment of a reminder."""
        # Find the most recently notified reminder
        result = await self.session.execute(
            select(Reminder)
            .where(
                Reminder.status == ReminderStatus.ACTIVE,
                Reminder.last_notified_at.isnot(None),
                Reminder.user_responded == False
            )
            .order_by(Reminder.last_notified_at.desc())
            .limit(1)
        )
        reminder = result.scalar_one_or_none()
        
        if reminder:
            reminder.user_responded = True
            reminder.status = ReminderStatus.COMPLETED
            reminder.updated_at = datetime.utcnow()
            await self.session.commit()
            
            # Cancel any follow-up jobs
            await cancel_reminder_jobs(reminder.id)
            
            return f"👍 Got it! Marked *{reminder.title}* as completed."
        else:
            return "👍 Thanks for your response!"
    
    async def _find_reminder_by_keyword(self, keyword: str) -> Optional[Reminder]:
        """Find a reminder by fuzzy matching on title."""
        keyword_lower = keyword.lower()
        
        # First try exact match
        result = await self.session.execute(
            select(Reminder)
            .where(
                Reminder.status.in_([ReminderStatus.ACTIVE, ReminderStatus.PAUSED]),
                func.lower(Reminder.title).contains(keyword_lower)
            )
            .order_by(Reminder.created_at.desc())
            .limit(1)
        )
        reminder = result.scalar_one_or_none()
        
        if reminder:
            return reminder
        
        # Try word-by-word matching
        result = await self.session.execute(
            select(Reminder)
            .where(Reminder.status.in_([ReminderStatus.ACTIVE, ReminderStatus.PAUSED]))
        )
        reminders = result.scalars().all()
        
        for r in reminders:
            title_words = r.title.lower().split()
            if any(keyword_lower in word or word in keyword_lower for word in title_words):
                return r
        
        return None
    
    async def _find_similar_reminder(
        self, 
        title: str, 
        scheduled_time: datetime, 
        time_window_minutes: int = 5
    ) -> Optional[Reminder]:
        """Find a similar reminder to prevent duplicates."""
        time_min = scheduled_time - timedelta(minutes=time_window_minutes)
        time_max = scheduled_time + timedelta(minutes=time_window_minutes)
        
        result = await self.session.execute(
            select(Reminder)
            .where(
                Reminder.status == ReminderStatus.ACTIVE,
                func.lower(Reminder.title) == title.lower(),
                Reminder.scheduled_time.between(time_min, time_max)
            )
            .limit(1)
        )
        
        return result.scalar_one_or_none()
    
    async def mark_reminder_notified(self, reminder_id: str) -> None:
        """Mark a reminder as having sent a notification."""
        result = await self.session.execute(
            select(Reminder).where(Reminder.id == reminder_id)
        )
        reminder = result.scalar_one_or_none()
        
        if reminder:
            reminder.last_notified_at = datetime.utcnow()
            reminder.user_responded = False
            await self.session.commit()
    
    async def check_user_responded(self, reminder_id: str) -> bool:
        """Check if the user has responded to a reminder."""
        result = await self.session.execute(
            select(Reminder.user_responded).where(Reminder.id == reminder_id)
        )
        responded = result.scalar_one_or_none()
        return responded or False
