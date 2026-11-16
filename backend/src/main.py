"""FastAPI Application Entrypoint & Lifespan Management."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings
from src.core.db.session import db_manager
from src.api.routes_chat import router as chat_router
from src.api.routes_files import router as files_router
from src.api.routes_admin import router as admin_router
from src.api.routes_mcp import router as mcp_router

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycles."""
    logger.info("Starting AI-Agent-ChatBot service...")
    try:
        await db_manager.connect()
    except Exception as e:
        logger.warning(f"Database connection deferred or failed on startup: {e}")

    if not settings.DEV_AUTH_BYPASS and settings.JWT_SECRET == "super-secret-key-change-in-production":
        logger.warning("SECURITY ALERT: Default JWT_SECRET detected while DEV_AUTH_BYPASS is False! Please set a secure JWT_SECRET in production.")

    yield

    logger.info("Shutting down AI-Agent-ChatBot service...")
    await db_manager.disconnect()

app = FastAPI(
    title="AI-Agent-ChatBot API",
    description="Autonomous Agentic Chatbot with Model Context Protocol (MCP) and Advanced RAG",
    version="0.1.0",
    lifespan=lifespan
)

# CORS Middleware (Configurable for local Vite frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(files_router)
app.include_router(admin_router)
app.include_router(mcp_router)

@app.get("/health", tags=["Health"])
async def health_check():
    """Service health check endpoint."""
    return {
        "status": "healthy",
        "service": "AI-Agent-ChatBot",
        "api_used": settings.API_USED,
        "dev_bypass": settings.DEV_AUTH_BYPASS
    }
