"""
Git API - Repository operations and commit-issue linking
"""

from fastapi import APIRouter, HTTPException, Query, Header, Request
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import Depends
import hmac
import hashlib

from services.git_service import git_service
from services.commit_link_service import commit_link_service
from services.commit_sync_service import commit_sync_service
from models import get_db, Project, CommitLink, Issue
from models.schemas import CommitLinkType
from app.config import settings

router = APIRouter(prefix="/git")


class GitCommitResponse(BaseModel):
    """Git commit response schema"""
    hash: str
    short_hash: str
    author: str
    email: str
    date: datetime
    message: str
    branch: Optional[str] = None


class GitBranchResponse(BaseModel):
    """Git branch response schema"""
    name: str
    is_current: bool
    tracking: Optional[str] = None
    ahead: int = 0
    behind: int = 0


class GitStatusResponse(BaseModel):
    """Git status response schema"""
    is_repo: bool
    branch: Optional[str] = None
    clean: bool = True
    staged: List[str] = []
    modified: List[str] = []
    untracked: List[str] = []
    ahead: int = 0
    behind: int = 0


class RepoSummaryResponse(BaseModel):
    """Repository summary response"""
    is_repo: bool
    branch: Optional[str] = None
    clean: Optional[bool] = None
    changes: Optional[dict] = None
    sync: Optional[dict] = None
    branches: Optional[List[str]] = None
    recent_commits: Optional[List[dict]] = None
    remote_url: Optional[str] = None


# Commit Link Schemas
class CommitLinkResponse(BaseModel):
    """Response schema for a linked commit"""
    id: str
    issueId: str
    projectId: str
    commitHash: str
    shortHash: str
    message: str
    author: str
    authorEmail: Optional[str] = None
    committedAt: datetime
    linkType: str
    autoLinked: bool
    triggeredStatusChange: bool
    createdAt: datetime

    class Config:
        from_attributes = True


class SyncSettingsRequest(BaseModel):
    """Request schema for updating sync settings"""
    autoSyncEnabled: Optional[bool] = None
    autoStatusUpdateEnabled: Optional[bool] = None


class SyncSettingsResponse(BaseModel):
    """Response schema for sync settings and statistics"""
    has_sync_state: bool
    total_commits_linked: int
    total_status_updates: int
    last_synced_at: Optional[str] = None
    last_synced_commit: Optional[str] = None
    auto_sync_enabled: bool
    auto_status_update_enabled: bool


class SyncResultResponse(BaseModel):
    """Response schema for sync operation results"""
    success: bool
    commits_scanned: int
    commits_linked: int
    status_updates: int
    issues_affected: List[str]
    last_commit: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None


class ManualLinkRequest(BaseModel):
    """Request schema for manually linking a commit to an issue"""
    issueId: str
    commitHash: str
    linkType: CommitLinkType = CommitLinkType.MENTIONS


async def get_project_path(project_id: str, db: AsyncSession) -> str:
    """Get project path from database"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.path:
        raise HTTPException(status_code=400, detail="Project has no path configured")
    return project.path


@router.get("/project/{project_id}/status", response_model=GitStatusResponse)
async def get_project_git_status(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get git status for a project"""
    path = await get_project_path(project_id, db)
    status = git_service.get_status(path)
    return GitStatusResponse(
        is_repo=status.is_repo,
        branch=status.branch,
        clean=status.clean,
        staged=status.staged,
        modified=status.modified,
        untracked=status.untracked,
        ahead=status.ahead,
        behind=status.behind,
    )


@router.get("/project/{project_id}/branches", response_model=List[GitBranchResponse])
async def get_project_branches(
    project_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get git branches for a project"""
    path = await get_project_path(project_id, db)
    branches = git_service.get_branches(path, limit=limit)
    return [
        GitBranchResponse(
            name=b.name,
            is_current=b.is_current,
            tracking=b.tracking,
            ahead=b.ahead,
            behind=b.behind,
        )
        for b in branches
    ]


@router.get("/project/{project_id}/commits", response_model=List[GitCommitResponse])
async def get_project_commits(
    project_id: str,
    branch: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get git commits for a project"""
    path = await get_project_path(project_id, db)
    commits = git_service.get_commits(path, branch=branch, limit=limit)
    return [
        GitCommitResponse(
            hash=c.hash,
            short_hash=c.short_hash,
            author=c.author,
            email=c.email,
            date=c.date,
            message=c.message,
            branch=c.branch,
        )
        for c in commits
    ]


@router.get("/project/{project_id}/summary", response_model=RepoSummaryResponse)
async def get_project_repo_summary(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get repository summary for a project"""
    path = await get_project_path(project_id, db)
    summary = git_service.repo_summary(path)
    return RepoSummaryResponse(**summary)


@router.get("/project/{project_id}/diff")
async def get_project_diff(
    project_id: str,
    staged: bool = False,
    file_path: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get diff for project changes"""
    path = await get_project_path(project_id, db)
    diff = git_service.get_diff(path, staged=staged, file_path=file_path)
    return {"diff": diff}


@router.get("/project/{project_id}/commits/issue/{issue_key}")
async def get_commits_for_issue(
    project_id: str,
    issue_key: str,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Find commits that reference an issue key"""
    path = await get_project_path(project_id, db)
    commits = git_service.get_commit_for_issue(path, issue_key, limit=limit)
    return {
        "issue_key": issue_key,
        "commits": [
            {
                "hash": c.hash,
                "short_hash": c.short_hash,
                "author": c.author,
                "email": c.email,
                "date": c.date.isoformat(),
                "message": c.message,
            }
            for c in commits
        ],
        "total": len(commits),
    }


# ============================================
# Commit Link Endpoints
# ============================================

@router.get("/project/{project_id}/linked-commits", response_model=List[CommitLinkResponse])
async def get_project_linked_commits(
    project_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get all linked commits for a project"""
    # Verify project exists
    await get_project_path(project_id, db)

    links = await commit_link_service.get_commits_for_project(db, project_id, limit)
    return [CommitLinkResponse.model_validate(link) for link in links]


@router.get("/issues/{issue_id}/linked-commits", response_model=List[CommitLinkResponse])
async def get_issue_linked_commits(
    issue_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get all linked commits for a specific issue"""
    # Verify issue exists
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    links = await commit_link_service.get_commits_for_issue(db, issue_id, limit)
    return [CommitLinkResponse.model_validate(link) for link in links]


@router.delete("/linked-commits/{link_id}", status_code=204)
async def delete_commit_link(
    link_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a commit link"""
    success = await commit_link_service.delete_link(db, link_id)
    if not success:
        raise HTTPException(status_code=404, detail="Commit link not found")
    await db.commit()


# ============================================
# Sync Endpoints
# ============================================

@router.get("/project/{project_id}/sync/settings", response_model=SyncSettingsResponse)
async def get_sync_settings(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get sync settings and statistics for a project"""
    # Verify project exists
    await get_project_path(project_id, db)

    stats = await commit_sync_service.get_sync_statistics(db, project_id)
    return SyncSettingsResponse(**stats)


@router.put("/project/{project_id}/sync/settings", response_model=SyncSettingsResponse)
async def update_sync_settings(
    project_id: str,
    settings: SyncSettingsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update sync settings for a project"""
    # Verify project exists
    await get_project_path(project_id, db)

    await commit_sync_service.update_sync_settings(
        db,
        project_id,
        auto_sync_enabled=settings.autoSyncEnabled,
        auto_status_update_enabled=settings.autoStatusUpdateEnabled
    )

    stats = await commit_sync_service.get_sync_statistics(db, project_id)
    return SyncSettingsResponse(**stats)


@router.post("/project/{project_id}/sync", response_model=SyncResultResponse)
async def sync_project_commits(
    project_id: str,
    force_full_scan: bool = Query(False, description="Force scan all commits"),
    limit: int = Query(100, ge=1, le=500, description="Max commits to process"),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync commits for a project.

    This will scan the repository for commits that reference issue keys
    and create links between commits and issues. If auto-status-update
    is enabled, issue statuses will be updated based on commit keywords.
    """
    path = await get_project_path(project_id, db)

    result = await commit_sync_service.sync_project(
        db=db,
        project_id=project_id,
        project_path=path,
        force_full_scan=force_full_scan,
        limit=limit
    )

    return SyncResultResponse(**result)


# ============================================
# Webhook Endpoint
# ============================================


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify GitHub webhook signature using HMAC-SHA256.
    Returns True only if the signature is valid.
    """
    if not secret or not signature:
        return False  # Cannot verify without both secret and signature

    expected = 'sha256=' + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


@router.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    GitHub webhook endpoint for push events.

    To use this webhook:
    1. Go to your GitHub repository settings
    2. Add a webhook with URL: https://your-domain/api/git/webhook/github
    3. Set content type to application/json
    4. Select "Just the push event"
    5. Add a secret and configure WEBHOOK_SECRET environment variable

    The webhook will automatically:
    - Parse commit messages for issue references
    - Create links between commits and issues
    - Update issue statuses based on commit keywords (if enabled)
    """
    # Get raw payload for signature verification
    payload = await request.body()

    # Verify webhook signature for security
    webhook_secret = settings.WEBHOOK_SECRET
    if settings.REQUIRE_WEBHOOK_SIGNATURE:
        if not webhook_secret:
            raise HTTPException(
                status_code=500,
                detail="Webhook secret not configured. Set WEBHOOK_SECRET environment variable."
            )
        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="Missing signature header")
        if not verify_github_signature(payload, x_hub_signature_256, webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid signature")
    elif webhook_secret and x_hub_signature_256:
        # Even in non-required mode, verify if both are present
        if not verify_github_signature(payload, x_hub_signature_256, webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse JSON payload
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Only process push events
    if x_github_event != "push":
        return {"message": f"Event type '{x_github_event}' ignored"}

    # Get repository info
    repository = data.get("repository", {})
    repo_name = repository.get("name", "")
    repo_full_name = repository.get("full_name", "")

    # Try to find the project by matching repository URL or name
    # This is a simple matching - in production you'd want a more robust mapping
    result = await db.execute(select(Project))
    projects = result.scalars().all()

    matched_project = None
    for project in projects:
        if not project.path:
            continue
        # Check if project path contains repo name
        if repo_name.lower() in project.path.lower():
            matched_project = project
            break
        # Check remote URL
        remote_url = git_service.get_remote_url(project.path)
        if remote_url and repo_full_name.lower() in remote_url.lower():
            matched_project = project
            break

    if not matched_project:
        return {
            "message": "No matching project found for repository",
            "repository": repo_full_name
        }

    # Process commits
    commits = data.get("commits", [])
    if not commits:
        return {"message": "No commits in push event"}

    result = await commit_sync_service.process_push_event(
        db=db,
        project_id=matched_project.id,
        project_path=matched_project.path,
        commits=commits
    )

    return {
        "message": "Webhook processed",
        "project": matched_project.name,
        "result": result
    }


@router.post("/webhook/test/{project_id}")
async def test_webhook_processing(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Test webhook processing by simulating a sync.
    This is useful for testing without setting up actual webhooks.
    """
    path = await get_project_path(project_id, db)

    # Just run a sync
    result = await commit_sync_service.sync_project(
        db=db,
        project_id=project_id,
        project_path=path,
        force_full_scan=False,
        limit=20
    )

    return {
        "message": "Test sync completed",
        "result": result
    }
