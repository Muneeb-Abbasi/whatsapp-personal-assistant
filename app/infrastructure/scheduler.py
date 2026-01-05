"""
APScheduler setup with persistent job store for reminder scheduling.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.date import DateTrigger

from app.config.settings import get_settings
from app.utils.time import to_pkt, from_pkt_to_utc

logger = logging.getLogger(__name__)
settings = get_settings()

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler instance."""
    global scheduler
    
    if scheduler is None:
        # Use SQLite for persistent job storage
        jobstores = {
            'default': SQLAlchemyJobStore(url='sqlite:///jobs.db')
        }
        
        scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone='Asia/Karachi'
        )
    
    return scheduler


async def start_scheduler() -> None:
    """Start the scheduler."""
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        logger.info("Scheduler started")


async def stop_scheduler() -> None:
    """Stop the scheduler gracefully."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")


async def schedule_reminder(reminder) -> None:
    """
    Schedule a reminder notification.
    
    Args:
        reminder: Reminder model instance
    """
    from app.domain.reminder import ReminderStatus
    
    if reminder.status != ReminderStatus.ACTIVE:
        logger.info(f"Skipping scheduling for non-active reminder: {reminder.id}")
        return
    
    sched = get_scheduler()
    
    # Schedule the main reminder notification
    job_id = f"reminder_{reminder.id}"
    
    # Convert to PKT-aware datetime
    scheduled_time = to_pkt(reminder.scheduled_time)
    
    try:
        sched.add_job(
            send_reminder_notification,
            trigger=DateTrigger(run_date=scheduled_time),
            id=job_id,
            replace_existing=True,
            kwargs={
                'reminder_id': reminder.id,
                'title': reminder.title,
                'description': reminder.description,
                'follow_up_minutes': reminder.follow_up_minutes,
                'call_if_no_response': reminder.call_if_no_response,
                'call_opt_out': reminder.call_opt_out
            }
        )
        logger.info(f"Scheduled reminder {job_id} for {scheduled_time}")
    except Exception as e:
        logger.exception(f"Failed to schedule reminder {reminder.id}: {e}")


async def cancel_reminder_jobs(reminder_id: str) -> None:
    """
    Cancel all jobs associated with a reminder.
    
    Args:
        reminder_id: The reminder's ID
    """
    sched = get_scheduler()
    
    job_ids = [
        f"reminder_{reminder_id}",
        f"followup_{reminder_id}",
        f"call_{reminder_id}"
    ]
    
    for job_id in job_ids:
        try:
            sched.remove_job(job_id)
            logger.info(f"Cancelled job: {job_id}")
        except Exception:
            pass  # Job might not exist


async def send_reminder_notification(
    reminder_id: str,
    title: str,
    description: Optional[str],
    follow_up_minutes: Optional[int],
    call_if_no_response: bool,
    call_opt_out: bool
) -> None:
    """
    Send a reminder notification to the user.
    
    This function is called by the scheduler at the scheduled time.
    """
    from app.infrastructure.twilio_whatsapp import send_reminder_notification as send_notification
    from app.infrastructure.database import DatabaseSession
    from app.usecases.reminder_service import ReminderService
    
    logger.info(f"Sending reminder notification: {reminder_id} - {title}")
    
    try:
        # Send the WhatsApp notification
        await send_notification(
            reminder_title=title,
            reminder_description=description
        )
        
        # Mark as notified in database
        async with DatabaseSession() as session:
            service = ReminderService(session)
            await service.mark_reminder_notified(reminder_id)
        
        # Schedule follow-up if needed
        if follow_up_minutes and call_if_no_response and not call_opt_out:
            await schedule_follow_up(
                reminder_id=reminder_id,
                title=title,
                follow_up_minutes=follow_up_minutes
            )
    except Exception as e:
        logger.exception(f"Error sending reminder notification: {e}")


async def schedule_follow_up(
    reminder_id: str,
    title: str,
    follow_up_minutes: int
) -> None:
    """
    Schedule a follow-up check after the specified minutes.
    
    Args:
        reminder_id: The reminder's ID
        title: Reminder title for call message
        follow_up_minutes: Minutes to wait before follow-up
    """
    from app.utils.time import get_current_time_pkt
    
    sched = get_scheduler()
    
    follow_up_time = get_current_time_pkt() + timedelta(minutes=follow_up_minutes)
    job_id = f"followup_{reminder_id}"
    
    try:
        sched.add_job(
            check_response_and_call,
            trigger=DateTrigger(run_date=follow_up_time),
            id=job_id,
            replace_existing=True,
            kwargs={
                'reminder_id': reminder_id,
                'title': title
            }
        )
        logger.info(f"Scheduled follow-up {job_id} for {follow_up_time}")
    except Exception as e:
        logger.exception(f"Failed to schedule follow-up: {e}")


async def check_response_and_call(reminder_id: str, title: str) -> None:
    """
    Check if user responded and trigger call if not.
    
    Args:
        reminder_id: The reminder's ID
        title: Reminder title for call message
    """
    from app.infrastructure.database import DatabaseSession
    from app.usecases.reminder_service import ReminderService
    from app.infrastructure.twilio_calls import make_reminder_call
    
    logger.info(f"Checking response for reminder: {reminder_id}")
    
    try:
        async with DatabaseSession() as session:
            service = ReminderService(session)
            responded = await service.check_user_responded(reminder_id)
        
        if not responded:
            logger.info(f"User did not respond to {reminder_id}, initiating call")
            await make_reminder_call(title)
        else:
            logger.info(f"User already responded to {reminder_id}, skipping call")
    except Exception as e:
        logger.exception(f"Error checking response: {e}")
