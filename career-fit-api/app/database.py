"""
Database Configuration - SQLAlchemy 2.0 Async.

Provides:
- Async engine (asyncpg)
- Session factory for requests
- Declarative base for models
- Init/close functions for FastAPI lifespan
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


# =============================================================================
# Declarative Base - All models inherit from this class
# =============================================================================
class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.

    By inheriting from Base, SQLAlchemy knows this is a mappable table.
    """

    pass


# Global variables (singleton pattern)
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """
    Get or create the async engine (singleton).

    The engine manages the connection pool to PostgreSQL.
    Created once and reused.

    Returns:
        AsyncEngine: Configured database engine
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,  # True = logs all SQL
            pool_size=settings.DATABASE_POOL_SIZE,  # Base connections
            max_overflow=settings.DATABASE_MAX_OVERFLOW,  # Extra under load
            pool_pre_ping=True,  # Verify connection before use
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get or create the session factory (singleton).

    The factory creates new sessions for each request.
    expire_on_commit=False = objects remain accessible after commit.

    Returns:
        async_sessionmaker: Async session factory
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: provides a session per request.

    Usage in routes:
        @router.get("/jobs")
        async def list_jobs(session: AsyncSession = Depends(get_session)):
            ...

    Automatically handles:
    - Commit if all OK
    - Rollback if exception
    - Close on finish

    Yields:
        AsyncSession: Database session
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database - create all tables.

    Called ONCE at app startup (in main.py lifespan).
    Imports all models so SQLAlchemy registers them.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        # Import models HERE to avoid circular imports
        # and ensure they're registered before create_all
        from app.models import (  # noqa: F401
            analysis,
            company,
            job,
            market_snapshot,
            profile,
            role,
            salary_observation,
            skill,
        )

        # Creates tables that don't exist (doesn't drop data)
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close database connections.

    Called on app shutdown (in main.py lifespan).
    Releases the connection pool.
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
