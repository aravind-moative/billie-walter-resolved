from app.routes.api import api_router
from app.routes.auth import auth_router
from app.routes.bland import bland_router
from app.routes.dashboard import dashboard_router
from app.routes.twilio_phone import twilio_router
from app.routes.twilio_sms import sms_router
from app.routes.web import web_router
from app.routes.websocket import websocket_router


def init_app(app):
    app.include_router(auth_router)
    app.include_router(web_router)
    app.include_router(api_router, prefix="/api")
    app.include_router(bland_router)
    app.include_router(twilio_router)
    app.include_router(sms_router)
    app.include_router(dashboard_router)
    app.include_router(websocket_router)
