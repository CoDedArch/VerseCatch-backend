from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.database import session_manager
from apps.requotes.models import Base
from apps.requotes.router import router as bible_quotes_router


app = FastAPI(
    title="Bible ...", 
    description="...",  
    on_shutdown=[session_manager.close],
    on_startup=[session_manager.init_db],
)


@app.get("/", tags=["Home"], response_model=dict)
async def home():
    return {"message": "Welcome to ..."}


app.include_router(bible_quotes_router, tags=["Bible Quotes"])
