from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from core.database import session_manager, aget_db
from apps.requotes.router import router as bible_quotes_router
from apps.auth.router import router as auth_router
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Async context manager for app lifespan events"""
    # Startup
    try:
        logger.info("Initializing database...")
        await session_manager.init()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise
    
    yield  # App runs here
    
    # Shutdown
    try:
        logger.info("Closing database connections...")
        await session_manager.close()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {str(e)}")

app = FastAPI(
    title="Bible API",
    description="API for Bible quotes and resources",
    lifespan=lifespan,
    dependencies=[Depends(aget_db)]  # Auto-inject db session to all routes
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, specify your frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/", tags=["Health Check"])
async def health_check(db: AsyncSession = Depends(aget_db)):
    try:
        # Verify database connection
        await db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }

# Include routers
app.include_router(bible_quotes_router, tags=["Bible Quotes"])
app.include_router(auth_router, tags=["Authentication"])