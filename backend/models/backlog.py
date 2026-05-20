"""
SQLAlchemy ORM models for the Studio Backlog (CB-2384).

Tables:
  BacklogItem     — a planned work item flowing from Studio toward CodeBoard
  BacklogComment  — threaded comments on a backlog item
  BacklogActivity — append-only audit trail of backlog item state changes

Column names use camelCase to match the Prisma schema convention used throughout
this codebase (do not convert to snake_case).
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.database import Base


class BacklogItem(Base):
    """A planned work item that can be reviewed, scheduled, and promoted.

    ``sourceSessionId`` links the item back to the Studio session that
    generated it (optional — items can be created manually too).
    ``sourceArtifactId`` records the specific artifact that produced the item
    (e.g. a ``push_hierarchy_draft`` tool call artifact).

    Status flow:
      DRAFT → REVIEWING → APPROVED → SCHEDULED → PROMOTED → SHIPPED | ARCHIVED
    """

    __tablename__ = "BacklogItem"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    projectId = Column(
        String,
        ForeignKey("Project.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String, nullable=False, default="MEDIUM")  # LOW | MEDIUM | HIGH | CRITICAL
    status = Column(String, nullable=False, default="DRAFT")  # DRAFT | REVIEWING | APPROVED | SCHEDULED | PROMOTED | SHIPPED | ARCHIVED
    scheduledFor = Column(DateTime, nullable=True)
    cronExpression = Column(String, nullable=True)

    sourceSessionId = Column(
        String,
        ForeignKey("StudioSession.id", ondelete="SET NULL"),
        nullable=True,
    )
    sourceArtifactId = Column(
        String,
        ForeignKey("StudioArtifact.id", ondelete="SET NULL"),
        nullable=True,
    )
    promotedToFeatureId = Column(String, nullable=True)
    promoteJobId = Column(String, nullable=True)
    ownerEmail = Column(String, nullable=True)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    source_session = relationship(
        "StudioSession",
        back_populates="backlog_items",
        foreign_keys=[sourceSessionId],
    )
    source_artifact = relationship(
        "StudioArtifact",
        back_populates="backlog_items_source",
        foreign_keys=[sourceArtifactId],
    )
    comments = relationship(
        "BacklogComment",
        back_populates="item",
        cascade="all, delete-orphan",
    )
    activities = relationship(
        "BacklogActivity",
        back_populates="item",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("BacklogItem_tenantId_idx", "tenantId"),
        Index("BacklogItem_projectId_idx", "projectId"),
        Index("BacklogItem_status_idx", "status"),
        Index("BacklogItem_priority_idx", "priority"),
        Index("BacklogItem_sourceSessionId_idx", "sourceSessionId"),
        Index("BacklogItem_tenantId_projectId_idx", "tenantId", "projectId"),
        Index("BacklogItem_projectId_status_idx", "projectId", "status"),
        Index("BacklogItem_scheduledFor_idx", "scheduledFor"),
    )


class BacklogComment(Base):
    """A comment thread entry on a BacklogItem."""

    __tablename__ = "BacklogComment"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    itemId = Column(
        String,
        ForeignKey("BacklogItem.id", ondelete="CASCADE"),
        nullable=False,
    )
    author = Column(String, nullable=False)
    content = Column(Text, nullable=False)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    item = relationship("BacklogItem", back_populates="comments")

    __table_args__ = (
        Index("BacklogComment_itemId_idx", "itemId"),
        Index("BacklogComment_tenantId_idx", "tenantId"),
    )


class BacklogActivity(Base):
    """Append-only audit trail of state changes on a BacklogItem.

    ``payload`` is a JSON dict whose schema depends on ``action`` (e.g.
    ``{from: "DRAFT", to: "APPROVED"}`` for a status transition).
    """

    __tablename__ = "BacklogActivity"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    itemId = Column(
        String,
        ForeignKey("BacklogItem.id", ondelete="CASCADE"),
        nullable=False,
    )
    action = Column(String, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    actor = Column(String, nullable=True)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    item = relationship("BacklogItem", back_populates="activities")

    __table_args__ = (
        Index("BacklogActivity_itemId_idx", "itemId"),
        Index("BacklogActivity_tenantId_idx", "tenantId"),
        Index("BacklogActivity_itemId_createdAt_idx", "itemId", "createdAt"),
    )
