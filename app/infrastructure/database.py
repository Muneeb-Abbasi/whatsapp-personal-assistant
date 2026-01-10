"""
Database setup and session management.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import get_settings
from app.domain.reminder import Base
from app.domain.processed_message import ProcessedMessage  # noqa: F401 - needed for table creation

settings = get_settings()

# Create async engine
# Using StaticPool for SQLite to handle concurrent access
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_database() -> None:
    """Initialize database and create tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Get a new database session."""
    async with async_session_factory() as session:
        yield session


class DatabaseSession:
    """Context manager for database sessions."""
    
    async def __aenter__(self) -> AsyncSession:
        self.session = async_session_factory()
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            await self.session.rollback()
        await self.session.close()
