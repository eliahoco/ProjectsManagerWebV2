"""
Dependency Analyzer Service - Determines which tasks can run in parallel.

Analyzes issue hierarchy and IssueLink relationships to build a dependency
graph. Sibling tasks (same parent) are independent by default and can run
concurrently unless an explicit BLOCKS link constrains them.

Rules:
  - Only leaf types (TASK, SUBTASK, BUG) can execute -- not containers
    (FEATURE, EPIC, STORY).
  - Siblings under the same parent are independent unless linked via BLOCKS.
  - A BLOCKS link (A blocks B) means A must complete before B can start.
  - IS_BLOCKED_BY is the inverse of BLOCKS and is treated symmetrically.
"""

import logging
from typing import List, Tuple, Dict, Set, Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.issue import Issue, IssueLink

logger = logging.getLogger(__name__)

# Issue types that are executable leaf nodes (not containers)
LEAF_TYPES = {"TASK", "SUBTASK", "BUG"}

# Statuses that mean "not yet started" and eligible for execution
RUNNABLE_STATUSES = {"BACKLOG", "TODO"}

# Statuses that mean "finished" (dependency satisfied)
COMPLETED_STATUSES = {"DONE", "COMPLETED_WAITING_QA", "CANCELLED"}


class DependencyAnalyzer:
    """Analyzes issue hierarchy to determine which tasks can run in parallel."""

    async def can_execute(
        self, db: AsyncSession, issue_id: str
    ) -> Tuple[bool, str]:
        """
        Check if an issue can execute right now.

        Returns:
            (can_run, reason) -- reason explains why it can or cannot run.

        Rules applied:
          1. Issue must exist.
          2. Issue must be a leaf type (TASK, SUBTASK, BUG).
          3. Issue must be in a runnable status (BACKLOG, TODO) OR already
             IN_PROGRESS (re-execution / retry).
          4. No incomplete BLOCKS dependencies (issues that block this one).
        """
        # 1. Fetch the issue
        result = await db.execute(
            select(Issue.id, Issue.type, Issue.status, Issue.key)
            .where(Issue.id == issue_id)
        )
        row = result.first()
        if not row:
            return False, f"Issue {issue_id} not found"

        issue_type = row[1]
        issue_status = row[2]
        issue_key = row[3]

        # 2. Must be a leaf type
        if issue_type not in LEAF_TYPES:
            return (
                False,
                f"{issue_key} is a {issue_type} (container). "
                f"Only leaf types ({', '.join(sorted(LEAF_TYPES))}) can execute.",
            )

        # 3. Must be in an actionable status
        actionable_statuses = RUNNABLE_STATUSES | {"IN_PROGRESS"}
        if issue_status not in actionable_statuses:
            return (
                False,
                f"{issue_key} has status {issue_status}. "
                f"Must be one of {', '.join(sorted(actionable_statuses))} to execute.",
            )

        # 4. Check blocking dependencies
        #    A "blocks" link means: fromIssue BLOCKS toIssue
        #    So if another issue blocks THIS one, look for:
        #      IssueLink where toIssueId == issue_id AND linkType == 'BLOCKS'
        #    OR: IssueLink where fromIssueId == issue_id AND linkType == 'IS_BLOCKED_BY'
        blocker_ids = await self._get_blocker_ids(db, issue_id)

        if blocker_ids:
            # Check which blockers are still incomplete
            result = await db.execute(
                select(Issue.id, Issue.key, Issue.status)
                .where(Issue.id.in_(blocker_ids))
            )
            blockers = result.fetchall()
            incomplete = [
                (b[1], b[2]) for b in blockers if b[2] not in COMPLETED_STATUSES
            ]
            if incomplete:
                blocker_desc = ", ".join(
                    f"{key} ({status})" for key, status in incomplete
                )
                return (
                    False,
                    f"{issue_key} is blocked by incomplete tasks: {blocker_desc}",
                )

        return True, f"{issue_key} is ready to execute"

    async def get_runnable_tasks(
        self, db: AsyncSession, parent_id: str
    ) -> List[str]:
        """
        Get all tasks under a parent that can run right now.

        A task is runnable if:
          - It is a leaf type (TASK, SUBTASK, BUG)
          - Its status is BACKLOG or TODO
          - No incomplete blocking dependencies exist
          - It is not already running (IN_PROGRESS)

        Returns:
            List of issue IDs that are ready to execute, ordered by sequence.
        """
        # Fetch direct children that are leaf-type and in a runnable status
        result = await db.execute(
            select(Issue.id, Issue.key, Issue.type, Issue.status, Issue.sequence)
            .where(
                and_(
                    Issue.parentId == parent_id,
                    Issue.type.in_(LEAF_TYPES),
                    Issue.status.in_(RUNNABLE_STATUSES),
                )
            )
            .order_by(Issue.sequence)
        )
        candidates = result.fetchall()

        if not candidates:
            return []

        # Gather all candidate IDs for batch blocker lookup
        candidate_ids = [c[0] for c in candidates]
        blocker_map = await self._get_blocker_map(db, candidate_ids)

        runnable = []
        for issue_id, issue_key, issue_type, issue_status, sequence in candidates:
            blocker_ids = blocker_map.get(issue_id, set())
            if not blocker_ids:
                # No blockers at all -- runnable
                runnable.append(issue_id)
                continue

            # Check if all blockers are complete
            result = await db.execute(
                select(Issue.id, Issue.status)
                .where(Issue.id.in_(blocker_ids))
            )
            blockers = result.fetchall()
            all_complete = all(
                b[1] in COMPLETED_STATUSES for b in blockers
            )
            if all_complete:
                runnable.append(issue_id)

        return runnable

    async def get_runnable_tasks_deep(
        self, db: AsyncSession, parent_id: str
    ) -> List[str]:
        """
        Like get_runnable_tasks but also recurses into container children
        (STORY, EPIC) to find leaf tasks anywhere in the subtree.

        This is useful for AutoPilot: given a FEATURE or EPIC, find all
        leaf tasks across the entire hierarchy that are ready to run.
        """
        runnable = []

        # Get direct children
        result = await db.execute(
            select(Issue.id, Issue.type, Issue.status)
            .where(Issue.parentId == parent_id)
            .order_by(Issue.sequence)
        )
        children = result.fetchall()

        for child_id, child_type, child_status in children:
            if child_type in LEAF_TYPES:
                # Leaf node -- check if runnable
                if child_status in RUNNABLE_STATUSES:
                    can_run, _ = await self.can_execute(db, child_id)
                    if can_run:
                        runnable.append(child_id)
            else:
                # Container node -- recurse
                if child_status not in COMPLETED_STATUSES:
                    sub_runnable = await self.get_runnable_tasks_deep(db, child_id)
                    runnable.extend(sub_runnable)

        return runnable

    async def get_dependency_graph(
        self, db: AsyncSession, parent_id: str
    ) -> Dict:
        """
        Build a dependency graph for visualization.

        Returns:
            {
                "nodes": [
                    {"id": str, "key": str, "title": str, "type": str,
                     "status": str, "runnable": bool}
                ],
                "edges": [
                    {"from": str, "to": str, "type": "BLOCKS"}
                ],
                "parent_id": str,
                "stats": {
                    "total": int,
                    "runnable": int,
                    "running": int,
                    "completed": int,
                    "blocked": int,
                }
            }
        """
        # Fetch all direct children
        result = await db.execute(
            select(
                Issue.id, Issue.key, Issue.title, Issue.type,
                Issue.status, Issue.sequence,
            )
            .where(Issue.parentId == parent_id)
            .order_by(Issue.sequence)
        )
        children = result.fetchall()

        if not children:
            return {
                "nodes": [],
                "edges": [],
                "parent_id": parent_id,
                "stats": {"total": 0, "runnable": 0, "running": 0, "completed": 0, "blocked": 0},
            }

        child_ids = [c[0] for c in children]

        # Get all blocking links involving these children
        result = await db.execute(
            select(IssueLink.fromIssueId, IssueLink.toIssueId, IssueLink.linkType)
            .where(
                or_(
                    and_(
                        IssueLink.fromIssueId.in_(child_ids),
                        IssueLink.linkType == "BLOCKS",
                    ),
                    and_(
                        IssueLink.toIssueId.in_(child_ids),
                        IssueLink.linkType == "BLOCKS",
                    ),
                )
            )
        )
        links = result.fetchall()

        # Determine runnable set
        runnable_set = set(await self.get_runnable_tasks(db, parent_id))

        # Build nodes
        nodes = []
        stats = {"total": 0, "runnable": 0, "running": 0, "completed": 0, "blocked": 0}

        for issue_id, key, title, itype, status, sequence in children:
            is_runnable = issue_id in runnable_set
            node = {
                "id": issue_id,
                "key": key,
                "title": title,
                "type": itype,
                "status": status,
                "runnable": is_runnable,
            }
            nodes.append(node)

            stats["total"] += 1
            if status in COMPLETED_STATUSES:
                stats["completed"] += 1
            elif status == "IN_PROGRESS":
                stats["running"] += 1
            elif is_runnable:
                stats["runnable"] += 1
            elif status in RUNNABLE_STATUSES:
                stats["blocked"] += 1

        # Build edges
        edges = [
            {"from": link[0], "to": link[1], "type": link[2]}
            for link in links
        ]

        return {
            "nodes": nodes,
            "edges": edges,
            "parent_id": parent_id,
            "stats": stats,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_blocker_ids(
        self, db: AsyncSession, issue_id: str
    ) -> Set[str]:
        """
        Get all issue IDs that block the given issue.

        Considers both:
          - BLOCKS links where toIssueId == issue_id (other blocks this)
          - IS_BLOCKED_BY links where fromIssueId == issue_id (this is blocked by other)
        """
        result = await db.execute(
            select(IssueLink.fromIssueId, IssueLink.toIssueId, IssueLink.linkType)
            .where(
                or_(
                    and_(
                        IssueLink.toIssueId == issue_id,
                        IssueLink.linkType == "BLOCKS",
                    ),
                    and_(
                        IssueLink.fromIssueId == issue_id,
                        IssueLink.linkType == "IS_BLOCKED_BY",
                    ),
                )
            )
        )
        links = result.fetchall()

        blocker_ids = set()
        for from_id, to_id, link_type in links:
            if link_type == "BLOCKS":
                # fromIssue blocks toIssue -- fromIssue is the blocker
                blocker_ids.add(from_id)
            elif link_type == "IS_BLOCKED_BY":
                # fromIssue IS_BLOCKED_BY toIssue -- toIssue is the blocker
                blocker_ids.add(to_id)

        return blocker_ids

    async def _get_blocker_map(
        self, db: AsyncSession, issue_ids: List[str]
    ) -> Dict[str, Set[str]]:
        """
        Batch fetch blockers for multiple issues at once.

        Returns:
            Dict mapping each issue_id -> set of blocker issue IDs.
        """
        if not issue_ids:
            return {}

        result = await db.execute(
            select(IssueLink.fromIssueId, IssueLink.toIssueId, IssueLink.linkType)
            .where(
                or_(
                    and_(
                        IssueLink.toIssueId.in_(issue_ids),
                        IssueLink.linkType == "BLOCKS",
                    ),
                    and_(
                        IssueLink.fromIssueId.in_(issue_ids),
                        IssueLink.linkType == "IS_BLOCKED_BY",
                    ),
                )
            )
        )
        links = result.fetchall()

        blocker_map: Dict[str, Set[str]] = {}
        for from_id, to_id, link_type in links:
            if link_type == "BLOCKS":
                # fromIssue blocks toIssue
                blocker_map.setdefault(to_id, set()).add(from_id)
            elif link_type == "IS_BLOCKED_BY":
                # fromIssue is blocked by toIssue
                blocker_map.setdefault(from_id, set()).add(to_id)

        return blocker_map


# Singleton instance
dependency_analyzer = DependencyAnalyzer()
