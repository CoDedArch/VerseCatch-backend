import os
import hashlib
import logging
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

    APOSTGRES_DATABASE_URL: str = os.getenv("APOSTGRES_DATABASE_URL")
    API_KEY: str = Field(env="API_KEY")
    OPENAI_API_KEY: str = Field(env="OPENAI_API_KEY")
    SECRET_KEY: str = Field(env="SECRET_KEY")
    ALGORITHM: str = Field(env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(env="ACCESS_TOKEN_EXPIRE", default=30)
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "no-reply@versecatch.pro")
    BASE_URL: str = os.getenv("BASE_URL", "https://versecatch.pro")
    PAYSTACK_SECRET_KEY: str = os.getenv("PAYSTACK_SECRET_KEY")
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()