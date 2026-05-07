"""
SQLAlchemy ORM mirrors of the Prisma AutoPilot persistence models.

Mirrors three Prisma models added in CB-1951:
  - AutoPilotQueueRecord  → table "AutoPilotQueueRecord"
  - AutoPilotTaskRecord   → table "AutoPilotTaskRecord"
  - AutoPilotEvent        → table "AutoPilotEvent"

Column names use camelCase to match the Prisma schema (the codebase uses a
camelCase Prisma + camelCase SQLAlchemy hybrid; do not switch to snake_case).
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


class AutoPilotQueueRecord(Base):
    """Persistent record of an AutoPilot queue.

    Mirrors the in-memory ``AutoPilotQueue`` dataclass. One row per queue;
    survives backend restarts so a crashed run can be rehydrated.
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
    """Persistent record of a single task within an AutoPilot queue."""

    __tablename__ = "AutoPilotTaskRecord"

    id = Column(String, primary_key=True)
    queueId = Column(
        String,
        ForeignKey("AutoPilotQueueRecord.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence = Column(Integer, nullable=False)
    issueId = Column(String, nullable=False)
    status = Column(String, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    sessionId = Column(String, nullable=True)
    startedAt = Column(DateTime, nullable=True)
    completedAt = Column(DateTime, nullable=True)
    failureReason = Column(Text, nullable=True)

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
