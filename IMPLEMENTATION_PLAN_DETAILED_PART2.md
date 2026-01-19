# ProjectsManagerWebV2 - Detailed Implementation Plan (Part 2)

## Continued from Part 1...

---

## Story 2.2: Create FastAPI Models

**ID:** S2.2
**Epic:** E2
**Priority:** High
**Description:** Define SQLAlchemy models and Pydantic schemas for the FastAPI backend that mirror the Prisma schema.

---

### Task T2.2.1: Create SQLAlchemy Issue Model

**ID:** T2.2.1
**Story:** S2.2
**Priority:** High
**Estimated Effort:** 45 minutes

**Description:**
Create SQLAlchemy ORM models that mirror the Prisma schema for use in the FastAPI backend. Since we're using SQLite and the same database file, the models must be compatible with the Prisma-generated tables.

**File: backend/models/issue.py**
```python
"""SQLAlchemy models for CodeBoard issues."""

from sqlalchemy import (
    Column, String, Text, Integer, DateTime, Enum, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from .base import Base

# Enums matching Prisma schema
class IssueType(str, enum.Enum):
    EPIC = "EPIC"
    STORY = "STORY"
    TASK = "TASK"
    SUBTASK = "SUBTASK"
    BUG = "BUG"

class IssueStatus(str, enum.Enum):
    BACKLOG = "BACKLOG"
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    DONE = "DONE"
    CANCELLED = "CANCELLED"

class Priority(str, enum.Enum):
    LOWEST = "LOWEST"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    HIGHEST = "HIGHEST"

class Assignee(str, enum.Enum):
    AI = "AI"
    HUMAN = "HUMAN"
    UNASSIGNED = "UNASSIGNED"

class ActivityType(str, enum.Enum):
    CREATED = "CREATED"
    STATUS_CHANGED = "STATUS_CHANGED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"
    ASSIGNEE_CHANGED = "ASSIGNEE_CHANGED"
    DESCRIPTION_UPDATED = "DESCRIPTION_UPDATED"
    TITLE_UPDATED = "TITLE_UPDATED"
    COMMENT_ADDED = "COMMENT_ADDED"
    LINKED = "LINKED"
    UNLINKED = "UNLINKED"
    PARENT_CHANGED = "PARENT_CHANGED"
    LABELS_CHANGED = "LABELS_CHANGED"
    ESTIMATE_CHANGED = "ESTIMATE_CHANGED"
    DUE_DATE_CHANGED = "DUE_DATE_CHANGED"


class Issue(Base):
    """Issue model for CodeBoard."""
    __tablename__ = "Issue"

    id = Column(String, primary_key=True)
    key = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    type = Column(Enum(IssueType), default=IssueType.TASK, nullable=False)
    status = Column(Enum(IssueStatus), default=IssueStatus.BACKLOG, nullable=False)
    priority = Column(Enum(Priority), default=Priority.MEDIUM, nullable=False)
    assignee = Column(Enum(Assignee), default=Assignee.UNASSIGNED, nullable=False)

    # Foreign keys
    projectId = Column(String, ForeignKey("Project.id", ondelete="CASCADE"), nullable=False)
    parentId = Column(String, ForeignKey("Issue.id"), nullable=True)

    # Metadata
    storyPoints = Column(Integer, nullable=True)
    estimate = Column(Integer, nullable=True)  # minutes
    timeSpent = Column(Integer, nullable=True)  # minutes
    labels = Column(String, nullable=True)  # comma-separated

    # Timestamps
    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    dueDate = Column(DateTime, nullable=True)
    completedAt = Column(DateTime, nullable=True)
    deletedAt = Column(DateTime, nullable=True)  # Soft delete

    # Relationships
    project = relationship("Project", back_populates="issues")
    parent = relationship("Issue", remote_side=[id], back_populates="children")
    children = relationship("Issue", back_populates="parent")
    comments = relationship("Comment", back_populates="issue", cascade="all, delete-orphan")
    activities = relationship("Activity", back_populates="issue", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_issue_project", "projectId"),
        Index("idx_issue_parent", "parentId"),
        Index("idx_issue_status", "status"),
        Index("idx_issue_type", "type"),
    )


class Comment(Base):
    """Comment model for issue discussions."""
    __tablename__ = "Comment"

    id = Column(String, primary_key=True)
    content = Column(Text, nullable=False)
    author = Column(String, default="user", nullable=False)
    authorId = Column(String, nullable=True)

    issueId = Column(String, ForeignKey("Issue.id", ondelete="CASCADE"), nullable=False)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    editedAt = Column(DateTime, nullable=True)

    # Relationships
    issue = relationship("Issue", back_populates="comments")

    __table_args__ = (
        Index("idx_comment_issue", "issueId"),
    )


class Activity(Base):
    """Activity model for issue audit trail."""
    __tablename__ = "Activity"

    id = Column(String, primary_key=True)
    type = Column(Enum(ActivityType), nullable=False)
    field = Column(String, nullable=True)
    oldValue = Column(String, nullable=True)
    newValue = Column(String, nullable=True)
    actor = Column(String, default="user", nullable=False)

    issueId = Column(String, ForeignKey("Issue.id", ondelete="CASCADE"), nullable=False)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    issue = relationship("Issue", back_populates="activities")

    __table_args__ = (
        Index("idx_activity_issue", "issueId"),
        Index("idx_activity_type", "type"),
    )


class IssueSequence(Base):
    """Sequence model for generating issue keys."""
    __tablename__ = "IssueSequence"

    id = Column(String, primary_key=True)
    projectId = Column(String, ForeignKey("Project.id", ondelete="CASCADE"), unique=True, nullable=False)
    prefix = Column(String, nullable=False)
    nextNumber = Column(Integer, default=1, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="issueSequence")
```

**Acceptance Criteria:**
- [ ] All models match Prisma schema exactly
- [ ] Table names match Prisma conventions
- [ ] Relationships properly defined
- [ ] Indexes match Prisma indexes

**Sub-tasks:**
1. **Create base.py** - SQLAlchemy Base class
2. **Define all enums** - Match Prisma enums exactly
3. **Create Issue model** - All fields and relationships
4. **Create Comment model** - Linked to Issue
5. **Create Activity model** - Audit trail
6. **Create IssueSequence model** - Key generation
7. **Set up relationships** - Bidirectional where needed

---

### Task T2.2.2: Create Pydantic Schemas

**ID:** T2.2.2
**Story:** S2.2
**Priority:** High
**Estimated Effort:** 30 minutes

**Description:**
Create Pydantic models for API request/response validation. These schemas define the shape of data for create, update, and response operations.

**File: backend/models/schemas.py**
```python
"""Pydantic schemas for API validation."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# Enum types for API
class IssueTypeEnum(str, Enum):
    EPIC = "EPIC"
    STORY = "STORY"
    TASK = "TASK"
    SUBTASK = "SUBTASK"
    BUG = "BUG"


class IssueStatusEnum(str, Enum):
    BACKLOG = "BACKLOG"
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class PriorityEnum(str, Enum):
    LOWEST = "LOWEST"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    HIGHEST = "HIGHEST"


class AssigneeEnum(str, Enum):
    AI = "AI"
    HUMAN = "HUMAN"
    UNASSIGNED = "UNASSIGNED"


# Base schemas
class IssueBase(BaseModel):
    """Base fields shared by create and update."""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    type: IssueTypeEnum = IssueTypeEnum.TASK
    priority: PriorityEnum = PriorityEnum.MEDIUM
    assignee: AssigneeEnum = AssigneeEnum.UNASSIGNED
    parentId: Optional[str] = None
    storyPoints: Optional[int] = Field(None, ge=0, le=100)
    estimate: Optional[int] = Field(None, ge=0)  # minutes
    labels: Optional[str] = None
    dueDate: Optional[datetime] = None


class IssueCreate(IssueBase):
    """Schema for creating a new issue."""
    pass


class IssueUpdate(BaseModel):
    """Schema for updating an issue. All fields optional."""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    type: Optional[IssueTypeEnum] = None
    status: Optional[IssueStatusEnum] = None
    priority: Optional[PriorityEnum] = None
    assignee: Optional[AssigneeEnum] = None
    parentId: Optional[str] = None
    storyPoints: Optional[int] = Field(None, ge=0, le=100)
    estimate: Optional[int] = Field(None, ge=0)
    timeSpent: Optional[int] = Field(None, ge=0)
    labels: Optional[str] = None
    dueDate: Optional[datetime] = None


class IssueResponse(IssueBase):
    """Schema for issue in API responses."""
    id: str
    key: str
    status: IssueStatusEnum
    projectId: str
    timeSpent: Optional[int] = None
    createdAt: datetime
    updatedAt: datetime
    completedAt: Optional[datetime] = None

    # Counts for quick display
    commentCount: int = 0
    childCount: int = 0

    class Config:
        from_attributes = True


class IssueDetailResponse(IssueResponse):
    """Schema for full issue details including relations."""
    comments: List["CommentResponse"] = []
    activities: List["ActivityResponse"] = []
    children: List["IssueResponse"] = []
    parent: Optional["IssueResponse"] = None


# Comment schemas
class CommentCreate(BaseModel):
    """Schema for creating a comment."""
    content: str = Field(..., min_length=1, max_length=10000)


class CommentUpdate(BaseModel):
    """Schema for updating a comment."""
    content: str = Field(..., min_length=1, max_length=10000)


class CommentResponse(BaseModel):
    """Schema for comment in API responses."""
    id: str
    content: str
    author: str
    issueId: str
    createdAt: datetime
    updatedAt: datetime
    editedAt: Optional[datetime] = None

    class Config:
        from_attributes = True


# Activity schemas
class ActivityResponse(BaseModel):
    """Schema for activity in API responses."""
    id: str
    type: str
    field: Optional[str] = None
    oldValue: Optional[str] = None
    newValue: Optional[str] = None
    actor: str
    createdAt: datetime

    class Config:
        from_attributes = True


# Pagination
class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""
    items: List
    total: int
    page: int
    pageSize: int
    totalPages: int


class IssueListResponse(BaseModel):
    """Paginated list of issues."""
    items: List[IssueResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int


# Filters
class IssueFilters(BaseModel):
    """Query parameters for filtering issues."""
    type: Optional[List[IssueTypeEnum]] = None
    status: Optional[List[IssueStatusEnum]] = None
    priority: Optional[List[PriorityEnum]] = None
    assignee: Optional[List[AssigneeEnum]] = None
    parentId: Optional[str] = None
    search: Optional[str] = None
    labels: Optional[List[str]] = None


# Update forward references
IssueDetailResponse.model_rebuild()
```

**Acceptance Criteria:**
- [ ] All CRUD schemas defined
- [ ] Validation rules applied
- [ ] Response schemas include all needed fields
- [ ] Pagination schema reusable
- [ ] Filter schema comprehensive

**Sub-tasks:**
1. **Create enum types** - Match database enums
2. **Create IssueCreate schema** - Required fields for creation
3. **Create IssueUpdate schema** - All fields optional
4. **Create IssueResponse schema** - API response format
5. **Create IssueDetailResponse** - With nested relations
6. **Create Comment schemas** - Create, Update, Response
7. **Create Activity schema** - Response only (system-generated)
8. **Create pagination schemas** - Reusable wrapper

---

### Task T2.2.3: Set Up Database Connection

**ID:** T2.2.3
**Story:** S2.2
**Priority:** High
**Estimated Effort:** 30 minutes

**Description:**
Configure SQLAlchemy database connection with async support, session management, and connection pooling for the FastAPI application.

**File: backend/services/database.py**
```python
"""Database connection and session management."""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager, asynccontextmanager
from typing import AsyncGenerator, Generator

from app.config import settings
from models.base import Base

# Sync engine for migrations and simple queries
sync_engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite specific
    poolclass=StaticPool,  # Single connection pool for SQLite
    echo=settings.DEBUG,
)

# Async engine for API endpoints
async_engine = create_async_engine(
    settings.DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///"),
    connect_args={"check_same_thread": False},
    echo=settings.DEBUG,
)

# Session factories
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)

AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    class_=AsyncSession,
    expire_on_commit=False,
)


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=sync_engine)


@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    """Get synchronous database session."""
    db = SyncSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@asynccontextmanager
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI endpoints."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

**File: backend/models/base.py**
```python
"""SQLAlchemy declarative base."""

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Base class for all models."""
    pass
```

**Acceptance Criteria:**
- [ ] Sync and async engines configured
- [ ] Session management with proper cleanup
- [ ] Connection pooling appropriate for SQLite
- [ ] Dependency injection for FastAPI
- [ ] Debug logging optional

**Sub-tasks:**
1. **Create sync engine** - For migrations and simple operations
2. **Create async engine** - For API endpoints with aiosqlite
3. **Create session factories** - Both sync and async
4. **Create dependency function** - For FastAPI injection
5. **Add init_db function** - Table creation
6. **Test connection** - Verify database access

---

## Story 2.3: Implement Issue CRUD API

**ID:** S2.3
**Epic:** E2
**Priority:** Critical
**Description:** Create REST endpoints for complete issue management including create, read, update, delete operations with filtering and pagination.

---

### Task T2.3.1: GET /api/projects/{id}/issues

**ID:** T2.3.1
**Story:** S2.3
**Priority:** Critical
**Estimated Effort:** 1 hour

**Description:**
Implement the endpoint to list all issues for a project with comprehensive filtering, sorting, and pagination support.

**File: backend/api/issues.py**
```python
"""Issue API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
import math

from services.database import get_db
from models.issue import Issue, IssueStatus, IssueType, Priority, Assignee
from models.schemas import (
    IssueResponse, IssueListResponse, IssueCreate, IssueUpdate,
    IssueDetailResponse, IssueTypeEnum, IssueStatusEnum, PriorityEnum, AssigneeEnum
)

router = APIRouter(prefix="/projects/{project_id}/issues", tags=["Issues"])


@router.get("", response_model=IssueListResponse)
async def list_issues(
    project_id: str,
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    # Filters
    type: Optional[List[IssueTypeEnum]] = Query(None, description="Filter by issue types"),
    status: Optional[List[IssueStatusEnum]] = Query(None, description="Filter by statuses"),
    priority: Optional[List[PriorityEnum]] = Query(None, description="Filter by priorities"),
    assignee: Optional[List[AssigneeEnum]] = Query(None, description="Filter by assignee"),
    parent_id: Optional[str] = Query(None, description="Filter by parent issue"),
    search: Optional[str] = Query(None, description="Search in title and description"),
    labels: Optional[str] = Query(None, description="Filter by labels (comma-separated)"),
    # Sorting
    sort_by: str = Query("createdAt", description="Field to sort by"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    # Options
    include_children: bool = Query(False, description="Include child issues"),
    exclude_done: bool = Query(False, description="Exclude completed issues"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all issues for a project with filtering, sorting, and pagination.

    **Filters:**
    - `type`: Filter by one or more issue types (EPIC, STORY, TASK, SUBTASK, BUG)
    - `status`: Filter by one or more statuses
    - `priority`: Filter by one or more priorities
    - `assignee`: Filter by AI, HUMAN, or UNASSIGNED
    - `parent_id`: Show only children of specific issue
    - `search`: Full-text search in title and description
    - `labels`: Filter by labels (comma-separated)

    **Sorting:**
    - `sort_by`: Field to sort by (createdAt, updatedAt, priority, status, title)
    - `sort_order`: asc or desc

    **Pagination:**
    - `page`: Page number (starts at 1)
    - `page_size`: Items per page (1-100, default 20)
    """
    # Build base query
    query = select(Issue).where(
        Issue.projectId == project_id,
        Issue.deletedAt.is_(None)  # Exclude soft-deleted
    )

    # Apply filters
    conditions = []

    if type:
        conditions.append(Issue.type.in_([t.value for t in type]))

    if status:
        conditions.append(Issue.status.in_([s.value for s in status]))

    if priority:
        conditions.append(Issue.priority.in_([p.value for p in priority]))

    if assignee:
        conditions.append(Issue.assignee.in_([a.value for a in assignee]))

    if parent_id:
        conditions.append(Issue.parentId == parent_id)

    if search:
        search_term = f"%{search}%"
        conditions.append(or_(
            Issue.title.ilike(search_term),
            Issue.description.ilike(search_term),
            Issue.key.ilike(search_term)
        ))

    if labels:
        label_list = [l.strip() for l in labels.split(",")]
        label_conditions = [Issue.labels.contains(label) for label in label_list]
        conditions.append(or_(*label_conditions))

    if exclude_done:
        conditions.append(Issue.status != IssueStatus.DONE)

    if conditions:
        query = query.where(and_(*conditions))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply sorting
    sort_column = getattr(Issue, sort_by, Issue.createdAt)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # Execute query
    result = await db.execute(query)
    issues = result.scalars().all()

    # Build response
    items = []
    for issue in issues:
        # Get counts
        comment_count = await db.execute(
            select(func.count()).where(Comment.issueId == issue.id)
        )
        child_count = await db.execute(
            select(func.count()).where(Issue.parentId == issue.id)
        )

        item = IssueResponse(
            **issue.__dict__,
            commentCount=comment_count.scalar(),
            childCount=child_count.scalar(),
        )
        items.append(item)

    return IssueListResponse(
        items=items,
        total=total,
        page=page,
        pageSize=page_size,
        totalPages=math.ceil(total / page_size) if total > 0 else 0,
    )
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| page | int | 1 | Page number (1-indexed) |
| page_size | int | 20 | Items per page (1-100) |
| type | List[string] | null | Filter by issue types |
| status | List[string] | null | Filter by statuses |
| priority | List[string] | null | Filter by priorities |
| assignee | List[string] | null | Filter by assignee type |
| parent_id | string | null | Show children of issue |
| search | string | null | Search in title/description |
| labels | string | null | Comma-separated labels |
| sort_by | string | "createdAt" | Sort field |
| sort_order | string | "desc" | Sort direction |
| exclude_done | bool | false | Hide completed issues |

**Response Format:**
```json
{
  "items": [
    {
      "id": "clx123...",
      "key": "PM-42",
      "title": "Implement login page",
      "type": "TASK",
      "status": "IN_PROGRESS",
      "priority": "HIGH",
      "assignee": "AI",
      "commentCount": 3,
      "childCount": 2,
      "createdAt": "2024-01-15T10:00:00Z",
      "updatedAt": "2024-01-15T14:30:00Z"
    }
  ],
  "total": 45,
  "page": 1,
  "pageSize": 20,
  "totalPages": 3
}
```

**Acceptance Criteria:**
- [ ] Returns paginated list of issues
- [ ] All filters work correctly
- [ ] Sorting works on all specified fields
- [ ] Search finds matches in title and description
- [ ] Soft-deleted issues excluded
- [ ] Performance acceptable with 1000+ issues

**Sub-tasks:**
1. **Create base query** - Select from Issue with project filter
2. **Implement type filter** - Filter by issue types
3. **Implement status filter** - Filter by statuses
4. **Implement priority filter** - Filter by priorities
5. **Implement assignee filter** - Filter by AI/Human/Unassigned
6. **Implement parent filter** - Show children of specific issue
7. **Implement search** - Full-text search in title/description
8. **Implement label filter** - Filter by comma-separated labels
9. **Add pagination** - Offset-based with total count
10. **Add sorting** - Multiple fields, asc/desc
11. **Add counts** - Comment count, child count per issue

---

### Task T2.3.2: POST /api/projects/{id}/issues

**ID:** T2.3.2
**Story:** S2.3
**Priority:** Critical
**Estimated Effort:** 45 minutes

**Description:**
Implement the endpoint to create a new issue with automatic key generation, validation, and activity logging.

**Implementation:**
```python
@router.post("", response_model=IssueResponse, status_code=201)
async def create_issue(
    project_id: str,
    issue_data: IssueCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new issue in the project.

    **Auto-generated fields:**
    - `id`: Unique CUID
    - `key`: Project-specific key (e.g., "PM-123")
    - `status`: Defaults to BACKLOG
    - `createdAt`, `updatedAt`: Timestamps

    **Validation:**
    - Title is required (1-500 chars)
    - Parent must exist if parentId provided
    - Parent must be valid type (Epic→Story, Story→Task, Task→Subtask)
    """
    # Verify project exists
    project = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    if not project.scalar():
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate parent if provided
    if issue_data.parentId:
        parent = await db.execute(
            select(Issue).where(Issue.id == issue_data.parentId)
        )
        parent_issue = parent.scalar()
        if not parent_issue:
            raise HTTPException(status_code=400, detail="Parent issue not found")

        # Validate hierarchy (Epic→Story→Task→Subtask)
        valid_parent_types = {
            IssueType.STORY: [IssueType.EPIC],
            IssueType.TASK: [IssueType.STORY, IssueType.EPIC],
            IssueType.SUBTASK: [IssueType.TASK],
            IssueType.BUG: [IssueType.EPIC, IssueType.STORY],
        }
        if issue_data.type in valid_parent_types:
            if parent_issue.type not in valid_parent_types[issue_data.type]:
                raise HTTPException(
                    status_code=400,
                    detail=f"{issue_data.type} cannot have {parent_issue.type} as parent"
                )

    # Generate issue key
    issue_key = await generate_issue_key(project_id, db)

    # Create issue
    issue = Issue(
        id=generate_cuid(),
        key=issue_key,
        projectId=project_id,
        title=issue_data.title,
        description=issue_data.description,
        type=issue_data.type,
        status=IssueStatus.BACKLOG,
        priority=issue_data.priority,
        assignee=issue_data.assignee,
        parentId=issue_data.parentId,
        storyPoints=issue_data.storyPoints,
        estimate=issue_data.estimate,
        labels=issue_data.labels,
        dueDate=issue_data.dueDate,
    )

    db.add(issue)

    # Log activity
    activity = Activity(
        id=generate_cuid(),
        type=ActivityType.CREATED,
        issueId=issue.id,
        actor="user",
        newValue=f"Created {issue.type.value} '{issue.title}'",
    )
    db.add(activity)

    await db.commit()
    await db.refresh(issue)

    return IssueResponse(**issue.__dict__, commentCount=0, childCount=0)


async def generate_issue_key(project_id: str, db: AsyncSession) -> str:
    """Generate the next issue key for a project."""
    # Get or create sequence
    result = await db.execute(
        select(IssueSequence).where(IssueSequence.projectId == project_id)
    )
    sequence = result.scalar()

    if not sequence:
        # Get project for prefix
        project_result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = project_result.scalar()

        # Generate prefix from project name (first letters, max 4)
        prefix = "".join(word[0].upper() for word in project.name.split()[:4])
        if len(prefix) < 2:
            prefix = project.name[:3].upper()

        sequence = IssueSequence(
            id=generate_cuid(),
            projectId=project_id,
            prefix=prefix,
            nextNumber=1,
        )
        db.add(sequence)
        await db.flush()

    # Atomic increment
    key = f"{sequence.prefix}-{sequence.nextNumber}"
    sequence.nextNumber += 1

    return key
```

**Request Body:**
```json
{
  "title": "Implement user authentication",
  "description": "Add login and registration functionality...",
  "type": "STORY",
  "priority": "HIGH",
  "assignee": "AI",
  "parentId": "clx-epic-id",
  "storyPoints": 5,
  "labels": "auth,security",
  "dueDate": "2024-02-01T00:00:00Z"
}
```

**Response:** Created issue with generated key

**Acceptance Criteria:**
- [ ] Issue created with auto-generated ID and key
- [ ] Key follows project sequence (PM-1, PM-2...)
- [ ] Activity logged for creation
- [ ] Parent validation enforces hierarchy
- [ ] Returns 201 with created issue

**Sub-tasks:**
1. **Validate project exists** - 404 if not found
2. **Validate parent issue** - If parentId provided
3. **Enforce hierarchy rules** - Epic→Story→Task→Subtask
4. **Generate issue key** - From sequence
5. **Create issue record** - With all fields
6. **Log creation activity** - For audit trail
7. **Return created issue** - With 201 status

---

### Task T2.3.3: GET /api/issues/{id}

**ID:** T2.3.3
**Story:** S2.3
**Priority:** High
**Estimated Effort:** 30 minutes

**Description:**
Implement endpoint to get full issue details including comments, activities, and related issues.

**Implementation:**
```python
@router.get("/{issue_id}", response_model=IssueDetailResponse)
async def get_issue(
    issue_id: str,
    include_comments: bool = Query(True, description="Include comments"),
    include_activities: bool = Query(True, description="Include activity log"),
    include_children: bool = Query(True, description="Include child issues"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get full details for a single issue.

    **Includes:**
    - Issue data with all fields
    - Comments (if include_comments=true)
    - Activity log (if include_activities=true)
    - Child issues (if include_children=true)
    - Parent issue reference
    """
    # Fetch issue with relationships
    query = select(Issue).where(
        Issue.id == issue_id,
        Issue.deletedAt.is_(None)
    )

    if include_comments:
        query = query.options(selectinload(Issue.comments))

    if include_activities:
        query = query.options(selectinload(Issue.activities))

    if include_children:
        query = query.options(selectinload(Issue.children))

    result = await db.execute(query)
    issue = result.scalar()

    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    # Get parent if exists
    parent = None
    if issue.parentId:
        parent_result = await db.execute(
            select(Issue).where(Issue.id == issue.parentId)
        )
        parent = parent_result.scalar()

    # Build response
    response_data = {
        **issue.__dict__,
        "commentCount": len(issue.comments) if include_comments else 0,
        "childCount": len(issue.children) if include_children else 0,
        "comments": [CommentResponse(**c.__dict__) for c in issue.comments] if include_comments else [],
        "activities": sorted(
            [ActivityResponse(**a.__dict__) for a in issue.activities],
            key=lambda x: x.createdAt,
            reverse=True
        ) if include_activities else [],
        "children": [IssueResponse(**c.__dict__, commentCount=0, childCount=0) for c in issue.children] if include_children else [],
        "parent": IssueResponse(**parent.__dict__, commentCount=0, childCount=0) if parent else None,
    }

    return IssueDetailResponse(**response_data)
```

**Acceptance Criteria:**
- [ ] Returns full issue details
- [ ] Comments included and sorted by date
- [ ] Activities included and sorted (newest first)
- [ ] Children included if requested
- [ ] Parent reference included
- [ ] 404 for non-existent or deleted issues

**Sub-tasks:**
1. **Fetch issue by ID** - With soft-delete check
2. **Load comments** - Optionally with selectinload
3. **Load activities** - Sorted by createdAt desc
4. **Load children** - Direct child issues
5. **Load parent** - If parentId exists
6. **Build response** - Combine all data

---

### Task T2.3.4: PATCH /api/issues/{id}

**ID:** T2.3.4
**Story:** S2.3
**Priority:** High
**Estimated Effort:** 45 minutes

**Description:**
Implement endpoint to update issue fields with change tracking and activity logging.

**Implementation:**
```python
@router.patch("/{issue_id}", response_model=IssueResponse)
async def update_issue(
    issue_id: str,
    updates: IssueUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update an issue with partial data.

    **Features:**
    - Partial updates (only provided fields)
    - Activity logging for each change
    - Automatic completedAt timestamp when status→DONE
    - Validation of parent hierarchy on parentId change
    """
    # Fetch issue
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id, Issue.deletedAt.is_(None))
    )
    issue = result.scalar()

    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    # Track changes for activity log
    changes = []
    update_data = updates.model_dump(exclude_unset=True)

    for field, new_value in update_data.items():
        old_value = getattr(issue, field)

        # Skip if no change
        if old_value == new_value:
            continue

        # Validate parent change
        if field == "parentId" and new_value:
            parent_result = await db.execute(
                select(Issue).where(Issue.id == new_value)
            )
            if not parent_result.scalar():
                raise HTTPException(status_code=400, detail="Parent issue not found")

        # Track change
        changes.append({
            "field": field,
            "old": str(old_value) if old_value else None,
            "new": str(new_value) if new_value else None,
        })

        # Apply change
        setattr(issue, field, new_value)

    # Handle status change to DONE
    if "status" in update_data and update_data["status"] == IssueStatus.DONE:
        issue.completedAt = datetime.utcnow()
    elif "status" in update_data and update_data["status"] != IssueStatus.DONE:
        issue.completedAt = None

    # Log activities
    for change in changes:
        activity_type = ActivityType.STATUS_CHANGED
        if change["field"] == "status":
            activity_type = ActivityType.STATUS_CHANGED
        elif change["field"] == "priority":
            activity_type = ActivityType.PRIORITY_CHANGED
        elif change["field"] == "assignee":
            activity_type = ActivityType.ASSIGNEE_CHANGED
        elif change["field"] == "title":
            activity_type = ActivityType.TITLE_UPDATED
        elif change["field"] == "description":
            activity_type = ActivityType.DESCRIPTION_UPDATED
        elif change["field"] == "parentId":
            activity_type = ActivityType.PARENT_CHANGED
        elif change["field"] == "labels":
            activity_type = ActivityType.LABELS_CHANGED
        elif change["field"] == "estimate":
            activity_type = ActivityType.ESTIMATE_CHANGED
        elif change["field"] == "dueDate":
            activity_type = ActivityType.DUE_DATE_CHANGED

        activity = Activity(
            id=generate_cuid(),
            type=activity_type,
            field=change["field"],
            oldValue=change["old"],
            newValue=change["new"],
            issueId=issue.id,
            actor="user",
        )
        db.add(activity)

    issue.updatedAt = datetime.utcnow()
    await db.commit()
    await db.refresh(issue)

    # Get counts for response
    comment_count = await db.execute(
        select(func.count()).where(Comment.issueId == issue.id)
    )
    child_count = await db.execute(
        select(func.count()).where(Issue.parentId == issue.id)
    )

    return IssueResponse(
        **issue.__dict__,
        commentCount=comment_count.scalar(),
        childCount=child_count.scalar(),
    )
```

**Acceptance Criteria:**
- [ ] Partial updates work correctly
- [ ] Activity logged for each changed field
- [ ] completedAt set/cleared based on status
- [ ] Parent validation on change
- [ ] Returns updated issue

**Sub-tasks:**
1. **Fetch existing issue** - 404 if not found/deleted
2. **Compare old vs new values** - Only track actual changes
3. **Validate parent change** - If parentId updated
4. **Log activity per field** - With appropriate type
5. **Handle DONE status** - Set completedAt timestamp
6. **Update timestamp** - Touch updatedAt
7. **Return updated issue** - With counts

---

### Task T2.3.5: DELETE /api/issues/{id}

**ID:** T2.3.5
**Story:** S2.3
**Priority:** Medium
**Estimated Effort:** 20 minutes

**Description:**
Implement soft delete for issues with optional cascade to children.

**Implementation:**
```python
@router.delete("/{issue_id}", status_code=204)
async def delete_issue(
    issue_id: str,
    cascade: bool = Query(False, description="Also delete child issues"),
    hard_delete: bool = Query(False, description="Permanently delete (admin only)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete an issue (soft delete by default).

    **Options:**
    - `cascade`: Also delete all child issues
    - `hard_delete`: Permanently remove from database (use with caution)

    **Soft Delete:**
    - Sets deletedAt timestamp
    - Issue hidden from queries
    - Can be restored later

    **Hard Delete:**
    - Permanently removes issue and all related data
    - Cannot be undone
    """
    # Fetch issue
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = result.scalar()

    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    if hard_delete:
        # Permanent deletion
        if cascade:
            # Delete all descendants recursively
            await delete_children_recursive(issue.id, db, hard=True)
        await db.delete(issue)
    else:
        # Soft delete
        issue.deletedAt = datetime.utcnow()
        if cascade:
            await delete_children_recursive(issue.id, db, hard=False)

    await db.commit()
    return None


async def delete_children_recursive(parent_id: str, db: AsyncSession, hard: bool):
    """Recursively delete/soft-delete child issues."""
    result = await db.execute(
        select(Issue).where(Issue.parentId == parent_id)
    )
    children = result.scalars().all()

    for child in children:
        await delete_children_recursive(child.id, db, hard)
        if hard:
            await db.delete(child)
        else:
            child.deletedAt = datetime.utcnow()
```

**Acceptance Criteria:**
- [ ] Soft delete sets deletedAt
- [ ] Hard delete removes record
- [ ] Cascade option deletes children
- [ ] Returns 204 No Content
- [ ] 404 for non-existent issues

**Sub-tasks:**
1. **Fetch issue** - Handle not found
2. **Implement soft delete** - Set deletedAt timestamp
3. **Implement hard delete** - Actually remove from DB
4. **Cascade to children** - Recursive deletion
5. **Return 204** - No content on success

---

### Task T2.3.6: POST /api/issues/{id}/comments

**ID:** T2.3.6
**Story:** S2.3
**Priority:** High
**Estimated Effort:** 20 minutes

**Description:**
Implement endpoint to add comments to an issue with activity logging.

**Implementation:**
```python
@router.post("/{issue_id}/comments", response_model=CommentResponse, status_code=201)
async def add_comment(
    issue_id: str,
    comment_data: CommentCreate,
    author: str = Query("user", description="Comment author (user or ai)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a comment to an issue.

    **Authors:**
    - `user`: Human user comment
    - `ai`: AI-generated comment
    """
    # Verify issue exists
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id, Issue.deletedAt.is_(None))
    )
    issue = result.scalar()

    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    # Create comment
    comment = Comment(
        id=generate_cuid(),
        content=comment_data.content,
        author=author,
        issueId=issue_id,
    )
    db.add(comment)

    # Log activity
    activity = Activity(
        id=generate_cuid(),
        type=ActivityType.COMMENT_ADDED,
        issueId=issue_id,
        actor=author,
        newValue=f"Added comment: {comment_data.content[:100]}...",
    )
    db.add(activity)

    # Update issue timestamp
    issue.updatedAt = datetime.utcnow()

    await db.commit()
    await db.refresh(comment)

    return CommentResponse(**comment.__dict__)
```

**Acceptance Criteria:**
- [ ] Comment created and linked to issue
- [ ] Activity logged for comment
- [ ] Issue updatedAt touched
- [ ] Returns 201 with comment

**Sub-tasks:**
1. **Verify issue exists** - 404 if not found
2. **Create comment** - With content and author
3. **Log activity** - COMMENT_ADDED type
4. **Update issue timestamp** - Touch updatedAt
5. **Return comment** - With 201 status

---

## Story 2.4: Issue Sequence Generation

**ID:** S2.4
**Epic:** E2
**Priority:** High
**Description:** Implement automatic issue key generation with project-specific sequences.

*(Covered in T2.3.2 - generate_issue_key function)*

---

## Story 2.5: API Proxy Routes

**ID:** S2.5
**Epic:** E2
**Priority:** Medium
**Description:** Create Next.js API routes that proxy requests to the FastAPI backend.

---

### Task T2.5.1: Create /api/codeboard/[...path] Catch-all

**ID:** T2.5.1
**Story:** S2.5
**Priority:** Medium
**Estimated Effort:** 30 minutes

**Description:**
Create a Next.js catch-all API route that proxies all CodeBoard requests to the FastAPI backend.

**File: frontend/app/api/codeboard/[...path]/route.ts**
```typescript
/**
 * Proxy route for CodeBoard API requests to FastAPI backend.
 * All requests to /api/codeboard/* are forwarded to the backend.
 */

import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8401';

async function proxyRequest(
  request: NextRequest,
  path: string[]
): Promise<NextResponse> {
  const targetPath = path.join('/');
  const targetUrl = `${BACKEND_URL}/api/${targetPath}`;

  // Forward query parameters
  const searchParams = request.nextUrl.searchParams.toString();
  const fullUrl = searchParams ? `${targetUrl}?${searchParams}` : targetUrl;

  try {
    // Get request body for non-GET requests
    let body: string | undefined;
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      body = await request.text();
    }

    // Forward headers (except host)
    const headers = new Headers(request.headers);
    headers.delete('host');
    headers.set('Content-Type', 'application/json');

    // Make request to backend
    const response = await fetch(fullUrl, {
      method: request.method,
      headers,
      body,
    });

    // Get response data
    const data = await response.text();

    // Return proxied response
    return new NextResponse(data, {
      status: response.status,
      statusText: response.statusText,
      headers: {
        'Content-Type': response.headers.get('Content-Type') || 'application/json',
      },
    });
  } catch (error) {
    console.error('Proxy error:', error);
    return NextResponse.json(
      { error: 'Failed to connect to backend' },
      { status: 502 }
    );
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path);
}

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path);
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path);
}
```

**Acceptance Criteria:**
- [ ] All HTTP methods proxied
- [ ] Query parameters forwarded
- [ ] Request body forwarded
- [ ] Response status preserved
- [ ] Error handling for backend unavailable

**Sub-tasks:**
1. **Create catch-all route** - [...path] pattern
2. **Implement proxy function** - Forward request to backend
3. **Handle all HTTP methods** - GET, POST, PATCH, PUT, DELETE
4. **Forward query params** - Preserve search params
5. **Forward request body** - For POST/PATCH/PUT
6. **Handle errors** - 502 if backend unreachable

---

# Continue with remaining Epics in PART3...

Due to document length, Epics 3-7 continue in:
- `IMPLEMENTATION_PLAN_DETAILED_PART3.md` - Epic 3: CodeBoard UI
- `IMPLEMENTATION_PLAN_DETAILED_PART4.md` - Epics 4-7: RAG, AI, Git, Polish
