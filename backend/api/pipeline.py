"""
Pipeline API - Endpoints for multi-stage AI pipeline execution and agent registry.

Provides three groups of endpoints:
  1. Pipeline Execution  - start, monitor, cancel pipeline runs
  2. Agent Registry      - CRUD, scanning, and matching for AI agents
  3. Pipeline Config     - per-project pipeline configuration
"""

import json
import logging
from typing import Optional, List, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import get_db, Issue, Project
from models.agent_registry import AgentProfile
from services.pipeline_executor import pipeline_executor
from services.agent_registry_service import agent_registry_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models  -- Pipeline Execution
# ---------------------------------------------------------------------------

class PipelineStartRequest(BaseModel):
    """Request to start a pipeline execution for an issue."""
    provider: str = "claude_code"
    use_pipeline: bool = True
    agent_id: Optional[str] = None


class PipelineStageResponse(BaseModel):
    """Response representing a single pipeline stage."""
    id: str
    stageType: str
    stageIndex: int
    status: str
    sessionId: Optional[str] = None
    error: Optional[str] = None
    resultData: Optional[str] = None
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None


class PipelineExecutionResponse(BaseModel):
    """Response representing a full pipeline execution with stages."""
    id: str
    issueId: str
    projectId: str
    status: str
    currentStageIndex: int = 0
    retryCount: int = 0
    maxRetries: int = 3
    agentId: Optional[str] = None
    error: Optional[str] = None
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    stages: List[PipelineStageResponse] = []


# ---------------------------------------------------------------------------
# Pydantic models  -- Agent Registry
# ---------------------------------------------------------------------------

class AgentResponse(BaseModel):
    """Response representing an agent profile."""
    id: str
    name: str
    displayName: str
    description: Optional[str] = None
    agentPath: str = ""
    capabilities: Optional[List[str]] = None
    issueTypeAffinity: Optional[List[str]] = None
    projectPatterns: Optional[List[str]] = None
    isActive: bool = True
    priority: int = 50
    source: Optional[str] = "standalone"
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class AgentScanRequest(BaseModel):
    """Request to scan a directory for agents."""
    directory: Optional[str] = None


class AgentCreateRequest(BaseModel):
    """Request to register or update an agent profile."""
    name: str
    displayName: Optional[str] = None
    description: Optional[str] = None
    agentPath: str = ""
    capabilities: Optional[List[str]] = None
    issueTypeAffinity: Optional[List[str]] = None
    projectPatterns: Optional[List[str]] = None
    isActive: bool = True
    priority: int = 50


class AgentMatchRequest(BaseModel):
    """Request to find the best agent for a task."""
    issue_type: Optional[str] = None
    file_patterns: Optional[List[str]] = None
    project_type: Optional[str] = None


# ---------------------------------------------------------------------------
# Pydantic models  -- Pipeline Config
# ---------------------------------------------------------------------------

class PipelineConfigResponse(BaseModel):
    """Response for pipeline configuration."""
    id: str
    projectId: str
    enabled: bool = True
    defaultAgentId: Optional[str] = None
    maxRetries: int = 3
    verifyEnabled: bool = True
    autoFix: bool = True
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class PipelineConfigUpdateRequest(BaseModel):
    """Request to create or update pipeline configuration."""
    enabled: Optional[bool] = None
    defaultAgentId: Optional[str] = None
    maxRetries: Optional[int] = None
    verifyEnabled: Optional[bool] = None
    autoFix: Optional[bool] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_field(raw: Optional[str]) -> Optional[List[str]]:
    """Safely parse a JSON-encoded list field from the database."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _agent_to_response(agent: AgentProfile) -> AgentResponse:
    """Convert an AgentProfile ORM object to an AgentResponse."""
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        displayName=agent.displayName,
        description=agent.description,
        agentPath=agent.agentPath,
        capabilities=_parse_json_field(agent.capabilities),
        issueTypeAffinity=_parse_json_field(agent.issueTypeAffinity),
        projectPatterns=_parse_json_field(agent.projectPatterns),
        isActive=agent.isActive,
        priority=agent.priority,
        source=getattr(agent, "source", None) or "standalone",
        createdAt=agent.createdAt.isoformat() if agent.createdAt else None,
        updatedAt=agent.updatedAt.isoformat() if agent.updatedAt else None,
    )


def _execution_dict_to_response(data: dict) -> PipelineExecutionResponse:
    """Convert the dict returned by pipeline_executor.get_pipeline_status()
    into a PipelineExecutionResponse."""
    stages = [
        PipelineStageResponse(
            id=s["id"],
            stageType=s["stageType"],
            stageIndex=s["stageIndex"],
            status=s["status"],
            sessionId=s.get("sessionId"),
            error=s.get("error"),
            resultData=s.get("resultData"),
            startedAt=s.get("startedAt"),
            completedAt=s.get("completedAt"),
        )
        for s in data.get("stages", [])
    ]
    return PipelineExecutionResponse(
        id=data["id"],
        issueId=data["issueId"],
        projectId=data["projectId"],
        status=data["status"],
        currentStageIndex=data.get("currentStageIndex", 0),
        retryCount=data.get("retryCount", 0),
        maxRetries=data.get("maxRetries", 3),
        agentId=data.get("agentId"),
        error=data.get("error"),
        startedAt=data.get("startedAt"),
        completedAt=data.get("completedAt"),
        stages=stages,
    )


def _execution_orm_to_response(execution: Any, stages: Optional[list] = None) -> PipelineExecutionResponse:
    """Convert a PipelineExecution ORM object to a PipelineExecutionResponse."""
    stage_responses = []
    if stages:
        stage_responses = [
            PipelineStageResponse(
                id=s.id,
                stageType=s.stageType,
                stageIndex=s.stageIndex,
                status=s.status,
                sessionId=getattr(s, "sessionId", None),
                error=s.error,
                resultData=s.resultData,
                startedAt=s.startedAt.isoformat() if s.startedAt else None,
                completedAt=s.completedAt.isoformat() if s.completedAt else None,
            )
            for s in stages
        ]
    return PipelineExecutionResponse(
        id=execution.id,
        issueId=execution.issueId,
        projectId=execution.projectId,
        status=execution.status,
        currentStageIndex=getattr(execution, "currentStageIndex", 0),
        retryCount=getattr(execution, "retryCount", 0),
        maxRetries=getattr(execution, "maxRetries", 3),
        agentId=getattr(execution, "agentId", None),
        error=getattr(execution, "error", None),
        startedAt=execution.startedAt.isoformat() if execution.startedAt else None,
        completedAt=execution.completedAt.isoformat() if execution.completedAt else None,
        stages=stage_responses,
    )


# ===========================================================================
# 1. Pipeline Execution Endpoints
# ===========================================================================

@router.post("/pipeline/issue/{issue_id}", response_model=PipelineExecutionResponse)
async def start_pipeline(
    issue_id: str,
    request: PipelineStartRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Start a multi-stage pipeline execution for an issue.

    Stages: IMPLEMENT -> VERIFY -> (FIX -> RE_VERIFY if needed)
    """
    # Validate issue
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    # Validate project
    project_result = await db.execute(
        select(Project).where(Project.id == issue.projectId)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        execution = await pipeline_executor.start_pipeline(
            db=db,
            issue_id=issue.id,
            project_id=project.id,
            project_path=project.path,
            agent_id=request.agent_id,
        )
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Pipeline models not available: {exc}",
        )
    except Exception as exc:
        logger.exception("Failed to start pipeline for issue %s", issue_id)
        raise HTTPException(status_code=500, detail="Failed to start pipeline")

    return _execution_orm_to_response(execution)


@router.get("/pipeline/execution/{execution_id}", response_model=PipelineExecutionResponse)
async def get_pipeline_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get full pipeline execution status including all stages."""
    try:
        status = await pipeline_executor.get_pipeline_status(db, execution_id)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"Pipeline models not available: {exc}")

    if not status:
        raise HTTPException(status_code=404, detail="Pipeline execution not found")

    return _execution_dict_to_response(status)


@router.get("/pipeline/executions", response_model=List[PipelineExecutionResponse])
async def list_pipeline_executions(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    db: AsyncSession = Depends(get_db),
):
    """List all pipeline executions, optionally filtered by project_id."""
    try:
        from models.pipeline import PipelineExecution, PipelineStage
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"Pipeline models not available: {exc}")

    stmt = select(PipelineExecution).order_by(PipelineExecution.startedAt.desc())
    if project_id:
        stmt = stmt.where(PipelineExecution.projectId == project_id)

    result = await db.execute(stmt)
    executions = result.scalars().all()

    responses = []
    for execution in executions:
        # Fetch stages for each execution
        stage_result = await db.execute(
            select(PipelineStage)
            .where(PipelineStage.executionId == execution.id)
            .order_by(PipelineStage.stageIndex)
        )
        stages = stage_result.scalars().all()
        responses.append(_execution_orm_to_response(execution, stages))

    return responses


@router.post("/pipeline/execution/{execution_id}/cancel")
async def cancel_pipeline(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running pipeline execution."""
    try:
        success = await pipeline_executor.cancel_pipeline(db, execution_id)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"Pipeline models not available: {exc}")

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel pipeline (not found or not running)",
        )

    return {"success": True, "execution_id": execution_id, "status": "CANCELLED"}


@router.post("/pipeline/stop-all")
async def stop_all_pipelines(db: AsyncSession = Depends(get_db)):
    """Cancel all currently running pipeline executions."""
    try:
        cancelled_ids = await pipeline_executor.cancel_all_pipelines(db)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"Pipeline models not available: {exc}")

    return {
        "success": True,
        "cancelled_count": len(cancelled_ids),
        "cancelled": cancelled_ids,
    }


@router.get(
    "/pipeline/execution/{execution_id}/stages",
    response_model=List[PipelineStageResponse],
)
async def get_pipeline_stages(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all stages for a pipeline execution."""
    try:
        from models.pipeline import PipelineStage
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"Pipeline models not available: {exc}")

    result = await db.execute(
        select(PipelineStage)
        .where(PipelineStage.executionId == execution_id)
        .order_by(PipelineStage.stageIndex)
    )
    stages = result.scalars().all()

    if not stages:
        raise HTTPException(status_code=404, detail="No stages found for this execution")

    return [
        PipelineStageResponse(
            id=s.id,
            stageType=s.stageType,
            stageIndex=s.stageIndex,
            status=s.status,
            sessionId=getattr(s, "sessionId", None),
            error=s.error,
            resultData=s.resultData,
            startedAt=s.startedAt.isoformat() if s.startedAt else None,
            completedAt=s.completedAt.isoformat() if s.completedAt else None,
        )
        for s in stages
    ]


# ===========================================================================
# 2. Agent Registry Endpoints
# ===========================================================================

@router.get("/agents", response_model=List[AgentResponse])
async def list_agents(
    active_only: bool = Query(False, description="Only return active agents"),
    db: AsyncSession = Depends(get_db),
):
    """List all registered agents."""
    agents = await agent_registry_service.get_all_agents(db, active_only=active_only)
    return [_agent_to_response(a) for a in agents]


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single agent profile by ID."""
    agent = await agent_registry_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_to_response(agent)


@router.post("/agents/scan", response_model=List[AgentResponse])
async def scan_agents(
    request: AgentScanRequest = AgentScanRequest(),
    db: AsyncSession = Depends(get_db),
):
    """
    Scan a directory for agent folders and auto-register them.

    Defaults to ~/.claude/agents/ if no directory is provided.
    """
    try:
        registered = await agent_registry_service.scan_agents_directory(
            db, directory=request.directory
        )
    except Exception:
        logger.exception("Failed to scan agents directory")
        raise HTTPException(status_code=500, detail="Failed to scan agents directory")

    return [_agent_to_response(a) for a in registered]


@router.post("/agents", response_model=AgentResponse)
async def register_agent(
    request: AgentCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register or update an agent profile manually."""
    data = {
        "name": request.name,
        "displayName": request.displayName or request.name.replace("-", " ").title(),
        "description": request.description,
        "agentPath": request.agentPath,
        "capabilities": request.capabilities or [],
        "issueTypeAffinity": request.issueTypeAffinity or [],
        "projectPatterns": request.projectPatterns or [],
        "isActive": request.isActive,
        "priority": request.priority,
    }

    try:
        agent = await agent_registry_service.register_agent(db, data)
    except Exception:
        logger.exception("Failed to register agent %s", request.name)
        raise HTTPException(status_code=500, detail="Failed to register agent")

    return _agent_to_response(agent)


@router.delete("/agents/{agent_id}")
async def deactivate_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete (deactivate) an agent."""
    success = await agent_registry_service.deactivate_agent(db, agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"success": True, "agent_id": agent_id, "status": "deactivated"}


@router.patch("/agents/{agent_id}/toggle", response_model=AgentResponse)
async def toggle_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Toggle an agent's active status."""
    agent = await agent_registry_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.isActive = not agent.isActive
    await db.commit()
    await db.refresh(agent)
    return _agent_to_response(agent)


@router.post("/agents/match", response_model=Optional[AgentResponse])
async def match_agent(
    request: AgentMatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Find the best agent for a task based on issue type, file patterns,
    and project type.
    """
    agent = await agent_registry_service.match_agent(
        db,
        issue_type=request.issue_type,
        file_patterns=request.file_patterns,
        project_type=request.project_type,
    )
    if not agent:
        return None
    return _agent_to_response(agent)


# ===========================================================================
# 3. Pipeline Config Endpoints
# ===========================================================================

@router.get("/pipeline/config/{project_id}", response_model=PipelineConfigResponse)
async def get_pipeline_config(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get pipeline configuration for a project."""
    try:
        from models.pipeline import PipelineConfig
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"Pipeline models not available: {exc}")

    result = await db.execute(
        select(PipelineConfig).where(PipelineConfig.projectId == project_id)
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Pipeline config not found for this project")

    return PipelineConfigResponse(
        id=config.id,
        projectId=config.projectId,
        enabled=getattr(config, "enabled", True),
        defaultAgentId=getattr(config, "defaultAgentId", None),
        maxRetries=getattr(config, "maxRetries", 3),
        verifyEnabled=getattr(config, "verifyEnabled", True),
        autoFix=getattr(config, "autoFix", True),
        createdAt=config.createdAt.isoformat() if config.createdAt else None,
        updatedAt=config.updatedAt.isoformat() if config.updatedAt else None,
    )


@router.put("/pipeline/config/{project_id}", response_model=PipelineConfigResponse)
async def update_pipeline_config(
    project_id: str,
    request: PipelineConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create or update pipeline configuration for a project."""
    import uuid

    try:
        from models.pipeline import PipelineConfig
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"Pipeline models not available: {exc}")

    # Verify the project exists
    project_result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Try to find existing config
    result = await db.execute(
        select(PipelineConfig).where(PipelineConfig.projectId == project_id)
    )
    config = result.scalar_one_or_none()

    if config:
        # Update existing config
        if request.enabled is not None:
            config.enabled = request.enabled
        if request.defaultAgentId is not None:
            config.defaultAgentId = request.defaultAgentId
        if request.maxRetries is not None:
            config.maxRetries = request.maxRetries
        if request.verifyEnabled is not None:
            config.verifyEnabled = request.verifyEnabled
        if request.autoFix is not None:
            config.autoFix = request.autoFix
    else:
        # Create new config
        config = PipelineConfig(
            id=str(uuid.uuid4()),
            projectId=project_id,
            enabled=request.enabled if request.enabled is not None else True,
            defaultAgentId=request.defaultAgentId,
            maxRetries=request.maxRetries if request.maxRetries is not None else 3,
            verifyEnabled=request.verifyEnabled if request.verifyEnabled is not None else True,
            autoFix=request.autoFix if request.autoFix is not None else True,
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    return PipelineConfigResponse(
        id=config.id,
        projectId=config.projectId,
        enabled=getattr(config, "enabled", True),
        defaultAgentId=getattr(config, "defaultAgentId", None),
        maxRetries=getattr(config, "maxRetries", 3),
        verifyEnabled=getattr(config, "verifyEnabled", True),
        autoFix=getattr(config, "autoFix", True),
        createdAt=config.createdAt.isoformat() if config.createdAt else None,
        updatedAt=config.updatedAt.isoformat() if config.updatedAt else None,
    )
