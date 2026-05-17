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

CB-2748 additions:
- ``transition_state`` — the ONLY way callers should change queue state;
  validates legality, persists atomically, emits STATE_TRANSITION event.
- ``checkpoint`` — writes lastCheckpointAt and emits CHECKPOINT_WRITTEN.
- ``set_subprocess_pid`` — persists subprocess PID on task record.
- ``_persist`` (in service) now re-raises OperationalError on disk-full /
  locked conditions instead of swallowing all exceptions (G3 fix).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.autopilot import (
    AutoPilotEvent,
    AutoPilotEventType,
    AutoPilotQueueRecord,
    AutoPilotTaskRecord,
    is_transition_allowed,
)
from models.database import AsyncSessionLocal
from utils.exhaustion_detector import redact_secrets as _redact_secrets  # CB-2765


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
            # CB-2794: persist circuit-breaker counter so it survives restarts
            autoResumeAttempts=queue.auto_resume_attempts,
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
        # CB-2794: persist circuit-breaker counter so it survives restarts
        record.autoResumeAttempts = queue.auto_resume_attempts

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
                # CB-2673: persist key/title so rehydrated tasks have populated
                # identifiers without requiring a JOIN on every resume.
                issueKey=task.issue_key or None,
                issueTitle=task.issue_title or None,
                status=task_status,
                attempts=task.retry_count,
                sessionId=task.session_id,
                startedAt=task.started_at,
                completedAt=task.completed_at,
                # CB-2765: redact secrets from error before persisting to DB
                failureReason=_redact_secrets(task.error) if task.error else task.error,
            )
            session.add(new_task)
        else:
            existing_task.status = task_status
            existing_task.attempts = task.retry_count
            existing_task.sessionId = task.session_id
            existing_task.startedAt = task.started_at
            existing_task.completedAt = task.completed_at
            # CB-2765: redact secrets from error before persisting to DB
            existing_task.failureReason = _redact_secrets(task.error) if task.error else task.error
            # CB-2673: update key/title if we now have them (e.g. after a
            # backfill or the first persist that comes after a rehydration
            # with the defensive fallback in T5).
            if task.issue_key:
                existing_task.issueKey = task.issue_key
            if task.issue_title:
                existing_task.issueTitle = task.issue_title

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
    """When rehydrating, any task left in ``running`` state was interrupted by
    the backend crash — it did NOT fail due to a real execution error.

    CB-2738 semantics:
    - Reset interrupted tasks to ``pending`` (NOT ``failed``) so they are
      re-run on the next resume.  ``failed`` is reserved for tasks where the
      subprocess returned non-zero or raised an exception during execution.
    - Clear ``sessionId``, ``startedAt``, ``failureReason`` so the task
      looks identical to one that was never started.
    - The ``reason`` parameter is kept for the INFO log (emitted by the
      service layer's ``rehydrate_from_db``), not stored on the task row.

    Bump the parent queue to ``paused / crash_recovery`` so the recovery API
    surfaces the right banner and the user must manually resume. Caller commits.

    Returns the number of tasks reset to pending.
    """
    result = await session.execute(
        select(AutoPilotTaskRecord)
        .where(AutoPilotTaskRecord.queueId == queue_id)
        .where(AutoPilotTaskRecord.status == "running")
    )
    rows = list(result.scalars().all())
    for task in rows:
        # Reset to pending — a backend restart is not a task failure.
        # The task will be re-run when the user resumes the queue.
        task.status = "pending"
        task.failureReason = None
        task.sessionId = None
        task.startedAt = None
        task.completedAt = None

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


# ---------------------------------------------------------------------------
# CB-2748: State-machine transition helper
# ---------------------------------------------------------------------------


class IllegalStateTransitionError(ValueError):
    """Raised when a caller attempts a forbidden state-machine transition."""


async def transition_state(
    queue_id: str,
    new_state: str,
    new_reason: Optional[str] = None,
    *,
    emit_event: bool = True,
    extra_payload: Optional[dict] = None,
) -> None:
    """Atomically transition a queue to a new state and persist the change.

    This is the **only** authorised way to change queue state (CB-2748).
    It:
      1. Validates that the transition is legal per the state-machine table.
      2. Writes the new ``state`` / ``stateReason`` (and mirrors to ``status``
         / ``pauseReason`` for backward compat) inside a single transaction.
      3. Emits a ``STATE_TRANSITION`` audit event (unless ``emit_event=False``).

    Args:
        queue_id: The ``AutoPilotQueueRecord.id`` to update.
        new_state: Target state string (e.g. ``"paused"``, ``"running"``).
        new_reason: Optional reason string (e.g. ``"crash_recovery"``).
        emit_event: Whether to append a STATE_TRANSITION event (default True).
        extra_payload: Additional fields merged into the event payload.

    Raises:
        IllegalStateTransitionError: If the transition is not in the
            allowed-transitions table.
        OperationalError: On SQLite I/O errors (disk full, locked) — the
            caller must handle this and stop task execution.
        ValueError: If ``queue_id`` does not exist in the DB.
    """
    async with AsyncSessionLocal() as db:
        async with db.begin():
            result = await db.execute(
                select(AutoPilotQueueRecord).where(AutoPilotQueueRecord.id == queue_id)
            )
            record = result.scalar_one_or_none()
            if record is None:
                raise ValueError(f"Queue {queue_id!r} not found in DB")

            from_state = record.state or record.status  # fall back to legacy status
            from_reason = record.stateReason or record.pauseReason

            if not is_transition_allowed(from_state, new_state):
                raise IllegalStateTransitionError(
                    f"Illegal transition {from_state!r} → {new_state!r} for queue {queue_id}"
                )

            now = datetime.utcnow()
            record.state = new_state
            record.stateReason = new_reason
            # Mirror to legacy columns so existing callers keep working.
            record.status = new_state
            record.pauseReason = new_reason
            record.updatedAt = now

            if emit_event:
                payload = {
                    "from_state": from_state,
                    "from_reason": from_reason,
                    "to_state": new_state,
                    "to_reason": new_reason,
                    **(extra_payload or {}),
                }
                await record_event(db, queue_id, AutoPilotEventType.STATE_TRANSITION, payload)

            # Transaction commits on context exit; rolls back on any exception.


# ---------------------------------------------------------------------------
# CB-2748: Checkpoint helper
# ---------------------------------------------------------------------------


async def checkpoint(queue_id: str) -> None:
    """Write ``lastCheckpointAt = now()`` and emit a CHECKPOINT_WRITTEN event.

    Called after every successful task completion to record durable progress.
    A crash between checkpoints means the queue can recover to the last
    checkpoint position without re-running already-completed tasks.

    Raises:
        OperationalError: On SQLite I/O errors — caller must handle.
    """
    async with AsyncSessionLocal() as db:
        async with db.begin():
            result = await db.execute(
                select(AutoPilotQueueRecord).where(AutoPilotQueueRecord.id == queue_id)
            )
            record = result.scalar_one_or_none()
            if record is None:
                logger.warning("checkpoint: queue %s not found — skipping", queue_id)
                return

            now = datetime.utcnow()
            record.lastCheckpointAt = now
            record.updatedAt = now

            await record_event(
                db,
                queue_id,
                AutoPilotEventType.CHECKPOINT_WRITTEN,
                {"checkpoint_at": now.isoformat()},
            )


# ---------------------------------------------------------------------------
# CB-2748: Subprocess PID tracking
# ---------------------------------------------------------------------------


async def get_task_record_id(queue_id: str, sequence: int) -> Optional[str]:
    """Return the AutoPilotTaskRecord.id for the given queue + sequence number.

    Used by CB-2756: the service needs the DB UUID to call set_subprocess_pid
    without carrying the DB ID on the in-memory QueueTask dataclass.

    Returns None if not found (e.g. persistence disabled, task not yet saved).
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AutoPilotTaskRecord.id).where(
                    AutoPilotTaskRecord.queueId == queue_id,
                    AutoPilotTaskRecord.sequence == sequence,
                )
            )
            row = result.first()
            return row[0] if row else None
    except Exception:
        logger.warning(
            "get_task_record_id: lookup failed for queue=%s seq=%d", queue_id, sequence
        )
        return None


async def set_subprocess_pid(
    task_id: str, pid: Optional[int], queue_id: Optional[str] = None
) -> None:
    """Persist the subprocess PID on an AutoPilotTaskRecord (CB-2748 G2 fix).

    When ``pid`` is ``None``, the column is cleared (task finished/aborted).
    Emits SUBPROCESS_PID_RECORDED when ``pid`` is non-None and queue_id is given.

    Args:
        task_id: ``AutoPilotTaskRecord.id``
        pid: Process ID of the live claude subprocess, or None to clear.
        queue_id: Required to emit the SUBPROCESS_PID_RECORDED event;
                  pass None to skip the event (e.g. on cleanup).

    Raises:
        OperationalError: On SQLite I/O errors — caller should log and continue
            (PID tracking is best-effort; failure means orphan detection may
            be incomplete on the next boot, but does not lose task state).
    """
    async with AsyncSessionLocal() as db:
        async with db.begin():
            result = await db.execute(
                select(AutoPilotTaskRecord).where(AutoPilotTaskRecord.id == task_id)
            )
            task_record = result.scalar_one_or_none()
            if task_record is None:
                logger.warning(
                    "set_subprocess_pid: task record %s not found — skipping", task_id
                )
                return

            task_record.subprocessPid = pid
            task_record.lastProgressAt = datetime.utcnow()

            if pid is not None and queue_id:
                await record_event(
                    db,
                    queue_id,
                    AutoPilotEventType.SUBPROCESS_PID_RECORDED,
                    {"task_id": task_id, "pid": pid},
                )


# ---------------------------------------------------------------------------
# CB-2748: _persist exception classifier
# ---------------------------------------------------------------------------

#: SQLite error substrings that indicate disk-full or lock conditions.
#: These are CRITICAL — caller must stop the queue loop immediately.
_DISK_FULL_SUBSTRINGS: tuple[str, ...] = (
    "disk i/o error",
    "no space left",
    "enospc",
    "database disk image is malformed",
    "database is full",
)

_LOCK_SUBSTRINGS: tuple[str, ...] = (
    "database is locked",
    "unable to open database",
)


def classify_operational_error(exc: OperationalError) -> str:
    """Classify an SQLAlchemy OperationalError into a persistence-failure category.

    Returns:
        ``"disk_full"``  — ENOSPC / disk I/O error → stop queue loop immediately.
        ``"db_locked"``  — concurrent write lock → may be transient.
        ``"other"``      — unknown OperationalError subtype.
    """
    msg = str(exc).lower()
    if any(s in msg for s in _DISK_FULL_SUBSTRINGS):
        return "disk_full"
    if any(s in msg for s in _LOCK_SUBSTRINGS):
        return "db_locked"
    return "other"


async def emit_persist_failed_event(
    queue_id: str,
    event_type: str,
    error_msg: str,
) -> None:
    """Best-effort: emit a PERSIST_FAILED or DISK_FULL_DETECTED event.

    Used by the service's ``_persist`` on exception so there is an audit trail
    even when the primary write failed. A second DB open is attempted; if that
    also fails, the error is logged and swallowed (we cannot do more).
    """
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await record_event(
                    db,
                    queue_id,
                    event_type,
                    {"error": error_msg[:512]},  # cap to avoid secondary bloat
                )
    except Exception:
        logger.exception(
            "emit_persist_failed_event: secondary write also failed for queue %s",
            queue_id,
        )
