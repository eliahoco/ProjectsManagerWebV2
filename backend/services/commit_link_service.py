"""
CommitLinkService - Service for linking Git commits to issues

This service handles:
1. Parsing commit messages to detect issue references
2. Determining the link type (MENTIONS, FIXES, CLOSES, IMPLEMENTS)
3. Creating CommitLink records in the database
4. Querying linked commits for issues/projects
"""

import re
import uuid
from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from models import CommitLink, Issue, IssueStatus, Activity
from models.schemas import CommitLinkType
from services.git_service import GitCommit


class CommitLinkService:
    """Service for managing commit-to-issue links"""

    # Patterns for detecting issue references in commit messages
    # Matches: PROJ-123, CB-45, etc.
    ISSUE_KEY_PATTERN = re.compile(r'\b([A-Z]{2,10}-\d+)\b', re.IGNORECASE)

    # Patterns for detecting link types
    # Note: Order matters! More specific patterns should be checked first.
    FIX_PATTERNS = [
        re.compile(r'\b(?:fix(?:e[sd])?|resolv(?:e[sd])?)\s*[:#]?\s*([A-Z]{2,10}-\d+)', re.IGNORECASE),
        re.compile(r'\b([A-Z]{2,10}-\d+)\s*(?:fix(?:e[sd])?|resolv(?:e[sd])?)', re.IGNORECASE),
    ]

    CLOSES_PATTERNS = [
        re.compile(r'\b(?:close[sd]?)\s*[:#]?\s*([A-Z]{2,10}-\d+)', re.IGNORECASE),
        re.compile(r'\b([A-Z]{2,10}-\d+)\s*(?:close[sd]?)', re.IGNORECASE),
    ]

    IMPLEMENTS_PATTERNS = [
        re.compile(r'\b(?:implement(?:s|ed)?|complet(?:e[sd])?)\s*[:#]?\s*([A-Z]{2,10}-\d+)', re.IGNORECASE),
        re.compile(r'\b([A-Z]{2,10}-\d+)\s*(?:implement(?:s|ed)?|complet(?:e[sd])?)', re.IGNORECASE),
    ]

    # Status mappings for auto-update
    STATUS_TRANSITIONS = {
        CommitLinkType.FIXES: IssueStatus.DONE,
        CommitLinkType.CLOSES: IssueStatus.DONE,
        CommitLinkType.IMPLEMENTS: IssueStatus.IN_REVIEW,
        CommitLinkType.MENTIONS: None,  # No status change for mentions
    }

    def parse_commit_message(self, message: str) -> List[Tuple[str, CommitLinkType]]:
        """
        Parse a commit message to extract issue references and their link types.

        Returns a list of tuples: (issue_key, link_type)
        """
        results = []
        found_keys = set()

        # Check for fix patterns first (highest priority)
        for pattern in self.FIX_PATTERNS:
            for match in pattern.finditer(message):
                key = match.group(1).upper()
                if key not in found_keys:
                    results.append((key, CommitLinkType.FIXES))
                    found_keys.add(key)

        # Check for closes patterns
        for pattern in self.CLOSES_PATTERNS:
            for match in pattern.finditer(message):
                key = match.group(1).upper()
                if key not in found_keys:
                    results.append((key, CommitLinkType.CLOSES))
                    found_keys.add(key)

        # Check for implements patterns
        for pattern in self.IMPLEMENTS_PATTERNS:
            for match in pattern.finditer(message):
                key = match.group(1).upper()
                if key not in found_keys:
                    results.append((key, CommitLinkType.IMPLEMENTS))
                    found_keys.add(key)

        # Find any remaining issue references as mentions
        for match in self.ISSUE_KEY_PATTERN.finditer(message):
            key = match.group(1).upper()
            if key not in found_keys:
                results.append((key, CommitLinkType.MENTIONS))
                found_keys.add(key)

        return results

    async def find_issue_by_key(
        self,
        db: AsyncSession,
        issue_key: str,
        project_id: Optional[str] = None
    ) -> Optional[Issue]:
        """Find an issue by its key (e.g., CB-123)"""
        query = select(Issue).where(Issue.key == issue_key.upper())
        if project_id:
            query = query.where(Issue.projectId == project_id)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def link_exists(
        self,
        db: AsyncSession,
        issue_id: str,
        commit_hash: str
    ) -> bool:
        """Check if a link already exists between an issue and commit"""
        result = await db.execute(
            select(CommitLink).where(
                and_(
                    CommitLink.issueId == issue_id,
                    CommitLink.commitHash == commit_hash
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def create_commit_link(
        self,
        db: AsyncSession,
        issue_id: str,
        project_id: str,
        commit: GitCommit,
        link_type: CommitLinkType,
        auto_linked: bool = True,
        triggered_status_change: bool = False
    ) -> CommitLink:
        """Create a new commit link record"""
        link = CommitLink(
            id=str(uuid.uuid4()),
            issueId=issue_id,
            projectId=project_id,
            commitHash=commit.hash,
            shortHash=commit.short_hash,
            message=commit.message,
            author=commit.author,
            authorEmail=commit.email,
            committedAt=commit.date,
            linkType=link_type.value,
            autoLinked=auto_linked,
            triggeredStatusChange=triggered_status_change,
        )
        db.add(link)
        return link

    async def update_issue_status(
        self,
        db: AsyncSession,
        issue: Issue,
        new_status: IssueStatus,
        commit: GitCommit
    ) -> bool:
        """
        Update an issue's status based on a commit.
        Returns True if status was changed, False otherwise.
        """
        old_status = issue.status

        # Don't downgrade status (e.g., don't change DONE to IN_REVIEW)
        status_priority = {
            IssueStatus.BACKLOG.value: 0,
            IssueStatus.TODO.value: 1,
            IssueStatus.IN_PROGRESS.value: 2,
            IssueStatus.IN_REVIEW.value: 3,
            IssueStatus.DONE.value: 4,
            IssueStatus.CANCELLED.value: 5,
        }

        if status_priority.get(new_status.value, 0) <= status_priority.get(old_status, 0):
            return False

        # Update status
        issue.status = new_status.value
        issue.updatedAt = datetime.utcnow()

        # Set timestamps
        if new_status == IssueStatus.IN_PROGRESS and not issue.startedAt:
            issue.startedAt = datetime.utcnow()
        elif new_status in (IssueStatus.DONE, IssueStatus.IN_REVIEW):
            if new_status == IssueStatus.DONE:
                issue.completedAt = datetime.utcnow()
            if not issue.startedAt:
                issue.startedAt = datetime.utcnow()

        # Log activity
        activity = Activity(
            id=str(uuid.uuid4()),
            issueId=issue.id,
            actor=f"Git ({commit.author})",
            action="STATUS_CHANGED",
            field="status",
            oldValue=old_status,
            newValue=new_status.value,
        )
        db.add(activity)

        return True

    async def process_commit(
        self,
        db: AsyncSession,
        commit: GitCommit,
        project_id: str,
        auto_status_update: bool = True
    ) -> List[CommitLink]:
        """
        Process a single commit: parse message, link to issues, update statuses.

        Returns list of created CommitLink records.
        """
        created_links = []
        references = self.parse_commit_message(commit.message)

        for issue_key, link_type in references:
            # Find the issue
            issue = await self.find_issue_by_key(db, issue_key, project_id)
            if not issue:
                # Try without project filter (cross-project reference)
                issue = await self.find_issue_by_key(db, issue_key)

            if not issue:
                continue  # Issue not found, skip

            # Check if link already exists
            if await self.link_exists(db, issue.id, commit.hash):
                continue  # Already linked

            # Determine if we should update status
            triggered_status_change = False
            if auto_status_update:
                target_status = self.STATUS_TRANSITIONS.get(link_type)
                if target_status:
                    triggered_status_change = await self.update_issue_status(
                        db, issue, target_status, commit
                    )

            # Create the link
            link = await self.create_commit_link(
                db=db,
                issue_id=issue.id,
                project_id=issue.projectId,
                commit=commit,
                link_type=link_type,
                auto_linked=True,
                triggered_status_change=triggered_status_change,
            )
            created_links.append(link)

        return created_links

    async def get_commits_for_issue(
        self,
        db: AsyncSession,
        issue_id: str,
        limit: int = 50
    ) -> List[CommitLink]:
        """Get all linked commits for an issue"""
        result = await db.execute(
            select(CommitLink)
            .where(CommitLink.issueId == issue_id)
            .order_by(CommitLink.committedAt.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_commits_for_project(
        self,
        db: AsyncSession,
        project_id: str,
        limit: int = 100
    ) -> List[CommitLink]:
        """Get all linked commits for a project"""
        result = await db.execute(
            select(CommitLink)
            .where(CommitLink.projectId == project_id)
            .order_by(CommitLink.committedAt.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_link_by_id(
        self,
        db: AsyncSession,
        link_id: str
    ) -> Optional[CommitLink]:
        """Get a specific commit link by ID"""
        result = await db.execute(
            select(CommitLink).where(CommitLink.id == link_id)
        )
        return result.scalar_one_or_none()

    async def delete_link(
        self,
        db: AsyncSession,
        link_id: str
    ) -> bool:
        """Delete a commit link"""
        link = await self.get_link_by_id(db, link_id)
        if not link:
            return False
        await db.delete(link)
        return True

    async def get_recent_linked_commits(
        self,
        db: AsyncSession,
        project_id: str,
        since: Optional[datetime] = None,
        limit: int = 50
    ) -> List[CommitLink]:
        """Get recently linked commits, optionally since a specific date"""
        query = select(CommitLink).where(CommitLink.projectId == project_id)

        if since:
            query = query.where(CommitLink.committedAt >= since)

        query = query.order_by(CommitLink.committedAt.desc()).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())


# Singleton instance
commit_link_service = CommitLinkService()
