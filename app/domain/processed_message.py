"""
Processed message model for idempotency tracking.
Tracks message SIDs to prevent duplicate processing.
"""

from datetime import datetime

from sqlalchemy import Column, String, DateTime

from app.domain.reminder import Base


class ProcessedMessage(Base):
    """SQLAlchemy model for tracking processed WhatsApp messages."""
    
    __tablename__ = "processed_messages"
    
    message_sid = Column(String(64), primary_key=True)
    processed_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<ProcessedMessage(sid={self.message_sid}, at={self.processed_at})>"
