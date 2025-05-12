# src/core/database/init_db.py
import asyncio
import logging
from src.core.database._db import session_manager
from src.apps.requotes.models import Base

# Configure logging (optional but consistent)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_db():
    try:
        logger.info("Initializing database engine...")
        await session_manager.init()
        logger.info("Database engine initialized.")
    except Exception as e:
        logger.error(f"❌ Failed to initialize engine: {e}")
        raise

    if session_manager.engine is None:
        raise RuntimeError("❌ session_manager.engine is None after init()")

    try:
        logger.info("Creating database tables...")
        async with session_manager.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database tables created successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to create tables: {e}")
        raise
    finally:
        await session_manager.close()
        logger.info("🛑 Database connection closed.")

if __name__ == "__main__":
    asyncio.run(init_db())
