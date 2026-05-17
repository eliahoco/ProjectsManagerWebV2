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
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

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
from sqlalchemy.exc import OperationalError
from utils.db_queries import cascade_in_progress_to_parents, cascade_revert_to_parents, cascade_status_to_parents
from utils.autopilot_repository import (
    classify_operational_error,
    emit_persist_failed_event,
    get_task_record_id,  # CB-2756
    record_event,
    save_queue,
    transition_state,  # CB-2757
    checkpoint,        # CB-2758
    set_subprocess_pid,  # CB-2756
    IllegalStateTransitionError,  # CB-2757
)
from utils.exhaustion_detector import (
    NO_AUTO_RESUME_CATEGORIES,
    detect_exhaustion_from_session,
    redact_secrets,
)


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
# CB-2749: The flat list above is kept for backward-compat with
# test_token_exhaustion_detection.py and is_token_exhaustion().
# New run_queue code calls detect_exhaustion_from_session() from
# utils.exhaustion_detector which categorises failures properly.


def is_token_exhaustion(session) -> bool:
    """Check if a completed session failed due to token/quota exhaustion.

    .. deprecated::
        CB-2749: Use :func:`utils.exhaustion_detector.detect_exhaustion_from_session`
        in new code.  Retained for backward compat with existing tests.
    """
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

    # CB-2792: rolling window of recent failures for systemic-failure detection.
    # When N identical failures land within a short window without any success
    # in between, we suspect credit/quota exhaustion (claude CLI exits silently
    # with code 1 when its API client hits a quota/network issue).
    recent_failures: List[Tuple[datetime, str]] = field(default_factory=list, repr=False)

    # CB-2799: consecutive-failure streak tracker (duration-independent fallback
    # for the systemic-failure heuristic).  Tracks the normalised error signature
    # of the most recent failure and how many consecutive identical failures have
    # occurred without a success in between.
    consecutive_failure_count: int = field(default=0, repr=False)
    consecutive_failure_signature: Optional[str] = field(default=None, repr=False)

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
    # CB-2681/CB-2682: guard flag preventing two concurrent resume callers from
    # both spawning a run_queue coroutine before the first Task is visible on
    # ``_task``.  Set synchronously inside ``_ensure_run_queue_task`` before
    # ``create_tracked_task`` is called; cleared by the done-callback on the
    # spawned task.  Because asyncio is single-threaded, the check-and-set is
    # atomic with respect to other coroutines — no asyncio.Lock needed.
    _launching: bool = field(default=False, repr=False)

    def __post_init__(self):
        # Start unpaused (event is set = running)
        self._pause_event.set()


# ---------------------------------------------------------------------------
# Poll interval
# ---------------------------------------------------------------------------

_POLL_INTERVAL_SECONDS = 2.0

# CB-2792: systemic-failure heuristic thresholds.
# When N identical failures land within W seconds with zero successes
# between them, treat as systemic (likely credit / network exhaustion)
# even if the per-session detector found no Anthropic-format error text.
_SYSTEMIC_FAILURE_THRESHOLD = 3
# CB-2799: widened from 60 s to 1800 s (30 min) — tasks run 2-15 min each so
# 3 failures in 60 s was mathematically impossible at this cadence.
_SYSTEMIC_FAILURE_WINDOW_SECONDS = 1800.0
_SYSTEMIC_AUTO_RESUME_DELAY_SECONDS = 30 * 60  # 30 min — assume credits back

# CB-2799: consecutive-failure streak threshold.  Duration-independent — fires
# when N identical error signatures arrive consecutively with no success between.
_CONSECUTIVE_FAILURE_THRESHOLD = 3


def _normalize_error_for_systemic(text: str) -> str:
    """Strip task-specific bits so we can compare error strings across tasks.

    The most common silent-failure signature is `Process exited with code N`.
    We keep that whole pattern; everything else is normalised to lowercase
    + collapsed whitespace.
    """
    if not text:
        return ""
    s = " ".join(text.lower().split())
    # Drop session-id-like substrings + paths so the comparison stays stable.
    s = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<uuid>", s)
    s = re.sub(r"/[a-z0-9_./-]+", "<path>", s)
    return s[:200]


def _is_systemic_failure(queue: "AutoPilotQueue", error_text: str) -> bool:
    """Return True if the recent-failure window indicates systemic failure.

    Caller is responsible for appending the new failure to ``queue.recent_failures``
    BEFORE calling this. The function trims old entries in place.
    """
    now = datetime.utcnow()
    cutoff = now.timestamp() - _SYSTEMIC_FAILURE_WINDOW_SECONDS
    queue.recent_failures = [
        (ts, msg) for (ts, msg) in queue.recent_failures
        if ts.timestamp() >= cutoff
    ]
    if len(queue.recent_failures) < _SYSTEMIC_FAILURE_THRESHOLD:
        return False
    norm_recent = _normalize_error_for_systemic(error_text)
    if not norm_recent:
        return False
    matching = sum(
        1 for (_, msg) in queue.recent_failures
        if _normalize_error_for_systemic(msg) == norm_recent
    )
    return matching >= _SYSTEMIC_FAILURE_THRESHOLD


def _is_consecutive_systemic_failure(queue: "AutoPilotQueue", error_text: str) -> bool:
    """Return True when N identical error signatures have arrived consecutively.

    CB-2799: Duration-independent fallback for ``_is_systemic_failure``.  The
    window-based heuristic requires N failures to land within
    ``_SYSTEMIC_FAILURE_WINDOW_SECONDS`` — at 2-15 minutes per task the 60 s
    window was impossible to trip.  This function tracks a *streak* instead:

    - On every task failure: normalise the error string.  If the signature
      matches the previous failure, increment ``queue.consecutive_failure_count``;
      otherwise reset to 1 and update ``queue.consecutive_failure_signature``.
    - Returns ``True`` when ``consecutive_failure_count >= _CONSECUTIVE_FAILURE_THRESHOLD``
      AND the signature is non-empty.
    - On every task **success** the caller must reset both counters (see
      ``_reset_consecutive_failure_streak``).

    Mutates ``queue.consecutive_failure_count`` and
    ``queue.consecutive_failure_signature`` in place.

    Args:
        queue: The autopilot queue whose streak fields are updated.
        error_text: The raw error string from the failed task.

    Returns:
        ``True`` if the streak threshold has been reached.
    """
    norm = _normalize_error_for_systemic(error_text)
    if not norm:
        # Unclassifiable error — reset streak to prevent false positives.
        queue.consecutive_failure_count = 0
        queue.consecutive_failure_signature = None
        return False

    if norm == queue.consecutive_failure_signature:
        queue.consecutive_failure_count += 1
    else:
        queue.consecutive_failure_signature = norm
        queue.consecutive_failure_count = 1

    return (
        queue.consecutive_failure_signature is not None
        and queue.consecutive_failure_count >= _CONSECUTIVE_FAILURE_THRESHOLD
    )


def _reset_consecutive_failure_streak(queue: "AutoPilotQueue") -> None:
    """Reset the consecutive-failure streak after a successful task completion.

    CB-2799: Must be called from the success path in ``run_queue`` so that a
    single success between failures prevents a false-positive streak trigger.

    Args:
        queue: The autopilot queue whose streak counters are reset.
    """
    queue.consecutive_failure_count = 0
    queue.consecutive_failure_signature = None


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

    # CB-2750: background tick interval for the recovery scheduler loop.
    _RECOVERY_TICK_INTERVAL_SECONDS = 60

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
        # CB-2750 G8: per-queue asyncio.Lock to prevent concurrent resume calls
        # from double-spawning the run_queue coroutine or double-incrementing
        # the auto_resume_attempts counter.
        self._resume_locks: Dict[str, asyncio.Lock] = {}
        # CB-2750: background recovery tick task handle.  Started by
        # start_recovery_tick() (called from lifespan); cancelled in shutdown.
        self._recovery_tick_task: Optional[asyncio.Task] = None
        # CB-2750: set of queue IDs classified as zombies during rehydration
        # (RUNNING in DB, no live coroutine).  Exposed via recovery-status.
        self._zombie_queue_ids: set[str] = set()
        # CB-1951 E10: feature flag for the persistence layer. When False,
        # _persist and _persist_async become no-ops and the service falls
        # back to the original in-memory behaviour. Initial value comes
        # from the AUTOPILOT_PERSISTENCE_ENABLED env var (default True).
        # Runtime toggle via the
        # POST /api/execute/queue/settings/persistence-enabled endpoint.
        env_val = os.environ.get("AUTOPILOT_PERSISTENCE_ENABLED", "true").strip().lower()
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
        """Restore ALL non-terminal queues from the persistent store.

        CB-2750 universal rehydrate: covers EVERY non-terminal state
        (WAITING_RESET, PAUSED, RUNNING, PENDING), in that order.

        Called once at backend startup from the FastAPI lifespan hook.
        For every non-terminal queue record found:

        1. Classify the queue: crash_zombie | crash_recovery | waiting_reset |
           recoverable_paused | pending_never_started.
        2. For RUNNING queues: check subprocess PID liveness (CB-2750 G2,
           graceful degrade if subprocessPid column not present yet).
           PID alive → ZOMBIE_DETECTED event, classify as zombie.
           PID dead / unknown → classify as crash_recovery.
        3. For RUNNING queues: reset running tasks to pending (CB-2738).
        4. Reconstruct the in-memory AutoPilotQueue dataclass.
        5. Increment recoveryGeneration counter (graceful degrade if absent).
        6. Emit RECOVERY_STARTED event with classification payload.

        Returns the list of queue IDs that were rehydrated. Empty list is
        the normal clean-startup case.

        E10: when persistence is disabled, rehydration is a no-op.
        """
        if not self._persistence_enabled:
            self._logger.info(
                "[AutoPilot] Persistence flag disabled — skipping rehydration"
            )
            return []

        from models.autopilot import AutoPilotEventType
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

                # CB-2750: process in priority order:
                #   WAITING_RESET first (re-arm timers soonest)
                #   PAUSED next (already safe, just reconstruct)
                #   RUNNING last (needs zombie detection + reclassification)
                #   PENDING (never ran, just reconstruct)
                def _sort_key(r) -> int:
                    s = getattr(r, "status", "")
                    return {"waiting_reset": 0, "paused": 1, "running": 2, "pending": 3}.get(s, 4)

                for record in sorted(records, key=_sort_key):
                    classification, previous_state, previous_reason = \
                        self._classify_rehydration_record(record)

                    n_reset = 0
                    if record.status == "running":
                        # CB-2750 G2: subprocess PID liveness check.
                        # subprocessPid may live on task rows (E2 schema adds it to queue too).
                        pid: Optional[int] = getattr(record, "subprocess_pid", None)
                        if pid is None:
                            for task_rec in (record.tasks or []):
                                pid = getattr(task_rec, "subprocessPid", None)
                                if pid is not None:
                                    break

                        if pid is not None and self._check_pid_alive(pid):
                            self._zombie_queue_ids.add(record.id)
                            classification = "zombie_detected"
                            self._logger.warning(
                                "[AutoPilot][CB-2750] ZOMBIE_DETECTED: queue %s "
                                "has orphan subprocess pid=%d still alive — "
                                "reclassifying to crash_recovery WITHOUT kill",
                                record.id, pid,
                            )
                        elif pid is not None:
                            self._logger.info(
                                "[AutoPilot][CB-2750] Queue %s: orphan pid=%d "
                                "is dead — treating as crash_recovery",
                                record.id, pid,
                            )

                        # CB-2738: reset running tasks to pending (not failed).
                        n_reset = await mark_running_tasks_failed_on_recovery(
                            db, record.id, reason="backend_crash_recovery"
                        )
                        await db.commit()

                        if n_reset > 0:
                            self._logger.info(
                                "[AutoPilot][CB-2738] Queue %s: %d interrupted task(s) "
                                "reset to pending (backend restart is not a failure).",
                                record.id, n_reset,
                            )

                    queue = self._record_to_queue(record)
                    self._queues[record.id] = queue
                    self._recovered_queue_ids.add(record.id)

                    # Increment recoveryGeneration counter (E2 column, graceful degrade).
                    try:
                        gen_before = getattr(record, "recoveryGeneration", None) or 0
                        record.recoveryGeneration = gen_before + 1
                        await db.flush()
                    except Exception:
                        pass  # column may not exist yet in older DBs

                    if not recovered_ids:
                        self._active_queue_id = record.id

                    recovered_ids.append(record.id)

                    await record_event(
                        db,
                        record.id,
                        AutoPilotEventType.RECOVERY_STARTED,
                        {
                            "previous_state": previous_state,
                            "previous_reason": previous_reason,
                            "classification": classification,
                            "tasks_reset_to_pending": n_reset,
                            "current_index": record.currentIndex,
                            "feature_id": record.featureId,
                        },
                    )
                    await db.commit()

                self._logger.info(
                    "[AutoPilot][CB-2750] Rehydrated %d queue(s): %s",
                    len(recovered_ids),
                    recovered_ids,
                )

                # CB-1951 E4.2.3: re-arm auto-resume timers for any
                # WAITING_RESET queues that survived the crash.
                await self.rearm_auto_resume_timers()
                return recovered_ids

        except Exception:
            # Rehydration must NEVER break startup.
            self._logger.exception(
                "[AutoPilot] Rehydration failed; starting with empty queue state"
            )
            return []

    # ------------------------------------------------------------------
    # CB-2750: classification + PID liveness helpers
    # ------------------------------------------------------------------

    def _classify_rehydration_record(self, record) -> Tuple[str, str, Optional[str]]:
        """Return (classification, previous_state, previous_reason).

        classification values:
          waiting_reset         — was WAITING_RESET with valid reset_time
          crash_recovery        — was RUNNING in DB, no live coroutine
          zombie_detected       — was RUNNING, orphan PID still alive (set by caller)
          recoverable_paused    — was PAUSED for any reason
          pending_never_started — was PENDING, never ran
          unknown               — unrecognised status string
        """
        previous_state: str = getattr(record, "status", "unknown")
        previous_reason: Optional[str] = getattr(record, "pauseReason", None)

        if previous_state == "waiting_reset":
            return "waiting_reset", previous_state, previous_reason
        elif previous_state == "running":
            return "crash_recovery", previous_state, previous_reason
        elif previous_state == "paused":
            return "recoverable_paused", previous_state, previous_reason
        elif previous_state == "pending":
            return "pending_never_started", previous_state, previous_reason
        else:
            return "unknown", previous_state, previous_reason

    @staticmethod
    def _check_pid_alive(pid: int) -> bool:
        """Return True if the process with ``pid`` is still alive.

        Uses ``os.kill(pid, 0)`` — zero signal only probes liveness, does
        not deliver anything. PermissionError means the process exists but
        is not our child — treated as alive. ProcessLookupError means dead.
        """
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # process exists, not our child
        except OSError:
            return False

    # ------------------------------------------------------------------
    # CB-2750: background recovery tick loop
    # ------------------------------------------------------------------

    def start_recovery_tick(self) -> None:
        """Start the 60-second background recovery tick loop.

        Called from the FastAPI lifespan hook after rehydration completes.
        Stored on ``_recovery_tick_task`` so shutdown can cancel it.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._logger.warning(
                "[AutoPilot][CB-2750] No running event loop — cannot start recovery tick"
            )
            return

        if self._recovery_tick_task is not None and not self._recovery_tick_task.done():
            self._logger.debug("[AutoPilot][CB-2750] Recovery tick already running")
            return

        self._recovery_tick_task = loop.create_task(
            self._recovery_tick_loop(),
            name="autopilot-recovery-tick",
        )
        self._logger.info(
            "[AutoPilot][CB-2750] Recovery tick started (interval=%ds)",
            self._RECOVERY_TICK_INTERVAL_SECONDS,
        )

    def stop_recovery_tick(self) -> None:
        """Cancel the recovery tick loop (called from lifespan shutdown)."""
        if self._recovery_tick_task is not None and not self._recovery_tick_task.done():
            self._recovery_tick_task.cancel()
            self._logger.info("[AutoPilot][CB-2750] Recovery tick stopped")

    async def _recovery_tick_loop(self) -> None:
        """Infinite loop that calls ``_recovery_tick_once`` every 60s."""
        while True:
            try:
                await asyncio.sleep(self._RECOVERY_TICK_INTERVAL_SECONDS)
                await self._recovery_tick_once()
            except asyncio.CancelledError:
                self._logger.info("[AutoPilot][CB-2750] Recovery tick loop cancelled")
                return
            except Exception:
                self._logger.exception(
                    "[AutoPilot][CB-2750] Recovery tick iteration failed"
                )

    async def _recovery_tick_once(self) -> None:
        """Single tick body — exposed separately for unit tests.

        Pass 1: WAITING_RESET queues whose reset_time <= now + tick_interval.
          - If circuit breaker not exhausted → resume_queue + ensure coroutine.
          - If exhausted → downgrade to PAUSED/manual.
        Pass 2: RUNNING queues with no live coroutine → flag as zombie.
        """
        from datetime import timedelta
        from models.autopilot import AutoPilotEventType

        now = datetime.utcnow()
        lookahead = now + timedelta(seconds=self._RECOVERY_TICK_INTERVAL_SECONDS)

        # Pass 1: WAITING_RESET auto-resume
        for qid, queue in list(self._queues.items()):
            if queue.status != QueueStatus.WAITING_RESET:
                continue
            if queue.reset_time is None or queue.reset_time > lookahead:
                continue
            if qid in self._resume_handles:
                continue  # already has a timer scheduled

            # CB-2761: do NOT increment here; resume_queue() is the single source of truth.
            # CB-2794: >= so the tick pre-flight is consistent with resume_queue.
            if queue.auto_resume_attempts >= self._AUTO_RESUME_MAX_ATTEMPTS:
                # CB-2793 Fix3: hold the per-queue lock for the circuit-breaker branch
                # (counter increment + _transition) so clear_recovery_state / resume_queue
                # cannot race. The resume_queue branch below does NOT hold the lock —
                # resume_queue acquires it internally, and asyncio.Lock is not reentrant.
                _cb_lock = self._resume_locks.setdefault(qid, asyncio.Lock())
                async with _cb_lock:
                    # CB-2795: idempotency guard — if already tripped, the status
                    # will be PAUSED so this branch is unreachable; but guard
                    # explicitly so a logic regression doesn't re-emit the event.
                    if queue.pause_reason == self._CIRCUIT_BREAKER_PAUSE_REASON:
                        continue
                    # CB-2798: increment BEFORE the transition so the counter is
                    # visible even if the DB write fails (test_cb2750 regression).
                    queue.auto_resume_attempts += 1
                    self._logger.error(
                        "[AutoPilot][CB-2750] Tick circuit-breaker for queue %s "
                        "(attempts=%d) — transitioning WAITING_RESET → PAUSED/manual_circuit_breaker",
                        qid, queue.auto_resume_attempts,
                    )
                    # CB-2795: cancel any live timer BEFORE the state transition
                    # so a concurrent _fire_auto_resume cannot race us.
                    self._cancel_auto_resume(qid)
                    # CB-2795 / M1 fix (CB-2795-S2): transition status WAITING_RESET
                    # → PAUSED via the authorised helper so the DB is updated
                    # atomically and an audit STATE_TRANSITION event is recorded.
                    # M1: use await (not ensure_future) — _recovery_tick_once is
                    # async and must observe the result; fire-and-forget dropped
                    # exceptions silently.
                    try:
                        await self._transition(
                            queue, QueueStatus.PAUSED, self._CIRCUIT_BREAKER_PAUSE_REASON,
                            extra_payload={
                                "attempts": queue.auto_resume_attempts,
                                "source": "recovery_tick",
                            },
                        )
                    except Exception:
                        self._logger.exception(
                            "[AutoPilot][CB-2795] _transition failed for queue %s", qid
                        )
                        # CB-2797: safety fallback — circuit breaker must trip
                        # even when DB write fails. Must use _CIRCUIT_BREAKER_PAUSE_REASON
                        # so the idempotency guard at the top of the tick loop matches.
                        # CB-2797: direct mutation intentional here — _transition is
                        # the authorised path in production; this is a DB-failure escape.
                        queue.status = QueueStatus.PAUSED
                        queue.pause_reason = self._CIRCUIT_BREAKER_PAUSE_REASON
                    self._persist_async(queue, "auto_resume_circuit_breaker_tripped", {
                        "attempts": queue.auto_resume_attempts,
                        "source": "recovery_tick",
                    })
                continue

            self._logger.info(
                "[AutoPilot][CB-2750] Tick auto-resuming queue %s (attempt %d/%d)",
                qid, queue.auto_resume_attempts + 1, self._AUTO_RESUME_MAX_ATTEMPTS,
            )
            # CB-2793 Fix3: do NOT hold the per-queue lock here — resume_queue
            # acquires it internally, and asyncio.Lock is not reentrant.
            resumed = await self.resume_queue(qid, _is_auto_resume=True)  # CB-2761
            if resumed:
                self._ensure_run_queue_task(queue)
                self._persist_async(queue, AutoPilotEventType.AUTO_RESUME_FIRED, {
                    "queue_id": qid,
                    "source": "auto_resume_tick",
                    "attempt_n": queue.auto_resume_attempts,
                })
            else:
                self._logger.warning(
                    "[AutoPilot][CB-2750] Tick: resume_queue(%s) returned False", qid
                )

        # Pass 2: detect new zombie RUNNING queues
        for qid, queue in list(self._queues.items()):
            if queue.status != QueueStatus.RUNNING:
                continue
            if qid in self._zombie_queue_ids:
                continue
            task_missing = queue._task is None
            task_done = (not task_missing) and queue._task.done()
            if not (task_missing or task_done):
                continue  # healthy coroutine present

            self._logger.warning(
                "[AutoPilot][CB-2750] Tick detected zombie queue %s "
                "(task_missing=%s task_done=%s)",
                qid, task_missing, task_done,
            )
            self._zombie_queue_ids.add(qid)
            self._persist_async(queue, AutoPilotEventType.ZOMBIE_DETECTED, {
                "queue_id": qid,
                "source": "recovery_tick",
            })

    def get_zombie_queue_ids(self) -> set:
        """Return the set of queue IDs classified as zombies. Read-only."""
        return frozenset(self._zombie_queue_ids)

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
                # CB-2673: read persisted key/title; fall back to empty string
                # (T5 defensive fallback will re-fetch from Issue before execution).
                issue_key=trecord.issueKey or "",
                issue_title=trecord.issueTitle or "",
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
        # CB-2794: restore persisted circuit-breaker counter; getattr guards
        # against pre-migration rows that lack the column.
        queue.auto_resume_attempts = getattr(record, "autoResumeAttempts", 0) or 0
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

    async def clear_recovery_state(self, queue_id: str) -> dict:
        """Cancel auto-resume timer, remove from recovery/zombie sets,
        transition queue to PAUSED with pause_reason='manual_cleared'.

        CB-2798 (S5 RC5 fix): the previous one-liner only discarded the
        queue_id from _recovered_queue_ids; it left the timer running, the
        zombie set dirty, and the queue status unchanged.  This expanded
        version does real work so the call is not a no-op.

        Returns:
            dict with keys:
              ok (bool) — True on success, False if queue not found.
              error (str) — present only when ok=False.
              cancelled_timer (bool) — whether an auto-resume timer was live.
              transitions (list[str]) — state transitions performed.
        """
        from models.autopilot import AutoPilotEventType as _ET

        queue = await self.get_or_load_queue(queue_id)
        if queue is None:
            return {"ok": False, "error": "not_found"}

        # CB-2793 Fix3: hold the per-queue resume lock while mutating queue state
        # so a concurrent resume_queue / _recovery_tick_once cannot race.
        _lock = self._resume_locks.setdefault(queue_id, asyncio.Lock())
        async with _lock:
            cancelled_timer = self._cancel_auto_resume(queue_id)
            self._recovered_queue_ids.discard(queue_id)
            self._zombie_queue_ids.discard(queue_id)

            transitions: list[str] = []
            # Transition to PAUSED only if the queue is in a non-terminal, non-already-paused state.
            # PAUSED→PAUSED is illegal per the state machine; WAITING_RESET and RUNNING are legal.
            if queue.status in (QueueStatus.WAITING_RESET, QueueStatus.RUNNING):
                old_status = queue.status.value
                try:
                    await self._transition(queue, QueueStatus.PAUSED, "manual_cleared")
                    transitions.append(f"{old_status}→paused/manual_cleared")
                    await self._persist(
                        queue,
                        _ET.STATE_TRANSITION,
                        {
                            "queue_id": queue_id,
                            "source": "clear_recovery_state",
                            "cancelled_timer": cancelled_timer,
                        },
                    )
                except Exception:
                    self._logger.exception(
                        "[AutoPilot][CB-2798] clear_recovery_state: _transition failed for queue %s",
                        queue_id,
                    )
            elif queue.status == QueueStatus.PAUSED and queue.pause_reason != "manual_cleared":
                # Already paused — update the pause_reason in-memory and persist
                # without going through _transition (which would reject PAUSED→PAUSED).
                old_reason = queue.pause_reason
                queue.pause_reason = "manual_cleared"
                try:
                    await self._persist(
                        queue,
                        _ET.STATE_TRANSITION,
                        {
                            "queue_id": queue_id,
                            "source": "clear_recovery_state",
                            "from_reason": old_reason,
                            "cancelled_timer": cancelled_timer,
                        },
                    )
                    transitions.append(f"paused/{old_reason}→paused/manual_cleared")
                except Exception:
                    self._logger.exception(
                        "[AutoPilot][CB-2798] clear_recovery_state: persist failed for queue %s",
                        queue_id,
                    )
                    # Revert in-memory change
                    queue.pause_reason = old_reason

        return {
            "ok": True,
            "cancelled_timer": cancelled_timer,
            "transitions": transitions,
        }

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

        # CB-2757: transition through state machine (best-effort; log but don't stop if disallowed)
        try:
            await self._transition(queue, QueueStatus.RUNNING, None)
        except IllegalStateTransitionError:
            self._logger.warning(
                "Queue %s: state-machine disallowed pending→running; proceeding anyway (may be already running)",
                queue_id,
            )
            # CB-2797: direct mutation intentional — DB rejected the transition
            # (likely already running), but the run_queue loop must still execute.
            # This is the only site where we tolerate a DB-rejected transition and
            # force in-memory forward (idempotent start path). See CB-2797.
            queue.status = QueueStatus.RUNNING
        except Exception:
            self._logger.exception("Queue %s: _transition(running) failed — continuing", queue_id)
            # CB-2797: direct mutation intentional — DB write failed but the loop
            # coroutine must still run (caller already scheduled this task).
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
                    # CB-2797: use _transition so DB is written before in-memory update.
                    try:
                        await self._transition(queue, QueueStatus.PAUSED, "manual")
                    except Exception:
                        self._logger.exception("Queue %s: _transition(paused, manual) in pause-gate failed", queue_id)
                    await queue._pause_event.wait()
                    # After resume, re-check stop
                    if queue._stop_flag:
                        self._logger.info("Queue %s stop flag detected (post-resume)", queue_id)
                        break
                    # CB-2797: use _transition so DB is written before in-memory update.
                    try:
                        await self._transition(queue, QueueStatus.RUNNING, None)
                    except Exception:
                        self._logger.exception("Queue %s: _transition(running) post-pause failed", queue_id)

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
                    # CB-2792: a success also clears the systemic-failure window.
                    queue.recent_failures = []
                    # CB-2799: reset duration-independent consecutive streak.
                    _reset_consecutive_failure_streak(queue)
                    action = await self._apply_success(queue, task, queue.current_index)
                    if action == "terminate":
                        self._logger.info("Queue %s terminated by success action", queue_id)
                        break

                elif outcome == "failed":
                    error_msg = task.error or "Unknown failure"

                    # CB-2749: Categorised exhaustion detection replaces the
                    # flat is_token_exhaustion() + extract_reset_time() pair.
                    session = terminal_service.get_session(task.session_id) if task.session_id else None
                    exhaust_result = detect_exhaustion_from_session(session) if session else None
                    if exhaust_result:
                        category = exhaust_result.category
                        reset_time = exhaust_result.reset_time
                        raw_match = exhaust_result.raw_match  # already redacted + capped

                        redacted = _redact_for_audit(error_msg)
                        queue.last_error = (
                            f"EXHAUSTION[{category}]: {redacted}"
                            + (f" (resets at {reset_time.isoformat()})" if reset_time else "")
                        )

                        # auth_failure / credit_exhaustion → PAUSED, no timer.
                        # All others → WAITING_RESET with auto-resume.
                        no_auto_resume = category in NO_AUTO_RESUME_CATEGORIES
                        if no_auto_resume:
                            # CB-2797: use _transition so DB is written before in-memory update.
                            try:
                                await self._transition(queue, QueueStatus.PAUSED, category)
                            except Exception:
                                self._logger.exception("Queue %s: _transition(paused, %s) failed", queue_id, category)
                            queue.reset_time = None
                            self._logger.warning(
                                "Queue %s paused (no auto-resume) — %s on %s",
                                queue_id, category, task.issue_key,
                            )
                        else:
                            # Default reset_time when unknown: now + 5 min (CB-2749)
                            if reset_time is None:
                                from datetime import timedelta
                                reset_time = datetime.utcnow() + timedelta(minutes=5)
                            # CB-2797: use _transition so DB is written before in-memory update.
                            try:
                                await self._transition(queue, QueueStatus.WAITING_RESET, category)
                            except Exception:
                                self._logger.exception("Queue %s: _transition(waiting_reset, %s) failed", queue_id, category)
                            queue.reset_time = reset_time
                            self._logger.warning(
                                "Queue %s paused — exhaustion(%s) on %s (reset: %s)",
                                queue_id, category, task.issue_key, reset_time,
                            )

                        # Reset task to pending so it re-runs after resume.
                        task.status = TaskStatus.PENDING
                        task.session_id = None
                        task.started_at = None
                        task.completed_at = None
                        task.error = None

                        # Persist TOKEN_EXHAUSTION_DETECTED event (CB-2749).
                        # Payload capped at 8 KB per audit log policy.
                        event_payload: dict = {
                            "category": category,
                            "reset_time": reset_time.isoformat() if reset_time else None,
                            "raw_match": raw_match,
                            "issue_key": task.issue_key,
                            "no_auto_resume": no_auto_resume,
                        }
                        await self._persist(queue, "TOKEN_EXHAUSTION_DETECTED", event_payload)

                        # Arm auto-resume timer for eligible categories.
                        if not no_auto_resume and reset_time is not None:
                            self._schedule_auto_resume(queue_id, reset_time)

                        # Block until resumed (manual button OR timer fires).
                        queue._pause_event.clear()
                        await queue._pause_event.wait()

                        if queue._stop_flag:
                            break
                        # CB-2797: use _transition so DB is written before in-memory update.
                        try:
                            await self._transition(queue, QueueStatus.RUNNING, None)
                        except Exception:
                            self._logger.exception("Queue %s: _transition(running) post-exhaust failed", queue_id)
                        queue.last_error = None
                        queue.reset_time = None
                        await self._persist(queue, "resumed", {"from": category})
                        # Re-run the same index (don't increment).
                        continue

                    # CB-2792 / CB-2799: SYSTEMIC FAILURE HEURISTIC.
                    # The session-level detector returned None — meaning the
                    # claude CLI exited without printing an Anthropic-format
                    # error string. This is the silent-credit-exhaustion case
                    # where the binary's HTTP client fails internally and
                    # returns exit code 1 without writing anything we capture.
                    #
                    # Two complementary checks (either fires → systemic pause):
                    # 1. Window-based: N identical failures within the last 30 min
                    #    (CB-2792, widened from 60 s in CB-2799).
                    # 2. Streak-based: N identical failures in a row regardless of
                    #    elapsed time (CB-2799 — handles slow queues like LINK-124
                    #    where tasks run 2-15 min each).
                    queue.recent_failures.append((datetime.utcnow(), error_msg or "Unknown failure"))
                    consecutive_systemic = _is_consecutive_systemic_failure(queue, error_msg or "Unknown failure")
                    if _is_systemic_failure(queue, error_msg or "Unknown failure") or consecutive_systemic:
                        category = "unknown_systemic"
                        from datetime import timedelta
                        reset_time = datetime.utcnow() + timedelta(seconds=_SYSTEMIC_AUTO_RESUME_DELAY_SECONDS)
                        redacted = _redact_for_audit(error_msg or "")
                        queue.last_error = f"SYSTEMIC[{category}]: {len(queue.recent_failures)} consecutive identical failures — {redacted} (suspected credit/quota exhaustion; auto-resume at {reset_time.isoformat()})"
                        # CB-2797: use _transition so DB is written before in-memory update.
                        try:
                            await self._transition(queue, QueueStatus.WAITING_RESET, category)
                        except Exception:
                            self._logger.exception("Queue %s: _transition(waiting_reset, %s) failed", queue_id, category)
                        queue.reset_time = reset_time
                        self._logger.warning(
                            "Queue %s paused — SYSTEMIC failure detected (%d identical exits in %ds window) on %s; auto-resume in %ds",
                            queue_id, len(queue.recent_failures),
                            _SYSTEMIC_FAILURE_WINDOW_SECONDS, task.issue_key,
                            _SYSTEMIC_AUTO_RESUME_DELAY_SECONDS,
                        )
                        # Reset task to pending so it re-runs on resume.
                        task.status = TaskStatus.PENDING
                        task.session_id = None
                        task.started_at = None
                        task.completed_at = None
                        task.error = None
                        # Clear both heuristic windows so post-resume cycle
                        # can re-trigger independently if failures persist.
                        queue.recent_failures = []
                        _reset_consecutive_failure_streak(queue)
                        await self._persist(queue, "TOKEN_EXHAUSTION_DETECTED", {
                            "category": category,
                            "reset_time": reset_time.isoformat(),
                            "raw_match": _redact_for_audit(error_msg or "")[:500],
                            "issue_key": task.issue_key,
                            "no_auto_resume": False,
                        })
                        self._schedule_auto_resume(queue_id, reset_time)
                        # Block until resumed (manual or timer).
                        queue._pause_event.clear()
                        await queue._pause_event.wait()
                        if queue._stop_flag:
                            break
                        # CB-2797: use _transition so DB is written before in-memory update.
                        try:
                            await self._transition(queue, QueueStatus.RUNNING, None)
                        except Exception:
                            self._logger.exception("Queue %s: _transition(running) post-systemic failed", queue_id)
                        queue.last_error = None
                        queue.reset_time = None
                        await self._persist(queue, "resumed", {"from": category})
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
            # CB-1951 E2 LOW-1 / CB-2765: redact loop exception message before
            # exposing via last_error (surfaced through recovery API).
            self._logger.exception("Unhandled error in queue %s loop", queue_id)
            queue.last_error = redact_secrets(_redact_for_audit(f"Internal queue error: {exc}"))
            # CB-2797: use _transition so DB is written before in-memory update.
            try:
                await self._transition(queue, QueueStatus.ABORTED, "internal_error")
            except Exception:
                self._logger.exception("Queue %s: _transition(aborted) on exception failed", queue_id)

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

        # CB-2676: belt-and-braces fallback — if issue_key/issue_title are
        # empty (legacy data or a rehydrated queue that predates the T2/T3
        # schema fix), re-fetch them from the Issue table before proceeding.
        # This ensures the audit log, progress display, and any future callers
        # that depend on these fields never see blank values.
        if not task.issue_key or not task.issue_title:
            try:
                async with AsyncSessionLocal() as _fb_db:
                    _fb_result = await _fb_db.execute(
                        select(Issue).where(Issue.id == task.issue_id)
                    )
                    _fb_issue = _fb_result.scalar_one_or_none()
                    if _fb_issue:
                        if not task.issue_key:
                            task.issue_key = _fb_issue.key or ""
                        if not task.issue_title:
                            task.issue_title = _fb_issue.title or ""
                        # CB-2683: redact via _redact_for_audit before %r — defense-in-depth.
                        _redacted_key = _redact_for_audit(task.issue_key or "")
                        _redacted_title = _redact_for_audit((task.issue_title or "")[:40])
                        self._logger.warning(
                            "[AutoPilot] CB-2676 fallback: re-fetched issue_key=%r "
                            "issue_title=%r for task order=%d (issue_id=%s). "
                            "This indicates a legacy task row that predates the "
                            "CB-2673 schema migration — re-persisting to fix drift.",
                            _redacted_key, _redacted_title,
                            task.order, task.issue_id,
                        )
                        # Write the now-populated fields back to the DB so
                        # future restarts won't hit this path again.
                        await self._persist(queue, "task_key_backfill", {
                            "issue_key": task.issue_key,
                            "order": task.order,
                        })
            except Exception:
                self._logger.exception(
                    "[AutoPilot] CB-2676 fallback re-fetch failed for task %d "
                    "(issue_id=%s) — continuing with empty key/title",
                    task.order, task.issue_id,
                )

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

            # CB-2756: persist subprocess PID for zombie detection on next boot.
            # Look up the DB record id by queue+sequence, then write the PID.
            # Best-effort — PID tracking failure must not abort the task.
            _pid = None
            if session.process is not None:
                _pid = session.process.pid
            if _pid is not None:
                try:
                    _task_db_id = await get_task_record_id(queue.id, task.order)
                    if _task_db_id:
                        await set_subprocess_pid(_task_db_id, _pid, queue_id=queue.id)
                except Exception:
                    self._logger.exception(
                        "Queue %s: set_subprocess_pid failed for task order=%d (non-fatal)",
                        queue.id, task.order,
                    )

            # If the session failed immediately (e.g. path validation, pool full)
            if session.status == ExecutionStatus.FAILED:
                task.status = TaskStatus.FAILED
                task.error = redact_secrets(session.error or "")  # CB-2765
                task.completed_at = datetime.utcnow()
                # CB-2756: clear PID — subprocess is gone
                try:
                    if _task_db_id := await get_task_record_id(queue.id, task.order):
                        await set_subprocess_pid(_task_db_id, None)
                except Exception:
                    pass
                return "failed"

            # ---- Poll for completion ----
            result = await self._poll_session(queue, task, session.id)

            # CB-2756: clear PID after polling ends (task completed/failed/skipped/stopped)
            try:
                if _task_db_id2 := await get_task_record_id(queue.id, task.order):
                    await set_subprocess_pid(_task_db_id2, None)
            except Exception:
                pass  # best-effort

            return result

        except Exception as exc:
            self._logger.exception(
                "Error executing task %s in queue %s", task.issue_key, queue.id
            )
            task.status = TaskStatus.FAILED
            task.error = redact_secrets(str(exc))  # CB-2765
            task.completed_at = datetime.utcnow()
            # CB-2756: clear PID on exception path
            try:
                if _clear_db_id := await get_task_record_id(queue.id, task.order):
                    await set_subprocess_pid(_clear_db_id, None)
            except Exception:
                pass
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
                task.error = "Session lost — terminal_service returned None"  # no secrets
                task.completed_at = datetime.utcnow()
                return "failed"

            if session.status == ExecutionStatus.COMPLETED:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.utcnow()
                return "completed"

            if session.status in (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
                task.status = TaskStatus.FAILED
                _raw_err = session.error or f"Session ended with status {session.status.value}"
                task.error = redact_secrets(_raw_err)  # CB-2765
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
        # CB-2758: checkpoint after every successful task so lastCheckpointAt is populated
        try:
            await checkpoint(queue.id)
        except Exception:
            self._logger.exception("Queue %s: checkpoint() failed (non-fatal)", queue.id)
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
        queue.last_error = redact_secrets(f"{task.issue_key}: {error_msg}")  # CB-2765

        self._logger.warning(
            "Task %s failed (action=%s, retries=%d/%d): %s",
            task.issue_key, action, task.retry_count,
            queue.config.max_retries, error_msg,
        )

        if action == "TERMINATE":
            # CB-2797: use _transition so DB is written before in-memory update.
            try:
                await self._transition(queue, QueueStatus.ABORTED, "terminate_on_fail")
            except Exception:
                self._logger.exception("Queue %s: _transition(aborted, terminate) failed", queue.id)
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

    # ------------------------------------------------------------------
    # CB-2797: Canonical state-transition helper
    # ------------------------------------------------------------------

    async def _transition(
        self,
        queue: AutoPilotQueue,
        new_status: QueueStatus,
        reason: Optional[str],
        extra_payload: Optional[dict] = None,
    ) -> None:
        """Single authorised path to mutate queue.status.

        Writes to DB FIRST via ``transition_state`` (atomic with
        STATE_TRANSITION event). Only on DB success, mutates the in-memory
        dataclass. On DB failure, raises — caller must handle.

        Args:
            queue: The in-memory queue object to transition.
            new_status: Target QueueStatus enum value.
            reason: Pause reason string, or None for non-pause transitions.
            extra_payload: Additional fields merged into the STATE_TRANSITION
                event payload.

        Raises:
            IllegalStateTransitionError: Transition is not in the allow-list.
                Caller must NOT swallow — the in-memory status is left
                unchanged to keep memory/DB in sync.
            OperationalError: SQLite I/O error (disk full, locked).
            ValueError: queue.id not found in DB.
        """
        await transition_state(
            queue.id,
            new_status.value,
            reason,
            extra_payload=extra_payload,
        )
        # DB write succeeded — now mirror to in-memory dataclass.
        queue.status = new_status
        if new_status in (QueueStatus.PAUSED, QueueStatus.WAITING_RESET):
            queue.pause_reason = reason
        else:
            queue.pause_reason = None

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

        CB-2748 G3 fix: no longer swallows ALL exceptions. We now distinguish:
          - ``OperationalError`` with disk-full / locked indicators → log CRITICAL,
            emit DISK_FULL_DETECTED or PERSIST_FAILED event (best-effort), then
            **re-raise** so the run_queue loop can transition to paused/disk_full
            instead of silently advancing with no durability.
          - Other unexpected exceptions → emit PERSIST_FAILED (best-effort),
            log as exception, then re-raise so callers know the write failed.
        """
        from models.autopilot import AutoPilotEventType as _ET  # local import avoids circular
        if not self._persistence_enabled:
            return
        try:
            async with AsyncSessionLocal() as db:
                await save_queue(db, queue)
                if event_type:
                    await record_event(db, queue.id, event_type, payload)
                await db.commit()
        except OperationalError as exc:
            category = classify_operational_error(exc)
            error_msg = str(exc)
            if category == "disk_full":
                self._logger.critical(
                    "DISK FULL: failed to persist queue %s (event=%s): %s — "
                    "stopping queue loop to prevent data loss",
                    queue.id,
                    event_type,
                    error_msg,
                )
                await emit_persist_failed_event(
                    queue.id, _ET.DISK_FULL_DETECTED, error_msg
                )
            else:
                self._logger.critical(
                    "DB operational error persisting queue %s (event=%s, category=%s): %s",
                    queue.id,
                    event_type,
                    category,
                    error_msg,
                )
                await emit_persist_failed_event(
                    queue.id, _ET.PERSIST_FAILED, error_msg
                )
            raise
        except Exception as exc:
            error_msg = str(exc)
            self._logger.exception(
                "Unexpected error persisting queue %s state (event=%s) — re-raising",
                queue.id,
                event_type,
            )
            await emit_persist_failed_event(
                queue.id, _ET.PERSIST_FAILED, error_msg
            )
            raise

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
            # CB-2797: use _transition so DB is written before in-memory update.
            try:
                await self._transition(queue, QueueStatus.ABORTED, "stop_flag")
            except Exception:
                self._logger.exception("Queue %s: _transition(aborted) finalize failed", queue.id)

        all_done = all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
            for t in queue.tasks
        )
        if all_done and queue.status == QueueStatus.RUNNING:
            # CB-2797: use _transition so DB is written before in-memory update.
            try:
                await self._transition(queue, QueueStatus.COMPLETED, None)
            except Exception:
                self._logger.exception("Queue %s: _transition(completed) finalize failed", queue.id)

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

        # CB-2763: wrap the finalize _persist in try/except so a disk-full or DB-locked
        # error doesn't propagate uncaught out of run_queue, killing the asyncio task
        # silently. Emit PERSIST_FAILED and continue to prune.
        try:
            await self._persist(queue, "finalized", {
                "final_status": queue.status.value,
                "completed_count": sum(1 for t in queue.tasks if t.status == TaskStatus.COMPLETED),
                "total": len(queue.tasks),
            })
        except Exception as _fin_exc:
            self._logger.error(
                "Queue %s: _finalize_queue _persist failed (%s) — continuing to prune",
                queue.id, _fin_exc,
            )
            from models.autopilot import AutoPilotEventType as _ET2
            try:
                await emit_persist_failed_event(
                    queue.id, _ET2.PERSIST_FAILED, str(_fin_exc)[:512]
                )
            except Exception:
                pass  # best-effort

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

    async def get_or_load_queue(self, queue_id: str) -> Optional["AutoPilotQueue"]:
        """Return queue from memory if present; otherwise load from DB and cache.

        CB-2743 fix: endpoints that operate on paused queues (e.g. task-reset)
        must be able to find queues that exist only in the DB — e.g. after a
        backend restart where the queue was not rehydrated yet because the user
        had not explicitly resumed it.

        Returns None if not found anywhere (neither in-memory nor in DB).
        """
        # Fast path — in-memory cache
        queue = self._queues.get(queue_id)
        if queue is not None:
            return queue

        # DB fallback — load the record and reconstruct the in-memory queue
        from utils.autopilot_repository import load_queue as _load_queue  # noqa: PLC0415

        async with AsyncSessionLocal() as session:
            record = await _load_queue(session, queue_id)
            if record is None:
                return None
            queue = self._record_to_queue(record)
            self._queues[queue_id] = queue
            self._logger.info(
                "[AutoPilot] get_or_load_queue: loaded queue %s from DB "
                "(status=%s, tasks=%d)",
                queue_id,
                queue.status.value,
                len(queue.tasks),
            )
            return queue

    def get_active_queue(self) -> Optional[AutoPilotQueue]:
        """Get the currently active queue, if any."""
        if self._active_queue_id:
            return self._queues.get(self._active_queue_id)
        return None

    def _serialize_queue(self, queue: "AutoPilotQueue") -> dict:
        """Return the canonical JSON shape for a queue, with state derived from
        queue.status.value.  All response-building code must use this method so
        there is a single source of truth — no hard-coded string literals.

        CB-2798 (S5 RC6 fix): previously recovery-status sub-lists hard-coded
        "state": "running" (zombie) and "state": "waiting_reset" (auto_resume)
        regardless of the real in-memory/DB status.  Now every list entry goes
        through this helper.
        """
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
            # CB-2798: always derived from queue.status — never hard-coded.
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

    async def get_queue_status(self, queue_id: str) -> Optional[dict]:
        """Get a full serializable status dict for a queue.

        CB-2798 (S5): changed to async so it can call get_or_load_queue for
        the DB fallback.  Queues that exist only in DB (not yet loaded into
        _queues) now return a proper payload instead of 404.

        Returns None if the queue does not exist in memory or DB.
        """
        queue = await self.get_or_load_queue(queue_id)
        if not queue:
            return None
        return self._serialize_queue(queue)

    # ------------------------------------------------------------------
    # Control methods
    # ------------------------------------------------------------------

    async def _reset_failed_tasks_locked(self, queue_id: str) -> dict:
        """Inner body of reset_failed_tasks — caller MUST already hold the per-queue lock.

        CB-2793 Fix2: split from ``reset_failed_tasks`` so the endpoint can acquire
        the lock once and run both reset + resume inside a single critical section,
        eliminating the TOCTOU window that existed between the two separate lock
        acquisitions.
        """
        queue = await self.get_or_load_queue(queue_id)
        if queue is None:
            return {"queue_id": queue_id, "reset_count": 0, "task_ids": [], "task_keys": []}

        reset_ids: list[str] = []
        reset_keys: list[str] = []
        min_order: Optional[int] = None

        for task in queue.tasks:
            if task.status == TaskStatus.FAILED:
                task.status = TaskStatus.PENDING
                task.error = None
                task.started_at = None
                task.completed_at = None
                reset_ids.append(task.issue_id)
                reset_keys.append(task.issue_key)
                if min_order is None or task.order < min_order:
                    min_order = task.order

        if min_order is not None and min_order < queue.current_index:
            queue.current_index = min_order

        if reset_ids:
            self._persist_async(
                queue,
                "tasks_reset_for_retry",
                {"reset_count": len(reset_ids), "task_keys": reset_keys},
            )

        self._logger.info(
            "[AutoPilot] CB-2796: reset_failed_tasks(%s) — %d tasks reset to PENDING",
            queue_id,
            len(reset_ids),
        )

        return {
            "queue_id": queue_id,
            "reset_count": len(reset_ids),
            "task_ids": reset_ids,
            "task_keys": reset_keys,
        }

    async def reset_failed_tasks(self, queue_id: str) -> dict:
        """Reset all FAILED tasks in the queue back to PENDING so they can be retried.

        CB-2796 (S3): fixes RC3a — when a queue has only failed + completed tasks,
        ``resume_queue`` refuses (no pending tasks).  This method resets FAILED →
        PENDING atomically under the per-queue resume lock so a subsequent
        ``resume_queue`` call can pick them up.

        Side-effects:
          * ``task.status`` → PENDING
          * ``task.error`` → None
          * ``task.started_at`` → None
          * ``task.completed_at`` → None
          * ``task.retry_count`` is preserved (informational)
          * ``queue.current_index`` lowered to the minimum order of any newly-PENDING
            task if that is lower than the current index.
          * Persists state via ``save_queue``.
          * Emits ``tasks_reset_for_retry`` event.

        Returns:
            dict with ``queue_id``, ``reset_count`` (int), ``task_ids`` ([str]),
            and ``task_keys`` ([str]).
        """
        lock = self._resume_locks.setdefault(queue_id, asyncio.Lock())
        async with lock:
            return await self._reset_failed_tasks_locked(queue_id)

    async def pause_queue(self, queue_id: str) -> bool:
        """Pause the queue.  The current task finishes, then the queue blocks.

        CB-2745: uses get_or_load_queue so DB-only paused queues (after a
        backend restart where the queue was not rehydrated) can still be
        found and acted upon.
        """
        queue = await self.get_or_load_queue(queue_id)
        if not queue or queue.status not in (QueueStatus.RUNNING, QueueStatus.WAITING_RESET):
            return False
        queue._pause_event.clear()
        # CB-2797: use _transition so DB is written before in-memory update.
        try:
            await self._transition(queue, QueueStatus.PAUSED, "manual")
        except Exception:
            self._logger.exception("Queue %s: _transition(paused, manual) in pause_queue failed", queue_id)
        self._logger.info("Queue %s paused", queue_id)
        # Persist pause state (CB-1951)
        self._persist_async(queue, "manual_paused", {"reason": "manual"})
        return True

    async def resume_queue(self, queue_id: str, _is_auto_resume: bool = False) -> bool:
        """Resume a paused queue. (CB-1951 E4.1.1 + E4.1.2)

        CB-2750 G8: per-queue asyncio.Lock ensures concurrent callers are
        serialized. The second caller either sees the queue already RUNNING
        and returns False immediately (idempotent), or waits for the first
        caller to commit the transition and then also sees RUNNING.

        Refuses to resume if there is no active task to run — returning
        False rather than silently succeeding so the API caller can
        surface a clean error to the user.

        CB-2745: uses get_or_load_queue so DB-only paused queues (after a
        backend restart where the queue was not rehydrated) can still be
        found and resumed without a 400 "does not exist" error.

        Args:
            queue_id: The queue to resume.
            _is_auto_resume: True when called by an auto-resume timer or tick
                (not by the user). CB-2761: the counter increment is performed
                here (inside the lock) so concurrent auto-resume paths cannot
                double-increment.
        """
        # CB-2750 G8: per-queue asyncio.Lock serializes concurrent resume callers.
        # The second concurrent call sees status already RUNNING and returns False
        # (idempotent). asyncio is single-threaded so the setdefault + acquire
        # sequence is safe without a separate meta-lock.
        lock = self._resume_locks.setdefault(queue_id, asyncio.Lock())
        async with lock:
            queue = await self.get_or_load_queue(queue_id)
            if not queue or queue.status not in (QueueStatus.PAUSED, QueueStatus.WAITING_RESET):
                return False

            # CB-2761: increment auto_resume_attempts INSIDE the lock so the timer
            # path (_fire_auto_resume) and the tick path (_recovery_tick_once) cannot
            # race and double-increment the counter.
            # CB-2794: check BEFORE increment (>= not >) so the cap is exact at
            # _AUTO_RESUME_MAX_ATTEMPTS; counter stays at MAX when breaker trips
            # (prevents the off-by-one that allowed attempt #4 to slip through).
            if _is_auto_resume:
                if queue.auto_resume_attempts >= self._AUTO_RESUME_MAX_ATTEMPTS:
                    # CB-2795: idempotency guard — skip if already tripped.
                    if queue.pause_reason == self._CIRCUIT_BREAKER_PAUSE_REASON:
                        return False
                    # Circuit-breaker: max attempts reached, transition to PAUSED
                    # (not just setting pause_reason) so the tick/fire predicates
                    # stop matching. (CB-2795)
                    self._logger.error(
                        "[AutoPilot] Queue %s auto-resume circuit breaker tripped "
                        "after %d attempts — transitioning WAITING_RESET → PAUSED/manual_circuit_breaker",
                        queue_id, queue.auto_resume_attempts,
                    )
                    # CB-2795: cancel any live timer before state transition.
                    self._cancel_auto_resume(queue_id)
                    # CB-2797: use _transition so DB is written before in-memory update.
                    # Safety fallback: if DB write fails, circuit breaker must
                    # still trip to prevent runaway token burn. CB-2797.
                    try:
                        await self._transition(
                            queue, QueueStatus.PAUSED, self._CIRCUIT_BREAKER_PAUSE_REASON,
                            extra_payload={"attempts": queue.auto_resume_attempts},
                        )
                    except Exception:
                        self._logger.exception(
                            "[AutoPilot][CB-2795] _transition failed for queue %s", queue_id
                        )
                        # CB-2797: safety fallback — circuit breaker must trip even
                        # when DB write fails. Direct mutation intentional here.
                        queue.status = QueueStatus.PAUSED
                        queue.pause_reason = self._CIRCUIT_BREAKER_PAUSE_REASON
                    self._persist_async(queue, "auto_resume_circuit_breaker_tripped", {
                        "attempts": queue.auto_resume_attempts,
                    })
                    return False
                queue.auto_resume_attempts += 1

            # CB-2744 Part B: defensive self-heal — if current_index is past the
            # end of the task list OR the task at current_index is already finished,
            # scan forward to find the next pending task.  Only refuse when there
            # is genuinely no pending task remaining anywhere.
            def _find_next_pending(q: "AutoPilotQueue") -> Optional[int]:
                pending = [t.order for t in q.tasks if t.status == TaskStatus.PENDING]
                return min(pending) if pending else None

            needs_scan = (
                queue.current_index >= len(queue.tasks)
                or (
                    queue.current_index < len(queue.tasks)
                    and queue.tasks[queue.current_index].status
                    not in (TaskStatus.PENDING, TaskStatus.RUNNING)
                )
            )
            if needs_scan:
                next_order = _find_next_pending(queue)
                if next_order is None:
                    # E4.1.2: genuinely nothing left to run.
                    self._logger.warning(
                        "Queue %s resume refused — no active task at index %d/%d "
                        "and no pending tasks",
                        queue_id, queue.current_index, len(queue.tasks),
                    )
                    return False
                self._logger.info(
                    "[AutoPilot] CB-2744: self-healing current_index %d → %d "
                    "for queue %s on resume.",
                    queue.current_index, next_order, queue_id,
                )
                queue.current_index = next_order

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

    def _ensure_run_queue_task(self, queue: "AutoPilotQueue") -> None:
        """Re-launch the ``run_queue`` coroutine if it is absent or finished.

        CB-2681/CB-2682: after a backend crash + rehydration the in-memory
        ``queue._task`` is always ``None`` — ``resume_queue`` only sets the
        pause event but nothing is waiting on it, so execution never actually
        starts.  This helper detects that situation and spawns a fresh
        ``run_queue`` asyncio.Task via ``create_tracked_task``.

        **Idempotent** — safe to call multiple times; subsequent calls while
        the task is still running are no-ops.

        **Race-safe** — the ``_launching`` boolean flag on the queue dataclass
        is set synchronously (no ``await`` between check and set) before the
        task is created, preventing two concurrent callers from both spawning
        a coroutine.  Because asyncio is single-threaded, this check-and-set
        is atomic with respect to other coroutines.
        """
        from app.background import create_tracked_task  # local import avoids circular

        task_missing = queue._task is None
        task_done = (not task_missing) and queue._task.done()
        if not (task_missing or task_done):
            # Task is alive — nothing to do.
            return

        # Guard: if another resume caller already entered this block (before the
        # asyncio.Task was assigned to queue._task), skip the duplicate launch.
        if queue._launching:
            self._logger.warning(
                "[AutoPilot] CB-2681: _ensure_run_queue_task called while "
                "_launching=True for queue %s — skipping duplicate launch",
                queue.id,
            )
            return

        queue._launching = True

        def _clear_launching(fut: asyncio.Task) -> None:  # noqa: ARG001
            queue._launching = False

        self._logger.warning(
            "[AutoPilot] CB-2681: queue %s has no live run_queue coroutine "
            "(task_missing=%s, task_done=%s) — re-launching run_queue",
            queue.id, task_missing, task_done,
        )
        t = create_tracked_task(
            self.run_queue(queue.id),
            name=f"autopilot-queue-{queue.id}",
        )
        t.add_done_callback(_clear_launching)
        queue._task = t

    async def skip_current(self, queue_id: str) -> bool:
        """Skip the currently executing task.  The session is stopped and the
        queue advances to the next task.

        CB-2745: uses get_or_load_queue so DB-only paused queues (after a
        backend restart where the queue was not rehydrated) can still be found.
        """
        queue = await self.get_or_load_queue(queue_id)
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

        CB-2745: uses get_or_load_queue so DB-only paused queues (after a
        backend restart where the queue was not rehydrated) can still be aborted.
        """
        queue = await self.get_or_load_queue(queue_id)
        if not queue:
            return False

        queue._stop_flag = True
        # CB-2797: use _transition so DB is written before in-memory update.
        try:
            await self._transition(queue, QueueStatus.ABORTED, "user_abort")
        except Exception:
            self._logger.exception("Queue %s: _transition(aborted) abort_queue failed", queue_id)

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

    # CB-2795: pause_reason written when the circuit breaker trips. Using a
    # dedicated value (not "manual") lets downstream code distinguish a
    # breaker-tripped queue from a manually-paused one, and — critically —
    # provides an idempotency guard: a second trip attempt on a queue that
    # already has this reason is a no-op (status is already PAUSED so the
    # WAITING_RESET predicate no longer matches, but the guard is belt-and-
    # suspenders safety for _fire_auto_resume which is called directly).
    _CIRCUIT_BREAKER_PAUSE_REASON = "manual_circuit_breaker"

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
        queue = await self.get_or_load_queue(queue_id)
        if not queue:
            return

        target: Optional[datetime] = None
        if reset_time_str:
            target = _parse_reset_time_from_text(f"resets at {reset_time_str}")
        if target is None:
            from datetime import timedelta
            target = datetime.utcnow() + timedelta(hours=1)

        # CB-2797: use _transition so DB is written before in-memory update.
        try:
            await self._transition(queue, QueueStatus.WAITING_RESET, "manual_wait")
        except Exception:
            self._logger.exception(
                "Queue %s: _transition(waiting_reset, manual_wait) failed", queue_id
            )
        queue.reset_time = target

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

        # CB-2761: do NOT increment here; resume_queue() increments inside the lock
        # so concurrent timer + tick calls cannot double-count.
        # CB-2794: use >= (not >) so the pre-flight check here is consistent
        # with the >= guard in resume_queue; avoids the breaker being bypassed
        # when attempts == MAX before resume_queue has a chance to check.
        if queue.auto_resume_attempts >= self._AUTO_RESUME_MAX_ATTEMPTS:
            # CB-2795: idempotency guard — skip if already tripped.
            if queue.pause_reason == self._CIRCUIT_BREAKER_PAUSE_REASON:
                return
            # Circuit breaker: stop auto-resuming and require manual
            # intervention to prevent runaway token burn. (SEC MEDIUM-1)
            # CB-2795: transition WAITING_RESET → PAUSED so the queue status
            # changes and subsequent ticks stop matching the WAITING_RESET predicate.
            self._logger.error(
                "[AutoPilot] Queue %s auto-resume circuit breaker tripped "
                "after %d consecutive attempts — transitioning WAITING_RESET → PAUSED/manual_circuit_breaker",
                queue_id, queue.auto_resume_attempts,
            )
            # CB-2795: cancel any live timer (belt-and-suspenders; the caller
            # _runner already pops the handle after _fire_auto_resume returns,
            # but we cancel explicitly so the task.cancelled() state is set
            # immediately for test assertions).
            # H1 fix: detect self-cancel — if we ARE the _runner task that owns
            # this handle, calling task.cancel() would cancel ourselves and the
            # DB write below would be aborted.
            # Instead just pop the dict entry; _runner's finally block will not
            # re-insert it because current_task() == the popped task.
            existing = self._resume_handles.get(queue_id)
            if existing is not None and existing is asyncio.current_task():
                # Self-cancel path: only remove the dict entry, do not call cancel().
                self._resume_handles.pop(queue_id, None)
            else:
                self._cancel_auto_resume(queue_id)

            # CB-2797: use _transition so DB is written before in-memory update.
            # CancelledError propagates naturally so cooperative cancellation
            # is still honoured. If the DB write fails (e.g. DB not yet
            # persisted in tests, or disk I/O error), we MUST still update
            # in-memory so the circuit breaker actually trips and prevents
            # runaway token burn — a safety-critical fallback. See CB-2797.
            try:
                await self._transition(
                    queue, QueueStatus.PAUSED, self._CIRCUIT_BREAKER_PAUSE_REASON,
                    extra_payload={"attempts": queue.auto_resume_attempts},
                )
            except asyncio.CancelledError:
                # Re-raise so cooperative cancellation is honoured. In-memory
                # will be set in the finally block below.
                raise
            except Exception:
                self._logger.exception(
                    "[AutoPilot][CB-2795] _transition failed for queue %s", queue_id
                )
                # CB-2797: safety fallback — circuit breaker must trip even
                # when DB write fails. Direct mutation intentional here.
                queue.status = QueueStatus.PAUSED
                queue.pause_reason = self._CIRCUIT_BREAKER_PAUSE_REASON
            await self._persist(queue, "auto_resume_circuit_breaker_tripped", {
                "attempts": queue.auto_resume_attempts,
            })
            return

        self._logger.warning(
            "[AutoPilot] Queue %s auto-resuming after token reset (attempt %d/%d)",
            queue_id, queue.auto_resume_attempts, self._AUTO_RESUME_MAX_ATTEMPTS,
        )
        if await self.resume_queue(queue_id, _is_auto_resume=True):
            # CB-2681: ensure the run_queue coroutine is live after resume.
            # After a backend crash + rehydration queue._task is None, so the
            # pause-event set by resume_queue has nothing waiting on it.
            self._ensure_run_queue_task(queue)
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

    async def switch_model(
        self,
        queue_id: str,
        provider: str,
        model: Optional[str] = None,
    ) -> bool:
        """Switch the execution provider/model and resume the queue.

        Useful when tokens are exhausted on one provider and the user
        wants to continue with a different one.

        CB-2745: uses get_or_load_queue so DB-only paused queues (after a
        backend restart where the queue was not rehydrated) can still be found.
        """
        queue = await self.get_or_load_queue(queue_id)
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
            if await self.resume_queue(queue_id):
                # CB-2682: ensure the run_queue coroutine is live after model-switch
                # resume. After a backend crash + rehydration queue._task is None,
                # so the pause-event set by resume_queue has nothing waiting on it.
                self._ensure_run_queue_task(queue)

        return True


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

autopilot_queue_service = AutoPilotQueueService()
