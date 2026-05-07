"""
Repository layer for AutoPilot queue persistence (CB-1951).

Translates between the in-memory ``AutoPilotQueue`` / ``QueueTask`` dataclasses
used by ``services.autopilot_queue_service`` and the persistent SQLAlchemy
records (``AutoPilotQueueRecord`` / ``AutoPilotTaskRecord`` / ``AutoPilotEvent``).

Design notes:
- ``save_queue`` is upsert-style: it works whether the queue row exists or not.
- ``save_queue`` does NOT commit — caller commits explicitly. Note that the
  service's ``_persist`` helper opens its own ``AsyncSessionLocal`` so the
  queue snapshot is decoupled from the cascade transaction. This is by design:
  cascade integrity is the priority and persistence is best-effort. A crash
  between cascade-commit and persist-commit can leave a slight ``attempts``
  counter drift, recovered by ``mark_running_tasks_failed_on_recovery`` on
  the next startup.
- ``record_event`` does NOT commit either, for the same reason.
- Event ``payload`` is capped at 8 KB to avoid bloat; oversized payloads are
  replaced with a sentinel ``{"_truncated": True, "size": N}``.
- ``load_active_queue`` returns the single non-terminal queue if any. The
  service is single-active by design (api/execution.py:929-936 enforces this);
  if multiple non-terminal rows are found we log a warning and return the most
  recently updated one.
- Internal asyncio fields on ``AutoPilotQueue`` (_task, _pause_event, etc.)
  are reset to defaults on rehydration — they cannot survive a process
  restart and must be recreated by the runtime.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.autopilot import (
    AutoPilotEvent,
    AutoPilotQueueRecord,
    AutoPilotTaskRecord,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status / enum helpers
# ---------------------------------------------------------------------------
# We deliberately store enum values as strings so that string comparisons in
# raw SQL (e.g. for the recovery query) work without joining the enum module.

_NON_TERMINAL_QUEUE_STATUSES = ("pending", "running", "paused", "waiting_reset")
_TERMINAL_QUEUE_STATUSES = ("completed", "aborted")


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------

async def save_queue(session: AsyncSession, queue) -> AutoPilotQueueRecord:
    """Upsert an ``AutoPilotQueue`` (in-memory) into the persistent record.

    Args:
        session: Open AsyncSession; caller is responsible for ``commit()``.
        queue: ``services.autopilot_queue_service.AutoPilotQueue`` instance.

    Returns:
        The persisted ``AutoPilotQueueRecord`` (loaded with tasks).
    """
    # Find existing row, if any.
    existing = await session.execute(
        select(AutoPilotQueueRecord)
        .where(AutoPilotQueueRecord.id == queue.id)
        .options(selectinload(AutoPilotQueueRecord.tasks))
    )
    record = existing.scalar_one_or_none()

    config_json = json.dumps({
        "on_success": queue.config.on_success,
        "on_fail": queue.config.on_fail,
        "max_retries": queue.config.max_retries,
        "provider": queue.provider,
        "model": queue.model,
        "project_path": queue.project_path,
        "feature_key": queue.feature_key,
    })

    # Status / pauseReason / resetTime are sourced from the in-memory queue.
    # The ``waiting_reset`` and ``crash_recovery`` reasons are set by the
    # service layer before calling save_queue.
    pause_reason = getattr(queue, "pause_reason", None)
    reset_time = getattr(queue, "reset_time", None)

    if record is None:
        record = AutoPilotQueueRecord(
            id=queue.id,
            projectId=queue.project_id,
            featureId=queue.feature_id,
            status=queue.status.value if hasattr(queue.status, "value") else str(queue.status),
            currentIndex=queue.current_index,
            pauseReason=pause_reason,
            resetTime=reset_time,
            config=config_json,
            createdAt=queue.created_at,
            updatedAt=datetime.utcnow(),
            completedAt=queue.completed_at,
        )
        session.add(record)
    else:
        record.projectId = queue.project_id
        record.featureId = queue.feature_id
        record.status = queue.status.value if hasattr(queue.status, "value") else str(queue.status)
        record.currentIndex = queue.current_index
        record.pauseReason = pause_reason
        record.resetTime = reset_time
        record.config = config_json
        record.updatedAt = datetime.utcnow()
        record.completedAt = queue.completed_at

    # Upsert tasks. Map by issue_id+order — a queue's tasks are immutable in
    # ordering, so we can match by ``order``.
    existing_tasks_by_seq = {}
    if record.tasks:
        existing_tasks_by_seq = {t.sequence: t for t in record.tasks}

    for task in queue.tasks:
        task_status = task.status.value if hasattr(task.status, "value") else str(task.status)
        existing_task = existing_tasks_by_seq.get(task.order)
        if existing_task is None:
            new_task = AutoPilotTaskRecord(
                id=str(uuid.uuid4()),
                queueId=queue.id,
                sequence=task.order,
                issueId=task.issue_id,
                status=task_status,
                attempts=task.retry_count,
                sessionId=task.session_id,
                startedAt=task.started_at,
                completedAt=task.completed_at,
                failureReason=task.error,
            )
            session.add(new_task)
        else:
            existing_task.status = task_status
            existing_task.attempts = task.retry_count
            existing_task.sessionId = task.session_id
            existing_task.startedAt = task.started_at
            existing_task.completedAt = task.completed_at
            existing_task.failureReason = task.error

    # Flush so caller can commit cleanly together with sibling writes.
    await session.flush()
    return record


async def load_queue(
    session: AsyncSession, queue_id: str
) -> Optional[AutoPilotQueueRecord]:
    """Load a queue record by id with eager-loaded tasks. Read-only."""
    result = await session.execute(
        select(AutoPilotQueueRecord)
        .where(AutoPilotQueueRecord.id == queue_id)
        .options(selectinload(AutoPilotQueueRecord.tasks))
    )
    return result.scalar_one_or_none()


async def load_active_queues(session: AsyncSession) -> List[AutoPilotQueueRecord]:
    """Return all non-terminal queue records, newest first.

    Used by ``rehydrate_from_db`` on startup. Returns a list because the
    single-active invariant is enforced at runtime, not at the DB level — if
    a crash happened mid-creation we may see >1 row and need to choose.
    """
    result = await session.execute(
        select(AutoPilotQueueRecord)
        .where(AutoPilotQueueRecord.status.in_(_NON_TERMINAL_QUEUE_STATUSES))
        .options(selectinload(AutoPilotQueueRecord.tasks))
        .order_by(AutoPilotQueueRecord.updatedAt.desc())
    )
    queues = list(result.scalars().all())
    if len(queues) > 1:
        logger.warning(
            "AutoPilot found %d non-terminal queues on rehydration; "
            "expected at most 1. Using most-recent: %s",
            len(queues),
            queues[0].id,
        )
    return queues


async def load_active_queue(session: AsyncSession) -> Optional[AutoPilotQueueRecord]:
    """Convenience helper — returns the single most-recent non-terminal queue."""
    queues = await load_active_queues(session)
    return queues[0] if queues else None


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


# Defensive cap on event payload size. Audit log is unbounded in SQLite but
# we don't want a future caller dumping a full LLM response in here.
_MAX_PAYLOAD_BYTES = 8192


async def record_event(
    session: AsyncSession,
    queue_id: str,
    event_type: str,
    payload: Optional[dict] = None,
) -> AutoPilotEvent:
    """Append a row to the AutoPilotEvent audit log. Caller commits.

    Args:
        session: Open AsyncSession.
        queue_id: ``AutoPilotQueueRecord.id``.
        event_type: One of the ``AutoPilotEventType`` enum values.
        payload: Arbitrary dict; serialized to JSON. Capped at
            ``_MAX_PAYLOAD_BYTES`` — oversized payloads are replaced with a
            ``{"_truncated": True, "size": N}`` sentinel so the audit log
            entry is preserved even when content can't fit.
    """
    payload_str = json.dumps(payload or {})
    if len(payload_str) > _MAX_PAYLOAD_BYTES:
        logger.warning(
            "AutoPilotEvent payload exceeded %d bytes (was %d) for queue %s type=%s; truncated",
            _MAX_PAYLOAD_BYTES,
            len(payload_str),
            queue_id,
            event_type,
        )
        payload_str = json.dumps({"_truncated": True, "size": len(payload_str)})

    event = AutoPilotEvent(
        id=str(uuid.uuid4()),
        queueId=queue_id,
        type=event_type,
        payload=payload_str,
        createdAt=datetime.utcnow(),
    )
    session.add(event)
    await session.flush()
    return event


async def list_events(
    session: AsyncSession,
    queue_id: str,
    limit: int = 200,
) -> List[AutoPilotEvent]:
    """Return events for a queue, newest first."""
    result = await session.execute(
        select(AutoPilotEvent)
        .where(AutoPilotEvent.queueId == queue_id)
        .order_by(AutoPilotEvent.createdAt.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Crash-recovery helpers
# ---------------------------------------------------------------------------


async def mark_running_tasks_failed_on_recovery(
    session: AsyncSession, queue_id: str, reason: str = "backend_crash_recovery"
) -> int:
    """When rehydrating, any task left in ``running`` state was killed by the
    backend crash. Mark them ``failed`` with the given reason AND bump the
    parent queue's pauseReason to ``crash_recovery`` so the recovery API
    surfaces the right banner. Caller commits.

    Returns the number of tasks reverted.
    """
    result = await session.execute(
        select(AutoPilotTaskRecord)
        .where(AutoPilotTaskRecord.queueId == queue_id)
        .where(AutoPilotTaskRecord.status == "running")
    )
    rows = list(result.scalars().all())
    for task in rows:
        task.status = "failed"
        task.failureReason = reason
        task.completedAt = datetime.utcnow()

    # Bump the queue itself to a crash-recovery paused state. The service
    # layer's rehydrate flow then surfaces this through the recovery API.
    queue_result = await session.execute(
        select(AutoPilotQueueRecord).where(AutoPilotQueueRecord.id == queue_id)
    )
    queue_record = queue_result.scalar_one_or_none()
    if queue_record is not None and queue_record.status in _NON_TERMINAL_QUEUE_STATUSES:
        queue_record.status = "paused"
        queue_record.pauseReason = "crash_recovery"
        queue_record.updatedAt = datetime.utcnow()

    await session.flush()
    return len(rows)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


async def queue_status_counts(session: AsyncSession) -> dict:
    """Return ``{status: count}`` across all queues. Used by /metrics."""
    from sqlalchemy import func as sa_func

    result = await session.execute(
        select(AutoPilotQueueRecord.status, sa_func.count(AutoPilotQueueRecord.id))
        .group_by(AutoPilotQueueRecord.status)
    )
    return {status: int(count) for status, count in result.all()}
