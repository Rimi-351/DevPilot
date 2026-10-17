"""Database configuration, async engine, sessionmaker, and session dependency."""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.core.config import settings
from src.models.base import Base


def create_engine_instance(url: str, echo: bool = False) -> AsyncEngine:
    """Create configured AsyncEngine supporting PostgreSQL and SQLite."""
    engine_kwargs: dict[str, Any] = {
        "echo": echo,
    }
    # Pool pre-ping and pool sizes are only for network-based databases (like PostgreSQL)
    if not url.startswith("sqlite"):
        engine_kwargs.update(
            {
                "pool_size": settings.DB_POOL_SIZE,
                "max_overflow": settings.DB_MAX_OVERFLOW,
                "pool_timeout": settings.DB_POOL_TIMEOUT,
                "pool_pre_ping": True,
            }
        )
    return create_async_engine(url, **engine_kwargs)


engine: AsyncEngine = create_engine_instance(settings.DATABASE_URL, echo=settings.DB_ECHO)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """FastAPI dependency yielding the configured async sessionmaker."""
    return async_session_factory

