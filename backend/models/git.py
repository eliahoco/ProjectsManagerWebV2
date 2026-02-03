"""
SQLAlchemy models for Git integration and commit linking
"""

from sqlalchemy import (
    Column, String, DateTime, Text, ForeignKey, Index, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.database import Base


class CommitLink(Base):
    """
    Links a git commit to an issue.
    Tracks which commits are associated with which issues.
    """
    __tablename__ = "CommitLink"

    id = Column(String, primary_key=True)
    issueId = Column(String, ForeignKey("Issue.id", ondelete="CASCADE"), nullable=False)
    projectId = Column(String, ForeignKey("Project.id", ondelete="CASCADE"), nullable=False)

    # Commit details
    commitHash = Column(String, nullable=False)
    shortHash = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    author = Column(String, nullable=False)
    authorEmail = Column(String, nullable=True)
    committedAt = Column(DateTime, nullable=False)

    # Link metadata
    linkType = Column(String, default="MENTIONS", nullable=False)  # MENTIONS, FIXES, CLOSES, IMPLEMENTS
    autoLinked = Column(Boolean, default=True, nullable=False)  # True if detected automatically
    triggeredStatusChange = Column(Boolean, default=False, nullable=False)  # True if this commit triggered a status update

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    issue = relationship("Issue", backref="commitLinks")

    __table_args__ = (
        Index("CommitLink_issueId_idx", "issueId"),
        Index("CommitLink_projectId_idx", "projectId"),
        Index("CommitLink_commitHash_idx", "commitHash"),
        # Unique constraint: one commit can only be linked to one issue once
        Index("CommitLink_unique_idx", "issueId", "commitHash", unique=True),
        # Index for author-based filtering (common in commit history views)
        Index("CommitLink_author_idx", "author"),
        # Composite index for project + author filtering
        Index("CommitLink_projectId_author_idx", "projectId", "author"),
        # Index for committedAt for time-range queries
        Index("CommitLink_committedAt_idx", "committedAt"),
        # Composite index for project + time filtering
        Index("CommitLink_projectId_committedAt_idx", "projectId", "committedAt"),
    )


class GitSyncState(Base):
    """
    Tracks the last sync state for a project's git repository.
    Used to determine which commits to scan on subsequent syncs.
    """
    __tablename__ = "GitSyncState"

    id = Column(String, primary_key=True)
    projectId = Column(String, ForeignKey("Project.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Last synced commit
    lastSyncedCommitHash = Column(String, nullable=True)
    lastSyncedAt = Column(DateTime, nullable=True)

    # Sync statistics
    totalCommitsLinked = Column(String, default="0", nullable=False)  # Using String for compatibility
    totalStatusUpdates = Column(String, default="0", nullable=False)

    # Settings
    autoSyncEnabled = Column(Boolean, default=True, nullable=False)
    autoStatusUpdateEnabled = Column(Boolean, default=True, nullable=False)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("GitSyncState_projectId_idx", "projectId"),
    )
