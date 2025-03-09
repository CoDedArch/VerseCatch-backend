import hashlib
import logging
import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field

load_dotenv(".env", override=True)
logger = logging.getLogger(__name__)


def hash_key(key: str) -> str:
    """Hash the key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


class Settings(BaseSettings):
    """Class to store all the settings of the application."""

    APOSTGRES_DATABASE_URL: str = Field(default="postgresql+asyncpg://postgres:#Includeiostream98@localhost:5432/ai_bible_db")
    API_KEY: str = Field(default="62e239a244ee31921b68592a27a20d4713543376d4b188cf971d0b99d775cc6f")
    OPENAI_API_KEY: str = Field(default="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")
    SECRET_KEY: str = Field(default="uAJdru335pyW8L79R01EAzq3MIothtw8HC4ikwo6E_s")
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()