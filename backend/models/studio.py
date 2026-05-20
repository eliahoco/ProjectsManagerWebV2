"""
SQLAlchemy ORM models for Studio (CB-2384).

Tables:
  StudioSession           — workspace conversation session
  StudioMessage           — ordered messages in a session
  StudioToolCall          — individual tool invocations
  StudioSubAgentRun       — sub-agent (researcher/designer/etc.) executions
  StudioArtifact          — generated artifacts (markdown, code, hierarchy JSON, …)
  StudioHierarchyDraft    — pending/approved hierarchy trees before CodeBoard promote
  StudioAgentActivity     — append-only visibility log (fires BEFORE agent dispatch)

Every table carries:
  id        — cuid string PK
  tenantId  — nullable Phase-1 tenant scope (NOT NULL enforced via RLS in Phase 2)
  createdAt — server-default UTC timestamp
  updatedAt — auto-updated on write

Column names use camelCase to match the Prisma schema convention used throughout
this codebase (do not convert to snake_case).
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.database import Base


class StudioSession(Base):
    """A Studio workspace conversation session.

    One session maps to one planning conversation between the user and the
    orchestrator. A project can have multiple sessions (historical + active).
    """

    __tablename__ = "StudioSession"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    projectId = Column(
        String,
        ForeignKey("Project.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String, nullable=False)
    status = Column(
        String,
        nullable=False,
        default="ACTIVE",
    )  # ACTIVE | PAUSED | HIBERNATED | COMPLETED | FAILED
    planningState = Column(JSON, nullable=False, default=dict)
    lastMessageAt = Column(DateTime, nullable=True)
    tokenBudget = Column(Integer, nullable=False, default=50000)
    tokensUsed = Column(Integer, nullable=False, default=0)
    createdBy = Column(String, nullable=True)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    messages = relationship(
        "StudioMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="StudioMessage.sequenceNum",
    )
    tool_calls = relationship(
        "StudioToolCall",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    subagent_runs = relationship(
        "StudioSubAgentRun",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    artifacts = relationship(
        "StudioArtifact",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    hierarchy_drafts = relationship(
        "StudioHierarchyDraft",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    agent_activities = relationship(
        "StudioAgentActivity",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    agent_instances = relationship(
        "AgentInstance",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    backlog_items = relationship(
        "BacklogItem",
        back_populates="source_session",
    )

    __table_args__ = (
        Index("StudioSession_tenantId_idx", "tenantId"),
        Index("StudioSession_projectId_idx", "projectId"),
        Index("StudioSession_status_idx", "status"),
        Index("StudioSession_tenantId_projectId_idx", "tenantId", "projectId"),
        Index("StudioSession_projectId_status_idx", "projectId", "status"),
    )


class StudioMessage(Base):
    """An ordered message within a StudioSession.

    ``sequenceNum`` is monotonically increasing per session and is assigned by
    the service layer before insert.  The UNIQUE constraint on
    (sessionId, sequenceNum) makes concurrent-append races visible immediately
    rather than silently clobbering earlier messages.
    """

    __tablename__ = "StudioMessage"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    sessionId = Column(
        String,
        ForeignKey("StudioSession.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequenceNum = Column(Integer, nullable=False)
    role = Column(String, nullable=False)  # USER | ASSISTANT | TOOL_RESULT | SUB_AGENT
    content = Column(JSON, nullable=False)
    model = Column(String, nullable=True)
    tokensInput = Column(Integer, nullable=False, default=0)
    tokensOutput = Column(Integer, nullable=False, default=0)
    costUsd = Column(Float, nullable=False, default=0.0)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    session = relationship("StudioSession", back_populates="messages")
    tool_calls = relationship(
        "StudioToolCall",
        back_populates="message",
        foreign_keys="[StudioToolCall.messageId]",
    )
    subagent_runs = relationship(
        "StudioSubAgentRun",
        back_populates="parent_message",
        foreign_keys="[StudioSubAgentRun.parentMessageId]",
    )

    __table_args__ = (
        UniqueConstraint(
            "sessionId",
            "sequenceNum",
            name="StudioMessage_sessionId_sequenceNum_key",
        ),
        Index("StudioMessage_sessionId_idx", "sessionId"),
        Index("StudioMessage_tenantId_idx", "tenantId"),
        Index("StudioMessage_sessionId_sequenceNum_idx", "sessionId", "sequenceNum"),
    )


class StudioToolCall(Base):
    """A single tool invocation recorded during a Studio session turn."""

    __tablename__ = "StudioToolCall"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    sessionId = Column(
        String,
        ForeignKey("StudioSession.id", ondelete="CASCADE"),
        nullable=False,
    )
    messageId = Column(
        String,
        ForeignKey("StudioMessage.id", ondelete="SET NULL"),
        nullable=True,
    )
    toolName = Column(String, nullable=False)
    input = Column(JSON, nullable=False)
    output = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="PENDING")  # PENDING | RUNNING | COMPLETED | FAILED
    error = Column(Text, nullable=True)
    startedAt = Column(DateTime, nullable=True)
    completedAt = Column(DateTime, nullable=True)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    session = relationship("StudioSession", back_populates="tool_calls")
    message = relationship(
        "StudioMessage",
        back_populates="tool_calls",
        foreign_keys=[messageId],
    )

    __table_args__ = (
        Index("StudioToolCall_sessionId_idx", "sessionId"),
        Index("StudioToolCall_messageId_idx", "messageId"),
        Index("StudioToolCall_tenantId_idx", "tenantId"),
        Index("StudioToolCall_status_idx", "status"),
    )


class StudioSubAgentRun(Base):
    """Execution record for a sub-agent spawned within a session turn.

    Sub-agents are nested API calls (max chain depth 1) that specialise in
    a single role: RESEARCHER, DESIGNER, BREAKDOWN_WRITER, or AUDITOR.
    """

    __tablename__ = "StudioSubAgentRun"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    sessionId = Column(
        String,
        ForeignKey("StudioSession.id", ondelete="CASCADE"),
        nullable=False,
    )
    parentMessageId = Column(
        String,
        ForeignKey("StudioMessage.id", ondelete="SET NULL"),
        nullable=True,
    )
    agentRole = Column(String, nullable=False)  # RESEARCHER | DESIGNER | BREAKDOWN_WRITER | AUDITOR
    inputSnapshot = Column(JSON, nullable=False)
    outputSnapshot = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="PENDING")  # PENDING | RUNNING | DONE | FAILED
    model = Column(String, nullable=False)
    tokensInput = Column(Integer, nullable=False, default=0)
    tokensOutput = Column(Integer, nullable=False, default=0)
    costUsd = Column(Float, nullable=False, default=0.0)
    startedAt = Column(DateTime, nullable=True)
    completedAt = Column(DateTime, nullable=True)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    session = relationship("StudioSession", back_populates="subagent_runs")
    parent_message = relationship(
        "StudioMessage",
        back_populates="subagent_runs",
        foreign_keys=[parentMessageId],
    )

    __table_args__ = (
        Index("StudioSubAgentRun_sessionId_idx", "sessionId"),
        Index("StudioSubAgentRun_parentMessageId_idx", "parentMessageId"),
        Index("StudioSubAgentRun_tenantId_idx", "tenantId"),
        Index("StudioSubAgentRun_status_idx", "status"),
        Index("StudioSubAgentRun_agentRole_idx", "agentRole"),
    )


class StudioArtifact(Base):
    """A generated artifact (file, plan, diagram, …) produced during a session.

    Small artifacts (<= 64 KB) are stored inline in ``content``; larger ones
    reference an external store via ``storageUrl``.  Both ``sha256`` and
    ``sizeBytes`` are always populated so integrity can be verified without
    fetching remote content.
    """

    __tablename__ = "StudioArtifact"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    sessionId = Column(
        String,
        ForeignKey("StudioSession.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # MARKDOWN | MERMAID | CODE | HTML | HIERARCHY_JSON | IMAGE | OTHER
    content = Column(Text, nullable=True)   # inline storage, up to 64 KB
    storageUrl = Column(String, nullable=True)
    sizeBytes = Column(Integer, nullable=False, default=0)
    sha256 = Column(String, nullable=False)
    version = Column(Integer, nullable=False, default=1)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    session = relationship("StudioSession", back_populates="artifacts")
    backlog_items_source = relationship(
        "BacklogItem",
        back_populates="source_artifact",
        foreign_keys="[BacklogItem.sourceArtifactId]",
    )

    __table_args__ = (
        Index("StudioArtifact_sessionId_idx", "sessionId"),
        Index("StudioArtifact_tenantId_idx", "tenantId"),
        Index("StudioArtifact_kind_idx", "kind"),
        Index("StudioArtifact_sha256_idx", "sha256"),
    )


class StudioHierarchyDraft(Base):
    """A pending or approved FEATURE→…→SUBTASK hierarchy tree.

    Once a draft is APPROVED the service layer runs the promote pipeline which
    pushes the tree into CodeBoard issues and sets ``promotedToFeatureId``.
    """

    __tablename__ = "StudioHierarchyDraft"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    sessionId = Column(
        String,
        ForeignKey("StudioSession.id", ondelete="CASCADE"),
        nullable=False,
    )
    tree = Column(JSON, nullable=False)
    status = Column(String, nullable=False, default="DRAFT")  # DRAFT | REVIEWING | APPROVED | PROMOTED | FAILED
    promotedToFeatureId = Column(String, nullable=True)
    approvedBy = Column(String, nullable=True)
    approvedAt = Column(DateTime, nullable=True)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    session = relationship("StudioSession", back_populates="hierarchy_drafts")

    __table_args__ = (
        Index("StudioHierarchyDraft_sessionId_idx", "sessionId"),
        Index("StudioHierarchyDraft_tenantId_idx", "tenantId"),
        Index("StudioHierarchyDraft_status_idx", "status"),
        Index("StudioHierarchyDraft_sessionId_status_idx", "sessionId", "status"),
    )


class StudioAgentActivity(Base):
    """Append-only visibility log entry for agent communication events.

    Written BEFORE the dispatch executes (Visibility Principle) so the SSE
    stream surfaces intent before the agent has acted.  Never updated after
    insert.
    """

    __tablename__ = "StudioAgentActivity"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    sessionId = Column(
        String,
        ForeignKey("StudioSession.id", ondelete="CASCADE"),
        nullable=False,
    )
    verb = Column(String, nullable=False)  # NOTIFY | REQUEST | DELEGATE | BROADCAST
    sourceAgent = Column(String, nullable=False)
    targetAgent = Column(String, nullable=True)
    payload = Column(JSON, nullable=False)
    chainDepth = Column(Integer, nullable=False, default=0)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    session = relationship("StudioSession", back_populates="agent_activities")

    __table_args__ = (
        Index("StudioAgentActivity_sessionId_idx", "sessionId"),
        Index("StudioAgentActivity_tenantId_idx", "tenantId"),
        Index("StudioAgentActivity_verb_idx", "verb"),
        Index("StudioAgentActivity_sessionId_createdAt_idx", "sessionId", "createdAt"),
    )
