import os
import logging
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.routes.auth import get_current_user
from app.utilities.instances import get_db_manager

web_router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates"))

logger = logging.getLogger(__name__)


@web_router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    logger.debug("Root endpoint requested")
    # Check if user is authenticated
    user_id = request.session.get("user_id")
    if not user_id:
        logger.debug("No user_id in session, redirecting to login")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    logger.debug(f"User authenticated, redirecting to chat: {user_id}")
    return RedirectResponse(url="/chat", status_code=status.HTTP_302_FOUND)


@web_router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, current_user: dict = Depends(get_current_user)):
    logger.debug("Chat page requested")
    try:
        return templates.TemplateResponse("index.html", {"request": request, "session": request.session})
    except Exception as e:
        logger.error(f"Error rendering chat template: {e}", exc_info=True)
        raise


@web_router.get("/database", response_class=HTMLResponse)
async def database(request: Request, current_user: dict = Depends(get_current_user)):
    logger.debug("Database page requested")
    try:
        # Get all outages with customer information
        outages = get_db_manager().get_all_outages()
        # Get all customers with their billing information
        customers = get_db_manager().get_all_customers()
        return templates.TemplateResponse(
            "database.html",
            {
                "request": request,
                "recent_outages": outages,
                "customer_accounts": customers,
                "session": request.session
            }
        )
    except Exception as e:
        logger.error(f"Error rendering database template: {e}", exc_info=True)
        raise


@web_router.get("/voice", response_class=HTMLResponse)
async def voice_mode(request: Request, current_user: dict = Depends(get_current_user)):
    logger.debug("Voice mode page requested")
    try:
        return templates.TemplateResponse("voice_mode.html", {"request": request, "session": request.session})
    except Exception as e:
        logger.error(f"Error rendering voice mode template: {e}", exc_info=True)
        raise


@web_router.get("/convoai", response_class=HTMLResponse)
async def convoai_page(request: Request, current_user: dict = Depends(get_current_user)):
    logger.debug("ConvoAI page requested")
    try:
        return templates.TemplateResponse("convoai.html", {"request": request, "session": request.session})
    except Exception as e:
        logger.error(f"Error rendering ConvoAI template: {e}", exc_info=True)
        raise
