"""
Issue CRUD API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime
import uuid
import logging
import asyncio

from models import (
    get_db,
    AsyncSessionLocal,
    Issue,
    Comment,
    Activity,
    IssueSequence,
    IssueCreate,
    IssueUpdate,
    IssueResponse,
    IssueWithChildren,
    CommentCreate,
    CommentResponse,
    ActivityResponse,
    PaginatedResponse,
    BatchStatusUpdate,
    IssueStatus,
)
from models.qa import QATask, QATaskIssueLink, QASequence
from services.rag_service import rag_service
from services.qa_service import qa_service
from app.errors import NotFoundError, DatabaseError, ValidationError
from utils.db_queries import cascade_status_to_parents, cascade_done_to_parents, get_all_descendants_with_details

logger = logging.getLogger(__name__)

router = APIRouter()


# Helper function to embed issue for RAG
async def embed_issue_for_rag(issue: Issue):
    """Embed issue into vector store for semantic search"""
    try:
        await rag_service.embed_issue(
            project_id=issue.projectId,
            issue_id=issue.id,
            key=issue.key,
            title=issue.title,
            description=issue.description,
            issue_type=issue.type,
            status=issue.status,
            labels=issue.labels,
        )
    except Exception as e:
        # Don't fail the request if embedding fails, but log it
        logger.warning(f"Failed to embed issue {issue.key} for RAG search: {e}")


# Helper function to trigger async QA generation (CB-566)
async def trigger_qa_generation(issue_id: str, issue_key: str, project_id: str):
    """
    Trigger asynchronous QA plan generation for an issue.

    This is called when an issue status changes to COMPLETED_WAITING_QA.
    It runs in the background and doesn't block the status change response.
    """
    logger.info(f"Starting async QA generation for issue {issue_key}")

    try:
        # Create a new database session for the background task
        async with AsyncSessionLocal() as db:
            # Get the issue with its children
            result = await db.execute(
                select(Issue)
                .where(Issue.id == issue_id)
                .options(selectinload(Issue.children))
            )
            issue = result.scalar_one_or_none()

            if not issue:
                logger.warning(f"Issue {issue_key} not found for QA generation")
                return

            # Get children context
            children = [
                {"id": c.id, "title": c.title, "type": c.type, "status": c.status}
                for c in (issue.children or [])
            ]

            # Generate QA plan using AI
            logger.info(f"Calling qa_service.generate_qa_plan for {issue_key}")
            qa_suggestions = await qa_service.generate_qa_plan(
                project_id=issue.projectId,
                issue_id=issue.id,
                issue_title=issue.title,
                issue_description=issue.description,
                issue_type=issue.type,
                children=children,
            )

            if not qa_suggestions:
                logger.info(f"No QA tasks generated for issue {issue_key}")
                return

            # Create QA tasks in the database
            created_keys = []
            for suggestion in qa_suggestions:
                # Get next QA task key
                result = await db.execute(
                    select(QASequence).where(QASequence.projectId == project_id)
                )
                sequence = result.scalar_one_or_none()

                if not sequence:
                    sequence = QASequence(
                        id=str(uuid.uuid4()),
                        projectId=project_id,
                        prefix="QA",
                        lastNumber=0,
                    )
                    db.add(sequence)

                sequence.lastNumber += 1
                qa_key = f"{sequence.prefix}-{sequence.lastNumber}"

                # Handle scenario as list or string
                scenario = suggestion.get('scenario', '')
                if isinstance(scenario, list):
                    scenario = '\n'.join(scenario)

                # Handle expectedResult as list or string
                expected_result = suggestion.get('expectedResult', '')
                if isinstance(expected_result, list):
                    expected_result = '\n'.join(expected_result)

                # Create QA task
                task = QATask(
                    id=str(uuid.uuid4()),
                    projectId=project_id,
                    key=qa_key,
                    sequence=sequence.lastNumber,
                    title=suggestion.get('title', 'Unnamed test'),
                    scenario=scenario,
                    expectedResult=expected_result,
                    status="NOT_DONE",
                    type=suggestion.get('type', 'AUTOMATED'),
                    priority=suggestion.get('priority', 'MEDIUM'),
                    createdAt=datetime.utcnow(),
                    updatedAt=datetime.utcnow(),
                )
                db.add(task)

                # Link QA task to the issue
                link = QATaskIssueLink(
                    id=str(uuid.uuid4()),
                    qaTaskId=task.id,
                    issueId=issue.id,
                )
                db.add(link)

                created_keys.append(qa_key)

            await db.commit()
            logger.info(f"Created {len(created_keys)} QA tasks for issue {issue_key}: {created_keys}")

    except Exception as e:
        # Log but don't propagate - this is a background task
        logger.error(f"Failed to generate QA tasks for issue {issue_key}: {e}")


# Helper function to generate issue key
async def get_next_issue_key(db: AsyncSession, project_id: str) -> tuple[str, int]:
    """Get the next issue key for a project"""
    result = await db.execute(
        select(IssueSequence).where(IssueSequence.projectId == project_id)
    )
    sequence = result.scalar_one_or_none()

    if not sequence:
        # Create new sequence with project name prefix
        # For now, use first 4 chars of project_id as prefix
        prefix = project_id[:4].upper()
        sequence = IssueSequence(
            id=str(uuid.uuid4()),
            projectId=project_id,
            prefix=prefix,
            lastNumber=0,
        )
        db.add(sequence)

    sequence.lastNumber += 1
    next_number = sequence.lastNumber
    key = f"{sequence.prefix}-{next_number}"

    await db.commit()
    return key, next_number


# Helper function to create activity log
async def log_activity(
    db: AsyncSession,
    issue_id: str,
    actor: str,
    action: str,
    field: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
):
    """Create an activity log entry"""
    activity = Activity(
        id=str(uuid.uuid4()),
        issueId=issue_id,
        actor=actor,
        action=action,
        field=field,
        oldValue=old_value,
        newValue=new_value,
    )
    db.add(activity)


# GET /api/projects/{project_id}/issues - List issues for a project
@router.get("/projects/{project_id}/issues", response_model=PaginatedResponse)
async def list_project_issues(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000, alias="pageSize"),
    status: Optional[str] = None,
    type: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    parent_id: Optional[str] = None,
    search: Optional[str] = None,
    label: Optional[str] = None,
    breakdown_batch_id: Optional[str] = Query(None, alias="breakdownBatchId"),
    db: AsyncSession = Depends(get_db),
):
    """List all issues for a project with filtering and pagination"""
    # Build query
    query = select(Issue).where(Issue.projectId == project_id)

    # Apply filters
    if status:
        query = query.where(Issue.status == status)
    if type:
        query = query.where(Issue.type == type)
    if priority:
        query = query.where(Issue.priority == priority)
    if assignee:
        query = query.where(Issue.assignee == assignee)
    if parent_id:
        query = query.where(Issue.parentId == parent_id)
    if label:
        # Filter by label (stored as JSON array string like '["label1", "label2"]')
        query = query.where(Issue.labels.ilike(f'%"{label}"%'))
    if breakdown_batch_id:
        query = query.where(Issue.breakdownBatchId == breakdown_batch_id)
    if search:
        search_filter = or_(
            Issue.title.ilike(f"%{search}%"),
            Issue.key.ilike(f"%{search}%"),
            Issue.description.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Issue.sequence.desc())

    # Execute query
    result = await db.execute(query)
    issues = result.scalars().all()

    return PaginatedResponse(
        items=[IssueResponse.model_validate(issue) for issue in issues],
        total=total,
        page=page,
        pageSize=page_size,
        totalPages=(total + page_size - 1) // page_size,
    )


# POST /api/projects/{project_id}/issues - Create a new issue
@router.post("/projects/{project_id}/issues", response_model=IssueResponse, status_code=201)
async def create_issue(
    project_id: str,
    issue_data: IssueCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new issue in a project"""
    # Generate issue key
    key, sequence = await get_next_issue_key(db, project_id)

    # Create issue
    issue = Issue(
        id=str(uuid.uuid4()),
        projectId=project_id,
        key=key,
        sequence=sequence,
        title=issue_data.title,
        description=issue_data.description,
        type=issue_data.type.value,
        status=issue_data.status.value,
        priority=issue_data.priority.value,
        parentId=issue_data.parentId,
        assignee=issue_data.assignee,
        reporter=issue_data.reporter or "System",
        storyPoints=issue_data.storyPoints,
        estimate=issue_data.estimate,
        dueDate=issue_data.dueDate,
        labels=issue_data.labels,
        breakdownBatchId=issue_data.breakdownBatchId,
        updatedAt=datetime.utcnow(),
    )
    db.add(issue)

    # Log activity
    await log_activity(db, issue.id, issue.reporter or "System", "CREATED")

    await db.commit()
    await db.refresh(issue)

    # Embed for RAG search
    await embed_issue_for_rag(issue)

    return IssueResponse.model_validate(issue)


# GET /api/issues/{issue_id} - Get a single issue
@router.get("/issues/{issue_id}", response_model=IssueWithChildren)
async def get_issue(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single issue by ID with its children"""
    result = await db.execute(
        select(Issue)
        .options(selectinload(Issue.children))
        .where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()

    if not issue:
        raise NotFoundError("Issue", issue_id)

    response = IssueWithChildren.model_validate(issue)
    response.children = [IssueResponse.model_validate(child) for child in issue.children]
    return response


# PATCH /api/issues/{issue_id} - Update an issue
@router.patch("/issues/{issue_id}", response_model=IssueResponse)
async def update_issue(
    issue_id: str,
    issue_data: IssueUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an issue"""
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()

    if not issue:
        raise NotFoundError("Issue", issue_id)

    # Track changes for activity log
    update_data = issue_data.model_dump(exclude_unset=True)

    for field, new_value in update_data.items():
        old_value = getattr(issue, field)

        # Handle enum values
        if hasattr(new_value, "value"):
            new_value = new_value.value

        if old_value != new_value:
            # Log status changes specially
            if field == "status":
                await log_activity(
                    db, issue_id, "System", "STATUS_CHANGED",
                    field, str(old_value), str(new_value)
                )
                # Auto-set timestamps
                if new_value == IssueStatus.IN_PROGRESS.value and not issue.startedAt:
                    issue.startedAt = datetime.utcnow()
                elif new_value == IssueStatus.DONE.value:
                    issue.completedAt = datetime.utcnow()

                # Detect status change to COMPLETED_WAITING_QA for QA hook (CB-566)
                if new_value == IssueStatus.COMPLETED_WAITING_QA.value:
                    logger.info(f"Issue {issue.key} status changed to COMPLETED_WAITING_QA - triggering async QA generation")
                    # Fire-and-forget async QA generation
                    asyncio.create_task(trigger_qa_generation(issue.id, issue.key, issue.projectId))
            else:
                await log_activity(
                    db, issue_id, "System", "UPDATED",
                    field, str(old_value) if old_value else None, str(new_value)
                )

            setattr(issue, field, new_value)

    issue.updatedAt = datetime.utcnow()

    # Cascade status to parent containers if this is a work item
    # (when TASK/SUBTASK becomes COMPLETED_WAITING_QA or DONE, update parent STORY/EPIC)
    if "status" in update_data:
        new_status = update_data["status"]
        if hasattr(new_status, "value"):
            new_status = new_status.value

        if new_status == "COMPLETED_WAITING_QA":
            updated_parents = await cascade_status_to_parents(db, issue_id, "COMPLETED_WAITING_QA")
            if updated_parents:
                logger.info(f"Cascaded COMPLETED_WAITING_QA to {len(updated_parents)} parent(s)")
        elif new_status == "DONE":
            updated_parents = await cascade_done_to_parents(db, issue_id)
            if updated_parents:
                logger.info(f"Cascaded DONE to {len(updated_parents)} parent(s)")

    await db.commit()
    await db.refresh(issue)

    # Re-embed for RAG search
    await embed_issue_for_rag(issue)

    return IssueResponse.model_validate(issue)


# DELETE /api/issues/{issue_id} - Delete an issue
@router.delete("/issues/{issue_id}", status_code=204)
async def delete_issue(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete an issue"""
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()

    if not issue:
        raise NotFoundError("Issue", issue_id)

    project_id = issue.projectId

    await db.delete(issue)
    await db.commit()

    # Remove from RAG store
    try:
        await rag_service.delete_issue_embedding(project_id, issue_id)
    except Exception as e:
        logger.warning(f"Failed to delete RAG embedding for issue {issue_id}: {e}")


# POST /api/issues/{issue_id}/comments - Add a comment
@router.post("/issues/{issue_id}/comments", response_model=CommentResponse, status_code=201)
async def add_comment(
    issue_id: str,
    comment_data: CommentCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to an issue"""
    # Verify issue exists
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()

    if not issue:
        raise NotFoundError("Issue", issue_id)

    # Create comment
    comment = Comment(
        id=str(uuid.uuid4()),
        issueId=issue_id,
        author=comment_data.author,
        content=comment_data.content,
        updatedAt=datetime.utcnow(),
    )
    db.add(comment)

    # Log activity
    await log_activity(db, issue_id, comment_data.author, "COMMENTED")

    # Update issue timestamp
    issue.updatedAt = datetime.utcnow()

    await db.commit()
    await db.refresh(comment)

    return CommentResponse.model_validate(comment)


# GET /api/issues/{issue_id}/comments - Get comments for an issue
@router.get("/issues/{issue_id}/comments", response_model=List[CommentResponse])
async def get_comments(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all comments for an issue"""
    result = await db.execute(
        select(Comment)
        .where(Comment.issueId == issue_id)
        .order_by(Comment.createdAt.desc())
    )
    comments = result.scalars().all()

    return [CommentResponse.model_validate(comment) for comment in comments]


# GET /api/issues/{issue_id}/activities - Get activity log for an issue
@router.get("/issues/{issue_id}/activities", response_model=List[ActivityResponse])
async def get_activities(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get activity log for an issue"""
    result = await db.execute(
        select(Activity)
        .where(Activity.issueId == issue_id)
        .order_by(Activity.createdAt.desc())
    )
    activities = result.scalars().all()

    return [ActivityResponse.model_validate(activity) for activity in activities]


# POST /api/issues/batch/status - Batch update issue status
@router.post("/issues/batch/status", response_model=List[IssueResponse])
async def batch_update_status(
    batch_data: BatchStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Batch update status for multiple issues (e.g., drag-drop on Kanban)"""
    result = await db.execute(
        select(Issue).where(Issue.id.in_(batch_data.issueIds))
    )
    issues = result.scalars().all()

    updated_issues = []
    for issue in issues:
        old_status = issue.status
        new_status = batch_data.status.value

        if old_status != new_status:
            issue.status = new_status
            issue.updatedAt = datetime.utcnow()

            # Auto-set timestamps
            if new_status == IssueStatus.IN_PROGRESS.value and not issue.startedAt:
                issue.startedAt = datetime.utcnow()
            elif new_status == IssueStatus.DONE.value:
                issue.completedAt = datetime.utcnow()

            # Detect status change to COMPLETED_WAITING_QA for QA hook (CB-566)
            if new_status == IssueStatus.COMPLETED_WAITING_QA.value:
                logger.info(f"Issue {issue.key} status changed to COMPLETED_WAITING_QA - triggering async QA generation")
                # Fire-and-forget async QA generation
                asyncio.create_task(trigger_qa_generation(issue.id, issue.key, issue.projectId))

            await log_activity(
                db, issue.id, "System", "STATUS_CHANGED",
                "status", old_status, new_status
            )

            # Cascade to parent containers
            if new_status == IssueStatus.COMPLETED_WAITING_QA.value:
                await cascade_status_to_parents(db, issue.id, "COMPLETED_WAITING_QA")
            elif new_status == IssueStatus.DONE.value:
                await cascade_done_to_parents(db, issue.id)

        updated_issues.append(issue)

    await db.commit()

    return [IssueResponse.model_validate(issue) for issue in updated_issues]


# POST /api/issues/{issue_id}/log-breakdown-spec - Log original AI breakdown specification
@router.post("/issues/{issue_id}/log-breakdown-spec")
async def log_breakdown_specification(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    original_spec: str = Query(..., description="Original specification used for AI breakdown"),
):
    """
    Log the original specification used for AI breakdown.
    This creates an audit trail so users can see what they originally requested.
    """
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()

    if not issue:
        raise NotFoundError("Issue", issue_id)

    # Log the original specification as an activity
    await log_activity(
        db,
        issue_id,
        "AI",
        "BREAKDOWN_SPEC",
        field="original_specification",
        old_value=None,
        new_value=original_spec,
    )

    await db.commit()

    return {"success": True, "message": "Breakdown specification logged"}


# GET /api/projects/{project_id}/labels - Get all unique labels for a project
@router.get("/projects/{project_id}/labels")
async def get_project_labels(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all unique labels used in a project for filtering"""
    import json

    result = await db.execute(
        select(Issue.labels)
        .where(Issue.projectId == project_id)
        .where(Issue.labels.isnot(None))
        .distinct()
    )
    label_strings = result.scalars().all()

    # Parse JSON arrays and collect unique labels
    unique_labels = set()
    for label_str in label_strings:
        if label_str:
            try:
                labels = json.loads(label_str)
                if isinstance(labels, list):
                    unique_labels.update(labels)
            except json.JSONDecodeError:
                # If not valid JSON, treat as single label
                unique_labels.add(label_str)

    return {"labels": sorted(list(unique_labels))}


# POST /api/issues/batch/labels - Batch add labels to multiple issues
@router.post("/issues/batch/labels")
async def batch_add_labels(
    issue_ids: List[str] = Query(..., description="Issue IDs to update"),
    labels_to_add: List[str] = Query(..., description="Labels to add", alias="labels"),
    breakdown_batch_id: Optional[str] = Query(None, description="Optional batch ID to set", alias="breakdownBatchId"),
    db: AsyncSession = Depends(get_db),
):
    """Batch add labels to multiple issues"""
    import json

    result = await db.execute(
        select(Issue).where(Issue.id.in_(issue_ids))
    )
    issues = result.scalars().all()

    updated_count = 0
    for issue in issues:
        # Parse existing labels
        existing_labels = []
        if issue.labels:
            try:
                existing_labels = json.loads(issue.labels)
            except json.JSONDecodeError:
                existing_labels = [issue.labels]

        # Add new labels (avoid duplicates)
        for label in labels_to_add:
            if label not in existing_labels:
                existing_labels.append(label)

        # Update issue
        issue.labels = json.dumps(existing_labels)
        if breakdown_batch_id:
            issue.breakdownBatchId = breakdown_batch_id
        issue.updatedAt = datetime.utcnow()

        # Log activity
        await log_activity(
            db, issue.id, "System", "UPDATED",
            field="labels", old_value=None, new_value=json.dumps(labels_to_add)
        )

        updated_count += 1

    await db.commit()

    return {"success": True, "updated_count": updated_count}


# GET /api/issues/{issue_id}/descendants - Get all descendants of an issue
@router.get("/issues/{issue_id}/descendants", response_model=List[IssueResponse])
async def get_issue_descendants(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all descendants (children, grandchildren, etc.) of an issue.

    This is used by the Feature Execution Panel to get the complete hierarchy
    of issues under a feature, regardless of any filters applied in the UI.
    """
    # First verify the issue exists
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()

    if not issue:
        raise NotFoundError("Issue", issue_id)

    # Get all descendant IDs with their details using the optimized CTE query
    descendants_data = await get_all_descendants_with_details(
        db,
        issue_id,
        columns=["id", "key", "title", "type", "status", "priority", "sequence",
                 "description", "completedAt", "parentId", "projectId", "labels",
                 "dueDate", "startedAt", "createdAt", "updatedAt"]
    )

    if not descendants_data:
        return []

    # Fetch full Issue objects for proper response serialization
    descendant_ids = [d["id"] for d in descendants_data]
    result = await db.execute(
        select(Issue).where(Issue.id.in_(descendant_ids))
    )
    issues = result.scalars().all()

    # Sort by the original order (level, sequence) from the CTE query
    id_to_order = {d["id"]: (d.get("level", 0), d.get("sequence", 0)) for d in descendants_data}
    sorted_issues = sorted(issues, key=lambda i: id_to_order.get(i.id, (999, 999)))

    return [IssueResponse.model_validate(i) for i in sorted_issues]
