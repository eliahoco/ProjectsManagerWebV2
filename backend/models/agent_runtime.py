"""
SQLAlchemy ORM models for the shared Agent Runtime (CB-2384).

Tables:
  AgentTemplate     — versioned prompt + tool configuration for an agent role
  AgentInstance     — live agent bound to a session, carrying conversation memory
  TenantTokenUsage  — per-tenant per-day token cost rollup for billing attribution

Column names use camelCase to match the Prisma schema convention used throughout
this codebase (do not convert to snake_case).
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Date,
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


class AgentTemplate(Base):
    """Versioned system-prompt + tool configuration for a named agent role.

    ``key`` is a human-readable identifier (e.g. ``"orchestrator"``,
    ``"researcher"``).  ``version`` increments each time the prompt or tool
    set is changed so rollbacks and A/B comparisons stay possible without
    losing history.  ``UNIQUE(key, version)`` prevents duplicate registrations.
    """

    __tablename__ = "AgentTemplate"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    key = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    systemPrompt = Column(Text, nullable=False)
    tools = Column(JSON, nullable=False)
    modelDefault = Column(String, nullable=False)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    instances = relationship(
        "AgentInstance",
        back_populates="template",
        cascade="all, delete-orphan",
    )
    crew_assignments = relationship(
        "CrewAssignment",
        back_populates="agent_template",
    )

    __table_args__ = (
        UniqueConstraint(
            "key",
            "version",
            name="AgentTemplate_key_version_key",
        ),
        Index("AgentTemplate_tenantId_idx", "tenantId"),
        Index("AgentTemplate_key_idx", "key"),
        Index("AgentTemplate_key_version_idx", "key", "version"),
    )


class AgentInstance(Base):
    """A live agent instantiated from a template within a session.

    ``memory`` is a JSON blob that the service layer updates in-place as the
    agent accumulates context across turns.  It is keyed to the session so
    each session starts with fresh memory derived from the template.
    """

    __tablename__ = "AgentInstance"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    sessionId = Column(
        String,
        ForeignKey("StudioSession.id", ondelete="CASCADE"),
        nullable=True,
    )
    templateId = Column(
        String,
        ForeignKey("AgentTemplate.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory = Column(JSON, nullable=False, default=dict)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    session = relationship("StudioSession", back_populates="agent_instances")
    template = relationship("AgentTemplate", back_populates="instances")

    __table_args__ = (
        Index("AgentInstance_sessionId_idx", "sessionId"),
        Index("AgentInstance_templateId_idx", "templateId"),
        Index("AgentInstance_tenantId_idx", "tenantId"),
        Index("AgentInstance_tenantId_sessionId_idx", "tenantId", "sessionId"),
    )


class TenantTokenUsage(Base):
    """Per-tenant, per-day token usage rollup.

    One row per (tenantId, date) pair — the service layer upserts into this
    table each time a Studio message or sub-agent run completes.
    ``modelBreakdown`` is a JSON dict mapping model name → {input, output,
    costUsd} for per-model attribution.

    UNIQUE(tenantId, date) is enforced at DB level so concurrent upserts
    never create ghost rows.
    """

    __tablename__ = "TenantTokenUsage"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    date = Column(Date, nullable=False)
    tokensInput = Column(Integer, nullable=False, default=0)
    tokensOutput = Column(Integer, nullable=False, default=0)
    costUsd = Column(Float, nullable=False, default=0.0)
    modelBreakdown = Column(JSON, nullable=False, default=dict)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "tenantId",
            "date",
            name="TenantTokenUsage_tenantId_date_key",
        ),
        Index("TenantTokenUsage_tenantId_idx", "tenantId"),
        Index("TenantTokenUsage_date_idx", "date"),
        Index("TenantTokenUsage_tenantId_date_idx", "tenantId", "date"),
    )
