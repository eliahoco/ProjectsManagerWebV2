"""
AutoPilot Service - Backend-driven parallel task execution.

Discovers runnable tasks under a parent container (FEATURE, EPIC, STORY)
using the dependency analyzer, then launches batches in parallel up to
the session pool's capacity.

Execution flow:
  1. Frontend calls `get_next_batch()` to discover what can run now.
  2. Frontend calls `execute_batch()` to start them all at once.
  3. Frontend polls `get_autopilot_status()` for progress updates.
  4. When tasks complete, the next batch is available via `get_next_batch()`.

AutoPilot respects:
  - BLOCKS / IS_BLOCKED_BY link constraints (via dependency_analyzer)
  - Session pool capacity limits (via session_pool)
  - Only executes leaf types (TASK, SUBTASK, BUG)
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.issue import Issue, Project
from services.dependency_analyzer import dependency_analyzer, LEAF_TYPES, COMPLETED_STATUSES
from services.terminal_service import (
    terminal_service,
    ExecutionProvider,
    ExecutionStatus,
)
from services.session_pool import session_pool
from services.context_builder import build_execution_context, get_parent_chain
from utils.db_queries import cascade_in_progress_to_parents

logger = logging.getLogger(__name__)


class AutoPilotService:
    """Backend service for discovering and launching parallel task batches."""

    async def get_next_batch(
        self,
        db: AsyncSession,
        parent_id: str,
        max_parallel: int = 0,
    ) -> List[Dict]:
        """Get the next batch of tasks that can run in parallel.

        Args:
            db: Database session.
            parent_id: The container issue (FEATURE, EPIC, STORY) to scan.
            max_parallel: Max tasks to return. 0 = use pool's available slots.

        Returns:
            List of dicts with task info:
              [{"id", "key", "title", "type", "status", "can_run", "blocked_by"}]
        """
        # Determine how many slots are available
        available = session_pool.available_slots
        if max_parallel > 0:
            available = min(available, max_parallel)

        if available <= 0:
            return []

        # Use the deep search to find leaf tasks across the full subtree
        runnable_ids = await dependency_analyzer.get_runnable_tasks_deep(
            db, parent_id
        )

        if not runnable_ids:
            return []

        # Cap to available slots
        batch_ids = runnable_ids[:available]

        # Fetch details for the batch
        result = await db.execute(
            select(Issue.id, Issue.key, Issue.title, Issue.type, Issue.status)
            .where(Issue.id.in_(batch_ids))
        )
        rows = result.fetchall()

        # Preserve the order from runnable_ids
        row_map = {r[0]: r for r in rows}
        batch = []
        for issue_id in batch_ids:
            row = row_map.get(issue_id)
            if row:
                batch.append({
                    "id": row[0],
                    "key": row[1],
                    "title": row[2],
                    "type": row[3],
                    "status": row[4],
                    "can_run": True,
                    "blocked_by": [],
                })

        return batch

    async def execute_batch(
        self,
        db: AsyncSession,
        tasks: List[Dict],
        provider: str,
        project_path: str,
        project_id: str,
    ) -> List[Dict]:
        """Start execution for a batch of tasks.

        Args:
            db: Database session.
            tasks: List of task dicts (must have "id" field at minimum).
            provider: Execution provider name (e.g., "claude_code").
            project_path: Path to the project on disk.
            project_id: Project database ID.

        Returns:
            List of result dicts:
              [{"issue_id", "issue_key", "session_id", "status", "error"}]
        """
        try:
            exec_provider = ExecutionProvider(provider)
        except ValueError:
            return [{
                "issue_id": t.get("id", ""),
                "issue_key": t.get("key", ""),
                "session_id": None,
                "status": "failed",
                "error": f"Invalid provider: {provider}",
            } for t in tasks]

        results = []
        for task in tasks:
            issue_id = task.get("id") or task.get("issue_id")
            if not issue_id:
                results.append({
                    "issue_id": None,
                    "issue_key": None,
                    "session_id": None,
                    "status": "failed",
                    "error": "Task missing 'id' field",
                })
                continue

            # Fetch issue details
            issue_result = await db.execute(
                select(Issue).where(Issue.id == issue_id)
            )
            issue = issue_result.scalar_one_or_none()
            if not issue:
                results.append({
                    "issue_id": issue_id,
                    "issue_key": task.get("key"),
                    "session_id": None,
                    "status": "failed",
                    "error": "Issue not found",
                })
                continue

            # Build rich execution context
            rich_prompt = await build_execution_context(
                db=db,
                issue_id=issue.id,
                issue_key=issue.key,
                issue_title=issue.title,
                issue_type=issue.type,
                issue_description=issue.description or "",
            )

            # Resolve root feature ID for cache preservation
            parent_chain = await get_parent_chain(db, issue.id)
            feature_id = None
            for ancestor in parent_chain:
                if ancestor["type"] == "FEATURE":
                    feature_id = ancestor["id"]
                    break

            # Cascade IN_PROGRESS to parents
            await cascade_in_progress_to_parents(db, issue.id)

            # Start the execution with dependency checking
            session = await terminal_service.start_execution(
                issue_id=issue.id,
                issue_key=issue.key,
                issue_title=issue.title,
                issue_description=issue.description or "",
                issue_type=issue.type,
                provider=exec_provider,
                project_path=project_path,
                project_id=project_id,
                prompt_override=rich_prompt,
                feature_id=feature_id,
                db=db,
            )

            results.append({
                "issue_id": issue.id,
                "issue_key": issue.key,
                "session_id": session.id,
                "status": session.status.value,
                "error": session.error,
            })

        # Commit all status cascades in one go
        await db.commit()

        return results

    async def get_autopilot_status(
        self,
        db: AsyncSession,
        parent_id: str,
    ) -> Dict:
        """Get a comprehensive status view for autopilot monitoring.

        Returns:
            {
                "parent_id": str,
                "parent_key": str,
                "parent_title": str,
                "pool": {pool status dict},
                "running": [running session info],
                "next_batch": [next runnable tasks],
                "progress": {
                    "total_leaf_tasks": int,
                    "completed": int,
                    "running": int,
                    "blocked": int,
                    "remaining": int,
                    "percent_complete": float,
                },
                "dependency_graph": {graph dict},
            }
        """
        # Fetch parent issue
        result = await db.execute(
            select(Issue.id, Issue.key, Issue.title, Issue.type)
            .where(Issue.id == parent_id)
        )
        parent = result.first()
        if not parent:
            return {"error": f"Parent issue {parent_id} not found"}

        # Get all leaf children for progress tracking
        leaf_tasks = await self._get_all_leaf_tasks(db, parent_id)

        completed = [t for t in leaf_tasks if t["status"] in COMPLETED_STATUSES]
        running = [t for t in leaf_tasks if t["status"] == "IN_PROGRESS"]
        remaining = [t for t in leaf_tasks if t["status"] in ("BACKLOG", "TODO")]

        total = len(leaf_tasks)
        pct = (len(completed) / total * 100) if total > 0 else 0.0

        # Get running sessions info
        running_sessions = terminal_service.get_running_sessions()
        running_info = [
            {
                "session_id": s.id,
                "issue_id": s.issue_id,
                "issue_key": s.issue_key,
                "issue_title": s.issue_title,
                "phase": s.phase.value,
                "progress_percent": s.progress_percent,
                "current_action": s.current_action,
            }
            for s in running_sessions
        ]

        # Get next batch (what could run if we have slots)
        next_batch = await self.get_next_batch(db, parent_id)

        # Get dependency graph for the direct children
        dep_graph = await dependency_analyzer.get_dependency_graph(db, parent_id)

        return {
            "parent_id": parent[0],
            "parent_key": parent[1],
            "parent_title": parent[2],
            "parent_type": parent[3],
            "pool": session_pool.get_pool_status(),
            "running": running_info,
            "next_batch": next_batch,
            "progress": {
                "total_leaf_tasks": total,
                "completed": len(completed),
                "running": len(running),
                "blocked": len(remaining) - len(next_batch),
                "remaining": len(remaining),
                "percent_complete": round(pct, 1),
            },
            "dependency_graph": dep_graph,
        }

    async def _get_all_leaf_tasks(
        self, db: AsyncSession, parent_id: str
    ) -> List[Dict]:
        """Recursively collect all leaf tasks (TASK, SUBTASK, BUG) in the subtree."""
        result = await db.execute(
            select(Issue.id, Issue.key, Issue.title, Issue.type, Issue.status)
            .where(Issue.parentId == parent_id)
            .order_by(Issue.sequence)
        )
        children = result.fetchall()

        leaf_tasks = []
        for child_id, key, title, itype, status in children:
            if itype in LEAF_TYPES:
                leaf_tasks.append({
                    "id": child_id,
                    "key": key,
                    "title": title,
                    "type": itype,
                    "status": status,
                })
            else:
                # Container -- recurse
                sub_tasks = await self._get_all_leaf_tasks(db, child_id)
                leaf_tasks.extend(sub_tasks)

        return leaf_tasks


# Singleton instance
autopilot_service = AutoPilotService()
