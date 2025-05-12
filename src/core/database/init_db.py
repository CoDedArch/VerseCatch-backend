import asyncio
from src.core.database._db import session_manager
from src.apps.requotes.models import Base

async def init_db():
    if session_manager.engine is None:
        raise RuntimeError("Database engine is not initialized. Check your DB config.")
    
    print("🛠️ Creating database tables...")
    async with session_manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print('✅ Database tables created')

if __name__ == "__main__":
    asyncio.run(init_db())
