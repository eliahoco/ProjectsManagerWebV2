"""
Skills API — CRUD and scanning endpoints for the SkillProfile registry.

All endpoints live under the /api prefix (applied by the root router in
api/__init__.py).  Response shapes are defined in
models/skill_registry.py (SkillProfileRead) and local Pydantic models below.
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from models import get_db
from models.skill_registry import SkillProfile, SkillProfileCreate, SkillProfileRead
from services.skill_registry_service import skill_registry_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _skill_to_response(skill: SkillProfile) -> SkillProfileRead:
    """Convert a SkillProfile ORM row to a SkillProfileRead Pydantic model."""
    # capabilities is handled by the JsonList TypeDecorator and comes back as
    # a list already; guard against raw str just in case.
    caps = skill.capabilities
    if isinstance(caps, str):
        try:
            caps = json.loads(caps)
        except (json.JSONDecodeError, TypeError):
            caps = None

    return SkillProfileRead(
        id=skill.id,
        name=skill.name,
        displayName=skill.displayName,
        description=skill.description,
        skillPath=skill.skillPath,
        capabilities=caps,
        contextFork=skill.contextFork,
        agentRef=skill.agentRef,
        source=skill.source,
        isActive=skill.isActive,
        priority=skill.priority,
        createdAt=skill.createdAt.isoformat() if skill.createdAt else None,
        updatedAt=skill.updatedAt.isoformat() if skill.updatedAt else None,
    )


# ---------------------------------------------------------------------------
# Request models (local — only needed for the manual register endpoint)
# ---------------------------------------------------------------------------

class SkillScanResponse(BaseModel):
    """Response returned by POST /skills/scan."""

    count: int
    skills: List[SkillProfileRead]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/skills", response_model=List[SkillProfileRead])
async def list_skills(
    active_only: bool = Query(False, description="Only return active skills"),
    db: AsyncSession = Depends(get_db),
):
    """List all registered skills, optionally filtered to active-only."""
    skills = await skill_registry_service.get_all_skills(db, active_only=active_only)
    return [_skill_to_response(s) for s in skills]


@router.get("/skills/{skill_id}", response_model=SkillProfileRead)
async def get_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single skill profile by ID."""
    skill = await skill_registry_service.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _skill_to_response(skill)


@router.post("/skills/scan", response_model=SkillScanResponse)
async def scan_skills(
    db: AsyncSession = Depends(get_db),
):
    """Scan ``~/.claude/skills/`` and plugin cache directories for SKILL.md files.

    Upserts all discovered skills and returns the full list of created/updated
    records together with a count.
    """
    try:
        registered = await skill_registry_service.scan_skills_directory(db)
    except Exception:
        logger.exception("Failed to scan skills directories")
        raise HTTPException(status_code=500, detail="Failed to scan skills directories")

    return SkillScanResponse(
        count=len(registered),
        skills=[_skill_to_response(s) for s in registered],
    )


@router.post("/skills", response_model=SkillProfileRead, status_code=201)
async def register_skill(
    request: SkillProfileCreate,
    db: AsyncSession = Depends(get_db),
):
    """Manually register or update a skill profile."""
    data = {
        "name": request.name,
        "displayName": request.displayName or request.name.replace("-", " ").title(),
        "description": request.description,
        "skillPath": request.skillPath,
        "capabilities": request.capabilities or [],
        "contextFork": request.contextFork,
        "agentRef": request.agentRef,
        "source": request.source,
        "isActive": request.isActive,
        "priority": request.priority,
    }

    try:
        skill = await skill_registry_service.register_skill(db, data)
    except Exception:
        logger.exception("Failed to register skill %s", request.name)
        raise HTTPException(status_code=500, detail="Failed to register skill")

    return _skill_to_response(skill)


@router.patch("/skills/{skill_id}/toggle", response_model=SkillProfileRead)
async def toggle_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Toggle a skill's active status (active ↔ inactive)."""
    skill = await skill_registry_service.toggle_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _skill_to_response(skill)


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete (deactivate) a skill."""
    success = await skill_registry_service.delete_skill(db, skill_id)
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"success": True, "skill_id": skill_id, "status": "deactivated"}
