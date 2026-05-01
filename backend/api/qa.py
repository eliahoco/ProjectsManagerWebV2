"""
QA Board API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime
import uuid
import json
import logging
import asyncio

from models import get_db, Issue, Project
from models.qa import QATask, QATaskIssueLink, QASequence, QASettings
from models.schemas import (
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
    QATaskStatus,
    QAEvaluation,
    AreaCoverage,
    PriorityDistribution,
    TypeDistribution,
    QualityMetric,
    Recommendation,
    ExecutionTrend,
)
from services.qa_service import qa_service
from app.errors import NotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qa", tags=["qa"])


# ==================== Helper Functions ====================

async def reserve_qa_key_block(
    db: AsyncSession, project_id: str, count: int
) -> tuple[str, int, int]:
    """Atomically reserve `count` sequential QA keys for a project.

    Handles both drift (`QASequence.lastNumber` below max(QATask.sequence))
    and concurrent writers by performing a single atomic UPDATE that
    reconciles against max(QATask.sequence) and bumps lastNumber by `count`.
    SQLite serializes writes, so two racing callers get non-overlapping
    blocks. Does NOT commit — the caller commits with the QATask rows.

    Returns:
        (prefix, start_sequence, end_sequence) — reserved range is
        [start_sequence, end_sequence] inclusive.
    """
    if count <= 0:
        raise ValueError("count must be >= 1")

    # Ensure a sequence row exists so the UPDATE has something to hit.
    result = await db.execute(
        select(QASequence).where(QASequence.projectId == project_id)
    )
    sequence = result.scalar_one_or_none()
    if not sequence:
        max_existing = await db.execute(
            select(func.coalesce(func.max(QATask.sequence), 0))
            .where(QATask.projectId == project_id)
        )
        max_seq = int(max_existing.scalar_one() or 0)
        sequence = QASequence(
            id=str(uuid.uuid4()),
            projectId=project_id,
            prefix="QA",
            lastNumber=max_seq,
        )
        db.add(sequence)
        await db.flush()

    # Atomic reconcile-and-advance. Single UPDATE → SQLite serializes.
    result = await db.execute(
        text(
            'UPDATE "QASequence" '
            'SET "lastNumber" = '
            '  MAX("lastNumber", COALESCE((SELECT MAX(sequence) FROM "QATask" WHERE "projectId" = :pid), 0)) + :n '
            'WHERE "projectId" = :pid '
            'RETURNING "lastNumber", "prefix"'
        ),
        {"pid": project_id, "n": count},
    )
    row = result.first()
    if not row:
        raise RuntimeError(f"Failed to reserve QA key block for project {project_id}")
    end_seq = int(row[0])
    prefix = row[1]
    start_seq = end_seq - count + 1
    # Commit immediately so concurrent QA generations see the advanced counter.
    # Without this, the write lock is held until the caller commits task rows,
    # and other sessions reserve against a stale lastNumber → duplicate keys.
    await db.commit()
    return prefix, start_seq, end_seq


async def get_next_qa_key(db: AsyncSession, project_id: str) -> tuple[str, int]:
    """Get the next QA task key for a project.

    Thin wrapper over `reserve_qa_key_block(..., 1)`. Atomic, drift-proof,
    race-safe. Does NOT commit — the caller commits with the QATask row.
    """
    prefix, start, _ = await reserve_qa_key_block(db, project_id, 1)
    return f"{prefix}-{start}", start


async def get_or_create_settings(db: AsyncSession, project_id: str) -> QASettings:
    """Get or create QA settings for a project"""
    result = await db.execute(
        select(QASettings).where(QASettings.projectId == project_id)
    )
    settings = result.scalar_one_or_none()

    if not settings:
        settings = QASettings(
            id=str(uuid.uuid4()),
            projectId=project_id,
            passThreshold=0.9,
            autoCreateBugs=True,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return settings


def qa_task_to_response(task: QATask) -> QATaskWithIssues:
    """Convert QATask model to response with linked issue IDs"""
    linked_ids = [link.issueId for link in task.linkedIssues] if task.linkedIssues else []
    return QATaskWithIssues(
        id=task.id,
        projectId=task.projectId,
        key=task.key,
        sequence=task.sequence,
        title=task.title,
        scenario=task.scenario,
        expectedResult=task.expectedResult,
        actualResult=task.actualResult,
        status=QATaskStatus(task.status),
        type=task.type,
        priority=task.priority,
        executionHistory=task.executionHistory,
        lastExecutedAt=task.lastExecutedAt,
        bugIssueId=task.bugIssueId,
        createdAt=task.createdAt,
        updatedAt=task.updatedAt,
        linkedIssueIds=linked_ids,
    )


async def get_all_child_issue_ids(db: AsyncSession, parent_id: str) -> list[str]:
    """
    Get all child issue IDs for a given parent issue using optimized CTE query.

    Uses a recursive Common Table Expression (CTE) to fetch all descendants
    in a single database query instead of N+1 recursive queries.
    """
    from utils.db_queries import get_all_descendant_ids
    return await get_all_descendant_ids(db, parent_id)


# ==================== QA Task CRUD ====================

@router.get("/projects/{project_id}/tasks", response_model=List[QATaskWithIssues])
async def list_qa_tasks(
    project_id: str,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    issue_id: Optional[str] = None,
    include_descendants: bool = Query(False, description="Include QA tasks from all descendant issues"),
    db: AsyncSession = Depends(get_db),
):
    """List all QA tasks for a project with optional filters"""
    query = select(QATask).where(QATask.projectId == project_id)

    if status:
        query = query.where(QATask.status == status)
    if priority:
        query = query.where(QATask.priority == priority)
    if issue_id:
        if include_descendants:
            # Get all descendant issue IDs
            child_ids = await get_all_child_issue_ids(db, issue_id)
            all_issue_ids = [issue_id] + child_ids
            # Filter by linked issue or any descendant
            query = query.join(QATaskIssueLink).where(QATaskIssueLink.issueId.in_(all_issue_ids))
        else:
            # Filter by linked issue only
            query = query.join(QATaskIssueLink).where(QATaskIssueLink.issueId == issue_id)

    query = query.options(selectinload(QATask.linkedIssues))
    query = query.order_by(QATask.sequence.desc())

    result = await db.execute(query)
    tasks = result.scalars().unique().all()

    return [qa_task_to_response(task) for task in tasks]


@router.post("/projects/{project_id}/tasks", response_model=QATaskResponse)
async def create_qa_task(
    project_id: str,
    task_data: QATaskCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new QA task"""
    key, sequence = await get_next_qa_key(db, project_id)

    task = QATask(
        id=str(uuid.uuid4()),
        projectId=project_id,
        key=key,
        sequence=sequence,
        title=task_data.title,
        scenario=task_data.scenario,
        expectedResult=task_data.expectedResult,
        status="NOT_DONE",
        type=task_data.type.value,
        priority=task_data.priority.value,
        createdAt=datetime.now(),
        updatedAt=datetime.now(),
    )
    db.add(task)

    # Create issue links
    for issue_id in task_data.linkedIssueIds:
        link = QATaskIssueLink(
            id=str(uuid.uuid4()),
            qaTaskId=task.id,
            issueId=issue_id,
        )
        db.add(link)

    await db.commit()
    await db.refresh(task)

    logger.info(f"Created QA task {key}: {task_data.title}")
    return task


@router.get("/tasks/{task_id}", response_model=QATaskWithIssues)
async def get_qa_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single QA task by ID"""
    result = await db.execute(
        select(QATask)
        .where(QATask.id == task_id)
        .options(selectinload(QATask.linkedIssues))
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundError(f"QA task {task_id} not found")

    return qa_task_to_response(task)


@router.patch("/tasks/{task_id}", response_model=QATaskResponse)
async def update_qa_task(
    task_id: str,
    task_data: QATaskUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a QA task"""
    result = await db.execute(
        select(QATask).where(QATask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundError(f"QA task {task_id} not found")

    # Update fields
    update_data = task_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(value, 'value'):  # Handle enums
            value = value.value
        setattr(task, field, value)

    task.updatedAt = datetime.now()
    await db.commit()
    await db.refresh(task)

    logger.info(f"Updated QA task {task.key}")
    return task


@router.delete("/tasks/{task_id}")
async def delete_qa_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a QA task"""
    result = await db.execute(
        select(QATask).where(QATask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundError(f"QA task {task_id} not found")

    await db.delete(task)
    await db.commit()

    logger.info(f"Deleted QA task {task.key}")
    return {"success": True}


# ==================== QA Plan Generation ====================

@router.post("/generate", response_model=QAPlanGenerateResponse)
async def generate_qa_plan(
    request: QAPlanGenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Generate QA tasks for an issue using AI"""
    # Get the issue
    result = await db.execute(
        select(Issue)
        .where(Issue.id == request.issueId)
        .options(selectinload(Issue.children))
    )
    issue = result.scalar_one_or_none()

    if not issue:
        raise NotFoundError(f"Issue {request.issueId} not found")

    # Get children context
    children = [
        {"id": c.id, "title": c.title, "type": c.type, "status": c.status}
        for c in (issue.children or [])
    ]

    # Generate QA plan using AI
    qa_suggestions = await qa_service.generate_qa_plan(
        project_id=issue.projectId,
        issue_id=issue.id,
        issue_title=issue.title,
        issue_description=issue.description,
        issue_type=issue.type,
        children=children,
        custom_instructions=request.customInstructions,
        db=db,
    )

    # Create QA tasks
    created_keys = []
    for suggestion in qa_suggestions:
        key, sequence = await get_next_qa_key(db, issue.projectId)

        # Handle scenario as list or string
        scenario = suggestion.get('scenario', '')
        if isinstance(scenario, list):
            scenario = '\n'.join(scenario)

        # Handle expectedResult as list or string
        expected_result = suggestion.get('expectedResult', '')
        if isinstance(expected_result, list):
            expected_result = '\n'.join(expected_result)

        task = QATask(
            id=str(uuid.uuid4()),
            projectId=issue.projectId,
            key=key,
            sequence=sequence,
            title=suggestion.get('title', 'Unnamed test'),
            scenario=scenario,
            expectedResult=expected_result,
            status="NOT_DONE",
            type=suggestion.get('type', 'AUTOMATED'),
            priority=suggestion.get('priority', 'MEDIUM'),
            createdAt=datetime.now(),
            updatedAt=datetime.now(),
        )
        db.add(task)

        # Link to the issue
        link = QATaskIssueLink(
            id=str(uuid.uuid4()),
            qaTaskId=task.id,
            issueId=issue.id,
        )
        db.add(link)

        created_keys.append(key)

    await db.commit()

    logger.info(f"Generated {len(created_keys)} QA tasks for issue {issue.key}")
    return QAPlanGenerateResponse(
        issueId=request.issueId,
        qaTasksCreated=len(created_keys),
        qaTaskKeys=created_keys,
    )


@router.post("/generate/stream")
async def generate_qa_plan_stream(
    request: QAPlanGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate QA tasks for an issue using AI with streaming progress updates"""

    async def event_generator():
        try:
            # Step 1: Emit start event
            yield f"data: {json.dumps({'event': 'start', 'message': 'Initializing QA plan generation...'})}\n\n"
            await asyncio.sleep(0.1)

            # Step 2: Get the issue
            yield f"data: {json.dumps({'event': 'progress', 'progress': 10, 'message': 'Loading issue context...'})}\n\n"
            result = await db.execute(
                select(Issue)
                .where(Issue.id == request.issueId)
                .options(selectinload(Issue.children))
            )
            issue = result.scalar_one_or_none()

            if not issue:
                yield f"data: {json.dumps({'event': 'error', 'error': f'Issue {request.issueId} not found'})}\n\n"
                return

            yield f"data: {json.dumps({'event': 'progress', 'progress': 20, 'message': 'Analyzing issue requirements...'})}\n\n"
            await asyncio.sleep(0.1)

            # Step 3: Get children context
            children = [
                {"id": c.id, "title": c.title, "type": c.type, "status": c.status}
                for c in (issue.children or [])
            ]

            yield f"data: {json.dumps({'event': 'progress', 'progress': 30, 'message': 'Building test requirements...'})}\n\n"
            await asyncio.sleep(0.1)

            # Step 4: Generate QA plan using AI
            yield f"data: {json.dumps({'event': 'progress', 'progress': 40, 'message': 'Generating test scenarios with AI...'})}\n\n"

            qa_suggestions = await qa_service.generate_qa_plan(
                project_id=issue.projectId,
                issue_id=issue.id,
                issue_title=issue.title,
                issue_description=issue.description,
                issue_type=issue.type,
                children=children,
                custom_instructions=request.customInstructions,
                db=db,
            )

            if not qa_suggestions:
                yield f"data: {json.dumps({'event': 'error', 'error': 'Failed to generate QA suggestions'})}\n\n"
                return

            yield f"data: {json.dumps({'event': 'progress', 'progress': 70, 'message': f'Creating {len(qa_suggestions)} test cases...'})}\n\n"
            await asyncio.sleep(0.1)

            # Step 5: Create QA tasks
            created_keys = []
            total_tasks = len(qa_suggestions)

            for i, suggestion in enumerate(qa_suggestions):
                progress = 70 + int((i / total_tasks) * 25)
                yield f"data: {json.dumps({'event': 'progress', 'progress': progress, 'message': f'Creating test case {i + 1} of {total_tasks}...'})}\n\n"

                key, sequence = await get_next_qa_key(db, issue.projectId)

                # Handle scenario as list or string
                scenario = suggestion.get('scenario', '')
                if isinstance(scenario, list):
                    scenario = '\n'.join(scenario)

                # Handle expectedResult as list or string
                expected_result = suggestion.get('expectedResult', '')
                if isinstance(expected_result, list):
                    expected_result = '\n'.join(expected_result)

                task = QATask(
                    id=str(uuid.uuid4()),
                    projectId=issue.projectId,
                    key=key,
                    sequence=sequence,
                    title=suggestion.get('title', 'Unnamed test'),
                    scenario=scenario,
                    expectedResult=expected_result,
                    status="NOT_DONE",
                    type=suggestion.get('type', 'AUTOMATED'),
                    priority=suggestion.get('priority', 'MEDIUM'),
                    createdAt=datetime.now(),
                    updatedAt=datetime.now(),
                )
                db.add(task)

                # Link to the issue
                link = QATaskIssueLink(
                    id=str(uuid.uuid4()),
                    qaTaskId=task.id,
                    issueId=issue.id,
                )
                db.add(link)

                created_keys.append(key)

            yield f"data: {json.dumps({'event': 'progress', 'progress': 95, 'message': 'Finalizing QA plan...'})}\n\n"
            await db.commit()

            logger.info(f"Generated {len(created_keys)} QA tasks for issue {issue.key}")

            # Final success event
            yield f"data: {json.dumps({'event': 'complete', 'progress': 100, 'message': 'QA plan generated successfully!', 'result': {'issueId': request.issueId, 'qaTasksCreated': len(created_keys), 'qaTaskKeys': created_keys}})}\n\n"

        except Exception as e:
            logger.error(f"Error in streaming QA generation: {e}")
            yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ==================== QA Execution ====================

@router.post("/execute", response_model=List[QAExecutionResult])
async def execute_qa_tasks(
    request: QAExecutionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Execute QA tasks (automated) sequentially or in parallel"""
    # Get tasks with their linked issues
    result = await db.execute(
        select(QATask)
        .where(QATask.id.in_(request.qaTaskIds))
        .options(selectinload(QATask.linkedIssues))
    )
    tasks = result.scalars().unique().all()

    if not tasks:
        raise NotFoundError("No QA tasks found")

    # Get project path (for context)
    project_id = tasks[0].projectId
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    project_path = project.path if project else "/unknown"

    # Get the linked issue for context (use first task's first linked issue).
    # CB-1603 sec audit M-1: QATaskIssueLink does not enforce that the linked
    # Issue belongs to the same project as the QA task. Refuse to build the
    # issue_context from a foreign-project Issue — this would otherwise leak
    # that project's title/description AND its ExecutionSummary (via RAG)
    # into the QA execution prompt and back into actualResult.
    issue_context = None
    if tasks[0].linkedIssues:
        first_link = tasks[0].linkedIssues[0]
        result = await db.execute(
            select(Issue).where(Issue.id == first_link.issueId)
        )
        linked_issue = result.scalar_one_or_none()
        if linked_issue and linked_issue.projectId == project_id:
            issue_context = {
                "id": linked_issue.id,
                "projectId": linked_issue.projectId,
                "key": linked_issue.key,
                "title": linked_issue.title,
                "type": linked_issue.type,
                "status": linked_issue.status,
                "description": linked_issue.description,
            }
            logger.info(f"Using issue context: {linked_issue.key} - {linked_issue.title}")
        elif linked_issue:
            logger.warning(
                f"QA task {tasks[0].key} linked to issue {linked_issue.key} "
                f"in foreign project {linked_issue.projectId} (task is in "
                f"{project_id}) — skipping issue context to prevent "
                f"cross-project leakage (CB-1603 M-1)."
            )

    # Convert to dicts for service
    task_dicts = [
        {
            "id": t.id,
            "key": t.key,
            "title": t.title,
            "scenario": t.scenario,
            "expectedResult": t.expectedResult,
            "type": t.type,
            "priority": t.priority,
        }
        for t in tasks
    ]

    # Update status to IN_PROGRESS
    for task in tasks:
        task.status = "IN_PROGRESS"
    await db.commit()

    # Execute based on mode (CB-1603: pass db so qa_service can fetch the
    # latest ExecutionSummary and inject implementation context into the
    # per-task prompt).
    if request.executionMode == "parallel":
        results = await qa_service.execute_qa_tasks_parallel(
            task_dicts, project_path, issue_context, db=db
        )
    else:
        results = await qa_service.execute_qa_tasks_sequential(
            task_dicts, project_path, issue_context, db=db
        )

    # Update tasks with results
    for exec_result in results:
        task_id = exec_result.get('qaTaskId')
        result = await db.execute(
            select(QATask).where(QATask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if task:
            task.status = exec_result.get('status', 'FAILED')
            task.actualResult = exec_result.get('actualResult')
            task.lastExecutedAt = datetime.now()

            # Update execution history
            task.executionHistory = qa_service.add_execution_to_history(
                task.executionHistory,
                exec_result,
            )

    await db.commit()

    logger.info(f"Executed {len(results)} QA tasks")
    return [
        QAExecutionResult(
            qaTaskId=r.get('qaTaskId'),
            key=r.get('key'),
            status=QATaskStatus(r.get('status', 'FAILED')),
            actualResult=r.get('actualResult'),
            executionTime=r.get('executionTime', 0),
            error=r.get('error'),
        )
        for r in results
    ]


# ==================== Sequential Execution with Streaming ====================

@router.post("/execute/stream")
async def execute_qa_tasks_stream(
    request: QAExecutionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Execute QA tasks sequentially with real-time progress updates via Server-Sent Events.

    This endpoint streams progress updates as each task is executed, allowing the
    frontend to show live progress during execution.

    Events emitted:
    - start: Execution started with total task count
    - task_start: A task is starting execution
    - task_complete: A task finished with its result
    - complete: All tasks finished
    - aborted: Execution was aborted by user
    - error: An error occurred during execution
    """
    # Get tasks with their linked issues
    result = await db.execute(
        select(QATask)
        .where(QATask.id.in_(request.qaTaskIds))
        .options(selectinload(QATask.linkedIssues))
    )
    tasks = result.scalars().unique().all()

    if not tasks:
        raise NotFoundError("No QA tasks found")

    # Get project path (for context)
    project_id = tasks[0].projectId
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    project_path = project.path if project else "/unknown"

    # CB-1603 sec audit M-1: refuse foreign-project linked issues. See the
    # /qa/execute endpoint for full rationale.
    issue_context = None
    if tasks[0].linkedIssues:
        first_link = tasks[0].linkedIssues[0]
        result = await db.execute(
            select(Issue).where(Issue.id == first_link.issueId)
        )
        linked_issue = result.scalar_one_or_none()
        if linked_issue and linked_issue.projectId == project_id:
            issue_context = {
                "id": linked_issue.id,
                "projectId": linked_issue.projectId,
                "key": linked_issue.key,
                "title": linked_issue.title,
                "type": linked_issue.type,
                "status": linked_issue.status,
                "description": linked_issue.description,
            }
        elif linked_issue:
            logger.warning(
                f"QA task {tasks[0].key} linked to issue {linked_issue.key} "
                f"in foreign project {linked_issue.projectId} — skipping "
                f"issue context (CB-1603 M-1)."
            )

    # Convert to dicts for service
    task_dicts = [
        {
            "id": t.id,
            "key": t.key,
            "title": t.title,
            "scenario": t.scenario,
            "expectedResult": t.expectedResult,
            "type": t.type,
            "priority": t.priority,
        }
        for t in tasks
    ]

    # Update status to IN_PROGRESS
    for task in tasks:
        task.status = "IN_PROGRESS"
    await db.commit()

    # Generate execution ID
    execution_id = str(uuid.uuid4())

    async def event_generator():
        """Generate SSE events for the streaming response"""
        async for event in qa_service.execute_qa_tasks_sequential_stream(
            task_dicts, project_path, issue_context, execution_id, db=db
        ):
            # Update task in database when complete
            if event.get("event") == "task_complete":
                task_key = event.get("taskKey")
                # Find the task by key
                for task_dict in task_dicts:
                    if task_dict["key"] == task_key:
                        task_id = task_dict["id"]
                        result = await db.execute(
                            select(QATask).where(QATask.id == task_id)
                        )
                        db_task = result.scalar_one_or_none()
                        if db_task:
                            db_task.status = event.get("status", "FAILED")
                            # Find actual result from the execution results
                            state = qa_service.get_execution_state(execution_id)
                            if state and state.results:
                                for res in state.results:
                                    if res.get("key") == task_key:
                                        db_task.actualResult = res.get("actualResult")
                                        db_task.executionHistory = qa_service.add_execution_to_history(
                                            db_task.executionHistory,
                                            res,
                                        )
                                        break
                            db_task.lastExecutedAt = datetime.now()
                        await db.commit()
                        break

            # Format as SSE event
            event_data = json.dumps(event)
            yield f"data: {event_data}\n\n"

            # Small delay to ensure browser receives each event
            await asyncio.sleep(0.01)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/execute/stream-parallel")
async def execute_qa_tasks_parallel_stream(
    request: QAExecutionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Execute QA tasks in parallel with real-time progress updates via Server-Sent Events.

    Tasks are executed concurrently (up to max_concurrent at a time). Progress events
    are emitted as tasks start and complete, in completion order (not submission order).

    Events emitted:
    - start: Execution started with total task count and max concurrency
    - task_start: A task is starting execution (multiple can be in flight)
    - task_complete: A task finished with its result
    - complete: All tasks finished
    - aborted: Execution was aborted by user
    - error: An error occurred during execution
    """
    # Get tasks with their linked issues
    result = await db.execute(
        select(QATask)
        .where(QATask.id.in_(request.qaTaskIds))
        .options(selectinload(QATask.linkedIssues))
    )
    tasks = result.scalars().unique().all()

    if not tasks:
        raise NotFoundError("No QA tasks found")

    # Get project path (for context)
    project_id = tasks[0].projectId
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    project_path = project.path if project else "/unknown"

    # CB-1603 sec audit M-1: refuse foreign-project linked issues. See the
    # /qa/execute endpoint for full rationale.
    issue_context = None
    if tasks[0].linkedIssues:
        first_link = tasks[0].linkedIssues[0]
        result = await db.execute(
            select(Issue).where(Issue.id == first_link.issueId)
        )
        linked_issue = result.scalar_one_or_none()
        if linked_issue and linked_issue.projectId == project_id:
            issue_context = {
                "id": linked_issue.id,
                "projectId": linked_issue.projectId,
                "key": linked_issue.key,
                "title": linked_issue.title,
                "type": linked_issue.type,
                "status": linked_issue.status,
                "description": linked_issue.description,
            }
        elif linked_issue:
            logger.warning(
                f"QA task {tasks[0].key} linked to issue {linked_issue.key} "
                f"in foreign project {linked_issue.projectId} — skipping "
                f"issue context (CB-1603 M-1)."
            )

    # Convert to dicts for service
    task_dicts = [
        {
            "id": t.id,
            "key": t.key,
            "title": t.title,
            "scenario": t.scenario,
            "expectedResult": t.expectedResult,
            "type": t.type,
            "priority": t.priority,
        }
        for t in tasks
    ]

    # Update status to IN_PROGRESS
    for task in tasks:
        task.status = "IN_PROGRESS"
    await db.commit()

    # Generate execution ID
    execution_id = str(uuid.uuid4())

    # Get max_concurrent from request or use default
    max_concurrent = getattr(request, 'maxConcurrent', 5) or 5

    async def event_generator():
        """Generate SSE events for the parallel streaming response"""
        async for event in qa_service.execute_qa_tasks_parallel_stream(
            task_dicts, project_path, issue_context, max_concurrent, execution_id, db=db
        ):
            # Update task in database when complete
            if event.get("event") == "task_complete":
                task_key = event.get("taskKey")
                # Find the task by key
                for task_dict in task_dicts:
                    if task_dict["key"] == task_key:
                        task_id = task_dict["id"]
                        result = await db.execute(
                            select(QATask).where(QATask.id == task_id)
                        )
                        db_task = result.scalar_one_or_none()
                        if db_task:
                            db_task.status = event.get("status", "FAILED")
                            # Find actual result from the execution results
                            state = qa_service.get_execution_state(execution_id)
                            if state and state.results:
                                for res in state.results:
                                    if res.get("key") == task_key:
                                        db_task.actualResult = res.get("actualResult")
                                        db_task.executionHistory = qa_service.add_execution_to_history(
                                            db_task.executionHistory,
                                            res,
                                        )
                                        break
                            db_task.lastExecutedAt = datetime.now()
                        await db.commit()
                        break

            # Format as SSE event
            event_data = json.dumps(event)
            yield f"data: {event_data}\n\n"

            # Small delay to ensure browser receives each event
            await asyncio.sleep(0.01)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/execute/{execution_id}/abort")
async def abort_execution(
    execution_id: str,
):
    """
    Abort a running execution (sequential or parallel).

    The execution will stop after the current in-flight tasks complete.
    """
    success = qa_service.abort_execution(execution_id)
    if not success:
        raise NotFoundError(f"Execution {execution_id} not found or already completed")

    return {"success": True, "message": f"Abort requested for execution {execution_id}"}


@router.get("/execute/{execution_id}/status")
async def get_execution_status(
    execution_id: str,
):
    """Get the current status of an execution"""
    state = qa_service.get_execution_state(execution_id)
    if not state:
        raise NotFoundError(f"Execution {execution_id} not found")

    return state.to_dict()


@router.get("/executions/active")
async def list_active_executions():
    """List all currently active QA executions"""
    return {
        "executions": qa_service.list_active_executions()
    }


@router.post("/tasks/{task_id}/mark-manual")
async def mark_manual_qa_result(
    task_id: str,
    status: str = Query(..., description="PASS or FAILED"),
    actual_result: str = Query(..., description="Actual result observed"),
    db: AsyncSession = Depends(get_db),
):
    """Mark a manual QA task as passed or failed"""
    result = await db.execute(
        select(QATask).where(QATask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundError(f"QA task {task_id} not found")

    if status.upper() not in ['PASS', 'FAILED']:
        raise HTTPException(status_code=400, detail="Status must be PASS or FAILED")

    task.status = status.upper()
    task.actualResult = actual_result
    task.lastExecutedAt = datetime.now()

    # Update history
    exec_result = {
        'status': task.status,
        'actualResult': actual_result,
        'executionTime': 0,
        'error': None,
    }
    task.executionHistory = qa_service.add_execution_to_history(
        task.executionHistory,
        exec_result,
    )

    await db.commit()

    logger.info(f"Manual QA task {task.key} marked as {status}")
    return {"success": True, "status": task.status}


# ==================== QA Summary ====================

@router.get("/issues/{issue_id}/summary", response_model=QASummary)
async def get_qa_summary_for_issue(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get QA summary for an issue (including all linked QA tasks)"""
    # Get all QA tasks linked to this issue
    result = await db.execute(
        select(QATask)
        .join(QATaskIssueLink)
        .where(QATaskIssueLink.issueId == issue_id)
    )
    tasks = result.scalars().all()

    # Get settings for threshold
    if tasks:
        settings = await get_or_create_settings(db, tasks[0].projectId)
        threshold = settings.passThreshold
    else:
        threshold = 0.9

    # Calculate summary
    task_dicts = [{"status": t.status} for t in tasks]
    summary = qa_service.calculate_summary(task_dicts, threshold)

    return QASummary(**summary)


# ==================== QA Evaluation ====================

def detect_test_area(task: QATask) -> str:
    """Detect the test area based on task content"""
    text = f"{task.title} {task.scenario} {task.expectedResult}".lower()

    if any(kw in text for kw in ['security', 'auth', 'permission', 'xss', 'injection', 'csrf']):
        return 'security'
    if any(kw in text for kw in ['performance', 'load', 'speed', 'latency', 'response time', 'benchmark']):
        return 'performance'
    if any(kw in text for kw in ['accessibility', 'a11y', 'wcag', 'screen reader', 'keyboard navigation', 'aria']):
        return 'accessibility'
    if any(kw in text for kw in ['ui', 'visual', 'layout', 'display', 'render', 'css', 'style']):
        return 'ui'
    if any(kw in text for kw in ['api', 'integration', 'endpoint', 'service', 'external', 'http']):
        return 'integration'

    return 'functional'


def detect_flaky_tests(tasks: list[QATask]) -> list[str]:
    """Detect tests with inconsistent results"""
    flaky_ids = []

    for task in tasks:
        if not task.executionHistory:
            continue

        try:
            history = json.loads(task.executionHistory)
            # Filter out summary entries
            runs = [h for h in history if not h.get('summary')]

            if len(runs) < 3:
                continue

            # Count status flips
            flips = 0
            for i in range(1, len(runs)):
                if runs[i].get('status') != runs[i-1].get('status'):
                    flips += 1

            # More than 40% flips indicates flaky test
            if flips / (len(runs) - 1) > 0.4:
                flaky_ids.append(task.id)
        except (json.JSONDecodeError, KeyError):
            continue

    return flaky_ids


def calculate_execution_trend(tasks: list[QATask]) -> dict:
    """Calculate execution trend based on history"""
    all_runs = []

    for task in tasks:
        if not task.executionHistory:
            continue

        try:
            history = json.loads(task.executionHistory)
            runs = [h for h in history if not h.get('summary')]

            for run in runs:
                if run.get('timestamp') and run.get('status'):
                    all_runs.append({
                        'timestamp': run['timestamp'],
                        'passed': run['status'] == 'PASS'
                    })
        except (json.JSONDecodeError, KeyError):
            continue

    if len(all_runs) < 2:
        return {'trend': 'stable', 'change': 0}

    # Sort by timestamp
    all_runs.sort(key=lambda r: r['timestamp'])

    # Split into older and newer halves
    midpoint = len(all_runs) // 2
    older_runs = all_runs[:midpoint]
    newer_runs = all_runs[midpoint:]

    older_pass_rate = sum(1 for r in older_runs if r['passed']) / len(older_runs) if older_runs else 0
    newer_pass_rate = sum(1 for r in newer_runs if r['passed']) / len(newer_runs) if newer_runs else 0

    change = (newer_pass_rate - older_pass_rate) * 100

    if change > 5:
        return {'trend': 'up', 'change': change}
    if change < -5:
        return {'trend': 'down', 'change': change}
    return {'trend': 'stable', 'change': change}


@router.get("/issues/{issue_id}/evaluation", response_model=QAEvaluation)
async def get_qa_evaluation(
    issue_id: str,
    include_descendants: bool = Query(False, description="Include QA tasks from all descendant issues"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get comprehensive QA evaluation data for an issue's test plan.

    Returns detailed metrics including:
    - Summary statistics (pass rate, completion, etc.)
    - Coverage analysis by test area
    - Priority and type distribution
    - Quality metrics and overall score
    - Actionable recommendations
    - Execution trend analysis
    - Flaky test detection
    """
    # Get QA tasks
    if include_descendants:
        child_ids = await get_all_child_issue_ids(db, issue_id)
        all_issue_ids = [issue_id] + child_ids
        result = await db.execute(
            select(QATask)
            .join(QATaskIssueLink)
            .where(QATaskIssueLink.issueId.in_(all_issue_ids))
        )
    else:
        result = await db.execute(
            select(QATask)
            .join(QATaskIssueLink)
            .where(QATaskIssueLink.issueId == issue_id)
        )

    tasks = list(result.scalars().unique().all())

    # Get settings for threshold
    if tasks:
        settings = await get_or_create_settings(db, tasks[0].projectId)
        threshold = settings.passThreshold
    else:
        threshold = 0.9

    # Calculate summary
    total = len(tasks)
    passed = len([t for t in tasks if t.status == 'PASS'])
    failed = len([t for t in tasks if t.status == 'FAILED'])
    not_done = len([t for t in tasks if t.status == 'NOT_DONE'])
    in_progress = len([t for t in tasks if t.status == 'IN_PROGRESS'])
    executed = passed + failed
    pass_rate = (passed / executed * 100) if executed > 0 else 0
    completion_rate = (executed / total * 100) if total > 0 else 0
    is_passing = (pass_rate / 100) >= threshold if executed > 0 else False

    summary = QASummary(
        totalTasks=total,
        passedTasks=passed,
        failedTasks=failed,
        notDoneTasks=not_done,
        inProgressTasks=in_progress,
        passRate=pass_rate,
        isPassingThreshold=is_passing,
    )

    # Calculate area coverage
    area_stats: dict = {}
    area_names = {
        'functional': 'Functional',
        'ui': 'UI/UX',
        'integration': 'Integration',
        'performance': 'Performance',
        'security': 'Security',
        'accessibility': 'Accessibility',
    }

    for task in tasks:
        area = detect_test_area(task)
        if area not in area_stats:
            area_stats[area] = {'total': 0, 'passed': 0, 'failed': 0, 'notDone': 0}
        area_stats[area]['total'] += 1
        if task.status == 'PASS':
            area_stats[area]['passed'] += 1
        elif task.status == 'FAILED':
            area_stats[area]['failed'] += 1
        else:
            area_stats[area]['notDone'] += 1

    area_coverage = []
    for area, stats in sorted(area_stats.items(), key=lambda x: -x[1]['total']):
        executed_in_area = stats['passed'] + stats['failed']
        area_pass_rate = (stats['passed'] / executed_in_area * 100) if executed_in_area > 0 else 0
        area_coverage.append(AreaCoverage(
            area=area,
            name=area_names.get(area, area.title()),
            total=stats['total'],
            passed=stats['passed'],
            failed=stats['failed'],
            notDone=stats['notDone'],
            passRate=area_pass_rate,
        ))

    # Calculate priority distribution
    priority_order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
    priority_distribution = []
    for priority in priority_order:
        matching = [t for t in tasks if t.priority == priority]
        priority_distribution.append(PriorityDistribution(
            priority=priority,
            count=len(matching),
            passed=len([t for t in matching if t.status == 'PASS']),
            failed=len([t for t in matching if t.status == 'FAILED']),
            percentage=(len(matching) / total * 100) if total > 0 else 0,
        ))

    # Calculate type distribution
    automated = [t for t in tasks if t.type == 'AUTOMATED']
    manual = [t for t in tasks if t.type == 'MANUAL']
    type_distribution = [
        TypeDistribution(
            type='AUTOMATED',
            count=len(automated),
            passed=len([t for t in automated if t.status == 'PASS']),
            failed=len([t for t in automated if t.status == 'FAILED']),
            percentage=(len(automated) / total * 100) if total > 0 else 0,
        ),
        TypeDistribution(
            type='MANUAL',
            count=len(manual),
            passed=len([t for t in manual if t.status == 'PASS']),
            failed=len([t for t in manual if t.status == 'FAILED']),
            percentage=(len(manual) / total * 100) if total > 0 else 0,
        ),
    ]

    # Calculate quality metrics
    quality_metrics = []

    # Pass rate score
    pass_rate_score = min(100, pass_rate)
    quality_metrics.append(QualityMetric(
        id='pass-rate',
        label='Pass Rate',
        value=pass_rate_score,
        maxValue=100,
        status='good' if pass_rate_score >= 80 else ('warning' if pass_rate_score >= 60 else 'critical'),
        description=f'{passed} of {executed} executed tests passed',
    ))

    # Completion score
    completion_score = min(100, completion_rate)
    quality_metrics.append(QualityMetric(
        id='completion',
        label='Completion',
        value=completion_score,
        maxValue=100,
        status='good' if completion_score >= 80 else ('warning' if completion_score >= 50 else 'critical'),
        description=f'{executed} of {total} tests executed',
    ))

    # Coverage score (based on areas covered)
    covered_areas = len([a for a in area_coverage if a.total > 0])
    coverage_score = round((covered_areas / 6) * 100)
    quality_metrics.append(QualityMetric(
        id='coverage',
        label='Coverage',
        value=coverage_score,
        maxValue=100,
        status='good' if coverage_score >= 50 else ('warning' if coverage_score >= 33 else 'critical'),
        description=f'{covered_areas} of 6 test areas covered',
    ))

    # Priority focus score
    critical_high = len([t for t in tasks if t.priority in ('CRITICAL', 'HIGH')])
    priority_score = min(100, round((critical_high / total * 100 * 2) if total > 0 else 0))
    quality_metrics.append(QualityMetric(
        id='priority',
        label='Priority Focus',
        value=priority_score,
        maxValue=100,
        status='good' if priority_score >= 40 else ('warning' if priority_score >= 20 else 'critical'),
        description=f'{critical_high} critical/high priority tests',
    ))

    # Overall score
    overall_score = round(sum(m.value for m in quality_metrics) / len(quality_metrics)) if quality_metrics else 0

    # Detect flaky tests
    flaky_ids = detect_flaky_tests(tasks)

    # Calculate trend
    trend_data = calculate_execution_trend(tasks)
    trend = ExecutionTrend(trend=trend_data['trend'], change=trend_data['change'])

    # Generate recommendations
    recommendations = []

    # Low pass rate
    if pass_rate < threshold * 100 and executed > 0:
        recommendations.append(Recommendation(
            id='low-pass-rate',
            type='execution',
            severity='critical',
            title='Pass rate below threshold',
            description=f'Current pass rate ({pass_rate:.0f}%) is below the {threshold * 100:.0f}% threshold.',
            action='View failed tests',
            affectedTaskIds=[t.id for t in tasks if t.status == 'FAILED'],
        ))

    # Incomplete tests
    if completion_rate < 100 and not_done > 0:
        recommendations.append(Recommendation(
            id='incomplete',
            type='execution',
            severity='warning' if completion_rate < 50 else 'info',
            title=f'{not_done} tests not executed',
            description='Complete all tests for comprehensive coverage assessment.',
            action='Run pending tests',
            affectedTaskIds=[t.id for t in tasks if t.status == 'NOT_DONE'],
        ))

    # Flaky tests
    if flaky_ids:
        recommendations.append(Recommendation(
            id='flaky',
            type='flaky',
            severity='warning',
            title=f'{len(flaky_ids)} flaky test{"s" if len(flaky_ids) > 1 else ""} detected',
            description='Tests with inconsistent results may indicate unstable functionality.',
            action='Review flaky tests',
            affectedTaskIds=flaky_ids,
        ))

    # Coverage gaps
    missing_areas = [a for a in area_names.keys() if a not in [ac.area for ac in area_coverage]]
    if missing_areas and total > 5:
        recommendations.append(Recommendation(
            id='coverage-gap',
            type='coverage',
            severity='info',
            title='Coverage gaps detected',
            description=f'No tests for: {", ".join(area_names[a] for a in missing_areas)}',
        ))

    # Low priority focus
    if critical_high == 0 and total > 3:
        recommendations.append(Recommendation(
            id='priority-focus',
            type='priority',
            severity='info',
            title='Consider adding high-priority tests',
            description='No critical or high priority tests in the test plan.',
        ))

    # Declining trend
    if trend.trend == 'down' and abs(trend.change) > 10:
        recommendations.append(Recommendation(
            id='declining-trend',
            type='improvement',
            severity='warning',
            title='Declining pass rate trend',
            description=f'Pass rate has decreased by {abs(trend.change):.0f}% over recent runs.',
        ))

    return QAEvaluation(
        summary=summary,
        areaCoverage=area_coverage,
        priorityDistribution=priority_distribution,
        typeDistribution=type_distribution,
        qualityMetrics=quality_metrics,
        overallScore=overall_score,
        recommendations=recommendations,
        trend=trend,
        flakyTestIds=flaky_ids,
    )


@router.get("/projects/{project_id}/kanban")
async def get_qa_kanban_data(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get QA-related issues grouped by QA status for Kanban view.

    Shows top-level QA-eligible items:
    - FEATUREs that have development work completed in the descendant tree
    - BUGs (CB-1942): standalone QA-able units; show whenever the BUG itself
      is at COMPLETED_WAITING_QA or has any failed QA tasks

    Columns:
    - Waiting for QA: items with descendants (FEATURE) or self (BUG) in
      COMPLETED_WAITING_QA status
    - Pass: items where all QA tasks have passed
    - Failed: items with failed QA tasks
    """
    from utils.db_queries import get_all_descendant_ids

    # Get FEATUREs and BUGs for the project. BUGs are top-level QA units in
    # their own right — they don't typically have descendants but the BUG
    # itself can be at CWQ and needs a QA pass.
    result = await db.execute(
        select(Issue)
        .where(
            and_(
                Issue.projectId == project_id,
                func.upper(Issue.type).in_(("FEATURE", "BUG")),
            )
        )
        .options(selectinload(Issue.qaTaskLinks))
    )
    features = result.scalars().unique().all()
    logger.info(
        f"QA Kanban project {project_id}: Found {len(features)} FEATURE/BUG items"
    )

    # Determine which items have QA work waiting. Two paths:
    #   - FEATURE: walk descendants for any CWQ child OR feature itself CWQ
    #   - BUG: standalone — appears whenever the BUG itself is CWQ. If a BUG
    #     has descendants (rare but possible), evaluate them too.
    features_with_waiting_qa = []
    for feature in features:
        descendant_ids = await get_all_descendant_ids(db, feature.id)

        if descendant_ids:
            result = await db.execute(
                select(func.count(Issue.id))
                .where(
                    and_(
                        Issue.id.in_(descendant_ids),
                        Issue.status == "COMPLETED_WAITING_QA",
                    )
                )
            )
            waiting_count = result.scalar() or 0
        else:
            waiting_count = 0

        # Include the issue if its own status is CWQ (standalone BUG case),
        # or if any descendant is CWQ (FEATURE case).
        if waiting_count > 0 or feature.status == "COMPLETED_WAITING_QA":
            features_with_waiting_qa.append(
                (feature, waiting_count, len(descendant_ids))
            )

    logger.info(f"QA Kanban: Found {len(features_with_waiting_qa)} item(s) (FEATURE/BUG) with COMPLETED_WAITING_QA")

    # Use all features for processing (those with waiting items + those with QA tasks)
    all_issues = features

    # Get settings
    settings = await get_or_create_settings(db, project_id)

    # Group issues by QA status
    waiting_for_qa = []
    passed = []
    failed = []

    # OPTIMIZATION: Batch fetch all QA tasks for all issue trees in a single set of queries
    from utils.db_queries import batch_get_qa_tasks_for_issue_trees
    issue_ids = [issue.id for issue in all_issues]
    qa_tasks_by_issue = await batch_get_qa_tasks_for_issue_trees(db, issue_ids)

    # Track which features have waiting QA items
    features_with_waiting = {f.id for f, _, _ in features_with_waiting_qa}

    for issue in all_issues:
        # Get pre-fetched QA tasks for this issue tree
        qa_tasks = qa_tasks_by_issue.get(issue.id, [])

        # Build issue data
        if not qa_tasks:
            qa_summary = {
                "totalTasks": 0,
                "passedTasks": 0,
                "failedTasks": 0,
                "notDoneTasks": 0,
                "inProgressTasks": 0,
                "passRate": 0,
                "isPassingThreshold": False,
            }
        else:
            task_dicts = [{"status": t.status} for t in qa_tasks]
            qa_summary = qa_service.calculate_summary(task_dicts, settings.passThreshold)

        # Get waiting count for this feature
        waiting_info = next(((f, wc, tc) for f, wc, tc in features_with_waiting_qa if f.id == issue.id), None)
        waiting_count = waiting_info[1] if waiting_info else 0
        total_descendants = waiting_info[2] if waiting_info else 0

        issue_data = {
            "id": issue.id,
            "key": issue.key,
            "title": issue.title,
            "type": issue.type,
            "status": issue.status,
            "qaSummary": qa_summary,
            "waitingForQACount": waiting_count,  # Number of children waiting for QA
            "totalDescendants": total_descendants,  # Total children count
        }

        # Categorize based on whether FEATURE has items waiting for QA
        if issue.id in features_with_waiting:
            # FEATURE has children with COMPLETED_WAITING_QA status
            if qa_summary["failedTasks"] > 0:
                failed.append(issue_data)
            else:
                waiting_for_qa.append(issue_data)
        elif qa_summary["failedTasks"] > 0:
            # Has failed QA tasks
            failed.append(issue_data)
        elif qa_summary["isPassingThreshold"] and qa_summary["notDoneTasks"] == 0 and qa_summary["totalTasks"] > 0:
            # All QA tasks passed
            passed.append(issue_data)

    return {
        "waitingForQA": waiting_for_qa,
        "passed": passed,
        "failed": failed,
        "settings": {
            "projectId": project_id,
            "passThreshold": settings.passThreshold,
            "autoCreateBugs": settings.autoCreateBugs,
        },
    }


# ==================== Backfill ====================

BACKFILL_MAX_PER_CALL = 50  # Cap Claude API fan-out per call


@router.post("/projects/{project_id}/backfill")
async def backfill_qa_plans(
    project_id: str,
    limit: int = Query(BACKFILL_MAX_PER_CALL, ge=1, le=BACKFILL_MAX_PER_CALL),
    db: AsyncSession = Depends(get_db),
):
    """Fire QA plan generation for issues stuck in COMPLETED_WAITING_QA with no QATasks.

    Reconciles the state where a cascade transitioned issues to
    COMPLETED_WAITING_QA but no QA tasks were ever generated (e.g. because the
    cascade helper skipped the trigger hook). Idempotent: safe to re-run.

    Caps at `limit` (default/max 50) to bound Claude API fan-out. If more
    eligible issues exist, re-run until `deferred` reaches 0.
    """
    from app.background import create_tracked_task
    from api.issues import trigger_qa_generation

    # Count total eligible
    linked_subq = select(QATaskIssueLink.issueId).distinct().subquery()
    count_result = await db.execute(
        select(func.count(Issue.id)).where(
            and_(
                Issue.projectId == project_id,
                Issue.status == "COMPLETED_WAITING_QA",
                ~Issue.id.in_(select(linked_subq.c.issueId)),
            )
        )
    )
    total_eligible = int(count_result.scalar_one() or 0)

    result = await db.execute(
        select(Issue.id, Issue.key, Issue.projectId)
        .where(
            and_(
                Issue.projectId == project_id,
                Issue.status == "COMPLETED_WAITING_QA",
                ~Issue.id.in_(select(linked_subq.c.issueId)),
            )
        )
        .order_by(Issue.createdAt.asc())
        .limit(limit)
    )
    targets = result.fetchall()

    scheduled: list[str] = []
    for row in targets:
        create_tracked_task(
            trigger_qa_generation(row[0], row[1], row[2]),
            name=f"qa-backfill-{row[1]}",
        )
        scheduled.append(row[1])

    deferred = max(total_eligible - len(scheduled), 0)
    logger.info(
        f"Backfill scheduled {len(scheduled)} QA generations for project {project_id} "
        f"(deferred={deferred}, total_eligible={total_eligible})"
    )
    return {
        "projectId": project_id,
        "totalEligible": total_eligible,
        "scheduled": len(scheduled),
        "deferred": deferred,
        "issueKeys": scheduled,
    }


# ==================== QA Settings ====================

@router.get("/projects/{project_id}/settings", response_model=QASettingsResponse)
async def get_qa_settings(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get QA settings for a project"""
    settings = await get_or_create_settings(db, project_id)
    return settings


@router.put("/projects/{project_id}/settings", response_model=QASettingsResponse)
async def update_qa_settings(
    project_id: str,
    settings_data: QASettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update QA settings for a project"""
    settings = await get_or_create_settings(db, project_id)

    update_data = settings_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)

    await db.commit()
    await db.refresh(settings)

    logger.info(f"Updated QA settings for project {project_id}")
    return settings


# ==================== Bug Creation ====================

@router.post("/tasks/{task_id}/create-bug")
async def create_bug_from_qa_failure(
    task_id: str,
    additional_context: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Create a BUG issue from a failed QA task"""
    from models import IssueSequence as IssueSeq

    # Get the QA task
    result = await db.execute(
        select(QATask)
        .where(QATask.id == task_id)
        .options(selectinload(QATask.linkedIssues))
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundError(f"QA task {task_id} not found")

    if task.status != "FAILED":
        raise HTTPException(status_code=400, detail="Can only create bugs from failed QA tasks")

    # Get the linked issue for context
    issue = None
    if task.linkedIssues:
        result = await db.execute(
            select(Issue).where(Issue.id == task.linkedIssues[0].issueId)
        )
        issue = result.scalar_one_or_none()

    # Build bug description
    description = qa_service.build_bug_description(
        {
            "key": task.key,
            "title": task.title,
            "scenario": task.scenario,
            "expectedResult": task.expectedResult,
            "actualResult": task.actualResult,
        },
        {"key": issue.key, "title": issue.title, "type": issue.type} if issue else None,
    )

    if additional_context:
        description += f"\n### Additional Context\n{additional_context}\n"

    # Get next issue key
    result = await db.execute(
        select(IssueSeq).where(IssueSeq.projectId == task.projectId)
    )
    sequence = result.scalar_one_or_none()

    if not sequence:
        raise HTTPException(status_code=500, detail="Issue sequence not found")

    sequence.lastNumber += 1
    bug_key = f"{sequence.prefix}-{sequence.lastNumber}"

    # Create the bug issue
    bug = Issue(
        id=str(uuid.uuid4()),
        projectId=task.projectId,
        key=bug_key,
        sequence=sequence.lastNumber,
        title=f"[QA Bug] {task.title}",
        description=description,
        type="BUG",
        status="BACKLOG",
        priority="HIGH",
        parentId=issue.id if issue else None,
    )
    db.add(bug)

    # Update QA task with bug reference
    task.bugIssueId = bug.id

    await db.commit()

    logger.info(f"Created bug {bug_key} from QA task {task.key}")
    return {
        "success": True,
        "bugId": bug.id,
        "bugKey": bug_key,
    }
