"""
Execution API - Endpoints for AI task execution
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List, Literal
from pydantic import BaseModel
from datetime import datetime
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

from app.background import create_tracked_task
from models import get_db, Issue, Project, Comment, Activity
from models.database import AsyncSessionLocal
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
from utils.db_queries import (
    bulk_update_descendant_status_detailed,
    cascade_status_to_parents_detailed,
)
from api.issues import trigger_qa_generation
from services.autopilot_service import autopilot_service
from services.autopilot_queue_service import autopilot_queue_service
from services.session_pool import session_pool
from utils.db_queries import bulk_update_descendant_status, get_all_descendants_with_details, cascade_status_to_parents, cascade_done_to_parents, cascade_in_progress_to_parents

router = APIRouter(prefix="/execute")


class ExecutionRequest(BaseModel):
    """Request to start execution"""
    provider: str  # "claude_code" or "local_ai"
    execution_mode: str = "implement"  # "implement" | "audit" | "rewrite"
    force: bool = False  # bypass status check in dependency analyzer


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
        output_lines=len(session.get_output_snapshot()),
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

    # Validate execution_mode
    valid_modes = {"implement", "audit", "rewrite"}
    execution_mode = request.execution_mode
    if execution_mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid execution_mode: {execution_mode}. Must be one of {', '.join(sorted(valid_modes))}")

    # For rewrite mode: reset issue status to TODO so it gets a fresh implementation
    if execution_mode == "rewrite":
        issue.status = "TODO"
        issue.updatedAt = datetime.utcnow()
        await db.commit()

    # Build rich execution context (parent chain + siblings + description)
    rich_prompt = await build_execution_context(
        db=db,
        issue_id=issue.id,
        issue_key=issue.key,
        issue_title=issue.title,
        issue_type=issue.type,
        issue_description=issue.description or "",
    )

    # For audit mode: wrap the prompt with audit instructions
    if execution_mode == "audit":
        rich_prompt = (
            "AUDIT MODE: You are reviewing existing code, NOT implementing from scratch.\n\n"
            "Review the existing implementation of the following task. "
            "Check for: correctness, security vulnerabilities, edge cases, "
            "code quality, and adherence to project conventions.\n\n"
            "Report your findings clearly. Only modify code if you find critical bugs "
            "or security vulnerabilities that must be fixed immediately.\n\n"
            "---\n\n"
            + rich_prompt
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

    # Determine force flag: only audit and rewrite modes bypass status check
    # The client-provided force flag is ignored to prevent bypassing status guards
    force = execution_mode in ("audit", "rewrite")

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
        force=force,
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
            qa_targets = [{"id": issue.id, "key": issue.key, "projectId": issue.projectId}]
            # Cascade to parent containers (detailed — returns transitioned ancestors)
            qa_targets += await cascade_status_to_parents_detailed(
                db, session.issue_id, "COMPLETED_WAITING_QA"
            )
            await db.commit()
            logger.info(f"[AUTO-COMPLETE] Marked {session.issue_key} as COMPLETED_WAITING_QA after execution")
            # Fire QA generation hook for each newly-transitioned issue
            for t in qa_targets:
                create_tracked_task(
                    trigger_qa_generation(t["id"], t["key"], t["projectId"]),
                    name=f"qa-gen-{t['key']}",
                )

    return ExecutionOutputResponse(
        session_id=session_id,
        status=session.status.value,
        output=output,
        total_lines=len(session.get_output_snapshot()),
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
    Mark execution as complete and update issue status to COMPLETED_WAITING_QA.
    Also marks all child issues as COMPLETED_WAITING_QA (cascading completion).
    Issues should go through QA before being marked DONE.
    """
    session = terminal_service.get_session(session_id)

    # Get issue_id from session or query param
    target_issue_id = session.issue_id if session else issue_id
    issue_key = session.issue_key if session else "Unknown"

    if not target_issue_id:
        raise HTTPException(status_code=404, detail="Session not found and no issue_id provided")

    # Update issue status to COMPLETED_WAITING_QA (not DONE — needs QA first)
    result = await db.execute(
        select(Issue).where(Issue.id == target_issue_id)
    )
    issue = result.scalar_one_or_none()

    children_updated = 0
    qa_targets: list[dict] = []
    if issue:
        issue.status = "COMPLETED_WAITING_QA"
        issue.updatedAt = datetime.utcnow()
        issue_key = issue.key
        qa_targets.append({"id": issue.id, "key": issue.key, "projectId": issue.projectId})

        # Cascade: Mark all descendants as COMPLETED_WAITING_QA (detailed — returns transitions)
        descendant_transitions = await bulk_update_descendant_status_detailed(
            db, target_issue_id, "COMPLETED_WAITING_QA", datetime.utcnow()
        )
        qa_targets += descendant_transitions
        children_updated = len(descendant_transitions)

        # Cascade status upward to parent containers (detailed)
        qa_targets += await cascade_status_to_parents_detailed(
            db, target_issue_id, "COMPLETED_WAITING_QA"
        )

        await db.commit()

        # Fire QA generation hook for every newly-transitioned issue
        for t in qa_targets:
            create_tracked_task(
                trigger_qa_generation(t["id"], t["key"], t["projectId"]),
                name=f"qa-gen-{t['key']}",
            )

    # Mark session as completed and clean up if it exists
    if session:
        session.status = ExecutionStatus.COMPLETED
        session.completed_at = datetime.utcnow()
        terminal_service.cleanup_session(session_id)

    return {
        "success": True,
        "issue_id": target_issue_id,
        "issue_key": issue_key,
        "status": "COMPLETED_WAITING_QA",
        "children_updated": children_updated
    }


@router.get("/sessions/stream")
async def stream_execution_sessions(request: Request):
    """SSE endpoint for real-time execution session updates.

    Streams execution session data every 500ms as Server-Sent Events.
    Much faster than the 2-second polling interval of GET /sessions.
    Falls back gracefully - clients should use GET /sessions as fallback.
    """
    async def event_generator():
        last_data = None
        while True:
            if await request.is_disconnected():
                logger.debug("SSE client disconnected from stream_execution_sessions")
                break
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

            except Exception:
                logger.exception("SSE stream_execution_sessions error")
                # Send generic error to client — details logged server-side only
                yield f"event: error\ndata: {json.dumps({'error': 'internal_error'})}\n\n"
                break  # Exit on error — don't loop forever on a broken state

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


@router.get("/sessions/active")
async def get_active_sessions():
    """List all currently running execution sessions."""
    running = terminal_service.get_running_sessions()
    return {
        "success": True,
        "sessions": [
            {
                "session_id": s.id,
                "issue_id": s.issue_id,
                "issue_key": s.issue_key,
                "status": s.status.value,
                "started_at": s.started_at.isoformat() if s.started_at else None,
            }
            for s in running
        ],
    }


@router.post("/sessions/stop-all")
async def stop_all_sessions():
    """Stop all currently running execution sessions."""
    running = terminal_service.get_running_sessions()
    stopped = []
    for session in running:
        success = await terminal_service.stop_execution(session.id)
        if success:
            stopped.append({"session_id": session.id, "issue_key": session.issue_key})
    return {"success": True, "stopped_count": len(stopped), "stopped": stopped}


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


# ===========================================================================
# Backend-Driven AutoPilot Queue (CB-1667)
# ===========================================================================

class QueueTaskInput(BaseModel):
    """A single task to add to the queue."""
    issue_id: str
    issue_key: str
    issue_title: str
    execution_mode: Literal["implement", "audit", "rewrite", "skip"] = "implement"
    force: bool = False


class CreateQueueRequest(BaseModel):
    """Request to create and start a backend-driven autopilot queue."""
    feature_id: str
    feature_key: str
    project_id: str
    tasks: List[QueueTaskInput]
    config: Optional[dict] = None  # {on_success, on_fail, max_retries}
    provider: str = "claude_code"
    model: Optional[str] = None
    auto_start: bool = True


class AbortQueueRequest(BaseModel):
    """Request to abort a queue with action for remaining tasks."""
    action: Literal["leave", "mark_failed", "mark_skipped", "reset_todo"] = "leave"


class SwitchModelRequest(BaseModel):
    """Request to switch the execution provider/model."""
    provider: str
    model: Optional[str] = None


class WaitForResetRequest(BaseModel):
    """Request to auto-resume after token reset."""
    reset_time: Optional[str] = None  # e.g. "3:00 PM"


@router.post("/queue")
async def create_queue(
    request: CreateQueueRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a backend-driven autopilot queue and optionally start it.

    The queue executes tasks sequentially in the backend, independent of
    the frontend browser state.  The frontend tracks progress via SSE or polling.
    """
    # Check for existing active queue
    active = autopilot_queue_service.get_active_queue()
    if active and active.status in ("running", "paused", "waiting_reset"):
        raise HTTPException(
            status_code=409,
            detail=f"Queue {active.id} is already active ({active.status.value}). "
                   "Abort it first before starting a new one.",
        )

    # Validate project exists and get path
    project_result = await db.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate feature exists
    feature_result = await db.execute(
        select(Issue).where(Issue.id == request.feature_id)
    )
    feature = feature_result.scalar_one_or_none()
    if not feature:
        raise HTTPException(status_code=404, detail="Feature issue not found")

    # Validate task count
    MAX_QUEUE_TASKS = 200
    if len(request.tasks) == 0:
        raise HTTPException(status_code=400, detail="At least one task is required")
    if len(request.tasks) > MAX_QUEUE_TASKS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many tasks ({len(request.tasks)}). Maximum is {MAX_QUEUE_TASKS}",
        )

    # Create the queue (convert Pydantic models to dicts for service)
    tasks_data = [t.model_dump() for t in request.tasks]
    queue = autopilot_queue_service.create_queue(
        feature_id=request.feature_id,
        feature_key=request.feature_key,
        project_id=request.project_id,
        project_path=project.path,
        tasks=tasks_data,
        config=request.config,
        provider=request.provider,
        model=request.model,
    )

    # Auto-start if requested
    if request.auto_start:
        queue._task = create_tracked_task(
            autopilot_queue_service.run_queue(queue.id),
            name=f"autopilot-queue-{queue.id}",
        )

    return autopilot_queue_service.get_queue_status(queue.id)


@router.get("/queue/active")
async def get_active_queue():
    """Get the currently active autopilot queue status."""
    active = autopilot_queue_service.get_active_queue()
    if not active:
        return {"active": False, "queue": None}
    return {
        "active": True,
        "queue": autopilot_queue_service.get_queue_status(active.id),
    }


@router.get("/queue/available-models")
async def get_available_models():
    """Get available execution providers and models."""
    models = [
        {
            "provider": "claude_code",
            "label": "Claude Code CLI",
            "description": "Uses Claude Code CLI with user subscription auth",
            "models": [],  # CLI uses subscription, no model selection
        },
    ]

    # Check if local AI (Ollama) is available
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                ollama_data = resp.json()
                ollama_models = [
                    m["name"] for m in ollama_data.get("models", [])
                ]
                models.append({
                    "provider": "local_ai",
                    "label": "Ollama (Local AI)",
                    "description": "Local AI via Ollama",
                    "models": ollama_models,
                })
    except Exception:
        pass  # Ollama not available

    return {"providers": models}


@router.get("/queue/{queue_id}")
async def get_queue_status(queue_id: str):
    """Get full status for a specific autopilot queue."""
    status = autopilot_queue_service.get_queue_status(queue_id)
    if not status:
        raise HTTPException(status_code=404, detail="Queue not found")
    return status


@router.post("/queue/{queue_id}/pause")
async def pause_queue(queue_id: str):
    """Pause the queue.  The current task finishes, then the queue waits."""
    success = autopilot_queue_service.pause_queue(queue_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot pause — queue is not running or does not exist",
        )
    return {"success": True, "status": "paused"}


@router.post("/queue/{queue_id}/resume")
async def resume_queue(queue_id: str):
    """Resume a paused or waiting queue."""
    success = autopilot_queue_service.resume_queue(queue_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot resume — queue is not paused or does not exist",
        )
    return {"success": True, "status": "resumed"}


@router.post("/queue/{queue_id}/skip")
async def skip_current_task(queue_id: str):
    """Skip the currently executing task and move to the next one."""
    success = autopilot_queue_service.skip_current(queue_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot skip — queue is not running or does not exist",
        )
    return {"success": True}


@router.post("/queue/{queue_id}/abort")
async def abort_queue(queue_id: str, request: AbortQueueRequest):
    """
    Abort the queue entirely.

    Actions for remaining tasks:
    - "leave": keep current status as-is
    - "mark_failed": mark all pending tasks as FAILED
    - "mark_skipped": mark all pending tasks as SKIPPED
    - "reset_todo": PATCH all pending tasks back to TODO in the database
    """
    # Handle reset_todo action: reset pending issues in DB, then abort with "leave"
    abort_action = request.action
    if request.action == "reset_todo":
        queue = autopilot_queue_service.get_queue(queue_id)
        if queue:
            async with AsyncSessionLocal() as session_db:
                for task in queue.tasks:
                    if task.status.value == "pending":
                        result = await session_db.execute(
                            select(Issue).where(Issue.id == task.issue_id)
                        )
                        issue = result.scalar_one_or_none()
                        if issue and issue.status != "TODO":
                            issue.status = "TODO"
                            issue.updatedAt = datetime.utcnow()
                await session_db.commit()
        abort_action = "leave"

    success = await autopilot_queue_service.abort_queue(queue_id, abort_action)
    if not success:
        raise HTTPException(status_code=404, detail="Queue not found")
    return {"success": True, "status": "aborted", "action": request.action}


@router.post("/queue/{queue_id}/wait-for-reset")
async def wait_for_token_reset(
    queue_id: str,
    request: WaitForResetRequest,
):
    """
    Schedule an automatic resume when tokens reset.

    If reset_time is provided (e.g. "3:00 PM"), the service will sleep
    until that time.  Otherwise it defaults to 60 minutes.
    """
    queue = autopilot_queue_service.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    # Fire and forget — the wait happens in the background, tracked to prevent GC
    create_tracked_task(
        autopilot_queue_service.wait_for_reset(queue_id, request.reset_time),
        name=f"wait-reset-{queue_id}",
    )
    return {
        "success": True,
        "message": f"Auto-resume scheduled (reset_time={request.reset_time or 'default 60min'})",
    }


@router.post("/queue/{queue_id}/switch-model")
async def switch_queue_model(
    queue_id: str,
    request: SwitchModelRequest,
):
    """Switch the execution provider/model and resume the queue."""
    success = autopilot_queue_service.switch_model(
        queue_id, request.provider, request.model
    )
    if not success:
        raise HTTPException(status_code=404, detail="Queue not found")
    return {
        "success": True,
        "provider": request.provider,
        "model": request.model,
    }


@router.get("/queue/{queue_id}/stream")
async def stream_queue_status(queue_id: str, request: Request):
    """SSE endpoint for real-time autopilot queue status updates.

    Streams the full queue state every 2 seconds.
    """
    async def event_generator():
        last_data = None
        while True:
            if await request.is_disconnected():
                logger.debug("SSE client disconnected from stream_queue_status (queue=%s)", queue_id)
                break
            try:
                status = autopilot_queue_service.get_queue_status(queue_id)
                if not status:
                    yield f"event: error\ndata: {json.dumps({'error': 'Queue not found'})}\n\n"
                    break

                data = json.dumps(status)

                # Only send if data changed
                if data != last_data:
                    yield f"data: {data}\n\n"
                    last_data = data
                else:
                    yield ": heartbeat\n\n"

                # If queue is done, send final status and close
                if status["status"] in ("completed", "aborted"):
                    yield f"event: done\ndata: {data}\n\n"
                    break

            except Exception:
                logger.exception("Error in queue SSE stream for %s", queue_id)
                yield f"event: error\ndata: {json.dumps({'error': 'internal_error'})}\n\n"
                break  # Exit on error — don't loop forever on a broken state

            await asyncio.sleep(2.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
