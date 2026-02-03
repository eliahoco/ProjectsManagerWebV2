"""
Git webhook for commit tracking and status updates.

This module provides a generic webhook endpoint that can receive
commit data from any git provider (GitHub, GitLab, Bitbucket, etc.)
or from custom integrations.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional, Set
from datetime import datetime
import uuid
import logging

from models import get_db, Issue, Activity, CommitLink
from services.commit_link_service import commit_link_service
from services.git_service import GitCommit
from utils.db_queries import batch_get_issues_by_keys, batch_check_commit_links_exist

router = APIRouter(prefix="/webhook", tags=["Webhooks"])

logger = logging.getLogger(__name__)


class Commit(BaseModel):
    """Commit data from webhook payload."""
    hash: str
    message: str
    author: str
    timestamp: str
    email: Optional[str] = None


class GitWebhookPayload(BaseModel):
    """Generic git webhook payload."""
    commits: List[Commit]
    repository: str
    project_id: Optional[str] = None  # Optional: directly specify project ID


class StatusUpdateResult(BaseModel):
    """Result of a status update from a commit."""
    issue_key: str
    old_status: str
    new_status: str
    commit: str


class WebhookResponse(BaseModel):
    """Response from webhook processing."""
    commits_processed: int
    commits_linked: int
    status_updates: List[StatusUpdateResult]
    errors: List[str] = []


def extract_issue_keys(message: str) -> List[str]:
    """
    Extract issue keys from commit message.

    Uses the same pattern as commit_link_service for consistency.
    """
    references = commit_link_service.parse_commit_message(message)
    return [key for key, _ in references]


def get_status_from_commit(message: str) -> Optional[str]:
    """
    Determine target status based on commit message keywords.

    Returns:
        - "DONE" for fix/close keywords
        - "IN_REVIEW" for implement keywords
        - None for simple mentions
    """
    references = commit_link_service.parse_commit_message(message)

    for key, link_type in references:
        if link_type.value in ("FIXES", "CLOSES"):
            return "DONE"
        elif link_type.value == "IMPLEMENTS":
            return "IN_REVIEW"

    return None


@router.post("/git", response_model=WebhookResponse)
async def git_webhook(
    payload: GitWebhookPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle generic git webhook for commit tracking and status updates.

    This endpoint accepts commit data and:
    1. Extracts issue keys from commit messages
    2. Creates commit links between commits and issues
    3. Updates issue status based on commit keywords (fix, close, implement)
    4. Logs activity for all status changes

    Commit message patterns:
    - "fix CB-123" or "fixes #CB-123" -> Status changes to DONE
    - "close CB-123" or "closes CB-123" -> Status changes to DONE
    - "implement CB-123" or "implements CB-123" -> Status changes to IN_REVIEW
    - "CB-123" (mention only) -> Link created, no status change

    Example payload:
    ```json
    {
        "commits": [
            {
                "hash": "abc123def456",
                "message": "fix CB-123: Resolve login issue",
                "author": "John Doe",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        ],
        "repository": "my-project"
    }
    ```
    """
    processed = []
    total_linked = 0
    errors = []

    logger.info(f"Processing webhook with {len(payload.commits)} commits from {payload.repository}")

    # Phase 1: Extract all issue keys and parse commit data
    all_keys: Set[str] = set()
    commit_data = []

    for commit in payload.commits:
        try:
            # Parse timestamp
            try:
                commit_date = datetime.fromisoformat(commit.timestamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                commit_date = datetime.utcnow()

            issue_keys = extract_issue_keys(commit.message)
            new_status = get_status_from_commit(commit.message)
            references = commit_link_service.parse_commit_message(commit.message)

            all_keys.update(k.upper() for k in issue_keys)
            commit_data.append({
                "commit": commit,
                "commit_date": commit_date,
                "issue_keys": issue_keys,
                "new_status": new_status,
                "references": references,
            })
        except Exception as e:
            error_msg = f"Error parsing commit {commit.hash[:7]}: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)

    # Phase 2: Batch fetch all issues by keys (single query instead of N queries)
    issues_by_key = await batch_get_issues_by_keys(db, list(all_keys))
    logger.debug(f"Batch fetched {len(issues_by_key)} issues for {len(all_keys)} keys")

    # Phase 3: Collect all potential issue-commit pairs to check for existing links
    potential_links = []
    for data in commit_data:
        commit = data["commit"]
        for key in data["issue_keys"]:
            issue = issues_by_key.get(key.upper())
            if issue:
                potential_links.append((issue.id, commit.hash))

    # Phase 4: Batch check which links already exist (single query instead of N queries)
    existing_links = await batch_check_commit_links_exist(db, potential_links)
    logger.debug(f"Found {len(existing_links)} existing links out of {len(potential_links)} potential")

    # Phase 5: Process commits and create links (now with all data pre-fetched)
    for data in commit_data:
        commit = data["commit"]
        commit_date = data["commit_date"]
        new_status = data["new_status"]
        references = data["references"]

        try:
            for key in data["issue_keys"]:
                issue = issues_by_key.get(key.upper())

                if not issue:
                    logger.debug(f"Issue {key} not found, skipping")
                    continue

                # Check if link already exists (using pre-fetched data)
                if (issue.id, commit.hash) in existing_links:
                    logger.debug(f"Commit {commit.hash[:7]} already linked to {key}")
                    continue

                # Determine link type
                link_type = "MENTIONS"
                for ref_key, ref_type in references:
                    if ref_key.upper() == key.upper():
                        link_type = ref_type.value
                        break

                # Create commit link
                link = CommitLink(
                    id=str(uuid.uuid4()),
                    issueId=issue.id,
                    projectId=issue.projectId,
                    commitHash=commit.hash,
                    shortHash=commit.hash[:7],
                    message=commit.message[:500],  # Truncate long messages
                    author=commit.author,
                    authorEmail=commit.email,
                    committedAt=commit_date,
                    linkType=link_type,
                    autoLinked=True,
                    triggeredStatusChange=False,
                )
                db.add(link)
                total_linked += 1

                # Track new link to avoid duplicate processing
                existing_links.add((issue.id, commit.hash))

                # Update status if applicable
                if new_status and issue.status != new_status:
                    old_status = issue.status
                    issue.status = new_status
                    issue.updatedAt = datetime.utcnow()
                    link.triggeredStatusChange = True

                    # Set timestamps for status changes
                    if new_status == "DONE" and not issue.completedAt:
                        issue.completedAt = datetime.utcnow()
                    if new_status in ("IN_PROGRESS", "IN_REVIEW", "DONE") and not issue.startedAt:
                        issue.startedAt = datetime.utcnow()

                    # Create activity record
                    activity = Activity(
                        id=str(uuid.uuid4()),
                        issueId=issue.id,
                        actor=f"Git ({commit.author})",
                        action="STATUS_CHANGED",
                        field="status",
                        oldValue=old_status,
                        newValue=new_status,
                    )
                    db.add(activity)

                    processed.append(StatusUpdateResult(
                        issue_key=key,
                        old_status=old_status,
                        new_status=new_status,
                        commit=commit.hash[:7]
                    ))

                    logger.info(f"Issue {key} status changed from {old_status} to {new_status} by commit {commit.hash[:7]}")

        except Exception as e:
            error_msg = f"Error processing commit {commit.hash[:7]}: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)

    await db.commit()

    logger.info(f"Webhook processed: {len(payload.commits)} commits, {total_linked} linked, {len(processed)} status updates")

    return WebhookResponse(
        commits_processed=len(payload.commits),
        commits_linked=total_linked,
        status_updates=processed,
        errors=errors
    )
