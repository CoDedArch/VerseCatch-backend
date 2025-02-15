import hashlib
import logging
import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings


load_dotenv(".env", override=True)
logger = logging.getLogger(__name__)


def hash_key(key: str) -> str:
    """Hash the key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


class Settings(BaseSettings):
    """Class to store all the settings of the application."""

    APOSTGRES_DATABASE_URL: str = os.getenv("APOSTGRES_DATABASE_URL")
    API_KEY: str = os.getenv("API_KEY")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")


settings = Settings()
