"""
Async database session manager for PostgreSQL with SQLAlchemy
Optimized for Render deployment and FastAPI integration
"""
import os
from asyncio import current_task
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_scoped_session,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy.orm import declarative_base
from core.config import settings

Base = declarative_base()

class DatabaseSessionManager:
    """
    Enhanced database session manager with:
    - Automatic table creation
    - Connection pooling optimized for Render
    - Proper SSL handling
    - UUID extension management
    """
    
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._session = None

    async def init(self):
        """Initialize engine and verify connection"""
        db_url = self._ensure_ssl(settings.APOSTGRES_DATABASE_URL)
        
        self.engine = create_async_engine(
            db_url,
            pool_size=15,  # Render free tier max is 20
            max_overflow=5,
            pool_timeout=30,
            pool_recycle=300,  # Recycle connections every 5 minutes
            pool_pre_ping=True,  # Check connection health
            echo=False,  # Set to True for debugging
            connect_args={
                "ssl": "require" if "render.com" in db_url else None,
                "prepared_statement_cache_size": 0  # Disable for Render
            }
        )
        
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False
        )
        
        # Verify connection and setup
        async with self.engine.begin() as conn:
            await self._setup_database(conn)

    def _ensure_ssl(self, db_url: str) -> str:
        """Ensure SSL is properly configured for Render"""
        if "render.com" in db_url and "?ssl=" not in db_url:
            return f"{db_url}?ssl=require"
        return db_url

    async def _setup_database(self, conn):
        """Initialize database extensions and tables"""
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.run_sync(Base.metadata.create_all)

    @property
    def session(self) -> async_scoped_session:
        """Scoped session for the current async task"""
        if not self.session_factory:
            raise RuntimeError("DatabaseSessionManager not initialized")
        return async_scoped_session(
            self.session_factory,
            scopefunc=current_task
        )

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for safe session handling"""
        async with self.session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def close(self):
        """Cleanup connection pool"""
        if self.engine:
            await self.engine.dispose()

# Initialize session manager
session_manager = DatabaseSessionManager()

async def aget_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions
    Usage:
    @router.get("/")
    async def endpoint(db: AsyncSession = Depends(aget_db)):
        ...
    """
    async with session_manager.get_session() as session:
        yield session

async def init_db():
    """Initialize database connection (call at startup)"""
    await session_manager.init()