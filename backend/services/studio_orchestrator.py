"""
Studio Orchestrator Service (CB-2384).

Service layer between the Studio API and the chat-agent runtime.  All
database writes for Studio entities live here — the API layer only speaks
HTTP, never SQL.

Visibility Principle
--------------------
For tool calls and sub-agent dispatches the orchestrator FIRST writes
the row to the database (StudioToolCall / StudioAgentActivity), THEN
yields the event downstream.  This means the audit trail in the DB is
never behind what the SSE client has already seen.

Tenant Isolation
----------------
Every query scopes by tenantId.  Cross-tenant access returns None so
the caller can raise HTTP 404 (never 403 — tenant existence is not
disclosed).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from utils.exhaustion_detector import redact_secrets

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal
from models.studio import (
    StudioAgentActivity,
    StudioArtifact,
    StudioMessage,
    StudioSession,
    StudioToolCall,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """Return the current UTC datetime (tz-aware)."""
    return datetime.now(timezone.utc)


def _cuid() -> str:
    """Generate a random UUID string used as a CUID-compatible identifier."""
    return str(uuid.uuid4())


# Per-session locks preventing duplicate Anthropic turns when multiple SSE
# connections open simultaneously (React StrictMode double-mount, reconnect
# storms, multi-tab subscribes). The first connection acquires the lock and
# drives the turn; later connections see `locked()` and short-circuit. After
# the turn persists the assistant message, subsequent SSE handlers also
# short-circuit via the "last message is USER?" check.
_session_turn_locks: dict[str, "asyncio.Lock"] = {}
import asyncio  # noqa: E402 — placed here to keep the comment block self-contained


class StudioOrchestrator:
    """Orchestrates Studio sessions, messages, tool calls, and artifacts.

    All public methods accept ``tenant_id`` as the first argument and
    scope every DB query against it.  Methods that locate a resource by
    ``session_id`` return ``None`` when the row is absent *or* belongs to
    a different tenant — callers map ``None`` to HTTP 404.
    """

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def create_session(
        self,
        tenant_id: str,
        project_id: str,
        title: str,
        db: AsyncSession,
        *,
        token_budget: int = 50_000,
        created_by: Optional[str] = None,
    ) -> StudioSession:
        """Create and persist a new StudioSession.

        Args:
            tenant_id: Tenant scope for the session.
            project_id: Parent project identifier.
            title: Human-readable session title (1–500 chars).
            db: Active async database session.
            token_budget: Maximum token budget for this session.
            created_by: Optional actor identifier.

        Returns:
            The newly created and refreshed StudioSession ORM instance.
        """
        session = StudioSession(
            id=_cuid(),
            tenantId=tenant_id,
            projectId=project_id,
            title=title,
            status="ACTIVE",
            planningState={},
            tokenBudget=token_budget,
            tokensUsed=0,
            createdBy=created_by,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        logger.info(
            "studio.session.created tenant=%s project=%s id=%s",
            tenant_id,
            project_id,
            session.id,
        )
        return session

    async def list_sessions(
        self,
        tenant_id: str,
        db: AsyncSession,
        *,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[StudioSession]:
        """List Studio sessions scoped to tenant (and optionally project/status).

        Args:
            tenant_id: Tenant scope.
            db: Active async database session.
            project_id: Optional project filter.
            status: Optional status filter (e.g. ``"ACTIVE"``).

        Returns:
            List of matching StudioSession instances ordered by createdAt DESC.
        """
        query = (
            select(StudioSession)
            .where(StudioSession.tenantId == tenant_id)
            .order_by(StudioSession.createdAt.desc())
        )
        if project_id is not None:
            query = query.where(StudioSession.projectId == project_id)
        if status is not None:
            query = query.where(StudioSession.status == status)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_session(
        self,
        tenant_id: str,
        session_id: str,
        db: AsyncSession,
    ) -> Optional[StudioSession]:
        """Fetch a single session; returns None on missing or cross-tenant.

        Args:
            tenant_id: Tenant scope — cross-tenant rows return None.
            session_id: Primary key of the StudioSession.
            db: Active async database session.

        Returns:
            StudioSession instance or None.
        """
        result = await db.execute(
            select(StudioSession).where(
                StudioSession.id == session_id,
                StudioSession.tenantId == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_session(
        self,
        tenant_id: str,
        session_id: str,
        db: AsyncSession,
        **fields: Any,
    ) -> Optional[StudioSession]:
        """Patch allowed fields on an existing session.

        Args:
            tenant_id: Tenant scope.
            session_id: Target session PK.
            db: Active async database session.
            **fields: Keyword arguments matching StudioSession column names.

        Returns:
            Updated StudioSession or None when not found / cross-tenant.
        """
        session = await self.get_session(tenant_id, session_id, db)
        if session is None:
            return None
        _ALLOWED = {"title", "status", "planningState", "tokenBudget", "tokensUsed", "lastMessageAt"}
        for key, value in fields.items():
            if key in _ALLOWED:
                setattr(session, key, value)
        await db.commit()
        await db.refresh(session)
        return session

    async def delete_session(
        self,
        tenant_id: str,
        session_id: str,
        db: AsyncSession,
    ) -> bool:
        """Hard-delete a session (cascades to children via FK).

        Args:
            tenant_id: Tenant scope.
            session_id: Target session PK.
            db: Active async database session.

        Returns:
            True if deleted, False if not found / cross-tenant.
        """
        session = await self.get_session(tenant_id, session_id, db)
        if session is None:
            return False
        await db.delete(session)
        await db.commit()
        return True

    # ------------------------------------------------------------------
    # Message management
    # ------------------------------------------------------------------

    async def append_user_message(
        self,
        tenant_id: str,
        session_id: str,
        content: Any,
        db: AsyncSession,
    ) -> Optional[StudioMessage]:
        """Persist a USER message with monotonic sequence_num.

        The next sequence number is derived from ``SELECT MAX(sequenceNum)+1``
        inside the same transaction so concurrent appends race to a unique
        sequence number and the UNIQUE(sessionId, sequenceNum) constraint
        surfaces the collision as an IntegrityError rather than silently
        dropping a message.

        Args:
            tenant_id: Tenant scope.
            session_id: Target session PK.
            content: Message body (string or structured dict).
            db: Active async database session.

        Returns:
            The persisted StudioMessage or None when the session is not
            found / cross-tenant.
        """
        session = await self.get_session(tenant_id, session_id, db)
        if session is None:
            return None

        # Monotonic sequence number — all within the same transaction.
        max_result = await db.execute(
            select(func.max(StudioMessage.sequenceNum)).where(
                StudioMessage.sessionId == session_id
            )
        )
        current_max: Optional[int] = max_result.scalar()
        next_seq = (current_max or 0) + 1

        msg = StudioMessage(
            id=_cuid(),
            tenantId=tenant_id,
            sessionId=session_id,
            sequenceNum=next_seq,
            role="USER",
            content=content,
        )
        db.add(msg)

        # Stamp session.lastMessageAt while we have the lock.
        session.lastMessageAt = _now()

        await db.commit()
        await db.refresh(msg)
        return msg

    async def list_messages(
        self,
        tenant_id: str,
        session_id: str,
        db: AsyncSession,
        *,
        after_id: Optional[str] = None,
        before_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[StudioMessage]:
        """Cursor-based message pagination ordered by sequenceNum ASC.

        Cursor semantics avoid the off-by-one races that OFFSET-based
        pagination exhibits when new messages arrive during streaming.

        Args:
            tenant_id: Tenant scope (session ownership is validated first).
            session_id: Target session PK.
            db: Active async database session.
            after_id: Return messages with sequenceNum > the message with
                this id (exclusive lower bound).
            before_id: Return messages with sequenceNum < the message with
                this id (exclusive upper bound).
            limit: Maximum rows to return (1–200).

        Returns:
            Ordered list of StudioMessage instances, or empty list when the
            session is not found / cross-tenant.
        """
        session = await self.get_session(tenant_id, session_id, db)
        if session is None:
            return []

        query = (
            select(StudioMessage)
            .where(StudioMessage.sessionId == session_id)
            .order_by(StudioMessage.sequenceNum.asc())
            .limit(max(1, min(limit, 200)))
        )

        if after_id is not None:
            # Resolve cursor id → sequenceNum
            cursor_result = await db.execute(
                select(StudioMessage.sequenceNum).where(
                    StudioMessage.id == after_id,
                    StudioMessage.sessionId == session_id,
                )
            )
            cursor_seq = cursor_result.scalar_one_or_none()
            if cursor_seq is not None:
                query = query.where(StudioMessage.sequenceNum > cursor_seq)

        if before_id is not None:
            cursor_result = await db.execute(
                select(StudioMessage.sequenceNum).where(
                    StudioMessage.id == before_id,
                    StudioMessage.sessionId == session_id,
                )
            )
            cursor_seq = cursor_result.scalar_one_or_none()
            if cursor_seq is not None:
                query = query.where(StudioMessage.sequenceNum < cursor_seq)

        result = await db.execute(query)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Streaming (chat-agent turn)
    # ------------------------------------------------------------------

    async def stream_response(
        self,
        tenant_id: str,
        session_id: str,
        *,
        last_seq: int = 0,
    ) -> AsyncIterator[dict]:
        """Drive a chat-agent turn and yield SSE-ready event dicts.

        This method opens its **own** DB session (not the request session)
        so that the long-lived generator doesn't hold a connection across
        the full SSE stream lifetime.

        Visibility Principle — tool calls:
            1. Write ``StudioToolCall`` (PENDING) + ``StudioAgentActivity``
               to DB.
            2. Yield the event to the SSE stream.

        Visibility Principle — assistant messages:
            Persist ``StudioMessage`` (role=ASSISTANT) before yielding the
            ``message_delta`` / ``message_complete`` events.

        The chat agent is imported lazily so this module can be imported
        even before ``services/studio_chat_agent.py`` exists (the parallel
        Phase 6 agent creates it).

        Args:
            tenant_id: Tenant scope — validated before calling the agent.
            session_id: Target session PK.
            last_seq: Sequence number of the last event the client has
                already received (used by the SSE endpoint for catch-up;
                not consumed by this method directly but forwarded in events).

        Yields:
            Event dicts with at least ``{"type": str, ...}`` keys.
        """
        async with AsyncSessionLocal() as db:
            session = await self.get_session(tenant_id, session_id, db)
            if session is None:
                yield {"type": "error", "code": "session_not_found"}
                return

            # ── Idempotency: only run a turn if there is a pending USER message
            # without a following ASSISTANT. Multiple SSE reconnects (React
            # StrictMode dev-mode double-mount, exp-backoff retry, browser
            # tab focus reload) would otherwise fire duplicate Anthropic turns
            # for the same prompt. The SSE endpoint handles replay via
            # last_seq separately; this short-circuit is for "no new work."
            last = (
                await db.execute(
                    select(StudioMessage)
                    .where(StudioMessage.sessionId == session_id)
                    .order_by(StudioMessage.sequenceNum.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if last is None or last.role != "USER":
                # No pending user prompt — emit terminator and exit.
                yield {"type": "turn_complete", "reason": "no_pending_user_message"}
                return

            # Per-session lock so concurrent SSE handlers (StrictMode + reconnect)
            # don't double-start the turn. The lock is released when the first
            # generator finishes; subsequent SSE handlers find no pending USER
            # (the assistant message has been persisted) and short-circuit above.
            lock = _session_turn_locks.setdefault(session_id, asyncio.Lock())
            if lock.locked():
                # Another SSE handler is already driving this turn.
                # Yield a turn_complete and exit; the client's primary EventSource
                # will receive the real events from the live handler.
                yield {"type": "turn_complete", "reason": "turn_in_flight_elsewhere"}
                return

            async with lock:
                try:
                    # Use the module-level singleton which is correctly wired with
                    # db_factory.  Importing StudioChatAgent() bare (no args) would
                    # raise TypeError because __init__ requires db_factory.
                    from services.studio_chat_agent import get_studio_chat_agent  # noqa: PLC0415

                    agent = get_studio_chat_agent()
                    async for event in agent.run_turn(session=session, db=db):
                        event_type = event.get("type", "unknown")

                        # ----- Visibility Principle: tool_call_started -----
                        if event_type == "tool_call_started":
                            await self._on_tool_call_started(
                                tenant_id=tenant_id,
                                session_id=session_id,
                                event=event,
                                db=db,
                            )

                        # ----- Persist assistant messages -----
                        elif event_type == "message_complete":
                            await self._on_assistant_message_complete(
                                tenant_id=tenant_id,
                                session_id=session_id,
                                event=event,
                                db=db,
                            )

                        # ----- Sub-agent activity -----
                        elif event_type == "subagent_started":
                            await self._on_subagent_started(
                                tenant_id=tenant_id,
                                session_id=session_id,
                                event=event,
                                db=db,
                            )

                        yield event

                except ImportError:
                    # Phase 6 agent not yet available — yield a graceful stub.
                    logger.warning(
                        "studio_chat_agent not found — streaming stub response"
                    )
                    yield {
                        "type": "error",
                        "code": "agent_not_available",
                        "message": "StudioChatAgent not yet installed (Phase 6 pending)",
                    }
                except Exception:
                    # CRIT-2: log full exception server-side, never leak raw exc text to client.
                    logger.exception(
                        "studio.stream_response error session=%s", session_id
                    )
                    yield {"type": "error", "code": "internal_error", "message": "An internal error occurred"}

    # ------------------------------------------------------------------
    # Internal helpers for Visibility Principle writes
    # ------------------------------------------------------------------

    async def _on_tool_call_started(
        self,
        *,
        tenant_id: str,
        session_id: str,
        event: dict,
        db: AsyncSession,
    ) -> None:
        """Write StudioToolCall (PENDING) + StudioAgentActivity before SSE emit."""
        tool_name = event.get("tool_name", "unknown")
        tool_input = event.get("input", {})
        message_id = event.get("message_id")

        tool_call = StudioToolCall(
            id=_cuid(),
            tenantId=tenant_id,
            sessionId=session_id,
            messageId=message_id,
            toolName=tool_name,
            input=tool_input,
            status="PENDING",
            startedAt=_now(),
        )
        db.add(tool_call)

        # MED-6: redact secrets from tool_input before storing in the audit log.
        try:
            _redacted_input_str = redact_secrets(json.dumps(tool_input))
            _safe_input = json.loads(_redacted_input_str)
        except (TypeError, ValueError):
            _safe_input = {"_redacted": True}

        activity = StudioAgentActivity(
            id=_cuid(),
            tenantId=tenant_id,
            sessionId=session_id,
            verb="REQUEST",
            sourceAgent="orchestrator",
            targetAgent=tool_name,
            payload={"tool": tool_name, "input": _safe_input},
            chainDepth=0,
        )
        db.add(activity)

        try:
            await db.commit()
            # Embed the DB row id back into the event so the client can correlate.
            event["tool_call_id"] = tool_call.id
        except Exception:
            logger.exception("Failed to persist tool_call_started for session=%s", session_id)
            await db.rollback()

    async def _on_assistant_message_complete(
        self,
        *,
        tenant_id: str,
        session_id: str,
        event: dict,
        db: AsyncSession,
    ) -> None:
        """Persist ASSISTANT message after a complete turn."""
        content = event.get("content", "")
        model = event.get("model")
        tokens_input = event.get("tokens_input", 0)
        tokens_output = event.get("tokens_output", 0)
        cost_usd = event.get("cost_usd", 0.0)

        max_result = await db.execute(
            select(func.max(StudioMessage.sequenceNum)).where(
                StudioMessage.sessionId == session_id
            )
        )
        current_max: Optional[int] = max_result.scalar()
        next_seq = (current_max or 0) + 1

        msg = StudioMessage(
            id=_cuid(),
            tenantId=tenant_id,
            sessionId=session_id,
            sequenceNum=next_seq,
            role="ASSISTANT",
            content=content,
            model=model,
            tokensInput=tokens_input,
            tokensOutput=tokens_output,
            costUsd=cost_usd,
        )
        db.add(msg)

        try:
            await db.commit()
            event["message_id"] = msg.id
            event["sequence_num"] = next_seq
        except Exception:
            logger.exception(
                "Failed to persist assistant message for session=%s", session_id
            )
            await db.rollback()

    async def _on_subagent_started(
        self,
        *,
        tenant_id: str,
        session_id: str,
        event: dict,
        db: AsyncSession,
    ) -> None:
        """Write StudioAgentActivity for a sub-agent dispatch."""
        agent_role = event.get("agent_role", "UNKNOWN")
        activity = StudioAgentActivity(
            id=_cuid(),
            tenantId=tenant_id,
            sessionId=session_id,
            verb="DELEGATE",
            sourceAgent="orchestrator",
            targetAgent=agent_role,
            payload={"role": agent_role, "input": event.get("input", {})},
            chainDepth=event.get("chain_depth", 1),
        )
        db.add(activity)
        try:
            await db.commit()
            event["activity_id"] = activity.id
        except Exception:
            logger.exception(
                "Failed to persist subagent_started activity for session=%s", session_id
            )
            await db.rollback()

    # ------------------------------------------------------------------
    # Artifact management
    # ------------------------------------------------------------------

    async def create_artifact(
        self,
        tenant_id: str,
        session_id: str,
        name: str,
        kind: str,
        content: Optional[str],
        db: AsyncSession,
        *,
        storage_url: Optional[str] = None,
        version: int = 1,
    ) -> Optional[StudioArtifact]:
        """Create and persist a new StudioArtifact.

        Args:
            tenant_id: Tenant scope.
            session_id: Target session PK.
            name: Human-readable artifact name.
            kind: Artifact kind string (MARKDOWN, CODE, etc.).
            content: Inline content (up to 64 KB).
            db: Active async database session.
            storage_url: External storage URL for large artifacts.
            version: Artifact version number.

        Returns:
            Persisted StudioArtifact or None when session not found.
        """
        session = await self.get_session(tenant_id, session_id, db)
        if session is None:
            return None

        content_bytes = (content or "").encode("utf-8")
        sha256 = hashlib.sha256(content_bytes).hexdigest()
        size_bytes = len(content_bytes)

        artifact = StudioArtifact(
            id=_cuid(),
            tenantId=tenant_id,
            sessionId=session_id,
            name=name,
            kind=kind,
            content=content,
            storageUrl=storage_url,
            sizeBytes=size_bytes,
            sha256=sha256,
            version=version,
        )
        db.add(artifact)
        await db.commit()
        await db.refresh(artifact)
        return artifact

    async def get_artifact(
        self,
        tenant_id: str,
        session_id: str,
        artifact_id: str,
        db: AsyncSession,
    ) -> Optional[StudioArtifact]:
        """Fetch a single artifact; returns None on missing or cross-tenant.

        Args:
            tenant_id: Tenant scope.
            session_id: Parent session PK (must match artifact.sessionId).
            artifact_id: Artifact PK.
            db: Active async database session.

        Returns:
            StudioArtifact or None.
        """
        result = await db.execute(
            select(StudioArtifact).where(
                StudioArtifact.id == artifact_id,
                StudioArtifact.sessionId == session_id,
                StudioArtifact.tenantId == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_artifacts(
        self,
        tenant_id: str,
        session_id: str,
        db: AsyncSession,
    ) -> list[StudioArtifact]:
        """List all artifacts for a session.

        Args:
            tenant_id: Tenant scope.
            session_id: Target session PK.
            db: Active async database session.

        Returns:
            List of StudioArtifact ordered by createdAt ASC, or empty list
            when the session is not found / cross-tenant.
        """
        session = await self.get_session(tenant_id, session_id, db)
        if session is None:
            return []
        result = await db.execute(
            select(StudioArtifact)
            .where(
                StudioArtifact.sessionId == session_id,
                StudioArtifact.tenantId == tenant_id,
            )
            .order_by(StudioArtifact.createdAt.asc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Agent activity audit log
    # ------------------------------------------------------------------

    async def list_agent_activity(
        self,
        tenant_id: str,
        session_id: str,
        db: AsyncSession,
        *,
        limit: int = 100,
    ) -> list[StudioAgentActivity]:
        """Return the agent activity audit log for a session.

        Args:
            tenant_id: Tenant scope.
            session_id: Target session PK.
            db: Active async database session.
            limit: Maximum rows to return (1–500).

        Returns:
            List of StudioAgentActivity ordered by createdAt ASC, or empty
            list when the session is not found / cross-tenant.
        """
        session = await self.get_session(tenant_id, session_id, db)
        if session is None:
            return []
        result = await db.execute(
            select(StudioAgentActivity)
            .where(
                StudioAgentActivity.sessionId == session_id,
                StudioAgentActivity.tenantId == tenant_id,
            )
            .order_by(StudioAgentActivity.createdAt.asc())
            .limit(max(1, min(limit, 500)))
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Catch-up helpers (used by SSE replay)
    # ------------------------------------------------------------------

    async def get_messages_after_seq(
        self,
        tenant_id: str,
        session_id: str,
        after_seq: int,
        db: AsyncSession,
    ) -> list[StudioMessage]:
        """Return messages with sequenceNum > after_seq for SSE catch-up.

        Args:
            tenant_id: Tenant scope.
            session_id: Target session PK.
            after_seq: Exclusive lower bound on sequenceNum.
            db: Active async database session.

        Returns:
            Ordered list of StudioMessage instances.
        """
        result = await db.execute(
            select(StudioMessage)
            .where(
                StudioMessage.sessionId == session_id,
                StudioMessage.tenantId == tenant_id,
                StudioMessage.sequenceNum > after_seq,
            )
            .order_by(StudioMessage.sequenceNum.asc())
        )
        return list(result.scalars().all())


# Module-level singleton — imported by api/studio.py.
studio_orchestrator = StudioOrchestrator()
