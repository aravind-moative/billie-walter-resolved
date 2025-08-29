import os
import logging
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.utilities.database import AdminDatabaseManager

auth_router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates"))
admin_db_manager = AdminDatabaseManager()

logger = logging.getLogger(__name__)


def get_current_user(request: Request):
    logger.debug(f"Checking authentication for request: {request.url}")
    user_id = request.session.get("user_id")
    if not user_id:
        logger.debug("No user_id in session, raising 401")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Session"},
        )
    logger.debug(f"User authenticated: {user_id}")
    return {
        "user_id": user_id,
        "user_email": request.session.get("user_email"),
        "user_name": request.session.get("user_name"),
        "user_role": request.session.get("user_role"),
    }


@auth_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    logger.debug("Login page requested")
    try:
        return templates.TemplateResponse("login.html", {"request": request})
    except Exception as e:
        logger.error(f"Error rendering login template: {e}", exc_info=True)
        raise


@auth_router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember_me: str = Form(None)
):
    logger.debug(f"Login attempt for email: {email}")
    # Admin authentication
    admin = admin_db_manager.get_admin_by_email(email)
    if admin and admin.check_password(password):
        logger.debug(f"Login successful for user: {admin.id}")
        request.session["user_id"] = admin.id
        request.session["user_email"] = admin.email
        request.session["user_name"] = admin.name
        request.session["user_role"] = "admin"

        if remember_me == "on":
            request.session["permanent"] = True

        # Update last login timestamp
        admin_db_manager.update_last_login(admin.id)

        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    else:
        logger.debug(f"Login failed for email: {email}")
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Invalid email or password"}
        )


@auth_router.get("/logout")
async def logout(request: Request):
    logger.debug("Logout requested")
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
