"""
Studio API Router (CB-2384).

Provides CRUD + SSE streaming endpoints for Studio planning sessions.

All endpoints require a tenant scope delivered via the ``X-Tenant-ID``
header (falls back to ``settings.DEFAULT_TENANT_ID`` in Phase-1 single-
user mode — see ``api/deps.py``).

SSE format per endpoint ``GET /sessions/{id}/events``:

    id: <sequenceNum or epoch-ms>
    event: <type>
    data: <json>

    (blank line terminates each event frame)

Heartbeat: ``event: ping`` is emitted every 30 s so the TCP connection
is not silently dropped by proxies.

Visibility Principle: the orchestrator writes tool-call and agent-
activity rows to the DB **before** yielding each event frame — the DB
audit trail is never behind what the client has seen.
"""

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import TenantDep
from app.rate_limit import limiter
from models import get_db
from models.database import AsyncSessionLocal
from models.schemas import (
    StudioArtifactKind,
    StudioArtifactResponse,
    StudioMessageResponse,
    StudioSessionCreate,
    StudioSessionResponse,
    StudioSessionStatus,
    StudioAgentActivityResponse,
)
from services.studio_orchestrator import studio_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/studio", tags=["Studio"])

# ---------------------------------------------------------------------------
# Internal request/response models for endpoints that differ from the shared
# schemas (e.g., POST /messages only accepts {content} from the client).
# ---------------------------------------------------------------------------


class _MessageBody(BaseModel):
    """Body for POST /sessions/{id}/messages."""

    content: Any = Field(..., description="Message content (string or structured dict).")


class _SessionPatch(BaseModel):
    """Body for PATCH /sessions/{id}."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    status: Optional[StudioSessionStatus] = None


class _ArtifactBody(BaseModel):
    """Simplified body for POST /sessions/{id}/artifacts.

    The orchestrator computes ``sha256`` and ``sizeBytes`` from ``content``
    so callers do not need to supply them (unlike the internal
    ``StudioArtifactCreate`` schema which carries those fields for
    machine-generated writes where the content hash is known up-front).
    """

    name: str = Field(..., min_length=1, max_length=500)
    kind: StudioArtifactKind
    content: Optional[str] = None
    storageUrl: Optional[str] = None
    version: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Helper — format SSE frame
# ---------------------------------------------------------------------------

_SSE_HEARTBEAT = "event: ping\ndata: {}\n\n"
_SSE_HEARTBEAT_INTERVAL_S = 30


def _sse_frame(event_type: str, data: Any, event_id: Optional[str] = None) -> str:
    """Encode a single SSE event frame.

    Args:
        event_type: The ``event:`` field value.
        data: JSON-serialisable payload; will be encoded to a single line.
        event_id: Optional ``id:`` field (used for ``Last-Event-ID`` replay).

    Returns:
        A complete SSE frame string ending with a blank line.
    """
    parts: list[str] = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append(f"event: {event_type}")
    parts.append(f"data: {json.dumps(data, default=str)}")
    parts.append("")  # blank line terminates the frame
    parts.append("")  # second blank line for double-newline terminator
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/sessions",
    response_model=StudioSessionResponse,
    status_code=201,
    summary="Create a Studio session",
)
async def create_session(
    project_id: str,
    body: StudioSessionCreate,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> StudioSessionResponse:
    """Create a new Studio planning session for a project.

    Args:
        project_id: Parent project identifier.
        body: Session creation payload.
        tenant_id: Injected tenant scope (from X-Tenant-ID header or default).
        db: Injected async database session.

    Returns:
        Newly created StudioSessionResponse (HTTP 201).
    """
    session = await studio_orchestrator.create_session(
        tenant_id=tenant_id,
        project_id=project_id,
        title=body.title,
        db=db,
        token_budget=body.tokenBudget,
        created_by=body.createdBy,
    )
    return StudioSessionResponse.model_validate(session)


@router.get(
    "/projects/{project_id}/sessions",
    response_model=list[StudioSessionResponse],
    summary="List Studio sessions for a project",
)
async def list_sessions(
    project_id: str,
    status: Optional[str] = Query(None, description="Filter by session status"),
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> list[StudioSessionResponse]:
    """List all Studio sessions for a project, scoped to the calling tenant.

    Args:
        project_id: Parent project identifier.
        status: Optional status filter.
        tenant_id: Injected tenant scope.
        db: Injected async database session.

    Returns:
        List of StudioSessionResponse objects (may be empty).
    """
    sessions = await studio_orchestrator.list_sessions(
        tenant_id=tenant_id,
        db=db,
        project_id=project_id,
        status=status,
    )
    return [StudioSessionResponse.model_validate(s) for s in sessions]


@router.get(
    "/sessions/{session_id}",
    response_model=StudioSessionResponse,
    summary="Get a single Studio session",
)
async def get_session(
    session_id: str,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> StudioSessionResponse:
    """Retrieve a single Studio session by ID.

    Cross-tenant access returns HTTP 404 (not 403) to avoid tenant
    existence disclosure.

    Args:
        session_id: Target session PK.
        tenant_id: Injected tenant scope.
        db: Injected async database session.

    Returns:
        StudioSessionResponse or HTTP 404.
    """
    session = await studio_orchestrator.get_session(tenant_id, session_id, db)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return StudioSessionResponse.model_validate(session)


@router.patch(
    "/sessions/{session_id}",
    response_model=StudioSessionResponse,
    summary="Update a Studio session",
)
async def update_session(
    session_id: str,
    body: _SessionPatch,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> StudioSessionResponse:
    """Update the title and/or status of a Studio session.

    Args:
        session_id: Target session PK.
        body: Fields to update (all optional).
        tenant_id: Injected tenant scope.
        db: Injected async database session.

    Returns:
        Updated StudioSessionResponse or HTTP 404.
    """
    updates = body.model_dump(exclude_unset=True)
    # Normalise enum value to string so SQLAlchemy doesn't receive enum objects.
    if "status" in updates and updates["status"] is not None:
        updates["status"] = updates["status"].value if hasattr(updates["status"], "value") else updates["status"]

    updated = await studio_orchestrator.update_session(
        tenant_id, session_id, db, **updates
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return StudioSessionResponse.model_validate(updated)


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
    response_model=None,
    summary="Delete a Studio session",
)
async def delete_session(
    session_id: str,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Hard-delete a Studio session and all its child rows (cascade).

    Phase 1 implementation — hard delete.  Phase 2 can promote to
    soft-delete (status=ARCHIVED) without a breaking API change.

    Args:
        session_id: Target session PK.
        tenant_id: Injected tenant scope.
        db: Injected async database session.

    Returns:
        HTTP 204 on success, HTTP 404 on missing / cross-tenant.
    """
    deleted = await studio_orchestrator.delete_session(tenant_id, session_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")


# ---------------------------------------------------------------------------
# Message endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[StudioMessageResponse],
    summary="List messages in a session (cursor pagination)",
)
async def list_messages(
    session_id: str,
    after: Optional[str] = Query(None, description="Return messages after this message id (exclusive)"),
    before: Optional[str] = Query(None, description="Return messages before this message id (exclusive)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum messages to return"),
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> list[StudioMessageResponse]:
    """List messages in a session with cursor-based pagination.

    Ordered by ``sequenceNum`` ASC.  Use ``after`` / ``before`` message IDs
    as cursors instead of OFFSET to avoid races during active streaming.

    Args:
        session_id: Target session PK.
        after: Cursor — return messages *after* this message id.
        before: Cursor — return messages *before* this message id.
        limit: Maximum rows to return (1–200).
        tenant_id: Injected tenant scope.
        db: Injected async database session.

    Returns:
        List of StudioMessageResponse or HTTP 404 when session not found.
    """
    # get_session validates tenant ownership; empty list from list_messages
    # means cross-tenant or not-found — raise 404 explicitly.
    session = await studio_orchestrator.get_session(tenant_id, session_id, db)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = await studio_orchestrator.list_messages(
        tenant_id=tenant_id,
        session_id=session_id,
        db=db,
        after_id=after,
        before_id=before,
        limit=limit,
    )
    return [StudioMessageResponse.model_validate(m) for m in messages]


def _session_id_key(request: Request) -> str:
    """Rate-limit key: one bucket per session_id, not per IP.

    MED-5: behind the local proxy all callers share the same IP — keying on
    session_id ensures different sessions get independent 10/min budgets.
    """
    return request.path_params.get("session_id", "unknown")


@router.post(
    "/sessions/{session_id}/messages",
    status_code=202,
    summary="Append a user message and signal the client to open the SSE stream",
)
@limiter.limit("10/minute", key_func=_session_id_key)  # MED-5: per-session rate limit
async def append_message(
    request: Request,
    session_id: str,
    body: _MessageBody,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Append a USER message to the session and return the SSE stream URL.

    DESIGN NOTE — The agent turn is NOT started here.
    The SSE generator in ``GET /sessions/{id}/events`` is the sole driver of
    the Anthropic call.  This endpoint only persists the user message and
    returns HTTP 202 + streamUrl so the client can open the SSE connection
    before the agent has produced any output.  Starting the turn here as a
    background task would cause a double-execution bug (the SSE endpoint
    would also call ``stream_response``).

    MED-5: 10/minute per-session rate limit (keyed on session_id, not IP).

    Args:
        request: Starlette request (required by @limiter.limit).
        session_id: Target session PK.
        body: ``{content: ...}`` — the user message content.
        tenant_id: Injected tenant scope.
        db: Injected async database session.

    Returns:
        ``{messageId, streamUrl}`` with HTTP 202.
    """
    msg = await studio_orchestrator.append_user_message(
        tenant_id=tenant_id,
        session_id=session_id,
        content=body.content,
        db=db,
    )
    if msg is None:
        raise HTTPException(status_code=404, detail="Session not found")

    stream_url = f"/api/studio/sessions/{session_id}/events"
    return {"messageId": msg.id, "streamUrl": stream_url}


# ---------------------------------------------------------------------------
# SSE streaming endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/events",
    summary="SSE stream of agent events for a session",
    response_class=StreamingResponse,
)
async def session_events(
    session_id: str,
    request: Request,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
    last_event_id: Optional[str] = Header(
        default=None,
        alias="last-event-id",
        description="Last-Event-ID header for SSE replay from the last acknowledged event.",
    ),
    # HIGH-3: also accept as query params for clients that cannot set custom
    # headers (e.g. EventSource polyfills).  Priority: header > camelCase QP >
    # snake_case QP.
    lastEventId: Optional[str] = Query(
        default=None,
        alias="lastEventId",
        description="Fallback for Last-Event-ID as a camelCase query parameter.",
    ),
    last_event_id_qp: Optional[str] = Query(
        default=None,
        alias="last_event_id",
        description="Fallback for Last-Event-ID as a snake_case query parameter.",
    ),
) -> StreamingResponse:
    """Server-Sent Events stream for a Studio session.

    Supports ``Last-Event-ID`` for catch-up replay: persisted messages
    with ``sequenceNum > last_event_id`` are emitted as a burst before
    live events begin.

    The last-seen event ID is accepted in three ways (first match wins):
      1. ``Last-Event-ID`` HTTP header (standard browser EventSource).
      2. ``?lastEventId=<n>`` query parameter (camelCase, for proxied clients).
      3. ``?last_event_id=<n>`` query parameter (snake_case alias).

    Heartbeat ``event: ping`` is sent every 30 s to prevent proxy
    connection timeouts.

    Args:
        session_id: Target session PK.
        request: Raw FastAPI request (used to detect client disconnect).
        tenant_id: Injected tenant scope.
        db: Injected async database session.
        last_event_id: Optional Last-Event-ID header for replay.
        lastEventId: Optional camelCase query param fallback.
        last_event_id_qp: Optional snake_case query param fallback.

    Returns:
        StreamingResponse with ``media_type="text/event-stream"``.
    """
    # Validate tenant ownership before entering the generator.
    session = await studio_orchestrator.get_session(tenant_id, session_id, db)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Resolve Last-Event-ID: header takes priority, then camelCase QP, then
    # snake_case QP.  Parse to int; 0 means "no replay".
    raw_last_event_id: Optional[str] = last_event_id or lastEventId or last_event_id_qp
    last_seq: int = 0
    if raw_last_event_id is not None:
        try:
            last_seq = int(raw_last_event_id)
        except (TypeError, ValueError):
            last_seq = 0

    async def _generate() -> AsyncIterator[str]:
        # --- Catch-up burst: replay persisted messages since last_seq ---
        if last_seq > 0:
            async with AsyncSessionLocal() as catchup_db:
                catchup_msgs = await studio_orchestrator.get_messages_after_seq(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    after_seq=last_seq,
                    db=catchup_db,
                )
            for m in catchup_msgs:
                yield _sse_frame(
                    event_type="message_replay",
                    data={
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "sequenceNum": m.sequenceNum,
                        "createdAt": m.createdAt.isoformat() if m.createdAt else None,
                    },
                    event_id=str(m.sequenceNum),
                )

        # --- Live stream from the orchestrator ---
        last_heartbeat = time.monotonic()
        seq_counter: int = last_seq

        try:
            async for event in studio_orchestrator.stream_response(
                tenant_id=tenant_id,
                session_id=session_id,
                last_seq=last_seq,
            ):
                # Check if client disconnected.
                if await request.is_disconnected():
                    logger.info(
                        "studio.sse client disconnected session=%s", session_id
                    )
                    return

                # Emit heartbeat if interval exceeded.
                now = time.monotonic()
                if now - last_heartbeat >= _SSE_HEARTBEAT_INTERVAL_S:
                    yield _SSE_HEARTBEAT
                    last_heartbeat = now

                seq_counter += 1
                event_type = event.get("type", "event")
                yield _sse_frame(
                    event_type=event_type,
                    data=event,
                    event_id=str(seq_counter),
                )
                last_heartbeat = time.monotonic()

        except asyncio.CancelledError:
            return
        except Exception as exc:
            # CRIT-2: log full exception server-side; never emit raw exc text over SSE.
            logger.exception("studio.sse error session=%s", session_id)
            yield _sse_frame("error", {"code": "stream_error", "message": "An internal error occurred"})

        # Terminal frame.
        yield _sse_frame("done", {"session_id": session_id})

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Artifact endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/artifacts",
    response_model=list[StudioArtifactResponse],
    summary="List artifacts for a session",
)
async def list_artifacts(
    session_id: str,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> list[StudioArtifactResponse]:
    """List all artifacts produced during a session.

    Args:
        session_id: Target session PK.
        tenant_id: Injected tenant scope.
        db: Injected async database session.

    Returns:
        List of StudioArtifactResponse or HTTP 404 when session not found.
    """
    session = await studio_orchestrator.get_session(tenant_id, session_id, db)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    artifacts = await studio_orchestrator.list_artifacts(tenant_id, session_id, db)
    return [StudioArtifactResponse.model_validate(a) for a in artifacts]


@router.post(
    "/sessions/{session_id}/artifacts",
    response_model=StudioArtifactResponse,
    status_code=201,
    summary="Create an artifact in a session",
)
async def create_artifact(
    session_id: str,
    body: _ArtifactBody,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> StudioArtifactResponse:
    """Create a new artifact (e.g. a generated markdown plan).

    The orchestrator computes ``sha256`` and ``sizeBytes`` from ``content``
    automatically — callers only need to supply name, kind, and content.

    Args:
        session_id: Target session PK.
        body: Artifact creation payload (sha256/sizeBytes computed server-side).
        tenant_id: Injected tenant scope.
        db: Injected async database session.

    Returns:
        Created StudioArtifactResponse (HTTP 201) or HTTP 404.
    """
    artifact = await studio_orchestrator.create_artifact(
        tenant_id=tenant_id,
        session_id=session_id,
        name=body.name,
        kind=body.kind.value if hasattr(body.kind, "value") else body.kind,
        content=body.content,
        db=db,
        storage_url=body.storageUrl,
        version=body.version,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return StudioArtifactResponse.model_validate(artifact)


@router.get(
    "/sessions/{session_id}/artifacts/{artifact_id}",
    response_model=StudioArtifactResponse,
    summary="Get artifact metadata",
)
async def get_artifact(
    session_id: str,
    artifact_id: str,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> StudioArtifactResponse:
    """Retrieve artifact metadata (without content body).

    Args:
        session_id: Parent session PK.
        artifact_id: Target artifact PK.
        tenant_id: Injected tenant scope.
        db: Injected async database session.

    Returns:
        StudioArtifactResponse or HTTP 404.
    """
    artifact = await studio_orchestrator.get_artifact(tenant_id, session_id, artifact_id, db)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return StudioArtifactResponse.model_validate(artifact)


@router.get(
    "/sessions/{session_id}/artifacts/{artifact_id}/content",
    summary="Get artifact content with ETag support",
)
async def get_artifact_content(
    session_id: str,
    artifact_id: str,
    request: Request,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Retrieve the raw content of an artifact.

    Honors ``If-None-Match`` with the artifact's SHA-256 ETag — returns
    HTTP 304 when the client already holds a fresh copy.

    Args:
        session_id: Parent session PK.
        artifact_id: Target artifact PK.
        request: Raw request for ``If-None-Match`` inspection.
        tenant_id: Injected tenant scope.
        db: Injected async database session.

    Returns:
        Raw content with ``ETag`` header, or HTTP 304 / 404.
    """
    from fastapi.responses import Response  # noqa: PLC0415

    artifact = await studio_orchestrator.get_artifact(tenant_id, session_id, artifact_id, db)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    etag = f'"{artifact.sha256}"'
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return Response(status_code=304)

    content_bytes = (artifact.content or "").encode("utf-8")
    return Response(
        content=content_bytes,
        media_type="text/plain; charset=utf-8",
        headers={"ETag": etag},
    )


# ---------------------------------------------------------------------------
# Agent activity audit log
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/agent-activity",
    response_model=list[StudioAgentActivityResponse],
    summary="Get the agent activity audit log for a session",
)
async def list_agent_activity(
    session_id: str,
    limit: int = Query(100, ge=1, le=500, description="Maximum rows to return"),
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> list[StudioAgentActivityResponse]:
    """Return the agent activity visibility log for a session.

    The log is append-only and ordered by ``createdAt`` ASC.  Each row
    was written BEFORE the corresponding agent dispatch (Visibility
    Principle) so the log represents intent, not retrospective audit.

    Args:
        session_id: Target session PK.
        limit: Maximum rows to return (1–500).
        tenant_id: Injected tenant scope.
        db: Injected async database session.

    Returns:
        List of StudioAgentActivityResponse or HTTP 404.
    """
    session = await studio_orchestrator.get_session(tenant_id, session_id, db)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    activities = await studio_orchestrator.list_agent_activity(
        tenant_id, session_id, db, limit=limit
    )
    return [StudioAgentActivityResponse.model_validate(a) for a in activities]


# ---------------------------------------------------------------------------
# Capability suggestions (CB-2914 E5.1)
# ---------------------------------------------------------------------------


class CapabilitySuggestionResponse(BaseModel):
    """One ranked capability returned by GET /studio/capabilities/suggest."""

    name: str
    kind: str  # "agent" | "skill"
    description: str
    score: float
    reasons: list[str]


@router.get(
    "/capabilities/suggest",
    response_model=list[CapabilitySuggestionResponse],
    summary="Rank agents+skills against a chat session's recent context",
)
@limiter.limit(
    "60/minute",
    key_func=lambda request: (
        request.query_params.get("session_id") or request.client.host
    ),
)
async def suggest_capabilities(
    request: Request,
    session_id: str = Query(..., description="Active Studio chat session id"),
    message: str = Query("", max_length=4096, description="Latest user message (server falls back to last persisted user msg if empty). Capped at 4096 chars."),
    top_n: int = Query(7, ge=1, le=20),
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> list[CapabilitySuggestionResponse]:
    """Return the top-N relevant capabilities for the current chat turn.

    Security (CB-2914 sec-audit fixes):
      - HIGH-1: tenant ownership check on session_id BEFORE history lookup.
      - HIGH-2: 60/minute rate limit per session.
      - HIGH-3: message capped at 4096 chars to bound ReDoS surface.
    """
    from services.capability_suggester import build_suggester_from_db
    from sqlalchemy import desc as _desc
    from sqlalchemy import select as _select
    from models.studio import StudioMessage

    # HIGH-1: enforce session ownership before any cross-tenant-leaking read.
    session = await studio_orchestrator.get_session(tenant_id, session_id, db)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Defense-in-depth: tenant filter on the fallback message lookup.
    if not message.strip():
        result = await db.execute(
            _select(StudioMessage.content)
            .where(StudioMessage.sessionId == session_id)
            .where(StudioMessage.tenantId == tenant_id)
            .where(StudioMessage.role == "USER")
            .order_by(_desc(StudioMessage.createdAt))
            .limit(1)
        )
        row = result.first()
        message = str(row[0]) if row and row[0] else ""

    suggester = await build_suggester_from_db(db)
    suggestions = await suggester.suggest(
        message=message,
        session_id=session_id,
        db=db,
        top_n=top_n,
    )
    return [
        CapabilitySuggestionResponse(
            name=s.name, kind=s.kind, description=s.description,
            score=s.score, reasons=s.reasons,
        )
        for s in suggestions
    ]


# ---------------------------------------------------------------------------
# Investigation Engine endpoint (CB-2914 E1 + E2 + E7)
# ---------------------------------------------------------------------------


class InvestigationStartRequest(BaseModel):
    description: str = Field(..., max_length=8192, description="Bug description / user message / failure summary")
    evidence: dict = Field(default_factory=dict)


@router.post(
    "/sessions/{session_id}/investigate",
    summary="Trigger an SIE investigation cycle on a Studio session",
)
@limiter.limit("10/minute", key_func=lambda request: request.path_params.get("session_id", request.client.host))
async def trigger_investigation(
    request: Request,
    session_id: str,
    body: InvestigationStartRequest,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
):
    """Fire the SIE cycle on a Studio session.

    Streams Server-Sent Events with this contract:
      data: {"type": "layer_status", "layer": "code", "status": "running"}
      data: {"type": "layer_status", "layer": "code", "status": "completed"}
      data: {"type": "deliverable", "markdown": "..."}
      data: {"type": "done", "duration_s": 12.3, "cost_usd": 0.0123, "succeeded": 3, "total": 3}

    Security:
      - Rate-limited 10/minute per session (real-money fan-out protection).
      - Tenant ownership gate before invoking the engine.
      - Engine itself enforces dispatcher allow-listed tools (no RCE).
    """
    from services.investigation_engine import (
        InvestigationRequest,
        TriggerSource,
        get_investigation_engine,
    )

    session = await studio_orchestrator.get_session(tenant_id, session_id, db)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    inv_req = InvestigationRequest(
        trigger_source=TriggerSource.STUDIO_CHAT_INTENT,
        description=body.description,
        project_id=session.projectId,
        session_id=session_id,
        tenant_id=tenant_id,
        evidence=body.evidence,
    )

    engine = get_investigation_engine()

    async def event_stream():
        progress_queue: asyncio.Queue = asyncio.Queue()

        async def on_progress(layer, status):
            await progress_queue.put({
                "type": "layer_status",
                "layer": layer,
                "status": status.value if hasattr(status, "value") else str(status),
            })

        async def run_engine():
            try:
                result = await engine.run(inv_req, on_progress=on_progress)
                await progress_queue.put({
                    "type": "deliverable",
                    "markdown": result.deliverable_markdown,
                })
                await progress_queue.put({
                    "type": "done",
                    "duration_s": result.duration_s,
                    "cost_usd": result.total_cost_usd,
                    "succeeded": result.succeeded_layers,
                    "total": len(result.layer_reports),
                    "request_id": result.request.request_id,
                })
            except Exception as exc:
                logger.exception("Investigation cycle raised")
                await progress_queue.put({
                    "type": "error",
                    "error": "Investigation cycle failed",
                })
            finally:
                await progress_queue.put(None)  # sentinel

        engine_task = asyncio.create_task(run_engine())
        try:
            while True:
                event = await progress_queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            if not engine_task.done():
                engine_task.cancel()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
