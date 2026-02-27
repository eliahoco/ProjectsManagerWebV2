"""
Pydantic schemas for API request/response validation
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


def ms_to_datetime(ms_timestamp: Any) -> Optional[datetime]:
    """Convert millisecond timestamp to datetime"""
    if ms_timestamp is None:
        return None
    if isinstance(ms_timestamp, datetime):
        return ms_timestamp
    if isinstance(ms_timestamp, (int, float)):
        return datetime.fromtimestamp(ms_timestamp / 1000.0)
    return ms_timestamp


# Enums
class IssueType(str, Enum):
    FEATURE = "FEATURE"
    EPIC = "EPIC"
    STORY = "STORY"
    TASK = "TASK"
    SUBTASK = "SUBTASK"
    BUG = "BUG"


class IssueStatus(str, Enum):
    BACKLOG = "BACKLOG"
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    COMPLETED_WAITING_QA = "COMPLETED_WAITING_QA"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class LinkType(str, Enum):
    BLOCKS = "BLOCKS"
    IS_BLOCKED_BY = "IS_BLOCKED_BY"
    RELATES_TO = "RELATES_TO"
    DUPLICATES = "DUPLICATES"
    IS_DUPLICATED_BY = "IS_DUPLICATED_BY"


class CommitLinkType(str, Enum):
    MENTIONS = "MENTIONS"      # Commit message contains issue key
    FIXES = "FIXES"            # Commit fixes the issue (triggers DONE status)
    CLOSES = "CLOSES"          # Commit closes the issue (triggers DONE status)
    IMPLEMENTS = "IMPLEMENTS"  # Commit implements the issue (triggers IN_REVIEW status)


# Base schemas
class Complexity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IssueBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    type: IssueType = IssueType.TASK
    status: IssueStatus = IssueStatus.BACKLOG
    priority: Priority = Priority.MEDIUM
    parentId: Optional[str] = None
    assignee: Optional[str] = None
    reporter: Optional[str] = None
    storyPoints: Optional[int] = Field(None, ge=0)
    estimate: Optional[float] = Field(None, ge=0)
    dueDate: Optional[datetime] = None
    labels: Optional[str] = None  # JSON array
    breakdownBatchId: Optional[str] = None  # UUID to group issues from same AI breakdown


class IssueCreate(IssueBase):
    """Schema for creating a new issue"""
    pass


class IssueUpdate(BaseModel):
    """Schema for updating an issue - all fields optional"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    type: Optional[IssueType] = None
    status: Optional[IssueStatus] = None
    priority: Optional[Priority] = None
    parentId: Optional[str] = None
    assignee: Optional[str] = None
    reporter: Optional[str] = None
    storyPoints: Optional[int] = Field(None, ge=0)
    estimate: Optional[float] = Field(None, ge=0)
    timeSpent: Optional[float] = Field(None, ge=0)
    dueDate: Optional[datetime] = None
    labels: Optional[str] = None
    breakdownBatchId: Optional[str] = None
    # Implementation Documentation
    implementationSummary: Optional[str] = None
    technicalApproach: Optional[str] = None
    documentationPath: Optional[str] = None
    # Enhanced Metadata
    estimatedHours: Optional[float] = Field(None, ge=0)
    actualHours: Optional[float] = Field(None, ge=0)
    complexity: Optional[Complexity] = None
    # AI Context
    aiContext: Optional[str] = None


class IssueResponse(IssueBase):
    """Schema for issue response"""
    id: str
    projectId: str
    key: str
    sequence: int
    timeSpent: Optional[float] = None
    startedAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime
    # Implementation Documentation
    implementationSummary: Optional[str] = None
    technicalApproach: Optional[str] = None
    documentationPath: Optional[str] = None
    # Enhanced Metadata
    estimatedHours: Optional[float] = None
    actualHours: Optional[float] = None
    complexity: Optional[str] = None
    # AI Context
    aiContext: Optional[str] = None

    class Config:
        from_attributes = True


class IssueWithChildren(IssueResponse):
    """Issue with nested children"""
    children: List["IssueResponse"] = []


# Comment schemas
class CommentBase(BaseModel):
    content: str = Field(..., min_length=1)


class CommentCreate(CommentBase):
    author: str = Field(default="System")


class CommentResponse(CommentBase):
    id: str
    issueId: str
    author: str
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True


# Activity schemas
class ActivityResponse(BaseModel):
    id: str
    issueId: str
    actor: str
    action: str
    field: Optional[str] = None
    oldValue: Optional[str] = None
    newValue: Optional[str] = None
    createdAt: datetime

    class Config:
        from_attributes = True


# Issue Link schemas
class IssueLinkCreate(BaseModel):
    toIssueId: str
    linkType: LinkType


class IssueLinkResponse(BaseModel):
    id: str
    fromIssueId: str
    toIssueId: str
    linkType: LinkType
    createdAt: datetime

    class Config:
        from_attributes = True


# Project schemas (for reading from frontend DB)
class ProjectResponse(BaseModel):
    id: str
    name: str
    path: str
    status: str
    description: Optional[str] = None
    type: Optional[str] = None
    version: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime

    @field_validator('createdAt', 'updatedAt', mode='before')
    @classmethod
    def convert_timestamp(cls, v):
        return ms_to_datetime(v)

    class Config:
        from_attributes = True


# List response with pagination
class PaginatedResponse(BaseModel):
    items: List[IssueResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int


# Status update batch
class BatchStatusUpdate(BaseModel):
    issueIds: List[str]
    status: IssueStatus


# Issue sequence
class IssueSequenceResponse(BaseModel):
    projectId: str
    prefix: str
    lastNumber: int

    class Config:
        from_attributes = True


# ============================================
# QA Board Schemas
# ============================================

# QA Enums
class QATaskStatus(str, Enum):
    NOT_DONE = "NOT_DONE"
    IN_PROGRESS = "IN_PROGRESS"
    PASS = "PASS"
    FAILED = "FAILED"


class QATaskType(str, Enum):
    AUTOMATED = "AUTOMATED"
    MANUAL = "MANUAL"


class QAPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# QA Task schemas
class QATaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    scenario: str = Field(..., min_length=1)  # Test steps
    expectedResult: str = Field(..., min_length=1)
    type: QATaskType = QATaskType.AUTOMATED
    priority: QAPriority = QAPriority.MEDIUM


class QATaskCreate(QATaskBase):
    """Schema for creating a new QA task"""
    linkedIssueIds: List[str] = []  # Issues this QA task tests


class QATaskUpdate(BaseModel):
    """Schema for updating a QA task - all fields optional"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    scenario: Optional[str] = None
    expectedResult: Optional[str] = None
    actualResult: Optional[str] = None
    status: Optional[QATaskStatus] = None
    type: Optional[QATaskType] = None
    priority: Optional[QAPriority] = None
    # Enhanced Linking
    linkedFeatureId: Optional[str] = None
    linkedEpicId: Optional[str] = None
    linkedStoryId: Optional[str] = None
    linkedTaskId: Optional[str] = None
    # Context
    testContext: Optional[str] = None
    failureContext: Optional[str] = None
    environmentDetails: Optional[str] = None


class QATaskResponse(QATaskBase):
    """Schema for QA task response"""
    id: str
    projectId: str
    key: str
    sequence: int
    actualResult: Optional[str] = None
    status: QATaskStatus
    executionHistory: Optional[str] = None  # JSON
    lastExecutedAt: Optional[datetime] = None
    bugIssueId: Optional[str] = None
    # Enhanced Linking
    linkedFeatureId: Optional[str] = None
    linkedEpicId: Optional[str] = None
    linkedStoryId: Optional[str] = None
    linkedTaskId: Optional[str] = None
    # Context
    testContext: Optional[str] = None
    failureContext: Optional[str] = None
    environmentDetails: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True


class QATaskWithIssues(QATaskResponse):
    """QA task with linked issue IDs"""
    linkedIssueIds: List[str] = []


# QA Execution schemas
class QAExecutionRequest(BaseModel):
    """Request to execute QA tasks"""
    qaTaskIds: List[str]
    executionMode: str = "sequential"  # "sequential" or "parallel"


class QAExecutionResult(BaseModel):
    """Result of executing a single QA task"""
    qaTaskId: str
    key: str
    status: QATaskStatus
    actualResult: Optional[str] = None
    executionTime: float  # seconds
    error: Optional[str] = None


# QA Plan Generation schemas
class QAPlanGenerateRequest(BaseModel):
    """Request to generate QA plan for an issue"""
    issueId: str
    customInstructions: Optional[str] = None


class QAPlanGenerateResponse(BaseModel):
    """Response after generating QA plan"""
    issueId: str
    qaTasksCreated: int
    qaTaskKeys: List[str]


# QA Settings schemas
class QASettingsUpdate(BaseModel):
    """Schema for updating QA settings"""
    passThreshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    autoCreateBugs: Optional[bool] = None


class QASettingsResponse(BaseModel):
    """Schema for QA settings response"""
    projectId: str
    passThreshold: float
    autoCreateBugs: bool

    class Config:
        from_attributes = True


# QA Summary
class QASummary(BaseModel):
    """Summary statistics for QA tasks"""
    totalTasks: int
    passedTasks: int
    failedTasks: int
    notDoneTasks: int
    inProgressTasks: int
    passRate: float
    isPassingThreshold: bool


# QA Evaluation Types
class AreaCoverage(BaseModel):
    """Coverage statistics for a test area"""
    area: str
    name: str
    total: int
    passed: int
    failed: int
    notDone: int
    passRate: float


class PriorityDistribution(BaseModel):
    """Distribution of tests by priority"""
    priority: str
    count: int
    passed: int
    failed: int
    percentage: float


class TypeDistribution(BaseModel):
    """Distribution of tests by type"""
    type: str
    count: int
    passed: int
    failed: int
    percentage: float


class QualityMetric(BaseModel):
    """Quality metric with score"""
    id: str
    label: str
    value: float
    maxValue: float
    status: str
    description: str


class Recommendation(BaseModel):
    """Actionable recommendation for test plan improvement"""
    id: str
    type: str
    severity: str
    title: str
    description: str
    action: Optional[str] = None
    affectedTaskIds: Optional[List[str]] = None


class ExecutionTrend(BaseModel):
    """Trend information for test executions"""
    trend: str  # 'up', 'down', 'stable'
    change: float


class QAEvaluation(BaseModel):
    """Comprehensive test plan evaluation data"""
    summary: QASummary
    areaCoverage: List[AreaCoverage]
    priorityDistribution: List[PriorityDistribution]
    typeDistribution: List[TypeDistribution]
    qualityMetrics: List[QualityMetric]
    overallScore: int
    recommendations: List[Recommendation]
    trend: ExecutionTrend
    flakyTestIds: List[str]


# ============================================
# Execution Summary Schemas
# ============================================

class ExecutionSummaryCreate(BaseModel):
    """Schema for creating an execution summary"""
    summary: str = Field(..., min_length=1)
    executedAt: datetime
    executionTime: float = Field(..., ge=0)
    provider: str = Field(..., min_length=1)
    model: Optional[str] = None
    exitCode: Optional[int] = None
    componentsModified: str = Field(default="[]")  # JSON array
    filesTouched: str = Field(default="[]")  # JSON array
    linesAdded: Optional[int] = Field(None, ge=0)
    linesRemoved: Optional[int] = Field(None, ge=0)
    architectureNotes: Optional[str] = None
    technicalNotes: Optional[str] = None
    challengesFaced: Optional[str] = None
    lessonsLearned: Optional[str] = None
    commitHashes: Optional[str] = None  # JSON array
    docFilePath: Optional[str] = None


class ExecutionSummaryResponse(ExecutionSummaryCreate):
    """Schema for execution summary response"""
    id: str
    issueId: str
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True


# ============================================
# Feature Documentation Schemas
# ============================================

class FeatureDocumentationCreate(BaseModel):
    """Schema for creating feature documentation"""
    featureIssueId: str
    featureKey: str
    title: str = Field(..., min_length=1)
    overview: str
    requirements: str
    implementation: str
    architecture: str
    techStack: str  # JSON
    testingStrategy: str
    totalTasks: int = Field(default=0, ge=0)
    completedTasks: int = Field(default=0, ge=0)
    totalQATasks: int = Field(default=0, ge=0)
    passedQATasks: int = Field(default=0, ge=0)
    failedQATasks: int = Field(default=0, ge=0)
    mdFilePath: str
    embeddingId: Optional[str] = None


class FeatureDocumentationUpdate(BaseModel):
    """Schema for updating feature documentation"""
    title: Optional[str] = None
    overview: Optional[str] = None
    requirements: Optional[str] = None
    implementation: Optional[str] = None
    architecture: Optional[str] = None
    techStack: Optional[str] = None
    testingStrategy: Optional[str] = None
    totalTasks: Optional[int] = Field(None, ge=0)
    completedTasks: Optional[int] = Field(None, ge=0)
    totalQATasks: Optional[int] = Field(None, ge=0)
    passedQATasks: Optional[int] = Field(None, ge=0)
    failedQATasks: Optional[int] = Field(None, ge=0)
    mdFilePath: Optional[str] = None
    embeddingId: Optional[str] = None
    lastIndexedAt: Optional[datetime] = None


class FeatureDocumentationResponse(FeatureDocumentationCreate):
    """Schema for feature documentation response"""
    id: str
    projectId: str
    lastIndexedAt: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True
