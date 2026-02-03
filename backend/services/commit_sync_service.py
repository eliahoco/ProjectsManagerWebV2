"""
CommitSyncService - Service for syncing Git commits with issues

This service handles:
1. Scanning repository history for new commits
2. Tracking sync state per project
3. Automatic or manual sync operations
4. Statistics tracking
"""

import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from models import GitSyncState, CommitLink, Project
from services.git_service import git_service, GitCommit
from services.commit_link_service import commit_link_service


class CommitSyncService:
    """Service for syncing Git commits with the issue tracking system"""

    async def get_sync_state(
        self,
        db: AsyncSession,
        project_id: str
    ) -> Optional[GitSyncState]:
        """Get the sync state for a project"""
        result = await db.execute(
            select(GitSyncState).where(GitSyncState.projectId == project_id)
        )
        return result.scalar_one_or_none()

    async def create_sync_state(
        self,
        db: AsyncSession,
        project_id: str,
        auto_sync_enabled: bool = True,
        auto_status_update_enabled: bool = True
    ) -> GitSyncState:
        """Create a new sync state for a project"""
        state = GitSyncState(
            id=str(uuid.uuid4()),
            projectId=project_id,
            autoSyncEnabled=auto_sync_enabled,
            autoStatusUpdateEnabled=auto_status_update_enabled,
        )
        db.add(state)
        await db.commit()
        await db.refresh(state)
        return state

    async def get_or_create_sync_state(
        self,
        db: AsyncSession,
        project_id: str
    ) -> GitSyncState:
        """Get existing sync state or create a new one"""
        state = await self.get_sync_state(db, project_id)
        if not state:
            state = await self.create_sync_state(db, project_id)
        return state

    async def update_sync_state(
        self,
        db: AsyncSession,
        state: GitSyncState,
        last_commit_hash: Optional[str] = None,
        commits_linked: int = 0,
        status_updates: int = 0
    ) -> GitSyncState:
        """Update sync state after a sync operation"""
        if last_commit_hash:
            state.lastSyncedCommitHash = last_commit_hash
        state.lastSyncedAt = datetime.utcnow()

        # Update statistics
        current_linked = int(state.totalCommitsLinked or "0")
        current_updates = int(state.totalStatusUpdates or "0")
        state.totalCommitsLinked = str(current_linked + commits_linked)
        state.totalStatusUpdates = str(current_updates + status_updates)

        await db.commit()
        await db.refresh(state)
        return state

    async def update_sync_settings(
        self,
        db: AsyncSession,
        project_id: str,
        auto_sync_enabled: Optional[bool] = None,
        auto_status_update_enabled: Optional[bool] = None
    ) -> GitSyncState:
        """Update sync settings for a project"""
        state = await self.get_or_create_sync_state(db, project_id)

        if auto_sync_enabled is not None:
            state.autoSyncEnabled = auto_sync_enabled
        if auto_status_update_enabled is not None:
            state.autoStatusUpdateEnabled = auto_status_update_enabled

        await db.commit()
        await db.refresh(state)
        return state

    async def get_new_commits(
        self,
        project_path: str,
        since_commit: Optional[str] = None,
        limit: int = 100
    ) -> List[GitCommit]:
        """
        Get commits that haven't been synced yet.

        If since_commit is provided, gets commits after that commit.
        Otherwise, gets the most recent commits up to the limit.
        """
        # Get all recent commits
        all_commits = git_service.get_commits(project_path, limit=limit)

        if not since_commit:
            return all_commits

        # Filter to only commits after the last synced one
        new_commits = []
        for commit in all_commits:
            if commit.hash == since_commit:
                break
            new_commits.append(commit)

        return new_commits

    async def sync_project(
        self,
        db: AsyncSession,
        project_id: str,
        project_path: str,
        force_full_scan: bool = False,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Sync a project's commits with the issue tracking system.

        Args:
            db: Database session
            project_id: Project ID
            project_path: Path to the git repository
            force_full_scan: If True, scan all commits regardless of last sync
            limit: Maximum number of commits to process

        Returns:
            Dict with sync results including:
            - commits_scanned: Number of commits checked
            - commits_linked: Number of new commit links created
            - status_updates: Number of issue status updates
            - issues_affected: List of affected issue keys
        """
        # Check if repo is valid
        if not git_service.is_git_repo(project_path):
            return {
                "success": False,
                "error": "Not a git repository",
                "commits_scanned": 0,
                "commits_linked": 0,
                "status_updates": 0,
                "issues_affected": [],
            }

        # Get sync state
        sync_state = await self.get_or_create_sync_state(db, project_id)

        # Determine starting point
        since_commit = None if force_full_scan else sync_state.lastSyncedCommitHash

        # Get new commits
        new_commits = await self.get_new_commits(
            project_path,
            since_commit=since_commit,
            limit=limit
        )

        if not new_commits:
            return {
                "success": True,
                "commits_scanned": 0,
                "commits_linked": 0,
                "status_updates": 0,
                "issues_affected": [],
                "message": "No new commits to sync",
            }

        # Process commits
        total_linked = 0
        total_status_updates = 0
        issues_affected = set()
        auto_status_update = sync_state.autoStatusUpdateEnabled

        for commit in new_commits:
            links = await commit_link_service.process_commit(
                db=db,
                commit=commit,
                project_id=project_id,
                auto_status_update=auto_status_update
            )

            total_linked += len(links)
            for link in links:
                if link.triggeredStatusChange:
                    total_status_updates += 1
                # Get the issue key for this link
                issue_result = await db.execute(
                    select(Project).where(Project.id == link.issueId)
                )

        # Commit all changes
        await db.commit()

        # Update sync state
        latest_commit_hash = new_commits[0].hash if new_commits else None
        await self.update_sync_state(
            db=db,
            state=sync_state,
            last_commit_hash=latest_commit_hash,
            commits_linked=total_linked,
            status_updates=total_status_updates
        )

        return {
            "success": True,
            "commits_scanned": len(new_commits),
            "commits_linked": total_linked,
            "status_updates": total_status_updates,
            "issues_affected": list(issues_affected),
            "last_commit": latest_commit_hash,
        }

    async def process_push_event(
        self,
        db: AsyncSession,
        project_id: str,
        project_path: str,
        commits: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Process a webhook push event with pre-provided commit data.

        This is called from the webhook endpoint when GitHub sends a push event.
        The commits list should contain commit objects from the webhook payload.

        Args:
            db: Database session
            project_id: Project ID
            project_path: Path to the git repository
            commits: List of commit objects from webhook payload

        Returns:
            Dict with processing results
        """
        sync_state = await self.get_or_create_sync_state(db, project_id)

        if not sync_state.autoSyncEnabled:
            return {
                "success": False,
                "error": "Auto-sync is disabled for this project",
                "commits_processed": 0,
            }

        total_linked = 0
        total_status_updates = 0
        issues_affected = set()

        for commit_data in commits:
            # Convert webhook commit data to GitCommit
            commit = GitCommit(
                hash=commit_data.get("id", commit_data.get("sha", "")),
                short_hash=commit_data.get("id", commit_data.get("sha", ""))[:7],
                author=commit_data.get("author", {}).get("name", "Unknown"),
                email=commit_data.get("author", {}).get("email", ""),
                date=datetime.fromisoformat(
                    commit_data.get("timestamp", "").replace("Z", "+00:00")
                ) if commit_data.get("timestamp") else datetime.utcnow(),
                message=commit_data.get("message", ""),
            )

            links = await commit_link_service.process_commit(
                db=db,
                commit=commit,
                project_id=project_id,
                auto_status_update=sync_state.autoStatusUpdateEnabled
            )

            total_linked += len(links)
            for link in links:
                if link.triggeredStatusChange:
                    total_status_updates += 1

        await db.commit()

        # Update sync state
        if commits:
            latest_hash = commits[0].get("id", commits[0].get("sha"))
            await self.update_sync_state(
                db=db,
                state=sync_state,
                last_commit_hash=latest_hash,
                commits_linked=total_linked,
                status_updates=total_status_updates
            )

        return {
            "success": True,
            "commits_processed": len(commits),
            "commits_linked": total_linked,
            "status_updates": total_status_updates,
            "issues_affected": list(issues_affected),
        }

    async def get_sync_statistics(
        self,
        db: AsyncSession,
        project_id: str
    ) -> Dict[str, Any]:
        """Get sync statistics for a project"""
        sync_state = await self.get_sync_state(db, project_id)

        if not sync_state:
            return {
                "has_sync_state": False,
                "total_commits_linked": 0,
                "total_status_updates": 0,
                "last_synced_at": None,
                "auto_sync_enabled": True,
                "auto_status_update_enabled": True,
            }

        return {
            "has_sync_state": True,
            "total_commits_linked": int(sync_state.totalCommitsLinked or "0"),
            "total_status_updates": int(sync_state.totalStatusUpdates or "0"),
            "last_synced_at": sync_state.lastSyncedAt.isoformat() if sync_state.lastSyncedAt else None,
            "last_synced_commit": sync_state.lastSyncedCommitHash,
            "auto_sync_enabled": sync_state.autoSyncEnabled,
            "auto_status_update_enabled": sync_state.autoStatusUpdateEnabled,
        }


# Singleton instance
commit_sync_service = CommitSyncService()
