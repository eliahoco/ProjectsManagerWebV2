"""
API Routes for ProjectsManagerWebV2
"""

from fastapi import APIRouter

from api.issues import router as issues_router
from api.relations import router as relations_router
from api.groups import router as groups_router
from api.projects import router as projects_router
from api.search import router as search_router
from api.ai import router as ai_router
from api.git import router as git_router
from api.git_webhook import router as git_webhook_router
from api.import_tracker import router as import_router
from api.execution import router as execution_router
from api.qa import router as qa_router
from api.pipeline import router as pipeline_router
from api.park import router as park_router
from api.skills import router as skills_router
from api.documentation import router as documentation_router
from api.doc_settings import router as doc_settings_router
from api.system import router as system_router

# CB-2384: Studio + parallel Phase-4c routers.
# studio_router is wired now.  backlog_router and crew_map_router are being
# created by the parallel Phase-4c agent.  The imports are left AS-IS per
# spec so they resolve automatically when those files land.  Until then,
# ImportError is caught and the routers are skipped with a warning rather
# than blocking application startup.
from api.studio import router as studio_router
try:
    from api.backlog import router as backlog_router      # Phase-4c agent — pending
except Exception:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "api.backlog not yet available — skipping backlog_router registration (Phase-4c pending)",
        exc_info=True,
    )
    backlog_router = None  # type: ignore[assignment]
try:
    from api.crew_map import router as crew_map_router    # Phase-4c agent — pending
except Exception:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "api.crew_map not yet available — skipping crew_map_router registration (Phase-4c pending)",
        exc_info=True,
    )
    crew_map_router = None  # type: ignore[assignment]

router = APIRouter()


@router.get("/health")
async def api_health():
    """API health check"""
    return {"status": "ok", "api": "v1"}


# Include routes
router.include_router(projects_router, tags=["projects"])
router.include_router(issues_router, tags=["issues"])
router.include_router(relations_router, tags=["relations"])
router.include_router(groups_router, tags=["groups"])
router.include_router(search_router, tags=["search"])
router.include_router(ai_router, tags=["ai"])
router.include_router(git_router, tags=["git"])
router.include_router(git_webhook_router, tags=["webhooks"])
router.include_router(import_router, tags=["import"])
router.include_router(execution_router, tags=["execution"])
router.include_router(qa_router, tags=["qa"])
router.include_router(pipeline_router, tags=["pipeline"])
router.include_router(park_router, tags=["park"])
router.include_router(skills_router, tags=["skills"])
router.include_router(documentation_router, tags=["documentation"])
router.include_router(doc_settings_router, tags=["documentation-settings"])
router.include_router(system_router, tags=["system"])
# CB-2384: Studio + Backlog + Crew Map routers
router.include_router(studio_router, tags=["Studio"])
if backlog_router is not None:                             # Phase-4c agent — pending
    router.include_router(backlog_router, tags=["Backlog"])
if crew_map_router is not None:                            # Phase-4c agent — pending
    router.include_router(crew_map_router, tags=["Crew Map"])
