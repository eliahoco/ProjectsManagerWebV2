"""
AI API - Claude-powered issue management
"""

from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import uuid
import logging

from services.ai_service import ai_service
from models import get_db, Issue, IssueSequence, Activity, IssueType, IssueStatus
from services.rag_service import rag_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai")


class BreakdownRequest(BaseModel):
    """Request for feature breakdown"""
    title: str
    description: Optional[str] = None
    parent_type: str = "EPIC"


class SuggestedIssue(BaseModel):
    """Suggested issue from AI"""
    title: str
    type: str
    priority: str
    description: Optional[str] = None
    storyPoints: Optional[int] = None
    parentTitle: Optional[str] = None  # For hierarchical structure
    category: Optional[str] = None  # frontend, backend, database, security, testing


class BreakdownResponse(BaseModel):
    """Response from feature breakdown"""
    suggestions: List[SuggestedIssue]
    parent_title: str
    ai_available: bool
    original_input: Optional[str] = None  # Store original specification for audit


class BugAnalysis(BaseModel):
    """Bug detection analysis"""
    is_bug: bool
    confidence: Optional[float] = None
    severity: Optional[str] = None
    reason: Optional[str] = None


class StatusSuggestion(BaseModel):
    """Status update suggestion"""
    suggested_status: Optional[str] = None
    reason: Optional[str] = None


# New hierarchical breakdown models (CB-107)
class HierarchicalBreakdownRequest(BaseModel):
    """Request body for feature breakdown."""
    project_id: str
    feature_title: str
    feature_description: str
    auto_create: bool = False  # Automatically create issues


class HierarchicalBreakdownResponse(BaseModel):
    """Response from feature breakdown."""
    epic: Optional[dict] = None
    stories: List[dict] = []
    total_tasks: int
    estimated_hours: float
    issues_created: List[str] = []


# Helper functions for issue creation
async def get_next_issue_key(db: AsyncSession, project_id: str) -> tuple[str, int]:
    """Get the next issue key for a project"""
    from sqlalchemy import select

    result = await db.execute(
        select(IssueSequence).where(IssueSequence.projectId == project_id)
    )
    sequence = result.scalar_one_or_none()

    if not sequence:
        # Create new sequence with project name prefix
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

    return key, next_number


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
        logger.warning(f"Failed to embed issue {issue.key} for RAG search: {e}")


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


async def create_issue_from_breakdown(
    db: AsyncSession,
    project_id: str,
    data: dict,
    issue_type: IssueType,
    parent_id: Optional[str]
) -> Issue:
    """Create an issue from breakdown data."""
    key, sequence = await get_next_issue_key(db, project_id)

    issue = Issue(
        id=str(uuid.uuid4()),
        key=key,
        sequence=sequence,
        projectId=project_id,
        title=data["title"],
        description=data.get("description", ""),
        type=issue_type.value,
        status=IssueStatus.BACKLOG.value,
        priority=data.get("priority", "MEDIUM"),
        assignee=None,
        reporter="AI",
        parentId=parent_id,
        estimate=data.get("estimate_hours", 2) * 60 if data.get("estimate_hours") else None,
        storyPoints=data.get("storyPoints"),
        updatedAt=datetime.utcnow(),
    )

    db.add(issue)

    # Log activity
    await log_activity(db, issue.id, "AI", "CREATED")

    return issue


@router.get("/status")
async def ai_status():
    """Check if AI service is available and which provider"""
    return {
        "available": ai_service.is_available(),
        "provider": ai_service.get_provider(),
    }


class ApiKeyUpdate(BaseModel):
    """Request to update the Anthropic API key"""
    api_key: str


@router.get("/api-key")
async def get_api_key():
    """Get the current API key status (masked for security)"""
    masked = ai_service.get_masked_api_key()
    return {
        "configured": bool(masked),
        "masked_key": masked,
        "provider": ai_service.get_provider(),
        "available": ai_service.is_available(),
    }


@router.put("/api-key")
async def update_api_key(request: ApiKeyUpdate):
    """Update the Anthropic API key at runtime and persist to .env"""
    import os
    import re

    api_key = request.api_key.strip()

    # Basic validation
    if not api_key:
        raise HTTPException(status_code=400, detail="API key cannot be empty")

    # Update the service at runtime
    ai_service.set_api_key(api_key)

    # Persist to .env file
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    try:
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                content = f.read()
            # Replace existing key or add new one
            if re.search(r"^ANTHROPIC_API_KEY=.*$", content, re.MULTILINE):
                content = re.sub(
                    r"^ANTHROPIC_API_KEY=.*$",
                    f"ANTHROPIC_API_KEY={api_key}",
                    content,
                    flags=re.MULTILINE,
                )
            else:
                content += f"\nANTHROPIC_API_KEY={api_key}\n"
            with open(env_path, "w") as f:
                f.write(content)
            logger.info("Anthropic API key updated and persisted to .env")
        else:
            logger.warning(f".env file not found at {env_path}, key set in memory only")
    except Exception as e:
        logger.warning(f"Failed to persist API key to .env: {e}")
        # Key is still set in memory, just won't survive restart

    # Test the key by checking availability
    available = ai_service.is_available()

    return {
        "success": True,
        "configured": True,
        "masked_key": ai_service.get_masked_api_key(),
        "available": available,
        "provider": ai_service.get_provider(),
    }


@router.delete("/api-key")
async def remove_api_key():
    """Remove the Anthropic API key"""
    import os
    import re

    ai_service.set_api_key("")

    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    try:
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                content = f.read()
            content = re.sub(
                r"^ANTHROPIC_API_KEY=.*$",
                "ANTHROPIC_API_KEY=",
                content,
                flags=re.MULTILINE,
            )
            with open(env_path, "w") as f:
                f.write(content)
    except Exception as e:
        logger.warning(f"Failed to clear API key from .env: {e}")

    return {"success": True, "configured": False}


@router.get("/ollama/models")
async def list_ollama_models():
    """List available Ollama models"""
    available = ai_service.is_ollama_available()
    models = ai_service.get_ollama_models() if available else []
    return {
        "available": available,
        "models": models,
        "current_model": ai_service.get_ollama_model(),
    }


class OllamaModelSelect(BaseModel):
    """Request to select an Ollama model"""
    model: str


@router.put("/ollama/model")
async def select_ollama_model(request: OllamaModelSelect):
    """Set the preferred Ollama model"""
    ai_service.set_ollama_model(request.model)
    return {
        "success": True,
        "model": request.model,
        "provider": ai_service.get_provider(),
    }


@router.post("/api-key/test")
async def test_api_key():
    """Test the current API key by making a minimal API call"""
    if not ai_service.is_available():
        return {
            "success": False,
            "error": "No AI provider available. Please configure an API key.",
        }

    try:
        import asyncio
        import concurrent.futures

        provider = ai_service.get_provider()
        if provider.startswith("claude"):
            # Run the sync API call in a thread to avoid blocking the event loop
            client = ai_service.anthropic_client

            def _test_call():
                return client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=5,
                    messages=[{"role": "user", "content": "Say OK"}],
                )

            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                response = await asyncio.wait_for(
                    loop.run_in_executor(pool, _test_call),
                    timeout=10.0,
                )
            return {
                "success": True,
                "provider": provider,
                "message": "Claude API key is valid and working",
            }
        else:
            # Ollama - just check status
            return {
                "success": True,
                "provider": provider,
                "message": f"Connected to {provider}",
            }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Connection timed out. The API may be temporarily unavailable.",
        }
    except Exception as e:
        error_msg = str(e)
        logger.warning(f"API key test failed: {error_msg}")

        # Parse specific error types
        if "credit balance" in error_msg.lower() or "billing" in error_msg.lower():
            return {
                "success": False,
                "error": "API key is valid but account has insufficient credits. Please add credits at console.anthropic.com.",
            }
        if "authentication" in error_msg.lower() or "invalid" in error_msg.lower() or "api_key" in error_msg.lower():
            return {
                "success": False,
                "error": "Invalid API key. Please check and try again.",
            }
        if "rate_limit" in error_msg.lower():
            return {
                "success": False,
                "error": "Rate limited. The key is valid but temporarily throttled. Try again shortly.",
            }
        return {
            "success": False,
            "error": f"API test failed: {error_msg[:200]}",
        }


@router.post("/{project_id}/breakdown", response_model=BreakdownResponse)
async def breakdown_feature(project_id: str, request: BreakdownRequest):
    """
    Break down a feature/epic into smaller tasks using AI.
    Returns suggested child issues.
    """
    # Combine title and description as the original input for audit
    original_input = f"Title: {request.title}"
    if request.description:
        original_input += f"\n\nDescription:\n{request.description}"

    if not ai_service.is_available():
        return BreakdownResponse(
            suggestions=[],
            parent_title=request.title,
            ai_available=False,
            original_input=original_input,
        )

    suggestions = await ai_service.breakdown_feature(
        project_id=project_id,
        title=request.title,
        description=request.description,
        parent_type=request.parent_type,
    )

    return BreakdownResponse(
        suggestions=[SuggestedIssue(**s) for s in suggestions],
        parent_title=request.title,
        ai_available=True,
        original_input=original_input,
    )


@router.post("/detect-bug", response_model=BugAnalysis)
async def detect_bug(
    title: str = Query(..., description="Issue title"),
    description: Optional[str] = Query(None, description="Issue description"),
):
    """
    Analyze if an issue description indicates a bug.
    Returns bug analysis with severity.
    """
    if not ai_service.is_available():
        return BugAnalysis(is_bug=False)

    result = await ai_service.detect_potential_bug(
        title=title,
        description=description,
    )

    return BugAnalysis(**result)


@router.post("/suggest-status", response_model=StatusSuggestion)
async def suggest_status(
    issue_title: str = Query(...),
    current_status: str = Query(...),
    commit_message: Optional[str] = Query(None),
    pr_title: Optional[str] = Query(None),
):
    """
    Suggest a status update based on git activity.
    """
    if not ai_service.is_available():
        return StatusSuggestion(suggested_status=None)

    if not commit_message and not pr_title:
        return StatusSuggestion(suggested_status=None, reason="No activity provided")

    suggested = await ai_service.suggest_status_update(
        issue_title=issue_title,
        current_status=current_status,
        commit_message=commit_message,
        pr_title=pr_title,
    )

    return StatusSuggestion(
        suggested_status=suggested,
        reason=f"Based on {'commit' if commit_message else 'PR'} activity",
    )


@router.post("/{project_id}/generate-qa")
async def generate_qa_tasks(
    project_id: str,
    feature_title: str = Query(...),
    feature_description: Optional[str] = Query(None),
):
    """
    Generate QA/testing tasks for a feature.
    """
    if not ai_service.is_available():
        return {
            "tasks": [],
            "feature_title": feature_title,
            "ai_available": False,
        }

    tasks = await ai_service.generate_qa_tasks(
        project_id=project_id,
        feature_title=feature_title,
        feature_description=feature_description,
    )

    return {
        "tasks": tasks,
        "feature_title": feature_title,
        "ai_available": True,
    }


@router.post("/breakdown", response_model=HierarchicalBreakdownResponse)
async def hierarchical_breakdown_feature(
    request: HierarchicalBreakdownRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Use AI to break down a feature into epics, stories, tasks, and subtasks.

    **Options:**
    - `auto_create`: If true, automatically create all issues in the database

    **Returns:**
    - Hierarchical breakdown
    - Total task count
    - Estimated hours
    - Created issue IDs (if auto_create=true)
    """
    try:
        breakdown = await ai_service.hierarchical_breakdown_feature(
            project_id=request.project_id,
            feature_title=request.feature_title,
            feature_description=request.feature_description,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error in hierarchical breakdown: {e}")
        raise HTTPException(status_code=500, detail="AI service error")

    # Count tasks and hours
    total_tasks = 0
    estimated_hours = 0.0
    for story in breakdown.get("stories", []):
        for task in story.get("tasks", []):
            total_tasks += 1
            estimated_hours += task.get("estimate_hours", 2)
            total_tasks += len(task.get("subtasks", []))

    issues_created = []

    if request.auto_create:
        # Create issues in database
        epic_id = None
        created_issues = []

        # Create Epic if present
        if breakdown.get("epic"):
            epic = await create_issue_from_breakdown(
                db,
                request.project_id,
                breakdown["epic"],
                IssueType.EPIC,
                None
            )
            epic_id = epic.id
            issues_created.append(epic.key)
            created_issues.append(epic)

        # Create Stories and Tasks
        for story_data in breakdown.get("stories", []):
            story = await create_issue_from_breakdown(
                db,
                request.project_id,
                story_data,
                IssueType.STORY,
                epic_id
            )
            issues_created.append(story.key)
            created_issues.append(story)

            for task_data in story_data.get("tasks", []):
                task = await create_issue_from_breakdown(
                    db,
                    request.project_id,
                    task_data,
                    IssueType.TASK,
                    story.id
                )
                issues_created.append(task.key)
                created_issues.append(task)

                # Create subtasks
                for subtask_title in task_data.get("subtasks", []):
                    subtask = await create_issue_from_breakdown(
                        db,
                        request.project_id,
                        {"title": subtask_title, "description": ""},
                        IssueType.SUBTASK,
                        task.id
                    )
                    issues_created.append(subtask.key)
                    created_issues.append(subtask)

        await db.commit()

        # Embed all created issues for RAG search
        for issue in created_issues:
            await embed_issue_for_rag(issue)

    return HierarchicalBreakdownResponse(
        epic=breakdown.get("epic"),
        stories=breakdown.get("stories", []),
        total_tasks=total_tasks,
        estimated_hours=estimated_hours,
        issues_created=issues_created,
    )
