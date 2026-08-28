"""
API Routes for NMK Chatbot
"""
from api.routes.chat import router as chat_router
from api.routes.auth import router as auth_router
from api.routes.admin import router as admin_router
from api.health import router as health_router

__all__ = ["chat_router", "health_router", "auth_router", "admin_router"]