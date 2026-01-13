"""
Conversation history model for context memory.
Stores recent messages to provide context for follow-up questions.
"""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import Column, Integer, String, DateTime, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domain.reminder import Base


class ConversationMessage(Base):
    """SQLAlchemy model for storing conversation history."""
    
    __tablename__ = "conversation_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_message = Column(String(1000), nullable=False)
    bot_response = Column(String(2000), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<ConversationMessage(id={self.id}, timestamp={self.timestamp})>"


async def save_conversation(
    session: AsyncSession,
    user_message: str,
    bot_response: str
) -> None:
    """
    Save a conversation exchange to history.
    
    Args:
        session: Database session
        user_message: User's message
        bot_response: Bot's response
    """
    msg = ConversationMessage(
        user_message=user_message[:1000],  # Truncate if too long
        bot_response=bot_response[:2000],
        timestamp=datetime.utcnow()
    )
    session.add(msg)
    await session.commit()


async def get_conversation_history(
    session: AsyncSession,
    limit: int = 10
) -> List[dict]:
    """
    Get recent conversation history.
    
    Args:
        session: Database session
        limit: Number of recent messages to retrieve
    
    Returns:
        List of message dicts with 'user' and 'assistant' keys
    """
    result = await session.execute(
        select(ConversationMessage)
        .order_by(desc(ConversationMessage.timestamp))
        .limit(limit)
    )
    messages = result.scalars().all()
    
    # Reverse to get chronological order (oldest first)
    messages = list(reversed(messages))
    
    history = []
    for msg in messages:
        history.append({"role": "user", "content": msg.user_message})
        history.append({"role": "assistant", "content": msg.bot_response})
    
    return history


async def cleanup_old_conversations(
    session: AsyncSession,
    days: int = 7
) -> None:
    """
    Remove conversation history older than specified days.
    
    Args:
        session: Database session
        days: Number of days to retain
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    await session.execute(
        delete(ConversationMessage).where(ConversationMessage.timestamp < cutoff)
    )
    await session.commit()
