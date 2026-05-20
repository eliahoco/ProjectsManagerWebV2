"""
SQLAlchemy ORM models for the Crew Map (CB-2384).

Tables:
  CrewAssignment  — maps an agent template to a specific issue within a project
  CrewSkillUsage  — tracks per-skill invocation counts within an assignment

Column names use camelCase to match the Prisma schema convention used throughout
this codebase (do not convert to snake_case).
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.database import Base


class CrewAssignment(Base):
    """An agent template assigned to execute a specific issue.

    The Crew Map graph renders one node per CrewAssignment.  The ``status``
    lifecycle mirrors the issue execution lifecycle:
      ASSIGNED → ACTIVE → PAUSED → RELEASED
    """

    __tablename__ = "CrewAssignment"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    projectId = Column(
        String,
        ForeignKey("Project.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issueId = Column(
        String,
        ForeignKey("Issue.id", ondelete="RESTRICT"),
        nullable=False,
    )
    agentTemplateId = Column(
        String,
        ForeignKey("AgentTemplate.id", ondelete="RESTRICT"),
        nullable=False,
    )
    roleLabel = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ASSIGNED")  # ASSIGNED | ACTIVE | PAUSED | RELEASED

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    agent_template = relationship("AgentTemplate", back_populates="crew_assignments")
    skill_usages = relationship(
        "CrewSkillUsage",
        back_populates="assignment",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("CrewAssignment_tenantId_idx", "tenantId"),
        Index("CrewAssignment_projectId_idx", "projectId"),
        Index("CrewAssignment_issueId_idx", "issueId"),
        Index("CrewAssignment_agentTemplateId_idx", "agentTemplateId"),
        Index("CrewAssignment_status_idx", "status"),
        Index("CrewAssignment_tenantId_projectId_idx", "tenantId", "projectId"),
        Index("CrewAssignment_projectId_status_idx", "projectId", "status"),
    )


class CrewSkillUsage(Base):
    """Per-skill invocation counter within a CrewAssignment.

    Incremented by the service layer each time a named skill fires during
    agent execution.  ``lastUsedAt`` is updated on each increment so the
    Crew Map can show recency without a full activity scan.
    """

    __tablename__ = "CrewSkillUsage"

    id = Column(String, primary_key=True)
    tenantId = Column(String, nullable=True)

    assignmentId = Column(
        String,
        ForeignKey("CrewAssignment.id", ondelete="CASCADE"),
        nullable=False,
    )
    skillName = Column(String, nullable=False)
    invocationCount = Column(Integer, nullable=False, default=0)
    lastUsedAt = Column(DateTime, nullable=True)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    assignment = relationship("CrewAssignment", back_populates="skill_usages")

    __table_args__ = (
        Index("CrewSkillUsage_assignmentId_idx", "assignmentId"),
        Index("CrewSkillUsage_tenantId_idx", "tenantId"),
        Index("CrewSkillUsage_skillName_idx", "skillName"),
        Index("CrewSkillUsage_assignmentId_skillName_idx", "assignmentId", "skillName"),
    )
