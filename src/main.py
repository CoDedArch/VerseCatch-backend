from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.database import session_manager
from apps.requotes.models import Base
from apps.requotes.router import router as bible_quotes_router
from apps.auth.router import router as auth_router


app = FastAPI(
    title="Bible ...", 
    description="...",  
    on_shutdown=[session_manager.close],
    on_startup=[session_manager.init_db],
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (replace with your frontend URL in production)
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (including OPTIONS)
    allow_headers=["*"],  # Allow all headers
)


@app.get("/", tags=["Home"], response_model=dict)
async def home():
    return {"message": "Welcome to ..."}


app.include_router(bible_quotes_router, tags=["Bible Quotes"])
app.include_router(auth_router, tags=["Authentication"])
