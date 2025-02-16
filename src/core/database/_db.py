"""
This module provides an asynchronous database session manager for interacting with a PostgreSQL database using SQLAlchemy.
"""

from asyncio import current_task
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_scoped_session,
    create_async_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from core.config import settings

load_dotenv()

Base = declarative_base()


class DatabaseSessionManager:
    """
    Manages database connections and sessions for asynchronous database operations.

    This class handles the creation of an async SQLAlchemy engine, session management, 
    and database initialization. It provides a context manager for safely handling 
    database sessions, ensuring proper commit, rollback, and cleanup.

    Attributes:
        engine (AsyncEngine): The SQLAlchemy async engine for database connections.
        session_maker (sessionmaker): A session factory for creating `AsyncSession` instances.
        session (async_scoped_session): A session scoped to the current async task.
    """

    def __init__(self, database_url: str):
        """
        Initializes the database session manager with a given database URL.

        Args:
            database_url (str): The connection URL for the database.

        Raises:
            Exception: If the database engine fails to initialize.
        """
        print(database_url)
        self.engine = create_async_engine(
            database_url,
            pool_size=20,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=60 * 30,
            pool_pre_ping=True,
            connect_args={
                "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            },
        )

        self.session_maker = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

        self.session = async_scoped_session(self.session_maker, scopefunc=current_task)

    async def init_db(self):
        """
        Initializes the database by creating all tables asynchronously.

        This method ensures that the database is properly set up, including 
        enabling the `uuid-ossp` extension for UUID generation.

        Raises:
            Exception: If table creation fails.
        """
        async with self.engine.begin() as conn:
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def get_session(self):
        """
        Provides a database session for use with FastAPI dependency injection.

        This context manager ensures:
        - Automatic commit if no exceptions occur.
        - Rollback in case of errors.
        - Proper session cleanup.

        Yields:
            AsyncSession: An active database session.

        Raises:
            Exception: If an error occurs during the session lifecycle.
        """
        db_session = self.session()
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise
        finally:
            await db_session.close()

    async def close(self):
        """
        Closes the database engine, typically used during application shutdown.

        Raises:
            Exception: If the database session manager is not properly initialized.
        """
        if self.engine is None:
            raise Exception("DatabaseSessionManager is not initialized")
        await self.engine.dispose()


session_manager = DatabaseSessionManager(database_url="postgresql+asyncpg://postgres:#Includeiostream98@localhost:5432/ai_bible_db")


async def aget_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Asynchronous database session generator for dependency injection.

    This function provides an `AsyncSession` instance using the `DatabaseSessionManager`. 
    It is typically used as a FastAPI dependency to manage database interactions 
    efficiently.

    Yields:
        AsyncSession: An active database session that can be used within a request.

    Notes:
        - Uses `async with` to ensure proper session cleanup after use.
        - The session is automatically committed or rolled back based on execution outcome.
        - Designed for use in FastAPI route handlers that require database access.

    Example:
        ```python
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(aget_db)):
            return await db.execute(select(Item)).scalars().all()
        ```
    """
    async with session_manager.get_session() as session:
        yield session


engine = session_manager.engine