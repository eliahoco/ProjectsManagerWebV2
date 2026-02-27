"""
Execution API - Endpoints for AI task execution
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import asyncio
import json

from models import get_db, Issue, Project, Comment, Activity
import uuid
from services.terminal_service import (
    terminal_service,
    ExecutionProvider,
    ExecutionStatus,
    ExecutionPhase,
    TerminalSession,
)
from services.context_builder import build_execution_context
from services.dependency_analyzer import dependency_analyzer
from services.autopilot_service import autopilot_service
from services.session_pool import session_pool
from utils.db_queries import bulk_update_descendant_status, get_all_descendants_with_details, cascade_status_to_parents, cascade_done_to_parents, cascade_in_progress_to_parents

router = APIRouter(prefix="/execute")


class ExecutionRequest(BaseModel):
    """Request to start execution"""
    provider: str  # "claude_code" or "local_ai"


class ExecutionResponse(BaseModel):
    """Response for execution operations"""
    session_id: str
    issue_id: str
    issue_key: str
    project_id: str = ""
    provider: str
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output_lines: int = 0
    error: Optional[str] = None
    # Progress tracking
    phase: str = "initializing"
    progress_percent: int = 0
    current_action: str = "Starting..."
    # Pipeline tracking
    pipeline_stage: Optional[str] = None
    retry_count: Optional[int] = None
    max_retries: Optional[int] = None


class ExecutionOutputResponse(BaseModel):
    """Response with execution output"""
    session_id: str
    status: str
    output: List[str]
    total_lines: int
    exit_code: Optional[int] = None
    # Progress tracking
    phase: str = "initializing"
    progress_percent: int = 0
    current_action: str = "Starting..."
    files_read: int = 0
    files_written: int = 0
    commands_run: int = 0


class SendInputRequest(BaseModel):
    """Request to send input to execution"""
    text: str


def session_to_response(session: TerminalSession) -> ExecutionResponse:
    """Convert session to response"""
    return ExecutionResponse(
        session_id=session.id,
        issue_id=session.issue_id,
        issue_key=session.issue_key,
        project_id=session.project_id,
        provider=session.provider.value,
        status=session.status.value,
        started_at=session.started_at.isoformat() if session.started_at else None,
        completed_at=session.completed_at.isoformat() if session.completed_at else None,
        output_lines=len(session.output),
        error=session.error,
        phase=session.phase.value,
        progress_percent=session.progress_percent,
        current_action=session.current_action,
    )


@router.post("/issue/{issue_id}", response_model=ExecutionResponse)
async def start_execution(
    issue_id: str,
    request: ExecutionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Start AI execution for an issue.

    Providers:
    - claude_code: Execute with Claude Code CLI
    - local_ai: Execute with local Ollama model
    """
    # Get issue
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()

    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    # Get project for path
    project_result = await db.execute(
        select(Project).where(Project.id == issue.projectId)
    )
    project = project_result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Build rich execution context (parent chain + siblings + description)
    rich_prompt = await build_execution_context(
        db=db,
        issue_id=issue.id,
        issue_key=issue.key,
        issue_title=issue.title,
        issue_type=issue.type,
        issue_description=issue.description or "",
    )

    # Resolve the root feature ID for cache preservation
    from services.context_builder import get_parent_chain
    parent_chain = await get_parent_chain(db, issue.id)
    feature_id = None
    for ancestor in parent_chain:
        if ancestor["type"] == "FEATURE":
            feature_id = ancestor["id"]
            break

    # Determine provider
    try:
        provider = ExecutionProvider(request.provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {request.provider}")

    # Cascade IN_PROGRESS status to all parent containers (STORY, EPIC, FEATURE)
    # This ensures parent issues reflect that work is happening under them
    await cascade_in_progress_to_parents(db, issue.id)
    await db.commit()

    # Start execution with rich context prompt and dependency checking
    session = await terminal_service.start_execution(
        issue_id=issue.id,
        issue_key=issue.key,
        issue_title=issue.title,
        issue_description=issue.description or "",
        issue_type=issue.type,
        provider=provider,
        project_path=project.path,
        project_id=project.id,
        prompt_override=rich_prompt,
        feature_id=feature_id,
        db=db,
    )

    return session_to_response(session)


@router.get("/issue/{issue_id}", response_model=Optional[ExecutionResponse])
async def get_issue_execution(issue_id: str):
    """Get the current execution status for an issue"""
    session = terminal_service.get_session_by_issue(issue_id)
    if not session:
        return None
    return session_to_response(session)


@router.get("/session/{session_id}", response_model=ExecutionResponse)
async def get_execution_session(session_id: str):
    """Get execution session by ID"""
    session = terminal_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session_to_response(session)


@router.get("/session/{session_id}/output", response_model=ExecutionOutputResponse)
async def get_execution_output(
    session_id: str,
    since_line: int = Query(0, ge=0, description="Get output starting from this line"),
    db: AsyncSession = Depends(get_db),
):
    """Get output from an execution session. Auto-marks issue as DONE on successful completion."""
    session = terminal_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    output = terminal_service.get_output(session_id, since_line)

    # Check if this session just completed successfully and needs auto-DONE
    if terminal_service.check_pending_completion(session_id):
        # Auto-mark issue as COMPLETED_WAITING_QA (needs QA verification)
        result = await db.execute(
            select(Issue).where(Issue.id == session.issue_id)
        )
        issue = result.scalar_one_or_none()
        if issue and issue.status not in ("COMPLETED_WAITING_QA", "DONE"):
            issue.status = "COMPLETED_WAITING_QA"
            issue.updatedAt = datetime.utcnow()
            # Cascade to parent containers
            await cascade_status_to_parents(db, session.issue_id, "COMPLETED_WAITING_QA")
            await db.commit()
            print(f"[AUTO-COMPLETE] Marked {session.issue_key} as COMPLETED_WAITING_QA after execution")

    return ExecutionOutputResponse(
        session_id=session_id,
        status=session.status.value,
        output=output,
        total_lines=len(session.output),
        exit_code=session.exit_code,
        phase=session.phase.value,
        progress_percent=session.progress_percent,
        current_action=session.current_action,
        files_read=session.files_read,
        files_written=session.files_written,
        commands_run=session.commands_run,
    )


@router.post("/session/{session_id}/input")
async def send_execution_input(
    session_id: str,
    request: SendInputRequest,
):
    """Send input to a running execution session"""
    session = terminal_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != ExecutionStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Session is not running")

    success = await terminal_service.send_input(session_id, request.text)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send input")

    return {"success": True}


@router.post("/session/{session_id}/stop")
async def stop_execution(session_id: str):
    """Stop a running execution session"""
    session = terminal_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    success = await terminal_service.stop_execution(session_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to stop session")

    return {"success": True, "status": "cancelled"}


@router.post("/session/{session_id}/complete")
async def complete_execution(
    session_id: str,
    issue_id: Optional[str] = Query(None, description="Issue ID to mark as done if session not found"),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark execution as complete and update issue status to DONE.
    Also marks all child issues as DONE (cascading completion).
    Call this when the user confirms the task is finished.
    """
    session = terminal_service.get_session(session_id)

    # Get issue_id from session or query param
    target_issue_id = session.issue_id if session else issue_id
    issue_key = session.issue_key if session else "Unknown"

    if not target_issue_id:
        raise HTTPException(status_code=404, detail="Session not found and no issue_id provided")

    # Update issue status to DONE
    result = await db.execute(
        select(Issue).where(Issue.id == target_issue_id)
    )
    issue = result.scalar_one_or_none()

    children_updated = 0
    if issue:
        issue.status = "DONE"
        issue.completedAt = datetime.utcnow()
        issue_key = issue.key

        # Cascade: Mark all children as DONE using optimized bulk update
        # This uses a single CTE query + bulk UPDATE instead of N recursive queries
        children_updated = await bulk_update_descendant_status(
            db, target_issue_id, "DONE", datetime.utcnow()
        )

        # Also cascade DONE status upward to parent containers
        await cascade_done_to_parents(db, target_issue_id)

        await db.commit()

    # Mark session as completed and clean up if it exists
    if session:
        session.status = ExecutionStatus.COMPLETED
        session.completed_at = datetime.utcnow()
        terminal_service.cleanup_session(session_id)

    return {
        "success": True,
        "issue_id": target_issue_id,
        "issue_key": issue_key,
        "status": "DONE",
        "children_updated": children_updated
    }


@router.get("/sessions/stream")
async def stream_execution_sessions():
    """SSE endpoint for real-time execution session updates.

    Streams execution session data every 500ms as Server-Sent Events.
    Much faster than the 2-second polling interval of GET /sessions.
    Falls back gracefully - clients should use GET /sessions as fallback.
    """
    async def event_generator():
        last_data = None
        while True:
            try:
                sessions = terminal_service.get_all_sessions()
                data = json.dumps([{
                    "session_id": s.id,
                    "issue_id": s.issue_id,
                    "issue_key": s.issue_key,
                    "project_id": s.project_id,
                    "provider": s.provider.value,
                    "status": s.status.value,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "output_lines": len(s.output),
                    "error": s.error,
                    "phase": s.phase.value,
                    "progress_percent": s.progress_percent,
                    "current_action": s.current_action,
                    "pipeline_stage": None,  # TODO: from pipeline executor
                    "retry_count": None,
                    "max_retries": None,
                } for s in sessions])

                # Only send if data changed (avoid unnecessary client processing)
                if data != last_data:
                    yield f"data: {data}\n\n"
                    last_data = data
                else:
                    # Send a heartbeat comment to keep connection alive
                    yield ": heartbeat\n\n"

            except Exception as e:
                # Send error event but keep connection open
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

            # Check every 500ms for updates (much faster than 2s polling)
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/sessions", response_model=List[ExecutionResponse])
async def list_sessions():
    """List all execution sessions"""
    sessions = terminal_service.get_all_sessions()
    return [session_to_response(s) for s in sessions]


@router.delete("/session/{session_id}")
async def cleanup_session(session_id: str):
    """Clean up a completed session"""
    session = terminal_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status == ExecutionStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot cleanup running session")

    terminal_service.cleanup_session(session_id)
    return {"success": True}


class DocumentationRequest(BaseModel):
    """Request for generating execution documentation"""
    include_architecture: bool = True
    include_task_details: bool = True


class DocumentationResponse(BaseModel):
    """Response with generated documentation"""
    issue_id: str
    issue_key: str
    documentation: str
    tasks_documented: int
    comment_id: Optional[str] = None


@router.post("/issue/{issue_id}/generate-documentation", response_model=DocumentationResponse)
async def generate_execution_documentation(
    issue_id: str,
    request: DocumentationRequest = DocumentationRequest(),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate documentation for an Epic/Story execution.

    Collects all child tasks, their descriptions, and completion status,
    then generates a comprehensive documentation summary and adds it as
    a comment to the parent issue.
    """
    # Get the parent issue
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()

    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    if issue.type not in ["EPIC", "STORY"]:
        raise HTTPException(
            status_code=400,
            detail="Documentation generation is only available for Epics and Stories"
        )

    # Collect all child tasks using optimized CTE query (single query instead of N recursive queries)
    descendants = await get_all_descendants_with_details(
        db, issue_id,
        columns=["id", "key", "title", "description", "type", "status", "sequence", "completedAt"]
    )

    all_children = [
        {
            "key": d["key"],
            "title": d["title"],
            "description": d["description"] or "",
            "type": d["type"],
            "status": d["status"],
            "level": d["level"],
            "completed_at": d["completedAt"].isoformat() if d.get("completedAt") else None,
        }
        for d in descendants
    ]

    if not all_children:
        raise HTTPException(
            status_code=400,
            detail="No child tasks found for this issue"
        )

    # Generate documentation
    doc_parts = []

    # Header
    doc_parts.append(f"# Execution Documentation: {issue.key}")
    doc_parts.append(f"\n**{issue.title}**\n")
    doc_parts.append(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")

    # Summary
    completed_count = sum(1 for c in all_children if c["status"] == "DONE")
    total_count = len(all_children)
    doc_parts.append(f"## Summary")
    doc_parts.append(f"- **Total Tasks:** {total_count}")
    doc_parts.append(f"- **Completed:** {completed_count}")
    doc_parts.append(f"- **Completion Rate:** {(completed_count/total_count*100):.0f}%\n")

    # Group by type
    type_groups = {}
    for child in all_children:
        t = child["type"]
        if t not in type_groups:
            type_groups[t] = []
        type_groups[t].append(child)

    # Task breakdown by type
    if request.include_task_details:
        doc_parts.append("## Implementation Details\n")

        type_order = ["STORY", "TASK", "SUBTASK", "BUG"]
        for t in type_order:
            if t in type_groups:
                tasks = type_groups[t]
                doc_parts.append(f"### {t}s ({len(tasks)})\n")

                for task in tasks:
                    status_icon = "✅" if task["status"] == "DONE" else "⏳" if task["status"] == "IN_PROGRESS" else "📋"
                    indent = "  " * task["level"]
                    doc_parts.append(f"{indent}{status_icon} **{task['key']}**: {task['title']}")

                    if task["description"] and len(task["description"]) > 0:
                        # Add brief description (first 200 chars)
                        desc = task["description"][:200]
                        if len(task["description"]) > 200:
                            desc += "..."
                        doc_parts.append(f"{indent}   _{desc}_")
                    doc_parts.append("")

    # Architecture section (inferred from task descriptions)
    if request.include_architecture:
        doc_parts.append("## Architecture & Components\n")

        # Extract component mentions from task titles and descriptions
        components = set()
        patterns = {
            "frontend": ["frontend", "ui", "component", "page", "view", "react", "next"],
            "backend": ["backend", "api", "endpoint", "server", "route"],
            "database": ["database", "db", "model", "schema", "migration", "sql"],
            "testing": ["test", "spec", "e2e", "unit test", "integration"],
            "infrastructure": ["docker", "deploy", "ci/cd", "build", "config"],
            "styling": ["style", "css", "theme", "design", "layout"],
        }

        all_text = " ".join([
            f"{c['title']} {c['description']}" for c in all_children
        ]).lower()

        for category, keywords in patterns.items():
            if any(kw in all_text for kw in keywords):
                components.add(category)

        if components:
            doc_parts.append("Components touched in this implementation:")
            for comp in sorted(components):
                doc_parts.append(f"- {comp.title()}")
            doc_parts.append("")

        # List key files (inferred from task titles)
        file_indicators = [task for task in all_children if any(
            ext in task["title"].lower() or ext in task["description"].lower()
            for ext in [".tsx", ".ts", ".py", ".css", ".json", "component", "page", "api"]
        )]

        if file_indicators:
            doc_parts.append("### Key Areas Modified")
            shown = set()
            for task in file_indicators[:10]:  # Limit to 10
                if task["key"] not in shown:
                    doc_parts.append(f"- {task['key']}: {task['title']}")
                    shown.add(task["key"])
            doc_parts.append("")

    # Final documentation
    documentation = "\n".join(doc_parts)

    # Add as comment to the issue
    comment = Comment(
        id=str(uuid.uuid4()),
        issueId=issue_id,
        author="CodeBoard AI",
        content=documentation,
        updatedAt=datetime.utcnow(),
    )
    db.add(comment)

    # Add activity log
    activity = Activity(
        id=str(uuid.uuid4()),
        issueId=issue_id,
        actor="CodeBoard AI",
        action="DOCUMENTED",
        field="execution",
        newValue=f"Generated documentation for {total_count} tasks",
    )
    db.add(activity)

    # Update issue timestamp
    issue.updatedAt = datetime.utcnow()

    await db.commit()

    return DocumentationResponse(
        issue_id=issue_id,
        issue_key=issue.key,
        documentation=documentation,
        tasks_documented=total_count,
        comment_id=comment.id,
    )


# ===========================================================================
# AutoPilot & Dependency Graph Endpoints
# ===========================================================================

class AutoPilotBatchRequest(BaseModel):
    """Request to execute a batch of tasks via AutoPilot."""
    provider: str = "claude_code"
    max_parallel: int = 0  # 0 = use pool's available slots


class AutoPilotBatchResponse(BaseModel):
    """Response for a batch execution request."""
    parent_id: str
    tasks_started: int
    results: List[dict]


@router.get("/autopilot/{parent_id}/next-batch")
async def get_next_batch(
    parent_id: str,
    max_parallel: int = Query(0, ge=0, description="Max tasks to return (0=pool limit)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the next batch of tasks that can run in parallel under a parent.

    Analyzes dependency constraints and pool capacity to determine which
    leaf tasks (TASK, SUBTASK, BUG) are ready for execution.
    """
    # Validate parent exists
    result = await db.execute(
        select(Issue).where(Issue.id == parent_id)
    )
    parent = result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent issue not found")

    batch = await autopilot_service.get_next_batch(db, parent_id, max_parallel)
    return {
        "parent_id": parent_id,
        "parent_key": parent.key,
        "available_slots": session_pool.available_slots,
        "batch": batch,
        "count": len(batch),
    }


@router.post("/autopilot/{parent_id}/execute-batch", response_model=AutoPilotBatchResponse)
async def execute_batch(
    parent_id: str,
    request: AutoPilotBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Execute the next batch of runnable tasks under a parent in parallel.

    Discovers runnable tasks, starts them all, and returns the results.
    """
    # Validate parent exists and get project
    result = await db.execute(
        select(Issue).where(Issue.id == parent_id)
    )
    parent = result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent issue not found")

    project_result = await db.execute(
        select(Project).where(Project.id == parent.projectId)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get runnable batch
    batch = await autopilot_service.get_next_batch(
        db, parent_id, request.max_parallel
    )

    if not batch:
        return AutoPilotBatchResponse(
            parent_id=parent_id,
            tasks_started=0,
            results=[],
        )

    # Execute the batch
    results = await autopilot_service.execute_batch(
        db=db,
        tasks=batch,
        provider=request.provider,
        project_path=project.path,
        project_id=project.id,
    )

    started = sum(1 for r in results if r.get("status") == "running")

    return AutoPilotBatchResponse(
        parent_id=parent_id,
        tasks_started=started,
        results=results,
    )


@router.get("/autopilot/{parent_id}/status")
async def get_autopilot_status(
    parent_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get comprehensive AutoPilot status for a parent issue.

    Includes progress, running sessions, next batch, pool status,
    and dependency graph.
    """
    status = await autopilot_service.get_autopilot_status(db, parent_id)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    return status


@router.get("/dependencies/{parent_id}/graph")
async def get_dependency_graph(
    parent_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get the dependency graph for all children of a parent issue.

    Returns nodes (issues) and edges (BLOCKS links) for visualization,
    along with which tasks are currently runnable.
    """
    # Validate parent exists
    result = await db.execute(
        select(Issue).where(Issue.id == parent_id)
    )
    parent = result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent issue not found")

    graph = await dependency_analyzer.get_dependency_graph(db, parent_id)
    graph["parent_key"] = parent.key
    graph["parent_title"] = parent.title
    return graph


@router.get("/dependencies/{issue_id}/can-execute")
async def check_can_execute(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Check if a specific issue can execute right now.

    Verifies type, status, and blocking dependency constraints.
    """
    can_run, reason = await dependency_analyzer.can_execute(db, issue_id)
    return {
        "issue_id": issue_id,
        "can_execute": can_run,
        "reason": reason,
    }


@router.get("/pool/status")
async def get_pool_status():
    """Get the current session pool status (capacity, active sessions)."""
    return session_pool.get_pool_status()
