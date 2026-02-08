"""
SQLAlchemy models for QA Board - Quality Assurance Testing
"""

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, ForeignKey, Index, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.database import Base


class QATask(Base):
    """QA Task model - represents a test case"""
    __tablename__ = "QATask"

    id = Column(String, primary_key=True)
    projectId = Column(String, nullable=False)

    # Task identification
    key = Column(String, unique=True, nullable=False)  # e.g., "QA-001"
    sequence = Column(Integer, nullable=False)

    # Task details
    title = Column(String, nullable=False)
    scenario = Column(Text, nullable=False)  # Test steps (markdown)
    expectedResult = Column(Text, nullable=False)
    actualResult = Column(Text, nullable=True)  # Filled after execution

    # Status and type
    # status: NOT_DONE, IN_PROGRESS, PASS, FAILED
    status = Column(String, default="NOT_DONE", nullable=False)
    # type: AUTOMATED, MANUAL
    type = Column(String, default="AUTOMATED", nullable=False)
    # priority: LOW, MEDIUM, HIGH, CRITICAL
    priority = Column(String, default="MEDIUM", nullable=False)

    # Execution history (JSON - last 10 full runs, summaries for older)
    executionHistory = Column(Text, nullable=True)

    # Timestamps
    lastExecutedAt = Column(DateTime, nullable=True)
    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Bug link (when QA fails and bug is created)
    bugIssueId = Column(String, nullable=True)

    # Enhanced Linking for Documentation
    linkedFeatureId = Column(String, nullable=True)  # Direct link to feature being tested
    linkedEpicId = Column(String, nullable=True)
    linkedStoryId = Column(String, nullable=True)
    linkedTaskId = Column(String, nullable=True)

    # Context for RAG
    testContext = Column(Text, nullable=True)  # JSON: relevant docs, architecture notes

    # Results Context
    failureContext = Column(Text, nullable=True)  # JSON: what was happening when it failed
    environmentDetails = Column(Text, nullable=True)  # JSON: environment config during test

    # Relationships
    linkedIssues = relationship("QATaskIssueLink", back_populates="qaTask", cascade="all, delete-orphan")

    __table_args__ = (
        Index("QATask_projectId_idx", "projectId"),
        Index("QATask_status_idx", "status"),
        Index("QATask_priority_idx", "priority"),
        # Index for recently executed tasks queries
        Index("QATask_lastExecutedAt_idx", "lastExecutedAt"),
        # Composite index for project + status filtering (common in list views)
        Index("QATask_projectId_status_idx", "projectId", "status"),
        # Composite index for project + last executed (for recent activity views)
        Index("QATask_projectId_lastExecutedAt_idx", "projectId", "lastExecutedAt"),
    )


class QATaskIssueLink(Base):
    """Many-to-many link between QA Tasks and Issues"""
    __tablename__ = "QATaskIssueLink"

    id = Column(String, primary_key=True)
    qaTaskId = Column(String, ForeignKey("QATask.id", ondelete="CASCADE"), nullable=False)
    issueId = Column(String, ForeignKey("Issue.id", ondelete="CASCADE"), nullable=False)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    qaTask = relationship("QATask", back_populates="linkedIssues")
    issue = relationship("Issue", back_populates="qaTaskLinks")

    __table_args__ = (
        Index("QATaskIssueLink_qaTaskId_idx", "qaTaskId"),
        Index("QATaskIssueLink_issueId_idx", "issueId"),
    )


class QASequence(Base):
    """Sequence for QA task numbering"""
    __tablename__ = "QASequence"

    id = Column(String, primary_key=True)
    projectId = Column(String, unique=True, nullable=False)
    prefix = Column(String, default="QA", nullable=False)
    lastNumber = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("QASequence_projectId_idx", "projectId"),
    )


class QASettings(Base):
    """QA Settings per project"""
    __tablename__ = "QASettings"

    id = Column(String, primary_key=True)
    projectId = Column(String, unique=True, nullable=False)
    passThreshold = Column(Float, default=0.9, nullable=False)  # 90% pass threshold
    autoCreateBugs = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("QASettings_projectId_idx", "projectId"),
    )
