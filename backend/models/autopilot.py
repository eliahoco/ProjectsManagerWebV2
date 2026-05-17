"""
SQLAlchemy ORM mirrors of the Prisma AutoPilot persistence models.

Mirrors three Prisma models added in CB-1951:
  - AutoPilotQueueRecord  → table "AutoPilotQueueRecord"
  - AutoPilotTaskRecord   → table "AutoPilotTaskRecord"
  - AutoPilotEvent        → table "AutoPilotEvent"

Column names use camelCase to match the Prisma schema (the codebase uses a
camelCase Prisma + camelCase SQLAlchemy hybrid; do not switch to snake_case).

CB-2748 additions:
  AutoPilotQueueRecord: state, stateReason, lastCheckpointAt, recoveryGeneration
  AutoPilotTaskRecord:  lastProgressAt, subprocessPid
  AutoPilotEvent types: 11 new event type constants (see EVENT_TYPES below)
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.database import Base


# ---------------------------------------------------------------------------
# CB-2748: canonical event type constants for the new persistence overhaul.
# These extend the pre-existing informal string set used in the audit log.
# ---------------------------------------------------------------------------

class AutoPilotEventType:
    """String constants for AutoPilotEvent.type.

    Pre-existing types (CB-1951, kept for backward compat):
      created, task_started, task_completed, task_failed, auto_paused,
      manual_paused, resumed, auto_resume_scheduled, auto_resume_fired,
      aborted, crash_recovery_detected

    CB-2748 additions:
    """
    STATE_TRANSITION = "STATE_TRANSITION"
    CHECKPOINT_WRITTEN = "CHECKPOINT_WRITTEN"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    ZOMBIE_DETECTED = "ZOMBIE_DETECTED"
    TOKEN_EXHAUSTION_DETECTED = "TOKEN_EXHAUSTION_DETECTED"
    AUTO_RESUME_SCHEDULED = "AUTO_RESUME_SCHEDULED"
    AUTO_RESUME_FIRED = "AUTO_RESUME_FIRED"
    PERSIST_FAILED = "PERSIST_FAILED"
    DISK_FULL_DETECTED = "DISK_FULL_DETECTED"
    SUBPROCESS_PID_RECORDED = "SUBPROCESS_PID_RECORDED"


# ---------------------------------------------------------------------------
# CB-2748: canonical state machine table.
# Defines legal (from_state, to_state) pairs as a frozenset of 2-tuples.
# "paused" is the composite pause state — pauseReason differentiates sub-states.
# ---------------------------------------------------------------------------

_ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset([
    # From PENDING
    ("pending", "running"),
    ("pending", "aborted"),
    # From RUNNING
    ("running", "paused"),
    ("running", "waiting_reset"),
    ("running", "completed"),
    ("running", "aborted"),
    # From PAUSED (any reason)
    ("paused", "running"),
    ("paused", "aborted"),
    # From WAITING_RESET
    ("waiting_reset", "running"),
    ("waiting_reset", "paused"),
    ("waiting_reset", "aborted"),
    # Terminal states have no outgoing edges (completed, aborted)
])


def is_transition_allowed(from_state: str, to_state: str) -> bool:
    """Return True if transitioning from_state → to_state is legal.

    Terminal states (completed, aborted) reject all outgoing transitions.
    The from_state is compared case-insensitively.
    """
    return (from_state.lower(), to_state.lower()) in _ALLOWED_TRANSITIONS


class AutoPilotQueueRecord(Base):
    """Persistent record of an AutoPilot queue.

    Mirrors the in-memory ``AutoPilotQueue`` dataclass. One row per queue;
    survives backend restarts so a crashed run can be rehydrated.

    CB-2748 additions:
      state           — canonical state enum value (mirrors status for the
                        state-machine layer; status kept for backward compat)
      stateReason     — enum reason string (e.g. 'crash_recovery', 'disk_full')
      lastCheckpointAt — UTC timestamp of the last successful _checkpoint() call
      recoveryGeneration — monotonically increasing counter; incremented each
                           time rehydrate_from_db resets this queue after a crash
    """

    __tablename__ = "AutoPilotQueueRecord"

    id = Column(String, primary_key=True)
    projectId = Column(
        String,
        ForeignKey("Project.id", ondelete="CASCADE"),
        nullable=False,
    )
    featureId = Column(String, nullable=True)
    status = Column(String, nullable=False)
    currentIndex = Column(Integer, nullable=False, default=0)
    pauseReason = Column(String, nullable=True)
    resetTime = Column(DateTime, nullable=True)
    config = Column(Text, nullable=False, default="{}")
    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completedAt = Column(DateTime, nullable=True)

    # CB-2748: persistence overhaul additions
    # CB-2764: server_default ensures Base.metadata.create_all() generates the
    # same DDL as the Alembic migration (prevents schema drift on fresh installs).
    state = Column(String, nullable=True)             # canonical state enum value
    stateReason = Column(String, nullable=True)       # enum reason string
    lastCheckpointAt = Column(DateTime, nullable=True)  # last successful checkpoint
    recoveryGeneration = Column(Integer, nullable=False, default=0, server_default="0")

    # CB-2794: persist auto-resume attempt counter so the circuit breaker
    # survives backend restarts that occur during waiting_reset.
    autoResumeAttempts = Column(Integer, nullable=False, default=0, server_default="0")

    tasks = relationship(
        "AutoPilotTaskRecord",
        back_populates="queue",
        cascade="all, delete-orphan",
        order_by="AutoPilotTaskRecord.sequence",
    )
    events = relationship(
        "AutoPilotEvent",
        back_populates="queue",
        cascade="all, delete-orphan",
        order_by="AutoPilotEvent.createdAt",
    )

    __table_args__ = (
        Index("ix_AutoPilotQueueRecord_projectId_status", "projectId", "status"),
        Index("ix_AutoPilotQueueRecord_status", "status"),
    )


class AutoPilotTaskRecord(Base):
    """Persistent record of a single task within an AutoPilot queue.

    CB-2748 additions:
      lastProgressAt — UTC timestamp updated whenever files_read/files_written/
                       commands_run tick; used to distinguish stuck from active
      subprocessPid  — PID of the live claude subprocess; cleared on finish
    """

    __tablename__ = "AutoPilotTaskRecord"

    id = Column(String, primary_key=True)
    queueId = Column(
        String,
        ForeignKey("AutoPilotQueueRecord.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence = Column(Integer, nullable=False)
    issueId = Column(String, nullable=False)
    # CB-2673: persisted human-readable identifiers so rehydrated tasks
    # have populated key/title without a JOIN on every resume.
    issueKey = Column(String(64), nullable=True)
    issueTitle = Column(Text, nullable=True)
    status = Column(String, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    sessionId = Column(String, nullable=True)
    startedAt = Column(DateTime, nullable=True)
    completedAt = Column(DateTime, nullable=True)
    failureReason = Column(Text, nullable=True)

    # CB-2748: persistence overhaul additions
    lastProgressAt = Column(DateTime, nullable=True)  # last activity tick
    subprocessPid = Column(Integer, nullable=True)    # live claude subprocess PID

    queue = relationship("AutoPilotQueueRecord", back_populates="tasks")

    __table_args__ = (
        Index("ix_AutoPilotTaskRecord_queueId_sequence", "queueId", "sequence"),
        Index("ix_AutoPilotTaskRecord_issueId", "issueId"),
    )


class AutoPilotEvent(Base):
    """Append-only audit log of every AutoPilot state transition.

    Used for telemetry, post-incident debugging, and the SSE stream that
    powers frontend toast notifications. Payload is a JSON blob whose schema
    depends on the event ``type``.

    CB-2748 adds 11 new event type strings (see AutoPilotEventType above).
    """

    __tablename__ = "AutoPilotEvent"

    id = Column(String, primary_key=True)
    queueId = Column(
        String,
        ForeignKey("AutoPilotQueueRecord.id", ondelete="CASCADE"),
        nullable=False,
    )
    type = Column(String, nullable=False)
    payload = Column(Text, nullable=False, default="{}")
    createdAt = Column(DateTime, server_default=func.now(), nullable=False)

    queue = relationship("AutoPilotQueueRecord", back_populates="events")

    __table_args__ = (
        Index("ix_AutoPilotEvent_queueId_createdAt", "queueId", "createdAt"),
        Index("ix_AutoPilotEvent_type_createdAt", "type", "createdAt"),
    )
