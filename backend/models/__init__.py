"""
Database Models for ProjectsManagerWebV2
"""

from models.database import Base, get_db, init_db, AsyncSessionLocal, engine
from models.issue import Issue, Comment, Activity, IssueLink, IssueSequence, Project
from models.git import CommitLink, GitSyncState
from models.qa import QATask, QATaskIssueLink, QASequence, QASettings
from models.documentation import ExecutionSummary, FeatureDocumentation
from models.agent_registry import AgentProfile
from models.pipeline import PipelineExecution, PipelineStage, PipelineConfig
from models.park import ParkEvent
from models.schemas import (
    IssueType,
    IssueStatus,
    Priority,
    LinkType,
    Complexity,
    IssueBase,
    IssueCreate,
    IssueUpdate,
    IssueResponse,
    IssueWithChildren,
    CommentBase,
    CommentCreate,
    CommentResponse,
    ActivityResponse,
    IssueLinkCreate,
    IssueLinkResponse,
    ProjectResponse,
    PaginatedResponse,
    BatchStatusUpdate,
    IssueSequenceResponse,
    # QA Board schemas
    QATaskStatus,
    QATaskType,
    QAPriority,
    QATaskBase,
    QATaskCreate,
    QATaskUpdate,
    QATaskResponse,
    QATaskWithIssues,
    QAExecutionRequest,
    QAExecutionResult,
    QAPlanGenerateRequest,
    QAPlanGenerateResponse,
    QASettingsUpdate,
    QASettingsResponse,
    QASummary,
    # Documentation schemas
    ExecutionSummaryCreate,
    ExecutionSummaryResponse,
    FeatureDocumentationCreate,
    FeatureDocumentationUpdate,
    FeatureDocumentationResponse,
)
from models.pipeline_schemas import (
    PipelineStatus,
    StageStatus,
    StageName,
    PipelineExecutionCreate,
    PipelineExecutionUpdate,
    PipelineExecutionResponse,
    PipelineExecutionSummary,
    PipelineStageResponse,
    PipelineConfigCreate,
    PipelineConfigUpdate,
    PipelineConfigResponse,
)

__all__ = [
    # Database
    "Base",
    "get_db",
    "init_db",
    "AsyncSessionLocal",
    "engine",
    # SQLAlchemy Models - Issues
    "Issue",
    "Comment",
    "Activity",
    "IssueLink",
    "IssueSequence",
    "Project",
    "CommitLink",
    "GitSyncState",
    # SQLAlchemy Models - QA Board
    "QATask",
    "QATaskIssueLink",
    "QASequence",
    "QASettings",
    # SQLAlchemy Models - Documentation
    "ExecutionSummary",
    "FeatureDocumentation",
    # SQLAlchemy Models - Agent Registry
    "AgentProfile",
    # SQLAlchemy Models - Pipeline
    "PipelineExecution",
    "PipelineStage",
    "PipelineConfig",
    # SQLAlchemy Models - Park
    "ParkEvent",
    # Enums - Issues
    "IssueType",
    "IssueStatus",
    "Priority",
    "LinkType",
    "Complexity",
    # Enums - QA Board
    "QATaskStatus",
    "QATaskType",
    "QAPriority",
    # Enums - Pipeline
    "PipelineStatus",
    "StageStatus",
    "StageName",
    # Pydantic Schemas - Issues
    "IssueBase",
    "IssueCreate",
    "IssueUpdate",
    "IssueResponse",
    "IssueWithChildren",
    "CommentBase",
    "CommentCreate",
    "CommentResponse",
    "ActivityResponse",
    "IssueLinkCreate",
    "IssueLinkResponse",
    "ProjectResponse",
    "PaginatedResponse",
    "BatchStatusUpdate",
    "IssueSequenceResponse",
    # Pydantic Schemas - QA Board
    "QATaskBase",
    "QATaskCreate",
    "QATaskUpdate",
    "QATaskResponse",
    "QATaskWithIssues",
    "QAExecutionRequest",
    "QAExecutionResult",
    "QAPlanGenerateRequest",
    "QAPlanGenerateResponse",
    "QASettingsUpdate",
    "QASettingsResponse",
    "QASummary",
    # Pydantic Schemas - Documentation
    "ExecutionSummaryCreate",
    "ExecutionSummaryResponse",
    "FeatureDocumentationCreate",
    "FeatureDocumentationUpdate",
    "FeatureDocumentationResponse",
    # Pydantic Schemas - Pipeline
    "PipelineExecutionCreate",
    "PipelineExecutionUpdate",
    "PipelineExecutionResponse",
    "PipelineExecutionSummary",
    "PipelineStageResponse",
    "PipelineConfigCreate",
    "PipelineConfigUpdate",
    "PipelineConfigResponse",
]
