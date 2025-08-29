"""Configuration for synthetic data generation"""

import os
import secrets

from dotenv import load_dotenv

load_dotenv()


class Config:
    # Environment
    ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    # Base URL
    BASE_URL = os.getenv(
        "BASE_URL", "https://billie.moative.com"
    )  # "https://bd8d-122-164-82-70.ngrok-free.app"  #

    # API Keys
    # gemini_api_key = os.getenv("GEMINI_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    # Model Names
    # gemini_flash_model_name = os.getenv("GEMINI_FLASH_MODEL_NAME")
    openai_model_name = os.getenv("OPENAI_MODEL_NAME")

    # Session Configuration
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
    SESSION_TYPE = "filesystem"
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours in seconds


config = Config()
