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

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select

from app.config import settings
from app.errors import setup_exception_handlers, ErrorResponse, ErrorCode
from app.background import cancel_all_background_tasks
from app.rate_limit import limiter
from api import router as api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def evict_stale_sessions():
    """Evict completed sessions older than 1 hour to prevent memory growth."""
    from services.terminal_service import terminal_service
    from datetime import timedelta
    while True:
        try:
            cutoff = datetime.utcnow() - timedelta(hours=1)
            with terminal_service._sessions_lock:
                to_evict = [
                    sid for sid, s in terminal_service._sessions.items()
                    if s.status.value in ("completed", "cancelled", "failed")
                    and s.completed_at and s.completed_at < cutoff
                ]
            for sid in to_evict:
                terminal_service.cleanup_session(sid)
                logger.info(f"Evicted stale session {sid}")
            await asyncio.sleep(300)  # 5 min
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Eviction loop error")
            await asyncio.sleep(60)


async def _process_completion_for_session(db, session_id: str) -> bool:
    """Process one pending session: status flip + CB-1585 doc-gen hook.

    Returns True if the session was claimed (pending flag consumed), False
    otherwise. Raises only on programmer errors; downstream failures inside
    the doc-gen hook are swallowed since documentation is best-effort
    enrichment, never the primary completion path.

    CB-2116 (F1): caller is responsible for the transaction lifecycle AND
    for clearing the pending flag + doc-job on success. This function uses
    `peek_*` (non-destructive) so a rollback by the caller leaves the queue
    intact for retry on the next loop tick.

    Extracted from `process_pending_completions` so the hook is unit-testable
    without spinning up the infinite loop.
    """
    from services.terminal_service import terminal_service
    from services.documentation_generator import documentation_generator
    from models import Issue

    session = terminal_service.get_session(session_id)
    if not session or not terminal_service.peek_pending_completion(session_id):
        return False

    result = await db.execute(select(Issue).where(Issue.id == session.issue_id))
    issue = result.scalar_one_or_none()
    if issue and issue.status not in ("COMPLETED_WAITING_QA", "DONE"):
        issue.status = "COMPLETED_WAITING_QA"
        issue.updatedAt = datetime.utcnow()
        logger.info(
            f"[AUTO-COMPLETE] Marked {session.issue_key} as "
            f"COMPLETED_WAITING_QA after successful execution"
        )

    # CB-1585: documentation generation hook. Runs after status update,
    # before commit, so the ExecutionSummary row and issue status land in
    # the same transaction. Failures swallowed — best-effort enrichment.
    doc_job = terminal_service.peek_pending_doc_job(session_id)
    if doc_job and issue:
        # CB-2082 (T3.1.3): honor DocSettings.autoGenerate. When the user
        # has disabled auto-generation via /api/documentation/settings, we
        # still flip the issue to COMPLETED_WAITING_QA above (the primary
        # completion path) but skip the doc-gen call. The pending doc-job
        # is still cleared by the caller after commit so it doesn't leak.
        from services.doc_settings_service import get_or_create_settings
        try:
            doc_settings = await get_or_create_settings(db)
            auto_generate = bool(doc_settings.autoGenerate)
        except Exception:
            # Defensive: if settings load fails, default to ON so we don't
            # silently drop summaries because of an unrelated DB hiccup.
            logger.exception(
                "Failed to load DocSettings — defaulting autoGenerate=True"
            )
            auto_generate = True

        if not auto_generate:
            logger.info(
                "doc-gen skipped for %s (autoGenerate=False)",
                session.issue_key,
            )
        else:
            try:
                await documentation_generator.generate_from_execution(
                    session=session,
                    issue=issue,
                    project_path=doc_job.get("project_path") or session.project_path,
                    db=db,
                )
            except Exception:
                logger.exception(
                    "Documentation generation failed for %s",
                    session.issue_key,
                )
    elif doc_job and not issue:
        # Issue row vanished mid-flight (deleted concurrently). Drop the
        # captured snapshot rather than silently leaking it.
        logger.warning(
            "Discarding pending doc-gen job for %s — issue row not found",
            session.issue_key,
        )
        terminal_service.clear_pending_doc_job(session_id)
    return True


async def process_pending_completions():
    """Background task to process pending execution completions and update issue statuses.

    CB-2116 (F1): each session gets its OWN transaction so a flush/commit
    failure on session N does not roll back the work already done for
    sessions 0..N-1. The pending flag and queued doc-job are only cleared
    after the per-session commit succeeds — a rollback leaves them in place
    for the next loop tick to retry.
    """
    # Import here to avoid circular imports
    from services.terminal_service import terminal_service
    from models import AsyncSessionLocal

    while True:
        try:
            pending_session_ids = terminal_service.get_all_pending_completions()
            for session_id in pending_session_ids:
                async with AsyncSessionLocal() as db:
                    try:
                        claimed = await _process_completion_for_session(db, session_id)
                        if not claimed:
                            continue
                        await db.commit()
                    except Exception:
                        # Per-session rollback — pending flag + doc-job stay
                        # in the queue and will be retried on the next tick.
                        logger.exception(
                            "Per-session completion failed for %s — will retry",
                            session_id,
                        )
                        await db.rollback()
                        continue
                # Commit succeeded → safe to clear queue entries.
                terminal_service.clear_pending_completion(session_id)
                terminal_service.clear_pending_doc_job(session_id)
        except Exception as e:
            # Top-level safety net for failures outside the per-session block
            # (e.g., AsyncSessionLocal construction errors).
            logger.error(f"Error processing pending completions: {e}")

        # Check every 2 seconds
        await asyncio.sleep(2)


# CB-2083 (T3.1.4): retention loop — purges old ExecutionSummary rows
# according to DocSettings.retentionDays + maxPerIssue. Runs every 6 hours.
_RETENTION_INTERVAL_SECONDS = 6 * 60 * 60

# CB-2124 (H1): short delay before the FIRST retention pass. The 6h cadence
# is right for steady state but means an aggressive `retentionDays=1` config
# would not surface for a full window after boot. 60s gives enough time for
# the app to finish handling startup traffic before scanning the DB.
_RETENTION_FIRST_PASS_DELAY_SECONDS = 60


async def process_doc_retention():
    """Background task — applies DocSettings retention.

    First pass runs after `_RETENTION_FIRST_PASS_DELAY_SECONDS` (60s) so
    aggressive configs surface within a session, then settles into the
    `_RETENTION_INTERVAL_SECONDS` (6h) cadence. Failures are logged +
    swallowed so a transient DB error never kills the loop.
    """
    from models import AsyncSessionLocal
    from services.doc_settings_service import apply_retention

    delay = _RETENTION_FIRST_PASS_DELAY_SECONDS
    first_pass = True
    while True:
        try:
            await asyncio.sleep(delay)
            async with AsyncSessionLocal() as db:
                try:
                    purged_age, purged_cap = await apply_retention(db)
                    await db.commit()
                    if first_pass:
                        logger.info(
                            "[startup] Doc retention first pass complete: "
                            "purged_by_age=%d purged_by_cap=%d",
                            purged_age, purged_cap,
                        )
                    elif purged_age or purged_cap:
                        logger.info(
                            "Doc retention pass: purged_by_age=%d purged_by_cap=%d",
                            purged_age, purged_cap,
                        )
                except Exception:
                    logger.exception("Doc retention pass failed — rolling back")
                    await db.rollback()
            first_pass = False
            delay = _RETENTION_INTERVAL_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Doc retention loop iteration failed")
            # Don't tighten the loop on failure — keep the configured cadence.
            first_pass = False
            delay = _RETENTION_INTERVAL_SECONDS


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info(f"Starting ProjectsManagerWebV2 Backend on port {settings.PORT}")

    # Ensure all tables exist (creates any missing tables like CommitLink, GitSyncState)
    from models.database import init_db
    await init_db()
    logger.info("Database tables verified/created")

    # Initialize ChromaDB client — probe TCP and verify heartbeat before serving requests
    from services.rag_service import RAGService
    rag = RAGService()
    try:
        await asyncio.to_thread(rag._init_client_blocking)
        app.state.rag = rag
        logger.info("ChromaDB client connected successfully")
    except Exception as chroma_exc:
        logger.warning(
            "ChromaDB unreachable, falling back to local PersistentClient: %s",
            chroma_exc,
        )
        rag._fallback_to_persistent()
        app.state.rag = rag

    # CB-2043: surface the active RAG backend at startup. Silent fallback
    # to the embedded SQLite store is how we ended up running on a stale
    # `backend/data/chroma/chroma.sqlite3` for weeks — this line makes it
    # impossible to miss in the boot log.
    logger.info("[startup] %s", rag.describe_mode())

    # CB-1585: wire RAG into the documentation_generator singleton so the
    # post-execution hook can index ExecutionSummary embeddings in ChromaDB.
    # Done AFTER rag init and BEFORE the completion loop starts so the first
    # completion sees a fully wired generator.
    from services.documentation_generator import documentation_generator
    documentation_generator._rag = app.state.rag

    # CB-1600: wire RAG into qa_service so generate_qa_plan can fetch the
    # latest ExecutionSummary and inject implementation context into the
    # prompt. Same lifecycle/timing as the documentation_generator wiring.
    from services.qa_service import qa_service
    qa_service._rag = app.state.rag

    # CB-1951 E2 / CB-2750: universal rehydrate — covers all non-terminal
    # queue states (WAITING_RESET, PAUSED, RUNNING, PENDING).  RUNNING queues
    # are reclassified to paused/crash_recovery (or zombie_detected if an
    # orphan subprocess PID is still alive). Best-effort — failures are logged
    # but never block boot.
    from services.autopilot_queue_service import autopilot_queue_service
    recovered = await autopilot_queue_service.rehydrate_from_db()
    if recovered:
        logger.warning(
            "[AutoPilot] Rehydrated %d queue(s) from previous crash: %s. "
            "User must resume manually via the recovery banner.",
            len(recovered), recovered,
        )

    # CB-2750: start the 60-second background recovery tick loop.
    # Ticks auto-resume WAITING_RESET queues whose reset window has elapsed,
    # and detect new zombie RUNNING queues that lost their coroutine mid-flight.
    autopilot_queue_service.start_recovery_tick()
    logger.info("[AutoPilot] Recovery tick loop started")

    # Start background task for processing pending completions
    completion_task = asyncio.create_task(process_pending_completions())
    logger.info("Started background task for auto-completion processing")

    # Start background task for evicting stale sessions (memory leak prevention)
    evict_task = asyncio.create_task(evict_stale_sessions())
    logger.info("Started background task for stale session eviction")

    # CB-2083 (T3.1.4): doc retention loop — purges old ExecutionSummary
    # rows by retentionDays + maxPerIssue every 6h.
    retention_task = asyncio.create_task(process_doc_retention())
    logger.info("Started background task for doc retention")

    yield

    # Shutdown
    # CB-2750: stop the recovery tick loop before cancelling other tasks
    autopilot_queue_service.stop_recovery_tick()
    completion_task.cancel()
    evict_task.cancel()
    retention_task.cancel()
    try:
        await completion_task
    except asyncio.CancelledError:
        pass
    try:
        await evict_task
    except asyncio.CancelledError:
        pass
    try:
        await retention_task
    except asyncio.CancelledError:
        pass
    # Cancel any remaining fire-and-forget background tasks
    await cancel_all_background_tasks()
    logger.info("Shutting down ProjectsManagerWebV2 Backend")


# CB-2668: FastAPI's default /docs + /redoc + /openapi.json publish the full
# route map (every path, every project_id-shaped param, every request/response
# schema) to any Origin-less local caller. Combined with CB-2666 H-1 and
# CB-2667 H-2, that route map turns isolated identifier disclosures into a
# guided enumeration. We disable the surface unless `settings.is_development`
# explicitly opts in. Production / staging / unset ENVIRONMENT all stay locked.
#
# `swagger_ui_oauth2_redirect_url` is also pinned to None in non-dev as
# defense-in-depth — FastAPI today suppresses /docs/oauth2-redirect when
# `docs_url` is None, but that is an implementation detail rather than a
# documented contract. Pinning the URL collapses any upstream regression
# that re-mounts the asset path independently of the Swagger UI route.
_docs_url = "/docs" if settings.is_development else None
_redoc_url = "/redoc" if settings.is_development else None
_openapi_url = "/openapi.json" if settings.is_development else None
_swagger_oauth2_redirect_url = (
    "/docs/oauth2-redirect" if settings.is_development else None
)

app = FastAPI(
    title="ProjectsManagerWebV2 API",
    description="Backend API for ProjectsManagerWebV2 with CodeBoard",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
    swagger_ui_oauth2_redirect_url=_swagger_oauth2_redirect_url,
)

# Setup rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Setup standardized exception handlers
setup_exception_handlers(app)

# CORS Configuration - restricted to specific methods and headers for security
# Guard: wildcard origin + allow_credentials=True would let any site read credentialed
# responses — reject this misconfiguration loudly at startup rather than silently.
assert "*" not in settings.CORS_ORIGINS, (
    "Wildcard '*' in CORS_ORIGINS is forbidden when allow_credentials=True. "
    "Set CORS_ORIGINS to explicit origins."
)

# CB-2666 (sec audit F2): when the bind interface widens beyond loopback,
# the validate_origin middleware no longer constitutes a perimeter for
# Origin-less callers. INTERNAL_API_TOKEN is the deploy-gate that
# `app.security.require_local_or_token` enforces on the project-identifier
# endpoints. Forgetting to set the token while flipping ALLOW_LAN=true (or
# pointing HOST at a non-loopback interface) silently re-opens CB-2666 and
# every sibling endpoint covered by InternalAuthDep — fail loudly here.
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
if (settings.ALLOW_LAN or settings.HOST not in _LOOPBACK_HOSTS) and not settings.INTERNAL_API_TOKEN:
    raise RuntimeError(
        "INTERNAL_API_TOKEN must be set when ALLOW_LAN=true or HOST is "
        f"non-loopback (HOST={settings.HOST!r}, ALLOW_LAN={settings.ALLOW_LAN}). "
        "See backend/docs/DOC_PIPELINE_RUNBOOK.md §3 for the deploy gate."
    )
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


# Allowed origins for state-changing requests
ALLOWED_ORIGINS = {
    "http://localhost:3601",
    "http://127.0.0.1:3601",
}


@app.middleware("http")
async def validate_origin(request: Request, call_next):
    """Reject requests from unexpected origins for ALL credentialed methods.

    Enforces on POST/PUT/PATCH/DELETE (state-changing) AND GET (credentialed
    reads — CORS alone does not block a cross-origin GET from being sent, only
    from being read, but defence-in-depth blocks it at the server too).
    OPTIONS (CORS preflight) is left to the CORSMiddleware.
    Server-to-server calls (curl, internal services) carry no Origin header
    and are allowed through unchanged.

    Rationale: allow_credentials=True means cookies/tokens are forwarded; an
    attacker on a non-allow-listed origin must never receive a credentialed
    response body, even for read endpoints.
    """
    if request.method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            logger.warning(
                "Rejected cross-origin %s request from %s to %s",
                request.method,
                origin,
                request.url.path,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "invalid_origin"},
            )
    return await call_next(request)


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
