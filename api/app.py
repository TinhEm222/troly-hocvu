import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from core.logging_setup import setup_logging
from core.startup import initialize_rag_components
from core.db import init_db
from core.seed import seed_admin_user

setup_logging()
logger = logging.getLogger("api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info("Starting CTUT Student Academic Assistant API...")
    try:
        init_db()
        seed_admin_user()
        initialize_rag_components()
        logger.info("Application startup completed")
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
    
    yield
    
    # Shutdown
    logger.info("Shutting down NMK Chatbot API...")

app = FastAPI(
    title="Student Academic Assistant API",
    description="API cho hệ thống Trợ lý ảo hỗ trợ sinh viên tra cứu thông tin học vụ (RAG)",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def track_response_time(request: Request, call_next):
    """Track response time for all requests"""
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    response.headers["X-Response-Time"] = f"{duration:.3f}s"
    logger.info(f"{request.method} {request.url.path} took {duration:.3f}s")
    return response

from api.routes import chat_router, health_router, auth_router, admin_router

app.include_router(health_router, tags=["health"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Student Academic Assistant API",
        "version": "1.0.0",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=False)
