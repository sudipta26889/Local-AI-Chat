from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import settings
from app.models.database import init_db
from app.routes import auth, chats, messages, models, websocket
from app.services.cache_service import CacheService
from app.services.storage_service import StorageService
from app.services.vector_service import VectorService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting DharasLocalAI...")
    
    # Initialize database
    await init_db()
    
    # Initialize services
    cache_service = CacheService()
    await cache_service.initialize()
    
    storage_service = StorageService()
    await storage_service.initialize()
    
    vector_service = VectorService()
    await vector_service.initialize()
    
    logger.info("DharasLocalAI started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down DharasLocalAI...")
    await cache_service.close()
    logger.info("DharasLocalAI shut down successfully")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logger.add(
    "logs/app.log",
    rotation="500 MB",
    retention="10 days",
    level=settings.log_level,
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(chats.router, prefix="/api/chats", tags=["Chats"])
app.include_router(messages.router, prefix="/api/messages", tags=["Messages"])
app.include_router(models.router, prefix="/api/models", tags=["Models"])
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "message": "Welcome to DharasLocalAI API",
    }