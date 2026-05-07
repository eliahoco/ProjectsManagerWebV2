"""
AutoPilot Queue Service — Sequential task execution with pause/resume/skip/abort controls.

Manages a queue of tasks under a feature, executing them one-by-one via terminal_service.
Handles token exhaustion detection, automatic retries, model switching, and status cascading.

Execution flow:
  1. Frontend creates a queue via create_queue() with an ordered list of tasks.
  2. Frontend starts the queue by launching run_queue() as an asyncio.Task.
  3. The queue executes tasks sequentially, polling terminal_service for completion.
  4. Frontend can pause/resume/skip/abort at any time via control methods.
  5. On token exhaustion, the queue auto-pauses and can be resumed after reset.

Integration:
  - terminal_service: starts/stops/polls AI executions
  - context_builder: builds rich prompts with hierarchy context
  - db_queries: cascades status changes to parent containers
  - Issue model: reads/writes issue status in the database
"""

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal
from models.issue import Issue
from services.context_builder import build_execution_context, get_parent_chain
from services.terminal_service import (
    ExecutionProvider,
    ExecutionStatus,
    terminal_service,
)
from utils.db_queries import cascade_in_progress_to_parents, cascade_revert_to_parents, cascade_status_to_parents
from utils.autopilot_repository import record_event, save_queue


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class QueueStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_RESET = "waiting_reset"
    COMPLETED = "completed"
    ABORTED = "aborted"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Token exhaustion detection
# ---------------------------------------------------------------------------

TOKEN_EXHAUSTION_PATTERNS = [
    # Original 8 — substring-match on lowercased error text + tail of output
    "out of extra usage",
    "credit balance is too low",
    "rate limit exceeded",
    "quota exceeded",
    "usage limit",
    "too many requests",
    "billing",
    "exceeded your current quota",
    # CB-1951 E3.1.2 — additions sourced from Anthropic API + Claude CLI
    # error corpus (debugger pattern audit, 2026-05-03)
    "rate_limit_error",        # stream-json error.type field bleeds into [ERROR] line
    "overloaded_error",        # stream-json server-overload type (HTTP 529)
    "request too large",       # context-window overflow
    "prompt is too long",      # alternate context-window phrasing
    "your account has",        # prefix for credit-exhaustion messages
    "resets at",               # appears in Anthropic error body
    "resets in",               # alternate ("resets in 4h 30m")
    "5 hour reset",            # Claude.ai-specific phrasing
]


def is_token_exhaustion(session) -> bool:
    """Check if a completed session failed due to token/quota exhaustion."""
    if session.exit_code == 0:
        return False
    error_text = (session.error or "").lower()
    output_text = "\n".join(session.output[-20:]).lower() if session.output else ""
    return any(
        pattern in error_text or pattern in output_text
        for pattern in TOKEN_EXHAUSTION_PATTERNS
    )


def _redact_for_audit(text: Optional[str], max_chars: int = 200) -> str:
    """Trim and redact a string before storing it in AutoPilotEvent.payload.

    Audit-log payloads are eventually surfaced via the SSE stream + recovery
    endpoint (E2/E5), so any token-like substrings observable from upstream
    error messages must not survive into the persisted record. (CB-1951)

    Strips common credential patterns (Bearer tokens, sk-* keys, api_key=…)
    and truncates to ``max_chars`` from the first line only.
    """
    if not text:
        return ""
    first_line = text.splitlines()[0] if text else ""
    redacted = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***REDACTED***", first_line)
    redacted = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.=]+", "Bearer ***REDACTED***", redacted)
    redacted = re.sub(
        r"(api[_-]?key|authorization|token)\s*[:=]\s*[A-Za-z0-9_\-\.=]+",
        r"\1=***REDACTED***",
        redacted,
        flags=re.IGNORECASE,
    )
    return redacted[:max_chars]


def extract_reset_time(session) -> Optional[datetime]:
    """Try to extract a usage-reset time from the session output.

    Returns a tz-naive UTC ``datetime`` if a reset time can be parsed,
    otherwise ``None``. (CB-1951 E3.2 — was previously returning the raw
    matched string, now returns a real datetime so the auto-resume timer
    can compute a delay.)

    Supported formats (in order):
    1. ``resets at HH:MM am/pm`` — interpreted as today (UTC); rolls to
       tomorrow if already past
    2. ``resets in Nh [Mm]`` — relative offset
    3. ``resets at YYYY-MM-DDTHH:MM:SS`` — absolute ISO timestamp
    4. ``retry-after: <seconds>`` — relative seconds offset
    """
    if not session.output:
        return None
    output_text = "\n".join(session.output[-20:])
    return _parse_reset_time_from_text(output_text)


def _parse_reset_time_from_text(text: str) -> Optional[datetime]:
    """Pure helper for ``extract_reset_time`` so unit tests can drive it
    directly without building a session object. (CB-1951 E3.2.3)"""
    if not text:
        return None
    now = datetime.utcnow()

    # 1. resets at HH:MM am/pm
    m = re.search(
        r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)",
        text,
        re.IGNORECASE,
    )
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        meridian = m.group(3).lower()
        if meridian == "pm" and hour < 12:
            hour += 12
        elif meridian == "am" and hour == 12:
            hour = 0
        if 0 <= hour < 24 and 0 <= minute < 60:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                from datetime import timedelta
                target += timedelta(days=1)
            return target

    # 2. resets in Nh [Mm]
    m = re.search(
        r"resets?\s+in\s+(\d+)\s*h(?:ours?)?(?:\s+(\d+)\s*m(?:in(?:ute)?s?)?)?",
        text,
        re.IGNORECASE,
    )
    if m:
        from datetime import timedelta
        hours = int(m.group(1))
        minutes = int(m.group(2) or 0)
        return now + timedelta(hours=hours, minutes=minutes)

    # 3. ISO datetime (with or without T separator + tz)
    m = re.search(
        r"resets?\s+(?:at\s+)?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?)",
        text,
        re.IGNORECASE,
    )
    if m:
        ts = m.group(1).replace(" ", "T")
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                return datetime.strptime(ts, fmt)
            except ValueError:
                continue

    # 4. retry-after: <seconds>
    m = re.search(
        r"retry[-_]?after[:\s]+(\d+)",
        text,
        re.IGNORECASE,
    )
    if m:
        from datetime import timedelta
        return now + timedelta(seconds=int(m.group(1)))

    return None


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class QueueConfig:
    """Controls how the queue behaves on success and failure."""
    on_success: str = "MARK_WAITING_QA"   # MARK_WAITING_QA | MARK_DONE | MOVE_NEXT
    on_fail: str = "CONTINUE_MARK_FAILED"  # TERMINATE | RETRY | SKIP | CONTINUE_MARK_FAILED
    max_retries: int = 3


@dataclass
class QueueTask:
    """A single task entry in the autopilot queue."""
    issue_id: str
    issue_key: str
    issue_title: str
    order: int
    status: TaskStatus = TaskStatus.PENDING
    execution_mode: str = "implement"  # implement | audit | rewrite | skip
    force: bool = False
    session_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    retry_count: int = 0


@dataclass
class AutoPilotQueue:
    """Represents an active autopilot queue with ordered tasks and control flags."""
    id: str
    feature_id: str
    feature_key: str
    project_id: str
    project_path: str
    provider: str = "claude_code"        # claude_code | local_ai
    model: Optional[str] = None          # For local_ai model selection
    status: QueueStatus = QueueStatus.PENDING
    tasks: List[QueueTask] = field(default_factory=list)
    config: QueueConfig = field(default_factory=QueueConfig)
    current_index: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_error: Optional[str] = None

    # CB-1951 — pause/recovery metadata used by E3 (token-exhaust auto-pause)
    # and E2 (crash recovery banner). Persisted to AutoPilotQueueRecord.
    pause_reason: Optional[str] = None  # token_exhaustion|crash_recovery|manual
    reset_time: Optional[datetime] = None  # When auto-resume should fire

    # CB-1951 E4 review HIGH-1 / SEC MEDIUM-1: counter for consecutive
    # auto-resume attempts. Reset on successful task completion. When it
    # exceeds AUTO_RESUME_MAX_ATTEMPTS, the queue is downgraded to a
    # manual-resume state (circuit breaker — protects against runaway
    # token burn on a persistently-failing API key).
    auto_resume_attempts: int = 0

    # CB-2382: tracks issue IDs already appended by the audit-rescan pass so
    # the idempotency check is O(1) and survives multiple loop iterations.
    _appended_ids: set = field(default_factory=set, repr=False)
    # CB-2382: total auto-appended count for the lifetime of this queue.
    # Enforces _RESCAN_MAX_APPENDS_PER_RUN DoS cap.
    _appended_count: int = field(default=0, repr=False)
    # CB-2382: set to True once the rescan_cap_exceeded audit event has been
    # emitted, so we never duplicate it across rescan calls.
    _rescan_cap_logged: bool = field(default=False, repr=False)

    # Internal control fields — not serialized
    _task: Optional[asyncio.Task] = field(default=None, repr=False)
    _pause_event: asyncio.Event = field(
        default_factory=lambda: asyncio.Event(), repr=False
    )
    _skip_flag: bool = field(default=False, repr=False)
    _stop_flag: bool = field(default=False, repr=False)

    def __post_init__(self):
        # Start unpaused (event is set = running)
        self._pause_event.set()


# ---------------------------------------------------------------------------
# Poll interval
# ---------------------------------------------------------------------------

_POLL_INTERVAL_SECONDS = 2.0

# ---------------------------------------------------------------------------
# CB-2382 rescan safety limits
# ---------------------------------------------------------------------------

# Maximum total issues that may be auto-appended across all rescan calls for
# a single queue lifetime (DoS cap — prevents unbounded task injection).
_RESCAN_MAX_APPENDS_PER_RUN = 25

# Maximum issues appended in a single _rescan_subtree_for_new_tasks call
# (per-iteration rate limit).
_RESCAN_MAX_APPENDS_PER_ITERATION = 5

# BFS depth limit — prevents runaway traversal on pathologically deep trees.
_RESCAN_MAX_DEPTH = 10

# Reporters whose newly-spawned issues are trusted for auto-append.
# Restricts the candidate set to known AI agents; externally-created issues
# (e.g. reporter='external', manual entries) are never auto-appended.
_TRUSTED_REPORTERS = ("AI", "code-reviewer", "security-auditor", "debugger")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AutoPilotQueueService:
    """
    Manages autopilot queues — one active queue at a time.

    Thread-safety note: all public methods are called from the asyncio event
    loop, so no locking is required.  The long-running ``run_queue`` coroutine
    is launched as an ``asyncio.Task`` and communicates with control methods
    via ``asyncio.Event`` and boolean flags on the queue dataclass.
    """

    def __init__(self):
        self._queues: Dict[str, AutoPilotQueue] = {}
        self._active_queue_id: Optional[str] = None
        self._logger = logging.getLogger(__name__)
        # CB-1951 E2: queues recovered from disk after a backend crash. The
        # IDs in this set are gated behind manual user resume — we never
        # auto-resume from a crash since we can't trust the subprocess
        # actually died cleanly.
        self._recovered_queue_ids: set[str] = set()
        # CB-1951 E4: pending auto-resume timer handles, keyed by queue_id.
        # Set when a queue enters WAITING_RESET; cancelled on manual resume,
        # abort, or queue finalization.
        self._resume_handles: Dict[str, asyncio.Task] = {}
        # CB-1951 E10: feature flag for the persistence layer. When False,
        # _persist and _persist_async become no-ops and the service falls
        # back to the original in-memory behaviour. Initial value comes
        # from the AUTOPILOT_PERSISTENCE_ENABLED env var (default True).
        # Runtime toggle via the
        # POST /api/execute/queue/settings/persistence-enabled endpoint.
        import os as _os
        env_val = _os.environ.get("AUTOPILOT_PERSISTENCE_ENABLED", "true").strip().lower()
        self._persistence_enabled: bool = env_val not in ("0", "false", "no", "off")

    # ------------------------------------------------------------------
    # Queue lifecycle
    # ------------------------------------------------------------------

    def get_persistence_enabled(self) -> bool:
        """Return current state of the persistence feature flag (E10)."""
        return self._persistence_enabled

    def set_persistence_enabled(self, enabled: bool) -> None:
        """Toggle the persistence feature flag at runtime (E10).

        Note: in-flight queues snapshotted the flag at create_queue time
        for correctness; toggling at runtime affects future queues only.
        """
        prev = self._persistence_enabled
        self._persistence_enabled = bool(enabled)
        self._logger.warning(
            "[AutoPilot] Persistence flag toggled %s → %s",
            prev, self._persistence_enabled,
        )

    async def rehydrate_from_db(self) -> List[str]:
        """Restore any non-terminal queues from the persistent store.

        Called once at backend startup from the FastAPI lifespan hook
        (CB-1951 E2). For every non-terminal queue record found:

        1. Mark its ``running`` tasks as ``failed(backend_crash_recovery)``
           via :func:`mark_running_tasks_failed_on_recovery` — we can't
           prove the subprocess actually exited cleanly, so they have to
           be re-run.
        2. Flip the queue itself to ``paused`` with
           ``pauseReason=crash_recovery`` (gated behind manual user
           resume).
        3. Reconstruct the in-memory ``AutoPilotQueue`` dataclass from the
           DB record so existing accessors keep working.
        4. Add the queue id to ``_recovered_queue_ids`` so the recovery
           endpoint can surface it to the frontend banner.

        Returns the list of queue IDs that were rehydrated. Empty list
        is the normal clean-startup case.

        E10: when persistence is disabled, rehydration is a no-op (there's
        nothing to recover from since nothing was saved).
        """
        if not self._persistence_enabled:
            self._logger.info(
                "[AutoPilot] Persistence flag disabled — skipping rehydration"
            )
            return []

        from utils.autopilot_repository import (
            load_active_queues,
            mark_running_tasks_failed_on_recovery,
        )

        try:
            async with AsyncSessionLocal() as db:
                records = await load_active_queues(db)
                if not records:
                    self._logger.info(
                        "[AutoPilot] Recovered 0 queues from crash (clean startup)"
                    )
                    return []

                recovered_ids: List[str] = []
                for record in records:
                    n_failed = await mark_running_tasks_failed_on_recovery(
                        db, record.id, reason="backend_crash_recovery"
                    )
                    # Re-load with the updated state
                    await db.commit()

                    queue = self._record_to_queue(record)
                    self._queues[record.id] = queue
                    self._recovered_queue_ids.add(record.id)

                    # Last one in (most-recent) wins as active queue. The
                    # repository already sorts desc by updatedAt so the first
                    # record is the freshest.
                    if recovered_ids == []:
                        self._active_queue_id = record.id

                    recovered_ids.append(record.id)

                    # Emit a single recovery event so the audit log shows
                    # the rehydration happened.
                    await record_event(
                        db,
                        record.id,
                        "crash_recovery_detected",
                        {
                            "tasks_marked_failed": n_failed,
                            "current_index": record.currentIndex,
                            "feature_id": record.featureId,
                        },
                    )
                    await db.commit()

                self._logger.info(
                    "[AutoPilot] Recovered %d queue(s) from crash: %s",
                    len(recovered_ids),
                    recovered_ids,
                )
                # CB-1951 E4.2.3: re-arm auto-resume timers for any
                # WAITING_RESET queues that survived the crash. Note: queues
                # rehydrated with pauseReason=crash_recovery are NOT re-armed
                # — they require manual user resume.
                await self.rearm_auto_resume_timers()
                return recovered_ids
        except Exception:
            # Rehydration must NEVER break startup. Log and let the app
            # come up with an empty in-memory queue — worst case the user
            # has to re-trigger AutoPilot manually.
            self._logger.exception(
                "[AutoPilot] Rehydration failed; starting with empty queue state"
            )
            return []

    @staticmethod
    def _record_to_queue(record) -> AutoPilotQueue:
        """Reconstruct an in-memory ``AutoPilotQueue`` from a DB record."""
        cfg = {}
        try:
            cfg = json.loads(record.config or "{}")
        except (ValueError, TypeError):
            pass

        queue_config = QueueConfig(
            on_success=cfg.get("on_success", "MARK_WAITING_QA"),
            on_fail=cfg.get("on_fail", "CONTINUE_MARK_FAILED"),
            max_retries=int(cfg.get("max_retries", 3)),
        )

        # Reconstruct tasks (the DB rows are eagerly loaded by load_active_queues)
        tasks: List[QueueTask] = []
        for trecord in sorted(record.tasks, key=lambda t: t.sequence):
            try:
                ts = TaskStatus(trecord.status)
            except ValueError:
                ts = TaskStatus.PENDING
            tasks.append(QueueTask(
                issue_id=trecord.issueId,
                issue_key="",  # not persisted; UI re-fetches from Issue
                issue_title="",
                order=trecord.sequence,
                status=ts,
                session_id=trecord.sessionId,
                started_at=trecord.startedAt,
                completed_at=trecord.completedAt,
                error=trecord.failureReason,
                retry_count=trecord.attempts,
            ))

        try:
            qstatus = QueueStatus(record.status)
        except ValueError:
            qstatus = QueueStatus.PAUSED

        queue = AutoPilotQueue(
            id=record.id,
            feature_id=record.featureId or "",
            feature_key=cfg.get("feature_key", ""),
            project_id=record.projectId,
            project_path=cfg.get("project_path", ""),
            provider=cfg.get("provider", "claude_code"),
            model=cfg.get("model"),
            status=qstatus,
            tasks=tasks,
            config=queue_config,
            current_index=record.currentIndex,
            created_at=record.createdAt,
            completed_at=record.completedAt,
        )
        # Recovery state — typed dataclass fields, populated from the record
        queue.pause_reason = record.pauseReason
        queue.reset_time = record.resetTime
        return queue

    def get_recovered_queues(self) -> List[AutoPilotQueue]:
        """Return queues that were rehydrated after a backend crash.

        Frontend banner uses this to prompt the user. Once the user
        resumes / aborts a recovered queue, it should be removed from
        the recovery set via :meth:`clear_recovery_state`.
        """
        return [
            self._queues[qid]
            for qid in self._recovered_queue_ids
            if qid in self._queues
        ]

    def clear_recovery_state(self, queue_id: str) -> None:
        """Drop ``queue_id`` from the post-crash recovery set."""
        self._recovered_queue_ids.discard(queue_id)

    # ------------------------------------------------------------------
    # Queue lifecycle
    # ------------------------------------------------------------------

    def create_queue(
        self,
        feature_id: str,
        feature_key: str,
        project_id: str,
        project_path: str,
        tasks: List[dict],
        config: Optional[dict] = None,
        provider: str = "claude_code",
        model: Optional[str] = None,
    ) -> AutoPilotQueue:
        """Create a new autopilot queue (does NOT start it).

        Args:
            feature_id: The root feature/epic/story issue ID.
            feature_key: Human-readable key (e.g. "CB-1204").
            project_id: The project database ID.
            project_path: Filesystem path to the project root.
            tasks: Ordered list of task dicts.  Each must contain at minimum
                   ``issue_id``, ``issue_key``, ``issue_title``.  Optional
                   fields: ``execution_mode``, ``force``.
            config: Optional dict merged into QueueConfig defaults.
            provider: Execution provider name.
            model: Optional model name for local_ai.

        Returns:
            The newly created AutoPilotQueue instance.
        """
        queue_id = str(uuid.uuid4())

        # Build config with explicit validation
        VALID_ON_SUCCESS = {"MARK_WAITING_QA", "MARK_DONE", "MOVE_NEXT"}
        VALID_ON_FAIL = {"TERMINATE", "RETRY", "SKIP", "CONTINUE_MARK_FAILED"}
        MAX_RETRIES_LIMIT = 10

        queue_config = QueueConfig()
        if config:
            if "on_success" in config and config["on_success"] in VALID_ON_SUCCESS:
                queue_config.on_success = config["on_success"]
            if "on_fail" in config and config["on_fail"] in VALID_ON_FAIL:
                queue_config.on_fail = config["on_fail"]
            if "max_retries" in config:
                try:
                    queue_config.max_retries = min(int(config["max_retries"]), MAX_RETRIES_LIMIT)
                except (ValueError, TypeError):
                    pass  # Keep default

        # Build ordered task list
        queue_tasks: List[QueueTask] = []
        for idx, t in enumerate(tasks):
            queue_tasks.append(QueueTask(
                issue_id=t["issue_id"],
                issue_key=t["issue_key"],
                issue_title=t["issue_title"],
                order=idx,
                execution_mode=t.get("execution_mode", "implement"),
                force=t.get("force", False),
            ))

        queue = AutoPilotQueue(
            id=queue_id,
            feature_id=feature_id,
            feature_key=feature_key,
            project_id=project_id,
            project_path=project_path,
            provider=provider,
            model=model,
            tasks=queue_tasks,
            config=queue_config,
        )

        self._queues[queue_id] = queue
        self._active_queue_id = queue_id

        self._logger.info(
            "Created autopilot queue %s for %s with %d tasks",
            queue_id, feature_key, len(queue_tasks),
        )
        # Persist initial queue state + audit event (CB-1951)
        self._persist_async(queue, "created", {"feature_key": feature_key, "n_tasks": len(queue_tasks)})
        return queue

    # ------------------------------------------------------------------
    # Core execution loop
    # ------------------------------------------------------------------

    async def run_queue(self, queue_id: str) -> None:
        """Run the queue to completion (or until paused/aborted).

        This coroutine is intended to be launched as an ``asyncio.Task``
        by the API endpoint that starts the queue.
        """
        queue = self._queues.get(queue_id)
        if not queue:
            self._logger.error("run_queue called with unknown queue_id=%s", queue_id)
            return

        queue.status = QueueStatus.RUNNING
        queue.started_at = datetime.utcnow()
        self._logger.info("Queue %s started (%s)", queue_id, queue.feature_key)

        try:
            while queue.current_index < len(queue.tasks):
                # ---- Stop check (before pause wait) ----
                if queue._stop_flag:
                    self._logger.info("Queue %s stop flag detected (pre-pause)", queue_id)
                    break

                # ---- Pause gate ----
                if not queue._pause_event.is_set():
                    self._logger.info("Queue %s paused at index %d", queue_id, queue.current_index)
                    queue.status = QueueStatus.PAUSED
                    await queue._pause_event.wait()
                    # After resume, re-check stop
                    if queue._stop_flag:
                        self._logger.info("Queue %s stop flag detected (post-resume)", queue_id)
                        break
                    queue.status = QueueStatus.RUNNING

                # ---- CB-2382: rescan subtree for audit-spawned BUG/TASK issues ----
                try:
                    n_appended = await self._rescan_subtree_for_new_tasks(queue)
                    if n_appended:
                        self._logger.info(
                            "[AutoPilot] queue %s rescan appended %d new tasks",
                            queue_id, n_appended,
                        )
                except Exception:
                    self._logger.exception(
                        "[AutoPilot] queue %s rescan raised unexpectedly — continuing",
                        queue_id,
                    )

                task = queue.tasks[queue.current_index]

                # ---- Skip mode ----
                if task.execution_mode == "skip":
                    task.status = TaskStatus.SKIPPED
                    task.completed_at = datetime.utcnow()
                    self._logger.info("Skipped task %s (execution_mode=skip)", task.issue_key)
                    queue.current_index += 1
                    continue

                # ---- Execute the task ----
                outcome = await self._execute_task(queue, task)

                if outcome == "stopped":
                    break

                if outcome == "completed":
                    # E4 review HIGH-1 fix: a successful task resets the
                    # auto-resume circuit breaker counter so a future
                    # token-exhaust pause starts fresh.
                    queue.auto_resume_attempts = 0
                    action = await self._apply_success(queue, task, queue.current_index)
                    if action == "terminate":
                        self._logger.info("Queue %s terminated by success action", queue_id)
                        break

                elif outcome == "failed":
                    error_msg = task.error or "Unknown failure"

                    # Check for token exhaustion first
                    session = terminal_service.get_session(task.session_id) if task.session_id else None
                    if session and is_token_exhaustion(session):
                        reset_time = extract_reset_time(session)
                        # CB-1951 E3.3 + E2 LOW-1: redact error_msg before
                        # surfacing in last_error (which is exposed via the
                        # recovery API response).
                        redacted = _redact_for_audit(error_msg)
                        queue.last_error = (
                            f"TOKEN_EXHAUSTED: {redacted}"
                            + (f" (resets at {reset_time.isoformat()})" if reset_time else "")
                        )
                        queue.status = QueueStatus.WAITING_RESET
                        queue.pause_reason = "token_exhaustion"
                        queue.reset_time = reset_time
                        self._logger.warning(
                            "Queue %s paused — token exhaustion on %s (reset: %s)",
                            queue_id, task.issue_key, reset_time,
                        )
                        # Reset task to pending so it can be retried after resume
                        task.status = TaskStatus.PENDING
                        task.session_id = None
                        task.started_at = None
                        task.completed_at = None
                        task.error = None

                        # Persist auto-pause state so the recovery banner can
                        # surface it across a backend restart. (CB-1951 E3.3.2)
                        await self._persist(queue, "auto_paused", {
                            "reason": "token_exhaustion",
                            "issue_key": task.issue_key,
                            "reset_time": reset_time.isoformat() if reset_time else None,
                        })

                        # CB-1951 E4.2.1: arm the auto-resume timer if we
                        # know when the quota resets. Manual resume cancels
                        # the timer; if the timer fires it just calls
                        # resume_queue → sets _pause_event.
                        if reset_time is not None:
                            self._schedule_auto_resume(queue_id, reset_time)

                        # Block until resumed (manual button OR timer fires)
                        queue._pause_event.clear()
                        await queue._pause_event.wait()

                        if queue._stop_flag:
                            break
                        queue.status = QueueStatus.RUNNING
                        queue.last_error = None
                        queue.pause_reason = None
                        queue.reset_time = None
                        # Persist resume state
                        await self._persist(queue, "resumed", {"from": "token_exhaustion"})
                        # Re-run the same index (don't increment)
                        continue

                    # Normal failure handling
                    action = await self._apply_failure(queue, task, queue.current_index, error_msg)
                    if action == "terminate":
                        self._logger.info("Queue %s terminated by failure action", queue_id)
                        break
                    elif action == "retry":
                        # Don't increment — retry the same task
                        continue

                elif outcome == "skipped":
                    pass  # skip flag was set during polling

                # Advance to next task
                queue.current_index += 1

        except Exception as exc:
            # CB-1951 E2 LOW-1: redact loop exception message before exposing
            # via last_error (surfaced through recovery API).
            self._logger.exception("Unhandled error in queue %s loop", queue_id)
            queue.last_error = _redact_for_audit(f"Internal queue error: {exc}")
            queue.status = QueueStatus.ABORTED

        # ---- Finalize ----
        await self._finalize_queue(queue)

    # ------------------------------------------------------------------
    # Resume preflight (CB-1951 E4.3)
    # ------------------------------------------------------------------

    async def _resume_preflight(
        self, queue: AutoPilotQueue, task: QueueTask
    ) -> str:
        """Lightweight checks before executing a task.

        Returns:
            "ok"     — proceed with execution
            "skip"   — issue is already terminal externally; mark task
                        completed-skip and advance
            "abort"  — environment is broken (CLI missing); mark failed

        These guards are most useful on resume after long pauses, where
        the environment may have shifted (CLI uninstalled, issue closed
        manually in CodeBoard). Failures here never crash the queue —
        a False return just yields "abort" and the failure flow takes
        over with a clean error message.
        """
        import shutil

        # E4.3.1: verify the Claude CLI is still on PATH for the
        # claude_code provider. The full validation happens in
        # terminal_service.start_execution but doing it here lets us
        # short-circuit with a friendlier error path before the subprocess
        # spawn machinery kicks in.
        if queue.provider == "claude_code" and shutil.which("claude") is None:
            self._logger.error(
                "Queue %s preflight failed — `claude` CLI not on PATH",
                queue.id,
            )
            task.status = TaskStatus.FAILED
            task.error = "Claude CLI not found on PATH"
            task.completed_at = datetime.utcnow()
            return "abort"

        # E4.3.2: re-fetch the issue and skip if it's already terminal
        # (someone moved it to CWQ/DONE manually while we were paused).
        # Wrapping in a try-except so a transient DB hiccup doesn't break
        # a recovery — fall through to normal execution and let
        # terminal_service report the real error if any.
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Issue).where(Issue.id == task.issue_id)
                )
                issue = result.scalar_one_or_none()
                if issue is None:
                    self._logger.warning(
                        "Queue %s preflight: issue %s missing; skipping",
                        queue.id, task.issue_id,
                    )
                    task.status = TaskStatus.SKIPPED
                    task.error = "Issue not found in database"
                    task.completed_at = datetime.utcnow()
                    return "skip"
                if issue.status in ("COMPLETED_WAITING_QA", "DONE"):
                    self._logger.info(
                        "Queue %s preflight: issue %s already %s — skipping",
                        queue.id, task.issue_key, issue.status,
                    )
                    task.status = TaskStatus.SKIPPED
                    task.completed_at = datetime.utcnow()
                    return "skip"
        except Exception:
            self._logger.exception(
                "Queue %s preflight DB check failed — proceeding anyway",
                queue.id,
            )

        return "ok"

    # ------------------------------------------------------------------
    # CB-2382 — Audit-rescan: pull in new BUG/TASK issues spawned mid-run
    # ------------------------------------------------------------------

    async def _rescan_subtree_for_new_tasks(self, queue: AutoPilotQueue) -> int:
        """Walk the feature's descendant tree for new BACKLOG BUG/TASK issues.

        Code-reviewer and security-auditor agents spawn new ``BUG`` (and
        occasionally ``TASK``) issues under the active feature while the queue
        is running.  Without this rescan those issues are never picked up and
        the feature never reaches a clean terminal state.

        Strategy (two-query, Python-side filtering — simpler than a recursive
        CTE and equivalent for the typical subtree size):

        1. Collect all descendant IDs by walking ``Issue.parentId`` starting
           from ``queue.feature_id`` (BFS, capped at _RESCAN_MAX_DEPTH levels,
           IN-clause chunked at 500 IDs to avoid SQLite variable limits).
        2. Filter to: type IN ('BUG','TASK'), status='BACKLOG',
           createdAt > queue.started_at, reporter IN _TRUSTED_REPORTERS,
           id NOT already in queue.

        For each qualifying issue, append a ``QueueTask``, add to
        ``queue._appended_ids``, emit a ``task_appended`` audit event.
        ``save_queue`` + ``db.commit`` are called once after all appends
        (not per-issue) to reduce write amplification.

        Safety limits:
        - _RESCAN_MAX_APPENDS_PER_ITERATION: cap per call (rate limit).
        - _RESCAN_MAX_APPENDS_PER_RUN: lifetime cap per queue (DoS guard).
        - _RESCAN_MAX_DEPTH: BFS depth limit (runaway-tree guard).
        - _TRUSTED_REPORTERS: only issues from known AI agents are appended.

        Args:
            queue: The running ``AutoPilotQueue``.

        Returns:
            Number of tasks appended (0 when nothing new).
        """
        if not queue.started_at:
            return 0

        # --- Lifetime cap check (DoS guard HIGH-1) ---
        if queue._appended_count >= _RESCAN_MAX_APPENDS_PER_RUN:
            if not queue._rescan_cap_logged:
                queue._rescan_cap_logged = True
                try:
                    async with AsyncSessionLocal() as db:
                        await record_event(
                            db,
                            queue.id,
                            "rescan_cap_exceeded",
                            {
                                "total_appended": queue._appended_count,
                                "max": _RESCAN_MAX_APPENDS_PER_RUN,
                            },
                        )
                        await db.commit()
                except Exception:
                    self._logger.exception(
                        "[AutoPilot] queue %s failed to emit rescan_cap_exceeded event",
                        queue.id,
                    )
            return 0

        # IDs already tracked (original + previously appended) for O(1) de-dup
        existing_ids: set[str] = {t.issue_id for t in queue.tasks} | queue._appended_ids

        appended = 0
        try:
            async with AsyncSessionLocal() as db:
                # --- Step 1: BFS to collect all descendant issue IDs ---
                # Depth-bounded (_RESCAN_MAX_DEPTH) to prevent runaway traversal.
                # IN-clauses chunked at 500 IDs for SQLite compatibility.
                descendant_ids: list[str] = []
                frontier: list[str] = [queue.feature_id]
                visited: set[str] = set()
                depth = 0
                while frontier and depth < _RESCAN_MAX_DEPTH:
                    current_batch = [fid for fid in frontier if fid not in visited]
                    if not current_batch:
                        break
                    visited.update(current_batch)

                    # Chunk the IN-clause to avoid hitting SQLite's
                    # SQLITE_MAX_VARIABLE_NUMBER (default 999).
                    children: list[str] = []
                    for i in range(0, len(current_batch), 500):
                        chunk = current_batch[i:i + 500]
                        result = await db.execute(
                            select(Issue.id).where(Issue.parentId.in_(chunk))
                        )
                        children.extend(row[0] for row in result.all())

                    descendant_ids.extend(children)
                    frontier = children
                    depth += 1

                if not descendant_ids:
                    return 0

                # --- Step 2: Filter for new eligible tasks ---
                # Only issues from trusted AI reporters are auto-appended
                # (prevents externally-created issues from being silently
                # injected into the execution queue — HIGH-2).
                result = await db.execute(
                    select(Issue).where(
                        Issue.id.in_(descendant_ids),
                        Issue.type.in_(["BUG", "TASK"]),
                        Issue.status == "BACKLOG",
                        Issue.createdAt > queue.started_at,
                        Issue.reporter.in_(_TRUSTED_REPORTERS),
                    )
                )
                candidates = result.scalars().all()

                for issue in candidates:
                    if issue.id in existing_ids:
                        continue

                    # --- Per-iteration cap (rate limit) ---
                    if appended >= _RESCAN_MAX_APPENDS_PER_ITERATION:
                        break

                    # --- Lifetime cap check (re-checked inside loop for the
                    # case where we hit cap mid-iteration) ---
                    if queue._appended_count >= _RESCAN_MAX_APPENDS_PER_RUN:
                        break

                    new_idx = len(queue.tasks)
                    new_task = QueueTask(
                        issue_id=issue.id,
                        issue_key=issue.key or "",
                        issue_title=issue.title or "",
                        order=new_idx,
                        execution_mode="implement",
                        force=False,
                    )
                    queue.tasks.append(new_task)
                    queue._appended_ids.add(issue.id)
                    queue._appended_count += 1
                    existing_ids.add(issue.id)

                    # Emit per-issue audit event (granularity matters for the
                    # audit log); save_queue + commit deferred to after the loop.
                    await record_event(
                        db,
                        queue.id,
                        "task_appended",
                        {
                            "issueId": issue.id,
                            "issueKey": issue.key or "",
                            "source": "audit_rescan",
                            "sequence": new_idx,
                        },
                    )
                    appended += 1

                # Hoist save_queue + commit out of the per-issue loop (MEDIUM-1).
                # One write regardless of how many issues were appended.
                if appended > 0:
                    await save_queue(db, queue)
                    await db.commit()

        except Exception:
            self._logger.exception(
                "[AutoPilot] queue %s rescan failed — continuing without new tasks",
                queue.id,
            )
            return appended

        return appended

    # ------------------------------------------------------------------
    # Task execution + polling
    # ------------------------------------------------------------------

    async def _execute_task(self, queue: AutoPilotQueue, task: QueueTask) -> str:
        """Execute a single task and poll until completion.

        Returns one of: "completed", "failed", "skipped", "stopped".
        """
        # CB-1951 E4.3: preflight checks before launching a subprocess.
        # These guards matter most on resume after a long pause — the
        # environment may have changed (CLI uninstalled, issue completed
        # externally) and we don't want to burn tokens re-running stale
        # work.
        # E4 review MEDIUM-2: preflight "skip" returns "skipped" (NOT
        # "completed") so run_queue advances without firing MARK_WAITING_QA
        # on an issue we never touched.
        preflight = await self._resume_preflight(queue, task)
        if preflight == "skip":
            return "skipped"
        if preflight == "abort":
            return "failed"

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        # Persist task-started state (CB-1951)
        await self._persist(queue, "task_started", {
            "issue_key": task.issue_key, "order": task.order,
        })

        try:
            async with AsyncSessionLocal() as db:
                # Fetch full issue record
                result = await db.execute(
                    select(Issue).where(Issue.id == task.issue_id)
                )
                issue = result.scalar_one_or_none()
                if not issue:
                    task.status = TaskStatus.FAILED
                    task.error = f"Issue {task.issue_key} not found in database"
                    task.completed_at = datetime.utcnow()
                    return "failed"

                # Mark issue IN_PROGRESS
                issue.status = "IN_PROGRESS"
                issue.updatedAt = datetime.utcnow()
                await cascade_in_progress_to_parents(db, task.issue_id)
                await db.commit()

                # Build execution context
                rich_prompt = await build_execution_context(
                    db=db,
                    issue_id=issue.id,
                    issue_key=issue.key,
                    issue_title=issue.title,
                    issue_type=issue.type,
                    issue_description=issue.description or "",
                )

                # Handle audit/rewrite prompt prefixes
                if task.execution_mode == "audit":
                    rich_prompt = (
                        "AUDIT MODE: Review the existing implementation for this task. "
                        "Check for bugs, security issues, missing edge cases, and code quality. "
                        "Report findings but do NOT rewrite unless there are critical issues.\n\n"
                        + rich_prompt
                    )
                elif task.execution_mode == "rewrite":
                    # Reset issue to TODO so it can be re-implemented
                    issue.status = "TODO"
                    issue.updatedAt = datetime.utcnow()
                    await db.commit()
                    rich_prompt = (
                        "REWRITE MODE: The previous implementation was rejected. "
                        "Start fresh and re-implement this task from scratch.\n\n"
                        + rich_prompt
                    )

                # Resolve feature_id from parent chain for cache preservation
                parent_chain = await get_parent_chain(db, issue.id)
                feature_id = None
                for ancestor in parent_chain:
                    if ancestor["type"] == "FEATURE":
                        feature_id = ancestor["id"]
                        break
                # Fallback: use the queue's feature_id
                if not feature_id:
                    feature_id = queue.feature_id

                # Resolve execution provider
                try:
                    exec_provider = ExecutionProvider(queue.provider)
                except ValueError:
                    exec_provider = ExecutionProvider.CLAUDE_CODE

                # Start execution
                session = await terminal_service.start_execution(
                    issue_id=issue.id,
                    issue_key=issue.key,
                    issue_title=issue.title,
                    issue_description=issue.description or "",
                    issue_type=issue.type,
                    provider=exec_provider,
                    project_path=queue.project_path,
                    project_id=queue.project_id,
                    prompt_override=rich_prompt,
                    feature_id=feature_id,
                    db=db,
                    force=task.force,
                )

            # Store session reference on the task
            task.session_id = session.id

            # If the session failed immediately (e.g. path validation, pool full)
            if session.status == ExecutionStatus.FAILED:
                task.status = TaskStatus.FAILED
                task.error = session.error
                task.completed_at = datetime.utcnow()
                return "failed"

            # ---- Poll for completion ----
            return await self._poll_session(queue, task, session.id)

        except Exception as exc:
            self._logger.exception(
                "Error executing task %s in queue %s", task.issue_key, queue.id
            )
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.completed_at = datetime.utcnow()
            return "failed"

    async def _poll_session(
        self, queue: AutoPilotQueue, task: QueueTask, session_id: str
    ) -> str:
        """Poll terminal_service until the session finishes.

        Returns: "completed", "failed", "skipped", "stopped".
        """
        while True:
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

            # Check stop flag
            if queue._stop_flag:
                self._logger.info(
                    "Stop flag during poll for %s — cancelling session", task.issue_key
                )
                await terminal_service.stop_execution(session_id)
                task.status = TaskStatus.FAILED
                task.error = "Aborted by user"
                task.completed_at = datetime.utcnow()
                return "stopped"

            # Check skip flag
            if queue._skip_flag:
                self._logger.info("Skip flag during poll for %s", task.issue_key)
                await terminal_service.stop_execution(session_id)
                task.status = TaskStatus.SKIPPED
                task.completed_at = datetime.utcnow()
                queue._skip_flag = False
                return "skipped"

            session = terminal_service.get_session(session_id)
            if not session:
                # Session disappeared — treat as failure
                task.status = TaskStatus.FAILED
                task.error = "Session lost — terminal_service returned None"
                task.completed_at = datetime.utcnow()
                return "failed"

            if session.status == ExecutionStatus.COMPLETED:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.utcnow()
                return "completed"

            if session.status in (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
                task.status = TaskStatus.FAILED
                task.error = session.error or f"Session ended with status {session.status.value}"
                task.completed_at = datetime.utcnow()
                return "failed"

            # Still running — continue polling

    # ------------------------------------------------------------------
    # Success / failure actions
    # ------------------------------------------------------------------

    async def _apply_success(
        self, queue: AutoPilotQueue, task: QueueTask, index: int
    ) -> str:
        """Apply the configured success action.

        Returns "continue" or "terminate".
        """
        action = queue.config.on_success

        try:
            async with AsyncSessionLocal() as db:
                if action == "MARK_WAITING_QA":
                    await self._set_issue_status(db, task.issue_id, "COMPLETED_WAITING_QA")
                    await cascade_status_to_parents(
                        db, task.issue_id, target_status="COMPLETED_WAITING_QA"
                    )
                elif action == "MARK_DONE":
                    await self._set_issue_status(db, task.issue_id, "DONE")
                    await cascade_status_to_parents(
                        db, task.issue_id, target_status="DONE"
                    )
                elif action == "MOVE_NEXT":
                    # Don't change the issue status — just proceed
                    pass
                else:
                    self._logger.warning("Unknown on_success action: %s", action)

                await db.commit()

        except Exception:
            self._logger.exception(
                "Error applying success action for %s", task.issue_key
            )

        self._logger.info(
            "Task %s completed (action=%s)", task.issue_key, action
        )
        # Persist task-completed state (CB-1951)
        await self._persist(queue, "task_completed", {
            "issue_key": task.issue_key, "action": action, "order": task.order,
        })
        return "continue"

    async def _apply_failure(
        self,
        queue: AutoPilotQueue,
        task: QueueTask,
        index: int,
        error_msg: str,
    ) -> str:
        """Apply the configured failure action.

        Returns "continue", "retry", or "terminate".
        """
        action = queue.config.on_fail
        queue.last_error = f"{task.issue_key}: {error_msg}"

        self._logger.warning(
            "Task %s failed (action=%s, retries=%d/%d): %s",
            task.issue_key, action, task.retry_count,
            queue.config.max_retries, error_msg,
        )

        if action == "TERMINATE":
            queue.status = QueueStatus.ABORTED
            return "terminate"

        if action == "RETRY":
            if task.retry_count < queue.config.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                task.session_id = None
                task.started_at = None
                task.completed_at = None
                task.error = None
                self._logger.info(
                    "Retrying task %s (attempt %d/%d)",
                    task.issue_key, task.retry_count, queue.config.max_retries,
                )
                # Persist task-failed (will retry) state (CB-1951)
                await self._persist(queue, "task_failed", {
                    "issue_key": task.issue_key, "action": "retry",
                    "attempt": task.retry_count,
                    "max_retries": queue.config.max_retries,
                    "error": _redact_for_audit(error_msg),
                })
                # Reset issue to TODO so it can be re-executed.
                # Also revert any ancestor that was rolled up to CWQ — leaving
                # a CWQ container with an incomplete child is a corrupt state
                # that confuses subsequent cascades. (CB-1952)
                try:
                    async with AsyncSessionLocal() as db:
                        await self._set_issue_status(db, task.issue_id, "TODO")
                        await db.flush()
                        await cascade_revert_to_parents(db, task.issue_id)
                        await db.commit()
                except Exception:
                    self._logger.exception(
                        "Error resetting %s to TODO for retry", task.issue_key
                    )
                return "retry"
            else:
                self._logger.warning(
                    "Max retries exhausted for %s — marking failed", task.issue_key
                )
                # Persist task-failed (max retries) state (CB-1951)
                await self._persist(queue, "task_failed", {
                    "issue_key": task.issue_key, "action": "max_retries_exhausted",
                    "attempt": task.retry_count,
                    "error": _redact_for_audit(error_msg),
                })
                # Fall through to CONTINUE_MARK_FAILED behavior.
                # Revert ancestors so CWQ containers don't sit on incomplete
                # children. (CB-1952)
                try:
                    async with AsyncSessionLocal() as db:
                        await self._set_issue_status(db, task.issue_id, "TODO")
                        await db.flush()
                        await cascade_revert_to_parents(db, task.issue_id)
                        await db.commit()
                except Exception:
                    self._logger.exception(
                        "Error resetting %s to TODO after exhausted retries",
                        task.issue_key,
                    )
                return "continue"

        if action == "SKIP":
            task.status = TaskStatus.SKIPPED
            await self._persist(queue, "task_failed", {
                "issue_key": task.issue_key, "action": "skip",
                "error": _redact_for_audit(error_msg),
            })
            return "continue"

        # Default: CONTINUE_MARK_FAILED
        # Reset the issue back to TODO so it is visibly "not done", and
        # revert ancestors so we never leave a CWQ container holding an
        # incomplete child. (CB-1952)
        try:
            async with AsyncSessionLocal() as db:
                await self._set_issue_status(db, task.issue_id, "TODO")
                await db.flush()
                await cascade_revert_to_parents(db, task.issue_id)
                await db.commit()
        except Exception:
            self._logger.exception(
                "Error resetting %s to TODO after failure", task.issue_key
            )
        # Persist task-failed (continue) state (CB-1951)
        await self._persist(queue, "task_failed", {
            "issue_key": task.issue_key, "action": "continue_mark_failed",
            "error": _redact_for_audit(error_msg),
        })
        return "continue"

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_issue_status(
        db: AsyncSession, issue_id: str, status: str
    ) -> None:
        """Set an issue's status and update its timestamp."""
        result = await db.execute(select(Issue).where(Issue.id == issue_id))
        issue = result.scalar_one_or_none()
        if issue:
            issue.status = status
            issue.updatedAt = datetime.utcnow()
            if status in ("COMPLETED_WAITING_QA", "DONE"):
                issue.completedAt = datetime.utcnow()

    # ------------------------------------------------------------------
    # Persistence (CB-1951)
    # ------------------------------------------------------------------

    async def _persist(
        self,
        queue: AutoPilotQueue,
        event_type: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> None:
        """Write-through persistence helper.

        Saves the queue's current in-memory state to the DB and optionally
        appends an audit-log event in the same transaction. DB errors are
        swallowed and logged — the in-memory queue remains the source of
        truth during a session, so a transient DB hiccup must not crash
        the executor. (CB-1951)

        E10: when ``_persistence_enabled`` is False, returns immediately
        as a no-op. The queue runs in-memory only, matching pre-E1 behaviour.
        """
        if not self._persistence_enabled:
            return
        try:
            async with AsyncSessionLocal() as db:
                await save_queue(db, queue)
                if event_type:
                    await record_event(db, queue.id, event_type, payload)
                await db.commit()
        except Exception:
            self._logger.exception(
                "Failed to persist queue %s state (event=%s) — continuing in-memory only",
                queue.id,
                event_type,
            )

    def _persist_async(
        self,
        queue: AutoPilotQueue,
        event_type: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> None:
        """Fire-and-forget persistence for sync control methods.

        Used by ``pause_queue`` / ``resume_queue`` / ``skip_current`` which
        are called synchronously from FastAPI handlers. Schedules the save
        on the running event loop without awaiting — the in-memory flag
        flip has already taken effect, the persist is just durability.
        """
        if not self._persistence_enabled:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._persist(queue, event_type, payload))
        except RuntimeError:
            # No running loop — happens in tests or odd lifecycle moments.
            self._logger.debug(
                "No running event loop; skipping async persist for queue %s",
                queue.id,
            )

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    async def _finalize_queue(self, queue: AutoPilotQueue) -> None:
        """Finalize a queue after the loop exits."""
        queue.completed_at = datetime.utcnow()

        # Determine final status
        if queue._stop_flag and queue.status != QueueStatus.ABORTED:
            queue.status = QueueStatus.ABORTED

        all_done = all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
            for t in queue.tasks
        )
        if all_done and queue.status == QueueStatus.RUNNING:
            queue.status = QueueStatus.COMPLETED

        # If fully completed, mark the feature as COMPLETED_WAITING_QA
        if queue.status == QueueStatus.COMPLETED:
            try:
                async with AsyncSessionLocal() as db:
                    await self._set_issue_status(
                        db, queue.feature_id, "COMPLETED_WAITING_QA"
                    )
                    await cascade_status_to_parents(
                        db, queue.feature_id, target_status="COMPLETED_WAITING_QA"
                    )
                    await db.commit()
                self._logger.info(
                    "Queue %s fully completed — feature %s marked COMPLETED_WAITING_QA",
                    queue.id, queue.feature_key,
                )
            except Exception:
                self._logger.exception(
                    "Error marking feature %s complete", queue.feature_key
                )

        # Clear active queue
        if self._active_queue_id == queue.id:
            self._active_queue_id = None

        # CB-1951 E4.2.2: cancel any pending auto-resume timer for this queue
        self._cancel_auto_resume(queue.id)

        # Persist final terminal state (CB-1951) before pruning so the row
        # reflects status=completed|aborted on disk.
        await self._persist(queue, "finalized", {
            "final_status": queue.status.value,
            "completed_count": sum(1 for t in queue.tasks if t.status == TaskStatus.COMPLETED),
            "total": len(queue.tasks),
        })

        # Prune old completed/aborted queues (keep last 10)
        self._prune_old_queues(max_history=10)

        self._logger.info(
            "Queue %s finalized — status=%s, completed=%d/%d",
            queue.id,
            queue.status.value,
            sum(1 for t in queue.tasks if t.status == TaskStatus.COMPLETED),
            len(queue.tasks),
        )

    def _prune_old_queues(self, max_history: int = 10) -> None:
        """Remove old completed/aborted queues to prevent unbounded memory growth."""
        terminal_queues = [
            (qid, q) for qid, q in self._queues.items()
            if q.status in (QueueStatus.COMPLETED, QueueStatus.ABORTED)
               and qid != self._active_queue_id
        ]
        if len(terminal_queues) <= max_history:
            return
        # Sort by completed_at, oldest first
        terminal_queues.sort(
            key=lambda pair: pair[1].completed_at or pair[1].created_at
        )
        to_remove = terminal_queues[:len(terminal_queues) - max_history]
        for qid, _ in to_remove:
            del self._queues[qid]
            # E4 review HIGH-2: defensive cleanup of any stray timer handle
            # that didn't get cancelled through the normal abort/finalize
            # paths. Belt-and-suspenders against handle leaks.
            self._cancel_auto_resume(qid)
            self._recovered_queue_ids.discard(qid)
            self._logger.debug("Pruned old queue %s", qid)

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------

    def get_queue(self, queue_id: str) -> Optional[AutoPilotQueue]:
        """Get a queue by ID."""
        return self._queues.get(queue_id)

    def get_active_queue(self) -> Optional[AutoPilotQueue]:
        """Get the currently active queue, if any."""
        if self._active_queue_id:
            return self._queues.get(self._active_queue_id)
        return None

    def get_queue_status(self, queue_id: str) -> Optional[dict]:
        """Get a full serializable status dict for a queue.

        Returns None if the queue does not exist.
        """
        queue = self._queues.get(queue_id)
        if not queue:
            return None

        tasks_data = []
        for t in queue.tasks:
            # Enrich with live session info if running
            session_info = None
            if t.session_id and t.status == TaskStatus.RUNNING:
                session = terminal_service.get_session(t.session_id)
                if session:
                    session_info = {
                        "phase": session.phase.value,
                        "progress_percent": session.progress_percent,
                        "current_action": session.current_action,
                        "files_read": session.files_read,
                        "files_written": session.files_written,
                        "commands_run": session.commands_run,
                    }

            tasks_data.append({
                "issue_id": t.issue_id,
                "issue_key": t.issue_key,
                "issue_title": t.issue_title,
                "order": t.order,
                "status": t.status.value,
                "execution_mode": t.execution_mode,
                "session_id": t.session_id,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "error": t.error,
                "retry_count": t.retry_count,
                "session_info": session_info,
            })

        completed_count = sum(1 for t in queue.tasks if t.status == TaskStatus.COMPLETED)
        skipped_count = sum(1 for t in queue.tasks if t.status == TaskStatus.SKIPPED)
        failed_count = sum(1 for t in queue.tasks if t.status == TaskStatus.FAILED)
        total = len(queue.tasks)
        progress_pct = ((completed_count + skipped_count) / total * 100) if total > 0 else 0.0

        return {
            "id": queue.id,
            "feature_id": queue.feature_id,
            "feature_key": queue.feature_key,
            "project_id": queue.project_id,
            "provider": queue.provider,
            "model": queue.model,
            "status": queue.status.value,
            "current_index": queue.current_index,
            "tasks": tasks_data,
            "config": {
                "on_success": queue.config.on_success,
                "on_fail": queue.config.on_fail,
                "max_retries": queue.config.max_retries,
            },
            "progress": {
                "total": total,
                "completed": completed_count,
                "skipped": skipped_count,
                "failed": failed_count,
                "pending": total - completed_count - skipped_count - failed_count,
                "percent": round(progress_pct, 1),
            },
            "created_at": queue.created_at.isoformat() if queue.created_at else None,
            "started_at": queue.started_at.isoformat() if queue.started_at else None,
            "completed_at": queue.completed_at.isoformat() if queue.completed_at else None,
            "last_error": queue.last_error,
        }

    # ------------------------------------------------------------------
    # Control methods
    # ------------------------------------------------------------------

    def pause_queue(self, queue_id: str) -> bool:
        """Pause the queue.  The current task finishes, then the queue blocks."""
        queue = self._queues.get(queue_id)
        if not queue or queue.status not in (QueueStatus.RUNNING, QueueStatus.WAITING_RESET):
            return False
        queue._pause_event.clear()
        queue.status = QueueStatus.PAUSED
        self._logger.info("Queue %s paused", queue_id)
        # Persist pause state (CB-1951)
        self._persist_async(queue, "manual_paused", {"reason": "manual"})
        return True

    def resume_queue(self, queue_id: str) -> bool:
        """Resume a paused queue. (CB-1951 E4.1.1 + E4.1.2)

        Refuses to resume if there is no active task to run — returning
        False rather than silently succeeding so the API caller can
        surface a clean error to the user.
        """
        queue = self._queues.get(queue_id)
        if not queue or queue.status not in (QueueStatus.PAUSED, QueueStatus.WAITING_RESET):
            return False
        # E4.1.2: refuse resume if there is nothing left to run.
        if queue.current_index >= len(queue.tasks):
            self._logger.warning(
                "Queue %s resume refused — no active task at index %d/%d",
                queue_id, queue.current_index, len(queue.tasks),
            )
            return False
        # E4.1.1: clear pause/reset bookkeeping so the queue dataclass and
        # the persisted record both reflect the post-resume state.
        queue.last_error = None
        queue.pause_reason = None
        queue.reset_time = None
        # Cancel any pending auto-resume timer — manual takes priority.
        self._cancel_auto_resume(queue_id)
        queue._pause_event.set()
        # Status will be set back to RUNNING by the loop
        self._logger.info("Queue %s resumed", queue_id)
        # Persist resume state (CB-1951)
        self._persist_async(queue, "resumed", {})
        return True

    def skip_current(self, queue_id: str) -> bool:
        """Skip the currently executing task.  The session is stopped and the
        queue advances to the next task."""
        queue = self._queues.get(queue_id)
        if not queue or queue.status != QueueStatus.RUNNING:
            return False
        queue._skip_flag = True
        self._logger.info("Queue %s — skip requested for current task", queue_id)
        # Persist skip state (CB-1951)
        self._persist_async(queue, "task_failed", {
            "action": "skip_requested",
            "current_index": queue.current_index,
        })
        return True

    async def abort_queue(
        self, queue_id: str, action: str = "mark_failed"
    ) -> bool:
        """Abort the queue entirely.

        Args:
            queue_id: Queue to abort.
            action: What to do with remaining tasks.
                    "mark_failed" — mark all pending tasks as FAILED.
                    "mark_skipped" — mark all pending tasks as SKIPPED.
                    "leave" — leave pending tasks unchanged.
        """
        queue = self._queues.get(queue_id)
        if not queue:
            return False

        queue._stop_flag = True
        queue.status = QueueStatus.ABORTED

        # CB-1951 E4.2.2: cancel any pending auto-resume timer
        self._cancel_auto_resume(queue_id)

        # If paused, unblock the loop so it can exit
        queue._pause_event.set()

        # Stop current running session if any
        current_task = None
        if queue.current_index < len(queue.tasks):
            current_task = queue.tasks[queue.current_index]
            if current_task.session_id and current_task.status == TaskStatus.RUNNING:
                await terminal_service.stop_execution(current_task.session_id)
                current_task.status = TaskStatus.FAILED
                current_task.error = "Aborted by user"
                current_task.completed_at = datetime.utcnow()

        # Apply action to remaining pending tasks
        for task in queue.tasks:
            if task.status == TaskStatus.PENDING:
                if action == "mark_failed":
                    task.status = TaskStatus.FAILED
                    task.error = "Queue aborted"
                    task.completed_at = datetime.utcnow()
                elif action == "mark_skipped":
                    task.status = TaskStatus.SKIPPED
                    task.completed_at = datetime.utcnow()
                # "leave" — do nothing

        self._logger.info(
            "Queue %s aborted (action=%s)", queue_id, action
        )
        # Persist abort terminal state (CB-1951)
        await self._persist(queue, "aborted", {"action": action})
        return True

    # ------------------------------------------------------------------
    # Wait-for-reset / auto-resume
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # E4 — Scheduled auto-resume after token reset (CB-1951)
    # ------------------------------------------------------------------

    # Buffer added on top of the parsed reset time so we don't fire at the
    # exact instant the rate-limit window opens (Anthropic's clock + ours
    # may drift a few seconds, and a fresh request immediately after the
    # advertised reset has been observed to still 429).
    _AUTO_RESUME_BUFFER_SECONDS = 60

    # Cap on consecutive auto-resume attempts before the queue is downgraded
    # to manual-resume. Defends against runaway token-burn loops on a
    # persistently-failing API key. (E4 review HIGH-1 + SEC MEDIUM-1)
    _AUTO_RESUME_MAX_ATTEMPTS = 3

    # Sanity-check window for rehydrated `reset_time` values. Anything older
    # than this in the past, or further in the future, is treated as
    # corrupted state and the queue is downgraded to manual-resume rather
    # than auto-resumed. (E4 SEC MEDIUM-2)
    _REHYDRATION_RESET_WINDOW_HOURS = 12

    async def wait_for_reset(
        self, queue_id: str, reset_time_str: Optional[str] = None
    ) -> None:
        """Schedule an automatic resume when the token quota resets.

        This is the legacy callable used by the API layer; it now delegates
        to :meth:`_schedule_auto_resume` so cancellation, persistence, and
        rehydration share one path. (CB-1951 E4.2.1)

        ``reset_time_str`` accepts the legacy AM/PM format. New callers
        should prefer :meth:`_schedule_auto_resume` with a parsed
        ``datetime`` (see ``extract_reset_time``).
        """
        queue = self._queues.get(queue_id)
        if not queue:
            return

        target: Optional[datetime] = None
        if reset_time_str:
            target = _parse_reset_time_from_text(f"resets at {reset_time_str}")
        if target is None:
            from datetime import timedelta
            target = datetime.utcnow() + timedelta(hours=1)

        self._schedule_auto_resume(queue_id, target)
        # Wait synchronously so existing callers (API endpoint) keep their
        # request semantics — resolves when the timer fires or is cancelled.
        handle = self._resume_handles.get(queue_id)
        if handle is not None:
            try:
                await handle
            except asyncio.CancelledError:
                pass

    def _schedule_auto_resume(self, queue_id: str, reset_time: datetime) -> None:
        """Arm an asyncio timer that resumes the queue at
        ``reset_time + AUTO_RESUME_BUFFER_SECONDS``.

        Idempotent — if a handle already exists for this queue it is
        cancelled first so the new reset_time wins (CB-1951 E4.2.1).
        Cancellation also happens on manual resume, abort, finalize, and
        before re-arming on rehydration.
        """
        if queue_id not in self._queues:
            self._logger.warning(
                "Refusing to schedule auto-resume for unknown queue %s", queue_id
            )
            return
        # Cancel any pending timer first
        self._cancel_auto_resume(queue_id)

        from datetime import timedelta
        target = reset_time + timedelta(seconds=self._AUTO_RESUME_BUFFER_SECONDS)
        delay = (target - datetime.utcnow()).total_seconds()
        if delay < 0:
            # Reset is already past — fire immediately. Useful when the
            # backend rehydrates after a crash that lasted past the reset.
            delay = 0
        self._logger.info(
            "Queue %s auto-resume scheduled in %.1fs (target=%s)",
            queue_id, delay, target.isoformat(),
        )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._logger.debug(
                "No running loop for auto-resume scheduling on queue %s", queue_id
            )
            return

        async def _runner():
            # E4 review HIGH-2: always release the handle slot on exit,
            # whether the timer fires cleanly, gets cancelled, or crashes
            # inside _fire_auto_resume / _persist. Otherwise stale entries
            # leak into _resume_handles after pruning.
            try:
                try:
                    await asyncio.sleep(delay)
                    await self._fire_auto_resume(queue_id)
                except asyncio.CancelledError:
                    self._logger.info(
                        "Queue %s auto-resume timer cancelled", queue_id
                    )
                    raise
                except Exception:
                    self._logger.exception(
                        "Queue %s auto-resume timer crashed", queue_id
                    )
            finally:
                # Don't pop if a NEW handle replaced ours (idempotent
                # re-schedule case).
                current = self._resume_handles.get(queue_id)
                if current is asyncio.current_task():
                    self._resume_handles.pop(queue_id, None)

        task = loop.create_task(_runner())
        self._resume_handles[queue_id] = task

        # Persist the scheduling so a backend restart can re-arm it.
        # (E4 review MEDIUM-1: removed the walrus-on-None pattern.)
        queue_obj = self._queues.get(queue_id)
        if queue_obj is not None:
            self._persist_async(queue_obj, "auto_resume_scheduled", {
                "reset_time": reset_time.isoformat(),
                "fire_at": target.isoformat(),
            })

    def _cancel_auto_resume(self, queue_id: str) -> bool:
        """Cancel a pending auto-resume timer if present. Returns True if
        a timer was cancelled. (CB-1951 E4.2.2)"""
        task = self._resume_handles.pop(queue_id, None)
        if task is None:
            return False
        if not task.done():
            task.cancel()
        return True

    async def _fire_auto_resume(self, queue_id: str) -> None:
        """Timer-driven resume. Only resumes if the queue is still in
        WAITING_RESET — manual user actions in the meantime take priority.

        E4 review HIGH-1 fix: increment the auto-resume attempts counter
        FIRST and trip the circuit breaker if exceeded. Only then attempt
        ``resume_queue``; clearing of `pause_reason` / `reset_time` is
        moved INSIDE ``resume_queue`` so a refused resume (e.g. no active
        task) can't leave the queue with inconsistent bookkeeping.
        """
        queue = self._queues.get(queue_id)
        if queue is None:
            self._logger.info(
                "Auto-resume fired for unknown queue %s — dropping", queue_id
            )
            return
        if queue.status != QueueStatus.WAITING_RESET:
            self._logger.info(
                "Auto-resume fired for queue %s but status=%s — skipping",
                queue_id, queue.status.value,
            )
            return

        queue.auto_resume_attempts += 1
        if queue.auto_resume_attempts > self._AUTO_RESUME_MAX_ATTEMPTS:
            # Circuit breaker: stop auto-resuming and require manual
            # intervention to prevent runaway token burn. (SEC MEDIUM-1)
            self._logger.error(
                "[AutoPilot] Queue %s auto-resume circuit breaker tripped "
                "after %d consecutive attempts — downgrading to manual",
                queue_id, queue.auto_resume_attempts,
            )
            queue.pause_reason = "manual"
            await self._persist(queue, "auto_resume_circuit_breaker_tripped", {
                "attempts": queue.auto_resume_attempts,
            })
            return

        self._logger.warning(
            "[AutoPilot] Queue %s auto-resuming after token reset (attempt %d/%d)",
            queue_id, queue.auto_resume_attempts, self._AUTO_RESUME_MAX_ATTEMPTS,
        )
        if self.resume_queue(queue_id):
            await self._persist(queue, "auto_resume_fired", {
                "attempt": queue.auto_resume_attempts,
            })
        else:
            self._logger.warning(
                "Queue %s auto-resume refused by resume_queue (no active task?)",
                queue_id,
            )

    async def rearm_auto_resume_timers(self) -> int:
        """Re-arm pending auto-resume timers after a backend restart.

        Called from rehydrate_from_db once queues have been loaded back
        into _queues. Walks _queues looking for WAITING_RESET state with
        a sanity-checked reset_time and arms timers. Returns the count
        rearmed. (CB-1951 E4.2.3 + SEC MEDIUM-2)

        Refuses to re-arm and downgrades to manual-resume if:
          - reset_time is missing
          - pause_reason is crash_recovery (already manual-gated)
          - reset_time is more than ``_REHYDRATION_RESET_WINDOW_HOURS``
            in the past or future (likely corrupted DB state)
        """
        from datetime import timedelta
        rearmed = 0
        downgraded = 0
        now = datetime.utcnow()
        max_window = timedelta(hours=self._REHYDRATION_RESET_WINDOW_HOURS)

        for qid, queue in list(self._queues.items()):
            if queue.status != QueueStatus.WAITING_RESET:
                continue
            if queue.pause_reason == "crash_recovery":
                continue
            if not queue.reset_time:
                continue

            delta = queue.reset_time - now
            if delta < -max_window or delta > max_window:
                # Stale or far-future reset_time — refuse to auto-resume.
                self._logger.warning(
                    "[AutoPilot] Queue %s reset_time %s outside ±%dh window — "
                    "downgrading to manual resume",
                    qid, queue.reset_time.isoformat(),
                    self._REHYDRATION_RESET_WINDOW_HOURS,
                )
                queue.pause_reason = "manual"
                downgraded += 1
                continue

            self._schedule_auto_resume(qid, queue.reset_time)
            rearmed += 1

        if rearmed or downgraded:
            self._logger.info(
                "[AutoPilot] Re-armed %d auto-resume timer(s); downgraded %d to manual",
                rearmed, downgraded,
            )
        return rearmed

    # ------------------------------------------------------------------
    # Model switching
    # ------------------------------------------------------------------

    def switch_model(
        self,
        queue_id: str,
        provider: str,
        model: Optional[str] = None,
    ) -> bool:
        """Switch the execution provider/model and resume the queue.

        Useful when tokens are exhausted on one provider and the user
        wants to continue with a different one.
        """
        queue = self._queues.get(queue_id)
        if not queue:
            return False

        queue.provider = provider
        queue.model = model
        self._logger.info(
            "Queue %s switched to provider=%s model=%s",
            queue_id, provider, model,
        )

        # If paused or waiting, resume
        if queue.status in (QueueStatus.PAUSED, QueueStatus.WAITING_RESET):
            self.resume_queue(queue_id)

        return True


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

autopilot_queue_service = AutoPilotQueueService()
