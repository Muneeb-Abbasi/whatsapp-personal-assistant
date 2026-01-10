"""
Pytest configuration and fixtures for WhatsApp Personal Assistant tests.
"""

from datetime import datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.reminder import Base, Reminder, ReminderStatus, ParsedIntent
from app.domain.processed_message import ProcessedMessage


# Use a separate in-memory SQLite database for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_engine():
    """Create a test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def sample_reminder() -> Reminder:
    """Create a sample reminder for testing."""
    return Reminder(
        id="test-reminder-123",
        title="Pay electricity bill",
        description="Monthly electricity payment",
        scheduled_time=datetime.utcnow() + timedelta(hours=1),
        follow_up_minutes=10,
        call_if_no_response=False,
        call_opt_out=True,
        status=ReminderStatus.ACTIVE,
    )


@pytest.fixture
def sample_parsed_intent() -> ParsedIntent:
    """Create a sample parsed intent for testing."""
    return ParsedIntent(
        intent="create_reminder",
        title="Test reminder",
        description="Test description",
        scheduled_time=datetime.utcnow() + timedelta(hours=2),
        follow_up_minutes=None,
        call_if_no_response=False,
        target_reminder=None,
        response_message="Reminder created successfully!"
    )


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    return {
        "intent": "create_reminder",
        "title": "Pay electricity bill",
        "description": None,
        "scheduled_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        "follow_up_minutes": None,
        "call_if_no_response": False,
        "target_reminder": None,
        "response_message": "I'll remind you to pay the electricity bill tomorrow."
    }


@pytest.fixture
def mock_twilio_client():
    """Mock Twilio client for testing."""
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.sid = "SM123456789"
    mock_client.messages.create.return_value = mock_message
    return mock_client


@pytest.fixture
def mock_settings():
    """Mock application settings for testing."""
    mock = MagicMock()
    mock.twilio_account_sid = "ACtest123"
    mock.twilio_auth_token = "test_token"
    mock.twilio_whatsapp_number = "whatsapp:+14155238886"
    mock.twilio_phone_number = "+14155238886"
    mock.openai_api_key = "sk-test123"
    mock.user_whatsapp_number = "whatsapp:+923001234567"
    mock.user_phone_number = "+923001234567"
    mock.database_url = TEST_DATABASE_URL
    mock.debug = False
    mock.validate_twilio_signature = False
    mock.timezone = "Asia/Karachi"
    return mock
