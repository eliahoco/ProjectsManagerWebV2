"""
SQLAlchemy models for CodeBoard issue tracking
"""

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, ForeignKey, Index, BigInteger,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

from models.database import Base


def ms_to_datetime(ms_timestamp):
    """Convert millisecond timestamp to datetime"""
    if ms_timestamp is None:
        return None
    return datetime.fromtimestamp(ms_timestamp / 1000.0)


class Issue(Base):
    """Issue model - represents tasks, stories, epics, bugs, etc."""
    __tablename__ = "Issue"

    id = Column(String, primary_key=True)
    projectId = Column(String, ForeignKey("Project.id", ondelete="CASCADE"), nullable=False)

    # Issue identification
    key = Column(String, unique=True, nullable=False)  # e.g., "PROJ-123"
    sequence = Column(Integer, nullable=False)

    # Issue details
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String, default="TASK", nullable=False)  # FEATURE, EPIC, STORY, TASK, SUBTASK, BUG
    status = Column(String, default="BACKLOG", nullable=False)  # BACKLOG, TODO, IN_PROGRESS, IN_REVIEW, COMPLETED_WAITING_QA, DONE, CANCELLED
    priority = Column(String, default="MEDIUM", nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL

    # Hierarchy
    parentId = Column(String, ForeignKey("Issue.id", ondelete="SET NULL"), nullable=True)

    # Assignments
    assignee = Column(String, nullable=True)
    reporter = Column(String, nullable=True)

    # Estimation & tracking
    storyPoints = Column(Integer, nullable=True)
    estimate = Column(Float, nullable=True)
    timeSpent = Column(Float, nullable=True)

    # Dates
    dueDate = Column(DateTime, nullable=True)
    startedAt = Column(DateTime, nullable=True)
    completedAt = Column(DateTime, nullable=True)
    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Metadata
    labels = Column(Text, nullable=True)  # JSON array of labels
    breakdownBatchId = Column(String, nullable=True)  # UUID to group issues from same AI breakdown

    # Implementation Documentation
    implementationSummary = Column(Text, nullable=True)  # Markdown: what was actually built
    technicalApproach = Column(Text, nullable=True)  # JSON: tech stack, patterns used
    documentationPath = Column(String, nullable=True)  # Path to MD file: /docs/features/CB-851.md

    # Enhanced Metadata
    estimatedHours = Column(Float, nullable=True)  # Estimated hours
    actualHours = Column(Float, nullable=True)  # Actual hours spent
    complexity = Column(String, nullable=True)  # LOW, MEDIUM, HIGH, CRITICAL

    # AI Context — free-text field for guiding AI agents during execution
    # Stored in ChromaDB for RAG retrieval from ancestor issues
    aiContext = Column(Text, nullable=True)

    # Relationships
    parent = relationship("Issue", remote_side=[id], back_populates="children")
    children = relationship("Issue", back_populates="parent")
    comments = relationship("Comment", back_populates="issue", cascade="all, delete-orphan")
    activities = relationship("Activity", back_populates="issue", cascade="all, delete-orphan")
    qaTaskLinks = relationship("QATaskIssueLink", back_populates="issue", cascade="all, delete-orphan")
    executionSummaries = relationship("ExecutionSummary", back_populates="issue", cascade="all, delete-orphan")
    implementationNotes = relationship("ImplementationNote", back_populates="issue", cascade="all, delete-orphan")

    __table_args__ = (
        Index("Issue_projectId_idx", "projectId"),
        Index("Issue_parentId_idx", "parentId"),
        Index("Issue_status_idx", "status"),
        Index("Issue_type_idx", "type"),
        Index("Issue_breakdownBatchId_idx", "breakdownBatchId"),
        # Composite indexes for common filter combinations
        Index("Issue_projectId_status_idx", "projectId", "status"),
        Index("Issue_projectId_type_idx", "projectId", "type"),
        Index("Issue_projectId_type_status_idx", "projectId", "type", "status"),
        # Index for assignee filtering
        Index("Issue_assignee_idx", "assignee"),
        # Index for key lookups (frequently used in webhooks and searches)
        Index("Issue_key_idx", "key"),
        # Indexes for date-based sorting and filtering (commonly used in list views)
        Index("Issue_createdAt_idx", "createdAt"),
        Index("Issue_updatedAt_idx", "updatedAt"),
        Index("Issue_projectId_createdAt_idx", "projectId", "createdAt"),
        Index("Issue_projectId_updatedAt_idx", "projectId", "updatedAt"),
        # Index for due date filtering
        Index("Issue_dueDate_idx", "dueDate"),
    )


class Comment(Base):
    """Comment model - comments on issues"""
    __tablename__ = "Comment"

    id = Column(String, primary_key=True)
    issueId = Column(String, ForeignKey("Issue.id", ondelete="CASCADE"), nullable=False)

    author = Column(String, nullable=False)
    content = Column(Text, nullable=False)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    issue = relationship("Issue", back_populates="comments")

    __table_args__ = (
        Index("Comment_issueId_idx", "issueId"),
    )


class Activity(Base):
    """Activity model - audit log for issue changes"""
    __tablename__ = "Activity"

    id = Column(String, primary_key=True)
    issueId = Column(String, ForeignKey("Issue.id", ondelete="CASCADE"), nullable=False)

    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)  # CREATED, UPDATED, STATUS_CHANGED, etc.
    field = Column(String, nullable=True)
    oldValue = Column(Text, nullable=True)
    newValue = Column(Text, nullable=True)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    issue = relationship("Issue", back_populates="activities")

    __table_args__ = (
        Index("Activity_issueId_idx", "issueId"),
        # Index for time-range queries on activity logs
        Index("Activity_createdAt_idx", "createdAt"),
        # Composite index for filtering activities by issue and time
        Index("Activity_issueId_createdAt_idx", "issueId", "createdAt"),
    )


class IssueLink(Base):
    """IssueLink model - links between issues"""
    __tablename__ = "IssueLink"

    id = Column(String, primary_key=True)
    fromIssueId = Column(String, ForeignKey("Issue.id", ondelete="CASCADE"), nullable=False)
    toIssueId = Column(String, ForeignKey("Issue.id", ondelete="CASCADE"), nullable=False)

    linkType = Column(String, nullable=False)  # BLOCKS, IS_BLOCKED_BY, RELATES_TO, DUPLICATES, IS_DUPLICATED_BY, CAUSED_BY, CAUSES

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)

    # CB-1960: read-only relationships used to project endpoint summaries
    # ({id, key, title, status}) for both ends of the link without a second
    # round-trip. Never written through. lazy="raise_on_sql" forces eager
    # loading via selectinload while remaining safe on transient instances.
    fromIssue = relationship("Issue", foreign_keys=[fromIssueId], lazy="raise_on_sql")
    toIssue = relationship("Issue", foreign_keys=[toIssueId], lazy="raise_on_sql")

    __table_args__ = (
        Index("IssueLink_fromIssueId_idx", "fromIssueId"),
        Index("IssueLink_toIssueId_idx", "toIssueId"),
        UniqueConstraint(
            "fromIssueId", "toIssueId", "linkType",
            name="IssueLink_fromIssueId_toIssueId_linkType_key",
        ),
    )


class IssueSequence(Base):
    """IssueSequence model - tracks issue numbering per project"""
    __tablename__ = "IssueSequence"

    id = Column(String, primary_key=True)
    projectId = Column(String, unique=True, nullable=False)
    prefix = Column(String, nullable=False)  # e.g., "PROJ", "CB"
    lastNumber = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("IssueSequence_projectId_idx", "projectId"),
    )


# Project model (read from frontend database)
class Project(Base):
    """Project model - mirrors the frontend Prisma Project model"""
    __tablename__ = "Project"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    path = Column(String, nullable=False)
    status = Column(String, default="ACTIVE", nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String, nullable=True)
    version = Column(String, nullable=True)
    # Prisma stores datetime as Unix timestamps in milliseconds
    createdAt = Column(BigInteger, nullable=False)
    updatedAt = Column(BigInteger, nullable=False)

    @property
    def created_at_datetime(self):
        return ms_to_datetime(self.createdAt)

    @property
    def updated_at_datetime(self):
        return ms_to_datetime(self.updatedAt)
