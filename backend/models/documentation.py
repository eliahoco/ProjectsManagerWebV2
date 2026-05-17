"""
SQLAlchemy models for Documentation & Implementation Notes
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.database import Base


# Prisma owns the schema; its NOT NULL columns lack `DEFAULT CURRENT_TIMESTAMP`
# on `updatedAt`, so we must populate it from Python on INSERT (CB-1953).
# CB-2730 (CB-2377 follow-up): return tz-aware UTC. Naive `DateTime` columns
# strip tzinfo on round-trip, but the JSON-boundary `_isoformat_utc_z` serializer
# in `models/schemas.py` re-asserts UTC + emits the `Z` suffix on response.
def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ImplementationNote(Base):
    """ImplementationNote model - structured, editable notes for issues"""
    __tablename__ = "ImplementationNote"

    id = Column(String, primary_key=True)
    issueId = Column(String, ForeignKey("Issue.id", ondelete="CASCADE"), nullable=False)

    # Note content
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)  # Markdown
    category = Column(String, default="GENERAL", nullable=False)  # DECISION, APPROACH, TRADEOFF, DEPENDENCY, RISK, LESSON, GENERAL
    author = Column(String, default="System", nullable=False)

    # Optional metadata
    tags = Column(Text, nullable=True)  # JSON array of tags
    references = Column(Text, nullable=True)  # JSON array of file paths or URLs
    importance = Column(String, default="MEDIUM", nullable=False)  # LOW, MEDIUM, HIGH

    createdAt = Column(DateTime, default=_utc_now, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    issue = relationship("Issue", back_populates="implementationNotes")

    __table_args__ = (
        Index("ImplementationNote_issueId_idx", "issueId"),
        Index("ImplementationNote_category_idx", "category"),
        Index("ImplementationNote_issueId_category_idx", "issueId", "category"),
    )


class ExecutionSummary(Base):
    """ExecutionSummary model - captures implementation execution details for issues"""
    __tablename__ = "ExecutionSummary"

    id = Column(String, primary_key=True)
    issueId = Column(String, ForeignKey("Issue.id", ondelete="CASCADE"), nullable=False)

    # Execution Metadata
    summary = Column(Text, nullable=False)  # Markdown summary
    executedAt = Column(DateTime, nullable=False)
    executionTime = Column(Float, nullable=False)  # Seconds
    provider = Column(String, nullable=False)  # claude_code, ollama
    model = Column(String, nullable=True)  # claude-3-opus, etc.
    exitCode = Column(Integer, nullable=True)

    # Implementation Details
    componentsModified = Column(Text, nullable=False)  # JSON: ["frontend", "backend", "database"]
    filesTouched = Column(Text, nullable=False)  # JSON: ["src/app.tsx", "api/route.ts"]
    linesAdded = Column(Integer, nullable=True)
    linesRemoved = Column(Integer, nullable=True)

    # Documentation
    architectureNotes = Column(Text, nullable=True)  # Architectural decisions made
    technicalNotes = Column(Text, nullable=True)  # Technical implementation notes
    challengesFaced = Column(Text, nullable=True)  # Challenges and how resolved
    lessonsLearned = Column(Text, nullable=True)  # Learnings for future reference

    # Linked Artifacts
    commitHashes = Column(Text, nullable=True)  # JSON array of commit hashes
    docFilePath = Column(String, nullable=True)  # Path to generated MD file

    createdAt = Column(DateTime, default=_utc_now, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    issue = relationship("Issue", back_populates="executionSummaries")

    __table_args__ = (
        Index("ExecutionSummary_issueId_idx", "issueId"),
        Index("ExecutionSummary_executedAt_idx", "executedAt"),
    )


class FeatureDocumentation(Base):
    """FeatureDocumentation model - comprehensive documentation for features"""
    __tablename__ = "FeatureDocumentation"

    id = Column(String, primary_key=True)
    projectId = Column(String, nullable=False)
    featureIssueId = Column(String, nullable=False)
    featureKey = Column(String, nullable=False)  # CB-851

    # Documentation Content
    title = Column(String, nullable=False)
    overview = Column(Text, nullable=False)  # High-level summary
    requirements = Column(Text, nullable=False)  # Original requirements
    implementation = Column(Text, nullable=False)  # What was built
    architecture = Column(Text, nullable=False)  # Architecture decisions
    techStack = Column(Text, nullable=False)  # JSON: technologies used
    testingStrategy = Column(Text, nullable=False)  # QA approach

    # Metrics
    totalTasks = Column(Integer, nullable=False)
    completedTasks = Column(Integer, nullable=False)
    totalQATasks = Column(Integer, nullable=False)
    passedQATasks = Column(Integer, nullable=False)
    failedQATasks = Column(Integer, nullable=False)

    # File Reference
    mdFilePath = Column(String, nullable=False)  # /docs/features/CB-851.md

    # Indexing for RAG
    embeddingId = Column(String, nullable=True)  # ChromaDB document ID
    lastIndexedAt = Column(DateTime, nullable=True)

    createdAt = Column(DateTime, default=_utc_now, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("FeatureDocumentation_projectId_idx", "projectId"),
        Index("FeatureDocumentation_featureIssueId_idx", "featureIssueId"),
        Index("FeatureDocumentation_featureKey_idx", "featureKey"),
    )
