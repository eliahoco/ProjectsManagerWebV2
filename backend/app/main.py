"""
ProjectsManagerWebV2 - FastAPI Backend
Main application entry point with CORS configuration and security middleware
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time
import asyncio
from datetime import datetime

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select

from app.config import settings
from app.errors import setup_exception_handlers, ErrorResponse, ErrorCode
from api import router as api_router

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def process_pending_completions():
    """Background task to process pending execution completions and update issue statuses"""
    # Import here to avoid circular imports
    from services.terminal_service import terminal_service
    from models import AsyncSessionLocal, Issue

    while True:
        try:
            # Get all pending completions
            pending_session_ids = terminal_service.get_all_pending_completions()

            if pending_session_ids:
                async with AsyncSessionLocal() as db:
                    for session_id in pending_session_ids:
                        session = terminal_service.get_session(session_id)
                        if session and terminal_service.check_pending_completion(session_id):
                            # Update issue status to DONE
                            result = await db.execute(
                                select(Issue).where(Issue.id == session.issue_id)
                            )
                            issue = result.scalar_one_or_none()
                            if issue and issue.status != "DONE":
                                issue.status = "DONE"
                                issue.completedAt = datetime.utcnow()
                                logger.info(f"[AUTO-DONE] Marked {session.issue_key} as DONE after successful execution")

                    await db.commit()
        except Exception as e:
            logger.error(f"Error processing pending completions: {e}")

        # Check every 2 seconds
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info(f"Starting ProjectsManagerWebV2 Backend on port {settings.PORT}")

    # Start background task for processing pending completions
    completion_task = asyncio.create_task(process_pending_completions())
    logger.info("Started background task for auto-completion processing")

    yield

    # Shutdown
    completion_task.cancel()
    try:
        await completion_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down ProjectsManagerWebV2 Backend")


app = FastAPI(
    title="ProjectsManagerWebV2 API",
    description="Backend API for ProjectsManagerWebV2 with CodeBoard",
    version="1.0.0",
    lifespan=lifespan,
)

# Setup rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Setup standardized exception handlers
setup_exception_handlers(app)

# CORS Configuration - restricted to specific methods and headers for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Accept-Language",
        "Content-Language",
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "X-CSRF-Token",
    ],
    expose_headers=["X-Request-ID"],
    max_age=600,  # Cache preflight requests for 10 minutes
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing information"""
    start_time = time.time()

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration = time.time() - start_time

    # Log request (skip health checks to reduce noise)
    if request.url.path not in ["/health", "/"]:
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} ({duration:.3f}s)"
        )

    return response


# Include API routes
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {
        "success": True,
        "status": "ok",
        "service": "ProjectsManagerWebV2 API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "success": True,
        "status": "healthy",
        "service": "ProjectsManagerWebV2 API"
    }
