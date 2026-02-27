"""
Pydantic schemas for AI Execution Pipeline API request/response validation
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ============================================
# Pipeline Enums
# ============================================

class PipelineStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StageName(str, Enum):
    IMPLEMENT = "IMPLEMENT"
    VERIFY = "VERIFY"
    FIX = "FIX"
    RE_VERIFY = "RE_VERIFY"


# ============================================
# Pipeline Execution Schemas
# ============================================

class PipelineExecutionCreate(BaseModel):
    """Schema for creating a new pipeline execution"""
    issueId: str
    projectId: str
    agentId: Optional[str] = None
    maxRetries: int = Field(default=3, ge=0, le=10)


class PipelineExecutionUpdate(BaseModel):
    """Schema for updating a pipeline execution"""
    status: Optional[PipelineStatus] = None
    currentStage: Optional[StageName] = None
    retryCount: Optional[int] = Field(None, ge=0)
    startedAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None


class PipelineExecutionResponse(BaseModel):
    """Schema for pipeline execution response"""
    id: str
    issueId: str
    projectId: str
    agentId: Optional[str] = None
    status: PipelineStatus
    currentStage: str
    retryCount: int
    maxRetries: int
    startedAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime
    stages: List["PipelineStageResponse"] = []

    class Config:
        from_attributes = True


class PipelineExecutionSummary(BaseModel):
    """Lightweight pipeline execution for list views (without stages)"""
    id: str
    issueId: str
    projectId: str
    agentId: Optional[str] = None
    status: PipelineStatus
    currentStage: str
    retryCount: int
    maxRetries: int
    startedAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True


# ============================================
# Pipeline Stage Schemas
# ============================================

class PipelineStageResponse(BaseModel):
    """Schema for pipeline stage response"""
    id: str
    executionId: str
    stageName: StageName
    stageOrder: int
    status: StageStatus
    agentId: Optional[str] = None
    input: Optional[str] = None  # JSON string
    output: Optional[str] = None  # JSON string
    evidence: Optional[str] = None  # JSON string
    errorMessage: Optional[str] = None
    startedAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    durationSeconds: Optional[float] = None
    createdAt: datetime

    class Config:
        from_attributes = True


# ============================================
# Pipeline Config Schemas
# ============================================

class PipelineConfigCreate(BaseModel):
    """Schema for creating pipeline config"""
    projectId: str
    enableVerification: bool = True
    enableAutoFix: bool = True
    maxRetries: int = Field(default=3, ge=0, le=10)
    verificationTimeout: int = Field(default=120, ge=10, le=600)
    defaultAgentId: Optional[str] = None
    verificationRules: Optional[str] = None  # JSON string


class PipelineConfigUpdate(BaseModel):
    """Schema for updating pipeline config - all fields optional"""
    enableVerification: Optional[bool] = None
    enableAutoFix: Optional[bool] = None
    maxRetries: Optional[int] = Field(None, ge=0, le=10)
    verificationTimeout: Optional[int] = Field(None, ge=10, le=600)
    defaultAgentId: Optional[str] = None
    verificationRules: Optional[str] = None  # JSON string


class PipelineConfigResponse(BaseModel):
    """Schema for pipeline config response"""
    id: str
    projectId: str
    enableVerification: bool
    enableAutoFix: bool
    maxRetries: int
    verificationTimeout: int
    defaultAgentId: Optional[str] = None
    verificationRules: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True
