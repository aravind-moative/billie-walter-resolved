import os
import logging
from logging.config import dictConfig
from typing import Optional

from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.routes import init_app
from app.utilities.database import AdminDatabaseManager, DatabaseManager
from app.utilities.text_to_speech import TextToSpeech
from app.config import config


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Disable HTTPS redirect for local development
        # Check if we're in development mode or localhost
        if config.ENV == "development" or "localhost" in request.url.hostname or "127.0.0.1" in request.url.hostname:
            return await call_next(request)
        
        # Check if the request is secure by looking at the scheme
        scheme = request.scope.get("scheme", "http")
        if scheme != "https":
            url = str(request.url).replace("http://", "https://", 1)
            return RedirectResponse(url, status_code=301)
        
        return await call_next(request)


def create_app():
    # Set up logging with DEBUG level to show errors
    dictConfig(
        {
            "version": 1,
            "formatters": {
                "default": {
                    "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
                },
                "detailed": {
                    "format": "[%(asctime)s] %(levelname)s in %(module)s:%(lineno)d: %(message)s",
                },
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "detailed",
                    "level": "DEBUG",
                },
            },
            "root": {"level": "DEBUG", "handlers": ["default"]},
            "loggers": {
                "uvicorn": {"level": "DEBUG"},
                "uvicorn.error": {"level": "DEBUG"},
                "uvicorn.access": {"level": "DEBUG"},
                "fastapi": {"level": "DEBUG"},
            },
        },
    )

    # Ensure databases directory exists and is writable
    databases_dir = os.path.join(os.path.dirname(__file__), "databases")
    os.makedirs(databases_dir, exist_ok=True)
    if not os.access(databases_dir, os.W_OK):
        raise RuntimeError(f"Database directory {databases_dir} is not writable")

    app = FastAPI(
        title="Billie API",
        description="Utility management system with AI agent",
        version="1.0.0",
        docs_url="/docs" if config.ENV == "development" else None,
        redoc_url="/redoc" if config.ENV == "development" else None,
    )

    # Add CORS middleware first (order matters!)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000", "http://127.0.0.1:8000", "http://localhost:8000",
            "https://localhost:3000", "https://127.0.0.1:8000", "https://localhost:8000",
            "*"
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Add session middleware
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.SECRET_KEY,
        max_age=config.PERMANENT_SESSION_LIFETIME,
        same_site="lax",
        https_only=False  # Set to False for development
    )

    # Add HTTPS redirect middleware last (disabled for local development)
    # app.add_middleware(HTTPSRedirectMiddleware)

    # Mount static files
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Initialize shared instances
    app.state.db_manager = DatabaseManager()
    app.state.admin_db_manager = AdminDatabaseManager()
    app.state.tts = TextToSpeech()

    # Initialize routes
    init_app(app)

    return app


# Create the app instance
app = create_app()

