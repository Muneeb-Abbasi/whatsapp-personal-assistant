"""
Reminder domain model and schemas.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, String, DateTime, Integer, Boolean, Enum as SQLEnum
from sqlalchemy.orm import declarative_base
from pydantic import BaseModel, Field

Base = declarative_base()


class ReminderStatus(str, Enum):
    """Reminder status enumeration."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class Reminder(Base):
    """SQLAlchemy model for reminders."""
    
    __tablename__ = "reminders"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    scheduled_time = Column(DateTime, nullable=False)
    follow_up_minutes = Column(Integer, nullable=True)
    call_if_no_response = Column(Boolean, default=False)
    call_opt_out = Column(Boolean, default=True)  # Opt-out by default
    status = Column(SQLEnum(ReminderStatus), default=ReminderStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_notified_at = Column(DateTime, nullable=True)
    user_responded = Column(Boolean, default=False)
    
    def __repr__(self) -> str:
        return f"<Reminder(id={self.id}, title={self.title}, status={self.status})>"


# Pydantic Schemas

class ReminderCreate(BaseModel):
    """Schema for creating a reminder."""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    scheduled_time: datetime
    follow_up_minutes: Optional[int] = Field(None, ge=1, le=60)
    call_if_no_response: bool = False
    call_opt_out: bool = True


class ReminderUpdate(BaseModel):
    """Schema for updating a reminder."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    scheduled_time: Optional[datetime] = None
    follow_up_minutes: Optional[int] = Field(None, ge=1, le=60)
    call_if_no_response: Optional[bool] = None
    call_opt_out: Optional[bool] = None
    status: Optional[ReminderStatus] = None


class ReminderResponse(BaseModel):
    """Schema for reminder response."""
    id: str
    title: str
    description: Optional[str]
    scheduled_time: datetime
    follow_up_minutes: Optional[int]
    call_if_no_response: bool
    call_opt_out: bool
    status: ReminderStatus
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ParsedIntent(BaseModel):
    """Schema for parsed NLP intent."""
    intent: str
    title: Optional[str] = None
    description: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    follow_up_minutes: Optional[int] = None
    call_if_no_response: Optional[bool] = None
    target_reminder: Optional[str] = None  # For update/delete operations
    response_message: str = ""  # Message to send back to user
