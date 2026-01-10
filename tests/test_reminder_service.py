"""
Unit tests for ReminderService business logic.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.domain.reminder import Reminder, ReminderStatus, ParsedIntent
from app.usecases.reminder_service import ReminderService


class TestReminderServiceHandleIntent:
    """Tests for ReminderService.handle_intent method."""
    
    @pytest_asyncio.fixture
    async def service(self, test_session):
        """Create a ReminderService instance with test session."""
        return ReminderService(test_session)
    
    @pytest.mark.asyncio
    async def test_handle_create_reminder_success(self, service, test_session):
        """Test successful reminder creation."""
        intent = ParsedIntent(
            intent="create_reminder",
            title="Test reminder",
            description="Test description",
            scheduled_time=datetime.utcnow() + timedelta(hours=1),
            response_message="Reminder created!"
        )
        
        with patch("app.usecases.reminder_service.schedule_reminder", new_callable=AsyncMock):
            response = await service.handle_intent(intent)
        
        assert "✅" in response
        assert "Test reminder" in response
        assert "Reminder created" in response
    
    @pytest.mark.asyncio
    async def test_handle_create_reminder_missing_title(self, service):
        """Test reminder creation fails when title is missing."""
        intent = ParsedIntent(
            intent="create_reminder",
            title=None,
            scheduled_time=datetime.utcnow() + timedelta(hours=1),
            response_message=""
        )
        
        response = await service.handle_intent(intent)
        
        assert "title" in response.lower()
    
    @pytest.mark.asyncio
    async def test_handle_create_reminder_missing_time(self, service):
        """Test reminder creation fails when time is missing."""
        intent = ParsedIntent(
            intent="create_reminder",
            title="Test reminder",
            scheduled_time=None,
            response_message=""
        )
        
        response = await service.handle_intent(intent)
        
        assert "when" in response.lower() or "time" in response.lower()
    
    @pytest.mark.asyncio
    async def test_handle_list_reminders_empty(self, service):
        """Test listing reminders when none exist."""
        intent = ParsedIntent(
            intent="list_reminders",
            response_message=""
        )
        
        response = await service.handle_intent(intent)
        
        assert "don't have any" in response.lower() or "no" in response.lower()
    
    @pytest.mark.asyncio
    async def test_handle_list_reminders_with_items(self, service, test_session, sample_reminder):
        """Test listing reminders when some exist."""
        # Add a reminder to the database
        test_session.add(sample_reminder)
        await test_session.commit()
        
        intent = ParsedIntent(
            intent="list_reminders",
            response_message=""
        )
        
        response = await service.handle_intent(intent)
        
        assert "Pay electricity bill" in response
        assert "📋" in response
    
    @pytest.mark.asyncio
    async def test_handle_acknowledge(self, service, test_session, sample_reminder):
        """Test acknowledging a reminder."""
        # Mark as notified
        sample_reminder.last_notified_at = datetime.utcnow()
        sample_reminder.user_responded = False
        test_session.add(sample_reminder)
        await test_session.commit()
        
        intent = ParsedIntent(
            intent="acknowledge",
            response_message=""
        )
        
        with patch("app.usecases.reminder_service.cancel_reminder_jobs", new_callable=AsyncMock):
            response = await service.handle_intent(intent)
        
        assert "👍" in response
    
    @pytest.mark.asyncio
    async def test_handle_unknown_intent(self, service):
        """Test handling an unknown intent."""
        intent = ParsedIntent(
            intent="unknown",
            response_message="I'm not sure what you want."
        )
        
        response = await service.handle_intent(intent)
        
        assert response == "I'm not sure what you want."
    
    @pytest.mark.asyncio
    async def test_handle_delete_reminder_not_found(self, service):
        """Test deleting a reminder that doesn't exist."""
        intent = ParsedIntent(
            intent="delete_reminder",
            target_reminder="nonexistent",
            response_message=""
        )
        
        response = await service.handle_intent(intent)
        
        assert "couldn't find" in response.lower()
    
    @pytest.mark.asyncio
    async def test_handle_pause_reminder(self, service, test_session, sample_reminder):
        """Test pausing a reminder."""
        test_session.add(sample_reminder)
        await test_session.commit()
        
        intent = ParsedIntent(
            intent="pause_reminder",
            target_reminder="electricity",
            response_message=""
        )
        
        with patch("app.usecases.reminder_service.cancel_reminder_jobs", new_callable=AsyncMock):
            response = await service.handle_intent(intent)
        
        assert "⏸️" in response or "Paused" in response
    
    @pytest.mark.asyncio
    async def test_handle_opt_out_calls(self, service):
        """Test opting out of phone calls."""
        intent = ParsedIntent(
            intent="opt_out_calls",
            response_message=""
        )
        
        response = await service.handle_intent(intent)
        
        assert "calls disabled" in response.lower() or "won't call" in response.lower()
