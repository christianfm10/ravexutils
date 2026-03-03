"""
Async database session management and operations.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
from .base import Base


logger = logging.getLogger(__name__)


class AsyncDatabaseManager:
    """Manages async database connections and operations."""

    def __init__(
        self,
        database_url: str = "sqlite+aiosqlite:///database.db",
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
    ):
        """
        Initialize async database manager.

        Args:
            database_url: Database connection URL (async driver)
            echo: Whether to log SQL queries
            pool_size: Connection pool size
            max_overflow: Maximum overflow connections
        """
        self.database_url = database_url

        # Configure engine based on database type
        if database_url.startswith("sqlite"):
            # SQLite doesn't support connection pooling well
            self.engine = create_async_engine(
                database_url,
                echo=echo,
                poolclass=NullPool,
                connect_args={"check_same_thread": False},
            )
        else:
            # PostgreSQL (asyncpg), MySQL (aiomysql), etc.
            self.engine = create_async_engine(
                database_url,
                echo=echo,
                poolclass=AsyncAdaptedQueuePool,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_pre_ping=True,  # Verify connections before using
            )

        self.AsyncSessionLocal = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        logger.info(f"Async database manager initialized with URL: {database_url}")

    async def create_tables(self):
        """Create all tables in the database."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")

    async def drop_tables(self):
        """Drop all tables in the database."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.info("Database tables dropped successfully")

    async def truncate_tables(self):
        """Truncate all tables in the database."""
        async with self.engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                await conn.execute(table.delete())
        logger.info("Database tables truncated successfully")

    async def close(self):
        """Close database engine and connections."""
        await self.engine.dispose()
        logger.info("Database connections closed")

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """
        Get an async database session with automatic cleanup.

        Yields:
            AsyncSession instance
        """
        session = self.AsyncSessionLocal()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}", exc_info=True)
            raise
        finally:
            await session.close()


# Singleton instance
_async_db_manager: AsyncDatabaseManager | None = None


async def get_async_db_manager(
    database_url: str = "sqlite+aiosqlite:///database.db",
    echo: bool = False,
) -> AsyncDatabaseManager:
    """
    Get or create the async database manager singleton.

    Args:
        database_url: Database connection URL (with async driver)
        echo: Whether to log SQL queries

    Returns:
        AsyncDatabaseManager instance
    """
    global _async_db_manager

    if _async_db_manager is None:
        _async_db_manager = AsyncDatabaseManager(database_url=database_url, echo=echo)
        await _async_db_manager.create_tables()

    return _async_db_manager
