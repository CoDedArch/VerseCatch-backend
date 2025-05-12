from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.database import session_manager
from apps.requotes.models import Base
from apps.requotes.router import router as bible_quotes_router
from apps.auth.router import router as auth_router
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))


app = FastAPI(
    title="Bible ...", 
    description="...",  
    on_shutdown=[session_manager.close],
    on_startup=[session_manager.init_db],
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],
)


@app.get("/", tags=["Home"], response_model=dict)
async def home():
    return {"message": "Welcome to ..."}


app.include_router(bible_quotes_router, tags=["Bible Quotes"])
app.include_router(auth_router, tags=["Authentication"])
