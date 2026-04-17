"""
API Routes for ProjectsManagerWebV2
"""

from fastapi import APIRouter

from api.issues import router as issues_router
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

router = APIRouter()


@router.get("/health")
async def api_health():
    """API health check"""
    return {"status": "ok", "api": "v1"}


# Include routes
router.include_router(projects_router, tags=["projects"])
router.include_router(issues_router, tags=["issues"])
router.include_router(search_router, tags=["search"])
router.include_router(ai_router, tags=["ai"])
router.include_router(git_router, tags=["git"])
router.include_router(git_webhook_router, tags=["webhooks"])
router.include_router(import_router, tags=["import"])
router.include_router(execution_router, tags=["execution"])
router.include_router(qa_router, tags=["qa"])
router.include_router(pipeline_router, tags=["pipeline"])
router.include_router(park_router, tags=["park"])
