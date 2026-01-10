"""
WhatsApp Personal Assistant - Main Application Entry Point

A production-ready WhatsApp reminder assistant using FastAPI, Twilio,
OpenAI, SQLite, and APScheduler.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.whatsapp_webhook import router as whatsapp_router
from app.infrastructure.database import init_database
from app.infrastructure.scheduler import start_scheduler, stop_scheduler, get_scheduler
from app.config.settings import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting WhatsApp Personal Assistant...")
    
    # Initialize database
    logger.info("Initializing database...")
    await init_database()
    logger.info("Database initialized")
    
    # Start scheduler
    logger.info("Starting scheduler...")
    await start_scheduler()
    logger.info("Scheduler started")
    
    logger.info("Application startup complete!")
    logger.info(f"Timezone: Asia/Karachi (PKT)")
    logger.info(f"Twilio signature validation: {settings.validate_twilio_signature}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    await stop_scheduler()
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="WhatsApp Personal Assistant",
    description="A personal reminder assistant for WhatsApp with voice support",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware (restricted to Twilio for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://api.twilio.com"],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Register routers
app.include_router(whatsapp_router, tags=["WhatsApp"])


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "WhatsApp Personal Assistant",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "webhook": "/webhook/whatsapp",
            "health": "/health"
        }
    }


@app.get("/scheduler/status")
async def scheduler_status():
    """Get scheduler status and pending jobs."""
    scheduler = get_scheduler()
    
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None
        })
    
    return {
        "running": scheduler.running,
        "jobs_count": len(jobs),
        "jobs": jobs
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
