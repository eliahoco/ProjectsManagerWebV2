"""
Issue CRUD API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from typing import Optional, List
from datetime import datetime
import uuid
import logging
import asyncio

from app.background import create_tracked_task
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

            # Reserve a contiguous block of QA keys atomically (race-safe even
            # under concurrent background QA generations sharing the DB).
            from api.qa import reserve_qa_key_block

            try:
                prefix, start_seq, _end_seq = await reserve_qa_key_block(
                    db, project_id, len(qa_suggestions)
                )
            except Exception as e:
                logger.error(f"Failed to reserve QA key block for {issue_key}: {e}")
                return

            created_keys = []
            for offset, suggestion in enumerate(qa_suggestions):
                qa_seq_number = start_seq + offset
                qa_key = f"{prefix}-{qa_seq_number}"

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
                    sequence=qa_seq_number,
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


# Helper function to generate issue key — atomic to prevent duplicate keys under concurrency
async def get_next_issue_key(db: AsyncSession, project_id: str) -> tuple[str, int]:
    """Get the next issue key for a project using atomic SQL increment.

    Uses SQL-level UPDATE ... RETURNING to atomically increment the sequence
    counter, preventing duplicate keys when concurrent requests race.
    Falls back to INSERT on first use, with retry on IntegrityError race.
    """
    # Determine the prefix once (needed for INSERT path)
    prefix = project_id[:4].upper()

    # Try atomic increment of existing sequence row
    result = await db.execute(
        text(
            'UPDATE "IssueSequence" '
            'SET "lastNumber" = "lastNumber" + 1 '
            'WHERE "projectId" = :pid '
            'RETURNING "lastNumber", "prefix"'
        ),
        {"pid": project_id},
    )
    row = result.first()
    if row:
        next_number = row[0]
        key = f"{row[1]}-{next_number}"
        # No separate commit here — caller (create_issue) commits the full transaction
        return key, next_number

    # Sequence row doesn't exist yet — INSERT it, with retry on concurrent race
    for attempt in range(5):
        try:
            await db.execute(
                text(
                    'INSERT INTO "IssueSequence" ("id", "projectId", "prefix", "lastNumber") '
                    'VALUES (:id, :pid, :prefix, 1)'
                ),
                {"id": str(uuid.uuid4()), "pid": project_id, "prefix": prefix},
            )
            return f"{prefix}-1", 1
        except IntegrityError:
            await db.rollback()
            # Another request won the race — retry the atomic UPDATE
            result = await db.execute(
                text(
                    'UPDATE "IssueSequence" '
                    'SET "lastNumber" = "lastNumber" + 1 '
                    'WHERE "projectId" = :pid '
                    'RETURNING "lastNumber", "prefix"'
                ),
                {"pid": project_id},
            )
            row = result.first()
            if row:
                next_number = row[0]
                key = f"{row[1]}-{next_number}"
                return key, next_number

    raise RuntimeError(f"Failed to generate issue key for project {project_id} after 5 retries")


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
    date_field: Optional[str] = Query(None, alias="dateField"),
    date_from: Optional[str] = Query(None, alias="dateFrom"),
    date_to: Optional[str] = Query(None, alias="dateTo"),
    sort_by: Optional[str] = Query(None, alias="sortBy"),
    sort_order: Optional[str] = Query("desc", alias="sortOrder"),
    db: AsyncSession = Depends(get_db),
):
    """List all issues for a project with filtering, date range, and pagination"""
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

    # Apply date range filter
    if date_field and (date_from or date_to):
        date_column_map = {
            "createdAt": Issue.createdAt,
            "updatedAt": Issue.updatedAt,
            "dueDate": Issue.dueDate,
            "startedAt": Issue.startedAt,
            "completedAt": Issue.completedAt,
        }
        date_column = date_column_map.get(date_field)
        if date_column is not None:
            if date_from:
                try:
                    from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
                    query = query.where(date_column >= from_dt)
                except ValueError:
                    pass
            if date_to:
                try:
                    to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
                    query = query.where(date_column <= to_dt)
                except ValueError:
                    pass

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply sorting
    sort_column_map = {
        "sequence": Issue.sequence,
        "priority": Issue.priority,
        "createdAt": Issue.createdAt,
        "updatedAt": Issue.updatedAt,
        "dueDate": Issue.dueDate,
        "title": Issue.title,
        "type": Issue.type,
        "status": Issue.status,
    }
    order_column = sort_column_map.get(sort_by) if sort_by else None

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    if order_column is not None:
        if sort_order == "asc":
            query = query.order_by(order_column.asc())
        else:
            query = query.order_by(order_column.desc())
    else:
        query = query.order_by(Issue.sequence.desc())
    query = query.offset(offset).limit(page_size)

    # Execute query
    result = await db.execute(query)
    issues = result.scalars().all()

    # If search is active, compute relevance scores
    items = []
    for issue in issues:
        response = IssueResponse.model_validate(issue)
        if search:
            score = _compute_relevance_score(issue, search)
            response_dict = response.model_dump()
            response_dict["relevanceScore"] = score
            items.append(response_dict)
        else:
            items.append(response)

    # Sort by relevance if searching (within the page)
    if search and items and isinstance(items[0], dict):
        items.sort(key=lambda x: x.get("relevanceScore", 0), reverse=True)

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        pageSize=page_size,
        totalPages=(total + page_size - 1) // page_size,
    )


def _compute_relevance_score(issue: Issue, search: str) -> float:
    """
    Compute a relevance score for an issue against a search query.
    Higher scores indicate better matches.
    Scoring:
      - Exact key match: 100
      - Title starts with search: 80
      - Title contains search: 60
      - Description contains search: 30
      - Bonus for type (FEATURE/EPIC ranked higher): up to 10
    """
    search_lower = search.lower()
    score = 0.0

    # Exact key match
    if issue.key and issue.key.lower() == search_lower:
        score += 100

    title_lower = (issue.title or "").lower()
    desc_lower = (issue.description or "").lower()

    # Title matching
    if title_lower.startswith(search_lower):
        score += 80
    elif search_lower in title_lower:
        score += 60

    # Description matching
    if search_lower in desc_lower:
        score += 30

    # Type boost - features and epics rank higher
    type_boost = {
        "FEATURE": 10,
        "EPIC": 8,
        "STORY": 5,
        "BUG": 4,
        "TASK": 2,
        "SUBTASK": 1,
    }
    score += type_boost.get(issue.type, 0)

    return score


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
                    # Fire-and-forget async QA generation — tracked to prevent GC
                    create_tracked_task(
                        trigger_qa_generation(issue.id, issue.key, issue.projectId),
                        name=f"qa-gen-{issue.key}",
                    )
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

    # Embed aiContext into ChromaDB when the field changes
    if "aiContext" in update_data:
        try:
            new_ai_context = update_data["aiContext"]
            if new_ai_context:
                await rag_service.embed_ai_context(
                    project_id=issue.projectId,
                    issue_id=issue.id,
                    issue_key=issue.key,
                    issue_type=issue.type,
                    ai_context=new_ai_context,
                )
            else:
                # aiContext was cleared — remove the embedding
                await rag_service.delete_ai_context_embedding(
                    project_id=issue.projectId,
                    issue_id=issue.id,
                )
        except Exception as e:
            logger.warning(f"Failed to embed aiContext for {issue.key}: {e}")

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

    # Remove from RAG store (both issue embedding and aiContext embedding)
    try:
        await rag_service.delete_issue_embedding(project_id, issue_id)
        await rag_service.delete_ai_context_embedding(project_id, issue_id)
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
                # Fire-and-forget async QA generation — tracked to prevent GC
                create_tracked_task(
                    trigger_qa_generation(issue.id, issue.key, issue.projectId),
                    name=f"qa-gen-{issue.key}",
                )

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


# GET /api/issues/{issue_id}/descendants/search - Search within an issue's descendants (CB-1122)
@router.get("/issues/{issue_id}/descendants/search")
async def search_issue_descendants(
    issue_id: str,
    search: Optional[str] = Query(None, description="Text search query"),
    type: Optional[str] = Query(None, description="Filter by issue type (comma-separated for multiple)"),
    status: Optional[str] = Query(None, description="Filter by status (comma-separated for multiple)"),
    priority: Optional[str] = Query(None, description="Filter by priority (comma-separated for multiple)"),
    date_field: Optional[str] = Query(None, alias="dateField"),
    date_from: Optional[str] = Query(None, alias="dateFrom"),
    date_to: Optional[str] = Query(None, alias="dateTo"),
    sort_by: Optional[str] = Query(None, alias="sortBy", description="Sort field: relevance, priority, createdAt, updatedAt, status, type, sequence"),
    sort_order: Optional[str] = Query("desc", alias="sortOrder"),
    db: AsyncSession = Depends(get_db),
):
    """
    Search and filter within an issue's descendants with relevance ranking.
    Designed for epic-level search within feature hierarchies (CB-1122).

    Returns matching descendants with relevance scores, preserving ancestor
    chain for tree rendering.
    """
    # Verify the parent issue exists
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    parent_issue = result.scalar_one_or_none()
    if not parent_issue:
        raise NotFoundError("Issue", issue_id)

    # Get all descendants
    descendants_data = await get_all_descendants_with_details(
        db, issue_id,
        columns=["id", "key", "title", "type", "status", "priority", "sequence",
                 "description", "completedAt", "parentId", "projectId", "labels",
                 "dueDate", "startedAt", "createdAt", "updatedAt"]
    )

    if not descendants_data:
        return {"items": [], "total": 0, "matchCount": 0}

    # Fetch full Issue objects
    descendant_ids = [d["id"] for d in descendants_data]
    result = await db.execute(select(Issue).where(Issue.id.in_(descendant_ids)))
    all_issues = result.scalars().all()
    issue_map = {i.id: i for i in all_issues}

    # Parse multi-value filters
    type_filters = [t.strip() for t in type.split(",")] if type else []
    status_filters = [s.strip() for s in status.split(",")] if status else []
    priority_filters = [p.strip() for p in priority.split(",")] if priority else []

    has_any_filter = search or type_filters or status_filters or priority_filters or (date_field and (date_from or date_to))

    if not has_any_filter:
        # No filters, return all descendants
        items = []
        for issue in all_issues:
            resp = IssueResponse.model_validate(issue)
            resp_dict = resp.model_dump()
            resp_dict["relevanceScore"] = 0
            resp_dict["isDirectMatch"] = True
            items.append(resp_dict)
        return {"items": items, "total": len(items), "matchCount": len(items)}

    # Apply filters and compute relevance scores
    direct_matches = {}  # id -> (issue, score)

    for issue in all_issues:
        matches = True
        score = 0.0

        # Text search with relevance scoring
        if search:
            text_score = _compute_epic_search_relevance(issue, search)
            if text_score == 0:
                matches = False
            else:
                score += text_score

        # Type filter
        if matches and type_filters:
            if issue.type not in type_filters:
                matches = False

        # Status filter
        if matches and status_filters:
            if issue.status not in status_filters:
                matches = False

        # Priority filter
        if matches and priority_filters:
            if issue.priority not in priority_filters:
                matches = False

        # Date range filter
        if matches and date_field and (date_from or date_to):
            date_column_map = {
                "createdAt": issue.createdAt,
                "updatedAt": issue.updatedAt,
                "dueDate": issue.dueDate,
                "startedAt": issue.startedAt,
                "completedAt": issue.completedAt,
            }
            date_value = date_column_map.get(date_field)
            if date_value:
                if date_from:
                    try:
                        from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
                        if date_value < from_dt:
                            matches = False
                    except ValueError:
                        pass
                if date_to:
                    try:
                        to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
                        if date_value > to_dt:
                            matches = False
                    except ValueError:
                        pass
            else:
                matches = False

        if matches:
            direct_matches[issue.id] = (issue, score)

    # Build ancestor chains - include all ancestors of matches for tree rendering
    parent_map = {d["id"]: d.get("parentId") for d in descendants_data}
    ancestor_ids = set()
    for match_id in direct_matches:
        current_parent = parent_map.get(match_id)
        while current_parent and current_parent != issue_id:
            ancestor_ids.add(current_parent)
            current_parent = parent_map.get(current_parent)

    # Build response items
    items = []
    for mid, (issue, score) in direct_matches.items():
        resp = IssueResponse.model_validate(issue)
        resp_dict = resp.model_dump()
        resp_dict["relevanceScore"] = score
        resp_dict["isDirectMatch"] = True
        items.append(resp_dict)

    # Add ancestors that aren't direct matches (for tree structure)
    for anc_id in ancestor_ids:
        if anc_id not in direct_matches and anc_id in issue_map:
            resp = IssueResponse.model_validate(issue_map[anc_id])
            resp_dict = resp.model_dump()
            resp_dict["relevanceScore"] = 0
            resp_dict["isDirectMatch"] = False
            items.append(resp_dict)

    # Sort results
    if sort_by == "relevance" or (not sort_by and search):
        items.sort(key=lambda x: x.get("relevanceScore", 0), reverse=True)
    elif sort_by:
        sort_key_map = {
            "priority": lambda x: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(x.get("priority", ""), 99),
            "createdAt": lambda x: x.get("createdAt", ""),
            "updatedAt": lambda x: x.get("updatedAt", ""),
            "status": lambda x: {"IN_PROGRESS": 0, "IN_REVIEW": 1, "TODO": 2, "BACKLOG": 3, "COMPLETED_WAITING_QA": 4, "DONE": 5, "CANCELLED": 6}.get(x.get("status", ""), 99),
            "type": lambda x: {"EPIC": 0, "STORY": 1, "TASK": 2, "BUG": 2, "SUBTASK": 3}.get(x.get("type", ""), 99),
            "sequence": lambda x: x.get("sequence", 0),
        }
        key_fn = sort_key_map.get(sort_by)
        if key_fn:
            reverse = sort_order != "asc"
            items.sort(key=key_fn, reverse=reverse)

    return {
        "items": items,
        "total": len(items),
        "matchCount": len(direct_matches),
    }


def _compute_epic_search_relevance(issue: Issue, search: str) -> float:
    """
    Compute relevance score for epic-level search (CB-1122).
    Enhanced scoring that considers position in hierarchy and field matches.

    Scoring:
      - Exact key match: 100
      - Title starts with search: 80
      - Title contains search (word boundary): 70
      - Title contains search: 60
      - Description contains search: 30
      - Type hierarchy boost (STORY > TASK > SUBTASK): up to 10
      - Priority boost (CRITICAL > HIGH > MEDIUM > LOW): up to 5
      - Status boost (active items rank higher): up to 5
    """
    search_lower = search.lower()
    score = 0.0

    # Exact key match
    if issue.key and issue.key.lower() == search_lower:
        score += 100

    title_lower = (issue.title or "").lower()
    desc_lower = (issue.description or "").lower()

    # Title matching with word boundary awareness
    if title_lower.startswith(search_lower):
        score += 80
    elif f" {search_lower}" in f" {title_lower}":
        # Word boundary match (search appears at start of a word)
        score += 70
    elif search_lower in title_lower:
        score += 60

    # Description matching
    if search_lower in desc_lower:
        score += 30

    # Label matching
    labels_lower = (issue.labels or "").lower()
    if search_lower in labels_lower:
        score += 20

    # Only return score > 0 if there was at least one text match
    if score == 0:
        return 0

    # Type hierarchy boost - stories and tasks rank higher in epic context
    type_boost = {
        "STORY": 10,
        "TASK": 8,
        "BUG": 7,
        "SUBTASK": 5,
        "EPIC": 3,
        "FEATURE": 1,
    }
    score += type_boost.get(issue.type, 0)

    # Priority boost
    priority_boost = {
        "CRITICAL": 5,
        "HIGH": 4,
        "MEDIUM": 2,
        "LOW": 1,
    }
    score += priority_boost.get(issue.priority, 0)

    # Active status boost
    status_boost = {
        "IN_PROGRESS": 5,
        "IN_REVIEW": 4,
        "TODO": 3,
        "BACKLOG": 2,
        "COMPLETED_WAITING_QA": 1,
        "DONE": 0,
        "CANCELLED": 0,
    }
    score += status_boost.get(issue.status, 0)

    return score


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
