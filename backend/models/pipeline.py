"""
SQLAlchemy models for the multi-stage pipeline execution system.
"""

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.database import Base


class PipelineExecution(Base):
    """A multi-stage pipeline execution for an issue."""
    __tablename__ = "PipelineExecution"

    id = Column(String, primary_key=True)
    issueId = Column(String, ForeignKey("Issue.id", ondelete="CASCADE"), nullable=False)
    projectId = Column(String, nullable=False)
    projectPath = Column(String, nullable=True)
    agentId = Column(String, nullable=True)
    status = Column(String, default="PENDING", nullable=False)
    currentStageIndex = Column(Integer, default=0)
    maxRetries = Column(Integer, default=3)
    retryCount = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    startedAt = Column(DateTime, nullable=True)
    completedAt = Column(DateTime, nullable=True)
    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    stages = relationship("PipelineStage", back_populates="execution", cascade="all, delete-orphan",
                          order_by="PipelineStage.stageIndex")

    __table_args__ = (
        Index("PipelineExecution_issueId_idx", "issueId"),
        Index("PipelineExecution_projectId_idx", "projectId"),
        Index("PipelineExecution_status_idx", "status"),
    )


class PipelineStage(Base):
    """A single stage in a pipeline execution."""
    __tablename__ = "PipelineStage"

    id = Column(String, primary_key=True)
    executionId = Column(String, ForeignKey("PipelineExecution.id", ondelete="CASCADE"), nullable=False)
    stageType = Column(String, nullable=False)
    stageIndex = Column(Integer, nullable=False)
    status = Column(String, default="PENDING", nullable=False)
    sessionId = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    inputData = Column(Text, nullable=True)
    resultData = Column(Text, nullable=True)
    startedAt = Column(DateTime, nullable=True)
    completedAt = Column(DateTime, nullable=True)
    createdAt = Column(DateTime, server_default=func.now(), nullable=False)

    execution = relationship("PipelineExecution", back_populates="stages")

    __table_args__ = (
        Index("PipelineStage_executionId_idx", "executionId"),
    )


class PipelineConfig(Base):
    """Pipeline configuration per project."""
    __tablename__ = "PipelineConfig"

    id = Column(String, primary_key=True)
    projectId = Column(String, unique=True, nullable=False)
    enableVerification = Column(Boolean, default=True)
    enableAutoFix = Column(Boolean, default=True)
    maxRetries = Column(Integer, default=3)
    verificationTimeout = Column(Integer, default=120)
    defaultAgentId = Column(String, nullable=True)
    verificationRules = Column(Text, nullable=True)
    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("PipelineConfig_projectId_idx", "projectId"),
    )
