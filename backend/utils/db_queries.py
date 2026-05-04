"""
Optimized database query utilities.

This module provides efficient query patterns for common operations,
replacing recursive Python loops with single SQL queries.
"""

from sqlalchemy import select, text, and_, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Set
from datetime import datetime


# CB-1975 / CB-1976 — cycle-detection helper for IssueLink relations.
#
# Asymmetric transitive families only. Maps each user-facing linkType to the
# canonical-direction family that lives in the IssueLink graph; symmetric
# types (RELATES_TO, DUPLICATES / IS_DUPLICATED_BY) are present with value
# ``None`` so an unknown linkType raises (catches misuse loudly) while the
# known-symmetric set short-circuits to "no cycle" without a DB hit.
#
# Must stay in sync with ``api/relations.py::_TRANSITIVE_FAMILIES`` and the
# ``LinkType`` enum in ``models/schemas.py``. CB-1977 will dedupe the two
# dicts; until then a new LinkType added in one place must be mirrored
# here. The ``_CYCLE_KNOWN_LINK_TYPES`` set below catches the drift at
# call time even before that cleanup lands.
_CYCLE_TRANSITIVE_FAMILIES: dict = {
    "BLOCKS": "BLOCKS",
    "IS_BLOCKED_BY": "BLOCKS",
    "CAUSES": "CAUSES",
    "CAUSED_BY": "CAUSES",
}

# Symmetric link types — known but cycle-irrelevant. Listed explicitly so
# ``check_cycle_on_insert`` can distinguish "known and skipped" from
# "unknown and rejected" rather than collapsing both to a silent ``None``.
_CYCLE_SYMMETRIC_LINK_TYPES: frozenset = frozenset((
    "RELATES_TO",
    "DUPLICATES",
    "IS_DUPLICATED_BY",
))

_CYCLE_KNOWN_LINK_TYPES: frozenset = frozenset(
    _CYCLE_TRANSITIVE_FAMILIES
) | _CYCLE_SYMMETRIC_LINK_TYPES

# Hard cap on recursive-CTE depth (per CB-1976 spec). Bounds the longest
# path the cycle search will walk; the CTE's per-path ``seen`` membership
# guard further bounds total work to O(N) where N is the reachable
# node-set in the canonical family. Together they prevent both
# pathological-depth chains and diamond-shaped row explosion. A cycle
# deeper than 50 hops will not be detected — the cap is a DoS guard, not
# a correctness boundary.
_CYCLE_DEPTH_CAP = 50

# Path delimiter for the recursive CTE's path column. ``\x1f`` (ASCII Unit
# Separator) is a non-printable C0 control char that cannot appear in any
# text-encoded issue id (CUIDs match ``[a-z0-9]+``; the request layer's
# Pydantic regex restricts to ``[A-Za-z0-9_\-]+``). Using a non-printable
# means a direct-DB-write tool that plants a malformed id still cannot
# inject false path entries via delimiter collision; ``split('\x1f')``
# round-trips losslessly regardless of id alphabet.
_CYCLE_PATH_DELIMITER = "\x1f"


async def get_all_descendant_ids(db: AsyncSession, parent_id: str) -> List[str]:
    """
    Get all descendant issue IDs for a given parent using a single recursive CTE query.

    This replaces the N+1 recursive Python loop pattern with a single SQL query
    that efficiently traverses the entire hierarchy.

    For SQLite, we use a recursive CTE (Common Table Expression).

    Args:
        db: AsyncSession database session
        parent_id: The ID of the parent issue

    Returns:
        List of all descendant issue IDs (children, grandchildren, etc.)
    """
    # Recursive CTE to get all descendants in a single query
    # This works with SQLite which supports recursive CTEs since version 3.8.3
    sql = text("""
        WITH RECURSIVE descendants AS (
            -- Base case: direct children of the parent
            SELECT id, parentId
            FROM Issue
            WHERE parentId = :parent_id

            UNION ALL

            -- Recursive case: children of children
            SELECT i.id, i.parentId
            FROM Issue i
            INNER JOIN descendants d ON i.parentId = d.id
        )
        SELECT id FROM descendants
    """)

    result = await db.execute(sql, {"parent_id": parent_id})
    return [row[0] for row in result.fetchall()]


async def get_all_descendants_with_details(
    db: AsyncSession,
    parent_id: str,
    columns: List[str] = None
) -> List[dict]:
    """
    Get all descendant issues with specified columns using a single recursive CTE query.

    Args:
        db: AsyncSession database session
        parent_id: The ID of the parent issue
        columns: List of column names to fetch (defaults to id, key, title, type, status, sequence)

    Returns:
        List of dictionaries with descendant data and their level in the hierarchy
    """
    if columns is None:
        columns = ["id", "key", "title", "type", "status", "sequence", "description", "completedAt"]

    # Build the SELECT clause
    base_select = ", ".join(columns)
    recursive_select = ", ".join([f"i.{col}" for col in columns])

    sql = text(f"""
        WITH RECURSIVE descendants AS (
            -- Base case: direct children (level 0)
            SELECT {base_select}, parentId, 0 as level
            FROM Issue
            WHERE parentId = :parent_id

            UNION ALL

            -- Recursive case: children of children
            SELECT {recursive_select}, i.parentId, d.level + 1
            FROM Issue i
            INNER JOIN descendants d ON i.parentId = d.id
        )
        SELECT *, level FROM descendants ORDER BY level, sequence
    """)

    result = await db.execute(sql, {"parent_id": parent_id})
    rows = result.fetchall()

    # Convert to list of dicts
    return [
        {**dict(zip(columns + ["parentId", "level"], row))}
        for row in rows
    ]


async def bulk_update_descendant_status(
    db: AsyncSession,
    parent_id: str,
    new_status: str,
    completed_at: datetime = None
) -> int:
    """
    Update status of all descendants in a single query.

    This replaces the recursive Python loop that updates each child one by one.

    Args:
        db: AsyncSession database session
        parent_id: The ID of the parent issue
        new_status: The new status to set
        completed_at: Optional completion timestamp

    Returns:
        Number of issues updated
    """
    # First get all descendant IDs using the CTE
    descendant_ids = await get_all_descendant_ids(db, parent_id)

    if not descendant_ids:
        return 0

    # Build the update values
    from models import Issue
    update_values = {"status": new_status, "updatedAt": datetime.utcnow()}
    if completed_at:
        update_values["completedAt"] = completed_at

    # Perform bulk update
    stmt = (
        update(Issue)
        .where(
            and_(
                Issue.id.in_(descendant_ids),
                Issue.status != new_status  # Only update if status is different
            )
        )
        .values(**update_values)
    )

    result = await db.execute(stmt)
    return result.rowcount


async def bulk_update_descendant_status_detailed(
    db: AsyncSession,
    parent_id: str,
    new_status: str,
    completed_at: datetime = None
) -> List[dict]:
    """
    Same as bulk_update_descendant_status but returns transitioned rows.

    Used by callers that need to emit per-issue side effects (e.g. fire
    trigger_qa_generation for each descendant newly moved to
    COMPLETED_WAITING_QA). Returns descendants whose status CHANGED only.

    Returns:
        List of dicts with keys: id, key, projectId — one per transitioned issue.
    """
    from models import Issue

    descendant_ids = await get_all_descendant_ids(db, parent_id)
    if not descendant_ids:
        return []

    # Snapshot which descendants are actually going to transition
    before = await db.execute(
        select(Issue.id, Issue.key, Issue.projectId)
        .where(and_(Issue.id.in_(descendant_ids), Issue.status != new_status))
    )
    transitions = [{"id": r[0], "key": r[1], "projectId": r[2]} for r in before.fetchall()]
    if not transitions:
        return []

    update_values = {"status": new_status, "updatedAt": datetime.utcnow()}
    if completed_at:
        update_values["completedAt"] = completed_at

    stmt = (
        update(Issue)
        .where(and_(Issue.id.in_([t["id"] for t in transitions])))
        .values(**update_values)
    )
    await db.execute(stmt)
    return transitions


async def batch_get_issues_by_keys(
    db: AsyncSession,
    keys: List[str]
) -> dict:
    """
    Fetch multiple issues by their keys in a single query.

    This replaces the loop pattern where each key is looked up individually.

    Args:
        db: AsyncSession database session
        keys: List of issue keys to fetch

    Returns:
        Dictionary mapping uppercase key to Issue object
    """
    if not keys:
        return {}

    from models import Issue

    # Normalize keys to uppercase
    upper_keys = [k.upper() for k in keys]

    result = await db.execute(
        select(Issue).where(Issue.key.in_(upper_keys))
    )
    issues = result.scalars().all()

    return {issue.key.upper(): issue for issue in issues}


async def batch_check_commit_links_exist(
    db: AsyncSession,
    issue_commit_pairs: List[tuple]
) -> Set[tuple]:
    """
    Check which issue-commit links already exist in a single query.

    Args:
        db: AsyncSession database session
        issue_commit_pairs: List of (issue_id, commit_hash) tuples to check

    Returns:
        Set of (issue_id, commit_hash) tuples that already exist
    """
    if not issue_commit_pairs:
        return set()

    from models import CommitLink

    # Build OR conditions for each pair
    conditions = []
    for issue_id, commit_hash in issue_commit_pairs:
        conditions.append(
            and_(
                CommitLink.issueId == issue_id,
                CommitLink.commitHash == commit_hash
            )
        )

    from sqlalchemy import or_
    result = await db.execute(
        select(CommitLink.issueId, CommitLink.commitHash).where(or_(*conditions))
    )

    return {(row[0], row[1]) for row in result.fetchall()}


async def get_qa_tasks_for_issue_tree(
    db: AsyncSession,
    root_issue_id: str
) -> List:
    """
    Get all QA tasks linked to an issue and all its descendants in a single query.

    This combines getting descendant IDs and QA tasks into two efficient queries
    instead of N+1 queries per issue.

    Args:
        db: AsyncSession database session
        root_issue_id: The ID of the root issue

    Returns:
        List of QATask objects
    """
    from models.qa import QATask, QATaskIssueLink

    # Get all descendant IDs plus the root
    descendant_ids = await get_all_descendant_ids(db, root_issue_id)
    all_issue_ids = [root_issue_id] + descendant_ids

    # Get all QA tasks linked to any of these issues
    result = await db.execute(
        select(QATask)
        .join(QATaskIssueLink)
        .where(QATaskIssueLink.issueId.in_(all_issue_ids))
    )

    return result.scalars().unique().all()


async def get_all_descendants_for_multiple_roots(
    db: AsyncSession,
    root_ids: List[str]
) -> dict:
    """
    Get all descendant issue IDs for multiple root issues in a SINGLE query.

    This replaces N separate CTE queries with ONE query that handles all roots,
    dramatically reducing database round trips for batch operations.

    Args:
        db: AsyncSession database session
        root_ids: List of root issue IDs

    Returns:
        Dictionary mapping root_id to set of all descendant IDs (not including root)
    """
    if not root_ids:
        return {}

    # Build placeholders for the IN clause (SQLite requires this format)
    placeholders = ", ".join([f":root_{i}" for i in range(len(root_ids))])
    params = {f"root_{i}": root_id for i, root_id in enumerate(root_ids)}

    # Single CTE query that finds all descendants for all roots at once
    # Uses a recursive CTE with root tracking to maintain which descendants
    # belong to which root
    sql = text(f"""
        WITH RECURSIVE descendants AS (
            -- Base case: direct children of any root, tracking which root they belong to
            SELECT id, parentId, parentId as rootId
            FROM Issue
            WHERE parentId IN ({placeholders})

            UNION ALL

            -- Recursive case: children of children, preserving the original root
            SELECT i.id, i.parentId, d.rootId
            FROM Issue i
            INNER JOIN descendants d ON i.parentId = d.id
        )
        SELECT rootId, id FROM descendants
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    # Build mapping: root_id -> set of descendant IDs
    root_to_descendants: dict = {root_id: set() for root_id in root_ids}
    for root_id, descendant_id in rows:
        if root_id in root_to_descendants:
            root_to_descendants[root_id].add(descendant_id)

    return root_to_descendants


async def batch_get_qa_tasks_for_issue_trees(
    db: AsyncSession,
    root_issue_ids: List[str]
) -> dict:
    """
    Get all QA tasks for multiple issue trees in optimized batch queries.

    OPTIMIZED: Uses a single multi-root CTE query instead of N separate queries,
    reducing database round trips from O(N) to O(1) for descendant fetching.

    Total queries: 3 (down from N+2 where N = number of root issues)
    1. Single CTE query for ALL descendants of ALL roots
    2. Single query for ALL QA task links
    3. Single query for ALL QA tasks

    Args:
        db: AsyncSession database session
        root_issue_ids: List of root issue IDs

    Returns:
        Dictionary mapping root_issue_id to list of QATask objects
    """
    from models.qa import QATask, QATaskIssueLink

    if not root_issue_ids:
        return {}

    # OPTIMIZATION: Single CTE query gets descendants for ALL roots at once
    root_to_descendants = await get_all_descendants_for_multiple_roots(db, root_issue_ids)

    # Build mapping: root_id -> set of all issue IDs in tree (including root)
    root_to_tree_ids: dict = {}
    all_tree_ids: Set[str] = set(root_issue_ids)

    for root_id in root_issue_ids:
        tree_ids = {root_id}
        tree_ids.update(root_to_descendants.get(root_id, set()))
        root_to_tree_ids[root_id] = tree_ids
        all_tree_ids.update(tree_ids)

    if not all_tree_ids:
        return {root_id: [] for root_id in root_issue_ids}

    # Single query to get all QA task links for all tree issues
    link_result = await db.execute(
        select(QATaskIssueLink.issueId, QATaskIssueLink.qaTaskId)
        .where(QATaskIssueLink.issueId.in_(list(all_tree_ids)))
    )
    links = link_result.fetchall()

    # Build mapping: issue_id -> set of qa_task_ids
    issue_to_qa_task_ids: dict = {}
    all_qa_task_ids: Set[str] = set()
    for issue_id, qa_task_id in links:
        if issue_id not in issue_to_qa_task_ids:
            issue_to_qa_task_ids[issue_id] = set()
        issue_to_qa_task_ids[issue_id].add(qa_task_id)
        all_qa_task_ids.add(qa_task_id)

    if not all_qa_task_ids:
        return {root_id: [] for root_id in root_issue_ids}

    # Single query to get all QA tasks
    qa_result = await db.execute(
        select(QATask).where(QATask.id.in_(list(all_qa_task_ids)))
    )
    qa_tasks = {task.id: task for task in qa_result.scalars().all()}

    # Build final result: root_id -> list of QA tasks
    result_map: dict = {}
    for root_id in root_issue_ids:
        tree_issue_ids = root_to_tree_ids.get(root_id, set())
        qa_task_ids_for_tree: Set[str] = set()
        for issue_id in tree_issue_ids:
            qa_task_ids_for_tree.update(issue_to_qa_task_ids.get(issue_id, set()))
        result_map[root_id] = [qa_tasks[tid] for tid in qa_task_ids_for_tree if tid in qa_tasks]

    return result_map


async def get_issues_with_count(
    db: AsyncSession,
    project_id: str,
    filters: dict = None,
    page: int = 1,
    page_size: int = 50,
    order_by: str = "sequence",
    order_desc: bool = True
) -> tuple:
    """
    Get paginated issues with total count in a single round-trip using window functions.

    This is more efficient than executing separate queries for data and count,
    especially for complex filter conditions.

    Args:
        db: AsyncSession database session
        project_id: Project ID to filter by
        filters: Dictionary of filter conditions
        page: Page number (1-indexed)
        page_size: Number of items per page
        order_by: Column to order by
        order_desc: True for descending order

    Returns:
        Tuple of (issues list, total count)
    """
    from models import Issue

    filters = filters or {}
    offset = (page - 1) * page_size

    # Build WHERE clause conditions
    conditions = [f'"projectId" = :project_id']
    params = {"project_id": project_id, "limit": page_size, "offset": offset}

    if filters.get("status"):
        conditions.append('"status" = :status')
        params["status"] = filters["status"]

    if filters.get("type"):
        conditions.append('"type" = :type')
        params["type"] = filters["type"]

    if filters.get("priority"):
        conditions.append('"priority" = :priority')
        params["priority"] = filters["priority"]

    if filters.get("assignee"):
        conditions.append('"assignee" = :assignee')
        params["assignee"] = filters["assignee"]

    if filters.get("parent_id"):
        conditions.append('"parentId" = :parent_id')
        params["parent_id"] = filters["parent_id"]

    if filters.get("breakdown_batch_id"):
        conditions.append('"breakdownBatchId" = :breakdown_batch_id')
        params["breakdown_batch_id"] = filters["breakdown_batch_id"]

    where_clause = " AND ".join(conditions)
    order_direction = "DESC" if order_desc else "ASC"

    # Single query with window function for count
    sql = text(f"""
        SELECT *,
               COUNT(*) OVER() as total_count
        FROM Issue
        WHERE {where_clause}
        ORDER BY "{order_by}" {order_direction}
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    if not rows:
        return [], 0

    # Extract total count from first row
    total_count = rows[0][-1] if rows else 0

    # Convert rows to Issue objects (excluding the total_count column)
    issues = []
    for row in rows:
        # Map row to Issue object
        # Note: This requires knowing the column order
        issue_data = dict(row._mapping)
        issue_data.pop('total_count', None)
        issue = Issue(**issue_data)
        issues.append(issue)

    return issues, total_count


async def get_project_issue_counts(
    db: AsyncSession,
    project_id: str
) -> dict:
    """
    Get issue counts grouped by status and type in a single query.

    Useful for dashboard/summary views without loading all issues.

    Args:
        db: AsyncSession database session
        project_id: Project ID to count for

    Returns:
        Dictionary with 'by_status' and 'by_type' counts
    """
    sql = text("""
        SELECT
            'status' as group_type,
            status as group_value,
            COUNT(*) as count
        FROM Issue
        WHERE projectId = :project_id
        GROUP BY status

        UNION ALL

        SELECT
            'type' as group_type,
            type as group_value,
            COUNT(*) as count
        FROM Issue
        WHERE projectId = :project_id
        GROUP BY type
    """)

    result = await db.execute(sql, {"project_id": project_id})
    rows = result.fetchall()

    counts = {
        "by_status": {},
        "by_type": {},
        "total": 0
    }

    for group_type, group_value, count in rows:
        if group_type == "status":
            counts["by_status"][group_value] = count
        else:
            counts["by_type"][group_value] = count

    # Calculate total
    counts["total"] = sum(counts["by_status"].values())

    return counts


async def cascade_status_to_parents(
    db: AsyncSession,
    issue_id: str,
    target_status: str = "COMPLETED_WAITING_QA"
) -> List[str]:
    """
    Cascade status updates upward to parent containers (STORY, EPIC, FEATURE).

    When all children of a parent are in the target status (or DONE),
    the parent is updated to the target status.

    This implements the rule:
    - STORY becomes COMPLETED_WAITING_QA when ALL its TASKs/SUBTASKs are COMPLETED_WAITING_QA or DONE
    - EPIC becomes COMPLETED_WAITING_QA when ALL its STORYs are COMPLETED_WAITING_QA or DONE
    - FEATURE becomes COMPLETED_WAITING_QA when ALL its EPICs are COMPLETED_WAITING_QA or DONE

    Args:
        db: AsyncSession database session
        issue_id: The ID of the issue that was just updated
        target_status: The status to cascade (default: COMPLETED_WAITING_QA)

    Returns:
        List of parent issue IDs that were updated
    """
    from models import Issue

    updated_parents = []
    current_id = issue_id

    # Walk up the hierarchy
    while True:
        # Get the current issue's parent
        result = await db.execute(
            select(Issue.parentId).where(Issue.id == current_id)
        )
        row = result.first()

        if not row or not row[0]:
            # No parent, we're done
            break

        parent_id = row[0]

        # Get parent issue details
        parent_result = await db.execute(
            select(Issue).where(Issue.id == parent_id)
        )
        parent = parent_result.scalar_one_or_none()

        if not parent:
            break

        # Only cascade to container types (FEATURE, EPIC, STORY)
        if parent.type not in ("FEATURE", "EPIC", "STORY"):
            break

        # Session uses autoflush=False — flush so the just-mutated child's
        # new status is visible to the sibling SELECT below. Without this the
        # query reads pre-mutation DB state and the gate never closes.
        await db.flush()

        # Check if ALL children of this parent are in target_status or DONE
        children_result = await db.execute(
            select(Issue.id, Issue.status).where(Issue.parentId == parent_id)
        )
        children = children_result.fetchall()

        if not children:
            break

        # All children must be in COMPLETED_WAITING_QA or DONE
        all_completed = all(
            child_status in (target_status, "DONE")
            for _, child_status in children
        )

        if all_completed and parent.status != target_status and parent.status != "DONE":
            # Update parent to target status
            parent.status = target_status
            parent.updatedAt = datetime.utcnow()
            updated_parents.append(parent_id)

            # Continue up the hierarchy
            current_id = parent_id
        else:
            # Parent can't be cascaded, stop here
            break

    return updated_parents


async def cascade_status_to_parents_detailed(
    db: AsyncSession,
    issue_id: str,
    target_status: str = "COMPLETED_WAITING_QA"
) -> List[dict]:
    """
    Same as cascade_status_to_parents but returns transitioned rows.

    Returns list of dicts with keys: id, key, projectId — one per ancestor
    whose status was actually changed to target_status. Used by callers that
    need to emit per-issue side effects (e.g. QA trigger) for each transition.
    """
    from models import Issue

    transitions: List[dict] = []
    current_id = issue_id

    while True:
        result = await db.execute(
            select(Issue.parentId).where(Issue.id == current_id)
        )
        row = result.first()
        if not row or not row[0]:
            break

        parent_id = row[0]
        parent_result = await db.execute(
            select(Issue).where(Issue.id == parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            break
        if parent.type not in ("FEATURE", "EPIC", "STORY"):
            break

        # Flush pending child mutations so the sibling SELECT sees the new
        # status (session is autoflush=False).
        await db.flush()

        children_result = await db.execute(
            select(Issue.id, Issue.status).where(Issue.parentId == parent_id)
        )
        children = children_result.fetchall()
        if not children:
            break

        all_completed = all(
            child_status in (target_status, "DONE")
            for _, child_status in children
        )

        if all_completed and parent.status != target_status and parent.status != "DONE":
            parent.status = target_status
            parent.updatedAt = datetime.utcnow()
            transitions.append({"id": parent.id, "key": parent.key, "projectId": parent.projectId})
            current_id = parent_id
        else:
            break

    return transitions


async def cascade_revert_to_parents(
    db: AsyncSession,
    issue_id: str
) -> List[str]:
    """
    Cascade a "revert off completion" upward to parent containers.

    Symmetric counterpart to cascade_status_to_parents. When a child issue moves
    OFF COMPLETED_WAITING_QA / DONE (back to BACKLOG / TODO / IN_PROGRESS / IN_REVIEW),
    any parent that was previously rolled up to CWQ should revert to IN_PROGRESS,
    because its completion gate has been re-opened by the now-incomplete child.

    Stops walking up once an ancestor is encountered that was never at CWQ — its
    own ancestors are unaffected by this child's revert.

    Args:
        db: AsyncSession database session
        issue_id: The ID of the issue that was just moved off CWQ/DONE

    Returns:
        List of parent issue IDs that were reverted to IN_PROGRESS
    """
    from models import Issue

    updated_parents = []
    current_id = issue_id

    # Walk up the hierarchy
    while True:
        # Get the current issue's parent
        result = await db.execute(
            select(Issue.parentId).where(Issue.id == current_id)
        )
        row = result.first()

        if not row or not row[0]:
            break

        parent_id = row[0]

        # Get parent
        parent_result = await db.execute(
            select(Issue).where(Issue.id == parent_id)
        )
        parent = parent_result.scalar_one_or_none()

        if not parent:
            break

        # Only cascade to container types
        if parent.type not in ("FEATURE", "EPIC", "STORY"):
            break

        # If parent was never rolled up to CWQ, the chain stops here.
        # (Its status reflects work that this child's revert does not invalidate.)
        if parent.status not in ("COMPLETED_WAITING_QA", "DONE"):
            break

        # Session uses autoflush=False — flush so the just-mutated child's
        # new (non-CWQ) status is visible to the sibling SELECT below.
        await db.flush()

        # Re-evaluate the gate: are ALL of this parent's children still at
        # CWQ or DONE? If yes, the cascade-up gate is intact (e.g., a sibling
        # was the cause and is still complete) and we leave the parent alone.
        children_result = await db.execute(
            select(Issue.status).where(Issue.parentId == parent_id)
        )
        children_statuses = [r[0] for r in children_result.fetchall()]

        if not children_statuses:
            break

        all_complete = all(
            s in ("COMPLETED_WAITING_QA", "DONE")
            for s in children_statuses
        )

        if all_complete:
            # Gate still closed (this child must have been re-completed
            # by a sibling path, or the revert was already cascaded).
            # Stop walking — nothing to undo.
            break

        # Gate is open: revert parent off CWQ/DONE back to IN_PROGRESS.
        parent.status = "IN_PROGRESS"
        parent.updatedAt = datetime.utcnow()
        updated_parents.append(parent_id)

        # Continue walking up — the just-reverted parent may itself have
        # re-opened a gate further up the chain.
        current_id = parent_id

    return updated_parents


async def cascade_in_progress_to_parents(
    db: AsyncSession,
    issue_id: str
) -> List[str]:
    """
    Cascade IN_PROGRESS status upward to parent containers (STORY, EPIC, FEATURE).

    When any child starts executing, all parent containers should be IN_PROGRESS.
    This ensures that EPICs and STORYs properly reflect that work is happening.

    Args:
        db: AsyncSession database session
        issue_id: The ID of the issue that just started (set to IN_PROGRESS)

    Returns:
        List of parent issue IDs that were updated
    """
    from models import Issue

    updated_parents = []
    current_id = issue_id

    # Walk up the hierarchy
    while True:
        # Get the current issue's parent
        result = await db.execute(
            select(Issue.parentId).where(Issue.id == current_id)
        )
        row = result.first()

        if not row or not row[0]:
            # No parent, we're done
            break

        parent_id = row[0]

        # Get parent issue details
        parent_result = await db.execute(
            select(Issue).where(Issue.id == parent_id)
        )
        parent = parent_result.scalar_one_or_none()

        if not parent:
            break

        # Only cascade to container types (FEATURE, EPIC, STORY)
        if parent.type not in ("FEATURE", "EPIC", "STORY"):
            break

        # Never demote a parent that has reached completion. If we hit a
        # COMPLETED_WAITING_QA / DONE ancestor, stop walking — sibling activity
        # under it should not regress its status. (CB-1952)
        if parent.status in ("COMPLETED_WAITING_QA", "DONE"):
            break

        # Set parent to IN_PROGRESS if it's in BACKLOG or TODO
        if parent.status in ("BACKLOG", "TODO"):
            parent.status = "IN_PROGRESS"
            parent.updatedAt = datetime.utcnow()
            updated_parents.append(parent_id)

        # Continue up the hierarchy even if we didn't update
        # (to ensure all ancestors are checked)
        current_id = parent_id

    return updated_parents


async def cascade_done_to_parents(
    db: AsyncSession,
    issue_id: str
) -> List[str]:
    """
    Cascade DONE status upward to parent containers.

    When ALL children of a parent are DONE, the parent is also marked as DONE.

    Args:
        db: AsyncSession database session
        issue_id: The ID of the issue that was just marked DONE

    Returns:
        List of parent issue IDs that were updated
    """
    from models import Issue

    updated_parents = []
    current_id = issue_id

    while True:
        # Get parent ID
        result = await db.execute(
            select(Issue.parentId).where(Issue.id == current_id)
        )
        row = result.first()

        if not row or not row[0]:
            break

        parent_id = row[0]

        # Get parent
        parent_result = await db.execute(
            select(Issue).where(Issue.id == parent_id)
        )
        parent = parent_result.scalar_one_or_none()

        if not parent or parent.type not in ("FEATURE", "EPIC", "STORY"):
            break

        # Flush pending child mutations so the sibling SELECT sees the new
        # status (session is autoflush=False).
        await db.flush()

        # Check if ALL children are DONE
        children_result = await db.execute(
            select(Issue.status).where(Issue.parentId == parent_id)
        )
        children_statuses = [row[0] for row in children_result.fetchall()]

        if not children_statuses:
            break

        all_done = all(status == "DONE" for status in children_statuses)

        if all_done and parent.status != "DONE":
            parent.status = "DONE"
            parent.completedAt = datetime.utcnow()
            parent.updatedAt = datetime.utcnow()
            updated_parents.append(parent_id)
            current_id = parent_id
        else:
            break

    return updated_parents


async def compute_group_status(
    db: AsyncSession,
    group_id: str,
):
    """Aggregate-status snapshot for an IssueGroup (CB-1958 / CB-1966 / CB-1967).

    Single GROUP BY query joins ``IssueGroupMember`` to ``Issue`` and bins the
    member statuses. Returns a :class:`GroupAggregateStatus` with:

    * ``statusBreakdown`` — ``{status: count}`` for every status present.
    * ``completionPercent`` — share of members in ``DONE`` or
      ``COMPLETED_WAITING_QA``, expressed in ``[0, 100]`` and rounded to two
      decimals. Uses the same "complete" predicate as
      ``cascade_status_to_parents`` so the helper agrees with the cascade
      gate. ``CANCELLED`` rows count toward the denominator (no carve-out)
      to keep the percentage stable as members are cancelled vs. dropped.
    * ``dominantStatus`` — status with the highest count; ties broken by
      lexicographic sort of the status string (deterministic, no hidden
      enum priority — ``dominantStatus`` is plain str, see schema comment).

    Empty groups (and groups whose members are all orphaned by FK cleanup)
    return ``GroupAggregateStatus()`` defaults: ``{}``, ``0.0``, ``None``.

    Authorization contract: this is a util — it does NOT verify that the
    caller can read ``group_id``. Routers MUST scope on
    ``IssueGroup.projectId`` before invoking, or the helper becomes an IDOR
    surface for any caller who can guess a group id.
    """
    from models import GroupAggregateStatus, IssueGroupMember
    from models.issue import Issue

    result = await db.execute(
        select(Issue.status, func.count())
        .join(IssueGroupMember, IssueGroupMember.issueId == Issue.id)
        .where(IssueGroupMember.groupId == group_id)
        .group_by(Issue.status)
    )
    rows = result.all()

    # ``Issue.status`` is NOT NULL with a server-side default, so a None key
    # is unreachable today — filter anyway so a corrupted/migrated row can't
    # crash ``min()`` with a str/None comparison (defense in depth).
    breakdown = {status: int(count) for status, count in rows if status is not None}

    if not breakdown:
        return GroupAggregateStatus()

    total = sum(breakdown.values())

    completed = breakdown.get("DONE", 0) + breakdown.get("COMPLETED_WAITING_QA", 0)
    completion_percent = round(completed * 100.0 / total, 2) if total else 0.0

    # Tie-break: pick the lexicographically smallest status name among those
    # with the top count. Deterministic, no hidden enum priority.
    top_count = max(breakdown.values())
    dominant_status = min(s for s, c in breakdown.items() if c == top_count)

    return GroupAggregateStatus(
        statusBreakdown=breakdown,
        completionPercent=completion_percent,
        dominantStatus=dominant_status,
    )


async def get_recent_activity(
    db: AsyncSession,
    project_id: str = None,
    issue_id: str = None,
    limit: int = 50,
    since: datetime = None
) -> List[dict]:
    """
    Get recent activity with optimized query using indexes.

    Args:
        db: AsyncSession database session
        project_id: Optional project ID to filter by
        issue_id: Optional issue ID to filter by
        limit: Maximum number of activities to return
        since: Only return activities after this timestamp

    Returns:
        List of activity dictionaries with issue context
    """
    conditions = []
    params = {"limit": limit}

    if issue_id:
        conditions.append('a."issueId" = :issue_id')
        params["issue_id"] = issue_id
    elif project_id:
        conditions.append('i."projectId" = :project_id')
        params["project_id"] = project_id

    if since:
        conditions.append('a."createdAt" > :since')
        params["since"] = since

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    sql = text(f"""
        SELECT
            a.id,
            a."issueId",
            a.actor,
            a.action,
            a.field,
            a."oldValue",
            a."newValue",
            a."createdAt",
            i.key as issue_key,
            i.title as issue_title
        FROM Activity a
        JOIN Issue i ON a."issueId" = i.id
        WHERE {where_clause}
        ORDER BY a."createdAt" DESC
        LIMIT :limit
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    return [
        {
            "id": row[0],
            "issueId": row[1],
            "actor": row[2],
            "action": row[3],
            "field": row[4],
            "oldValue": row[5],
            "newValue": row[6],
            "createdAt": row[7],
            "issueKey": row[8],
            "issueTitle": row[9],
        }
        for row in rows
    ]


async def check_cycle_on_insert(
    db: AsyncSession,
    from_id: str,
    to_id: str,
    link_type: str,
) -> Optional[List[str]]:
    """Detect whether inserting a typed relation would close a directed cycle.

    Recursive-CTE reachability check for the asymmetric transitive families
    BLOCKS (BLOCKS / IS_BLOCKED_BY) and CAUSES (CAUSES / CAUSED_BY). The
    symmetric families (RELATES_TO, DUPLICATES / IS_DUPLICATED_BY) carry no
    direction so cannot form cycles — returns ``None`` for those without a
    DB hit.

    The proposed ``(from_id, to_id, link_type)`` is mapped to its canonical
    family edge ``a → b``. A cycle exists iff ``b`` can already reach ``a``
    via existing canonical-family rows. The CTE walks outgoing edges of the
    canonical family only — companion rows in the inverse direction are
    deliberately skipped so each undirected pair is counted once. This
    matches the canonical-edge convention used by the create path
    (``api/relations.py``) so the helper and the route agree on what counts
    as a cycle.

    Runs inside the caller's transaction. The CTE sees in-flight edges
    flushed by the caller (matters for bulk inserts where consecutive
    candidates can close a cycle against an earlier sibling in the same
    batch — caller must ``await db.flush()`` between iterations to make
    the new edges visible).

    Args:
        db: Async session participating in the caller's transaction.
        from_id: User-supplied source issue id.
        to_id: User-supplied target issue id.
        link_type: One of the LinkType enum values.

    Returns:
        ``None`` if no cycle would form, or if ``link_type`` is non-transitive.
        On detection: a list of canonical issue ids tracing the closing
        cycle, ordered as ``[a, b, ...intermediaries..., a]`` — the
        proposed canonical edge ``a → b`` followed by the existing path
        ``b → ... → a`` back to the source. Suitable for surfacing to the
        user as ``details.path`` per the CB-1977 contract.

    Authorization contract: this is a util — it does NOT verify that
    ``from_id`` and ``to_id`` share a project. Routers MUST enforce
    same-project before invoking, or the returned cycle path becomes an
    IDOR surface for any caller who can guess an issue id from another
    project. ``api/relations.py::create_relation`` performs this check
    before invoking the helper; new callers must follow suit.

    Raises:
        ValueError: if ``link_type`` is not a recognised LinkType value.
            Symmetric types (RELATES_TO, DUPLICATES, IS_DUPLICATED_BY)
            return ``None`` (cycle check is irrelevant); only truly
            unknown values raise. This catches misuse at the boundary
            instead of silently disabling the cycle check.

    Notes:
        * Depth is capped at 50 ancestors (``_CYCLE_DEPTH_CAP``) per
          CB-1976 spec. A cycle deeper than 50 hops will not be detected
          here — the cap is a DoS guard, not a correctness boundary.
          Combined with the per-path ``seen`` membership filter (which
          enforces simple paths), worst-case work for a graph with N
          reachable nodes and branching factor k is O(min(k^50, N!)),
          which is acceptable for realistic project graphs but can grow
          on pathological adversarial graphs. CB-1977 should layer in a
          per-request rate limit / size gate at the route boundary.
        * Self-link (``from_id == to_id``) is the caller's responsibility
          to reject upstream; this helper does not special-case it.
        * Returns the shortest path on tie (``ORDER BY depth, path``) so
          the surfaced diagnostic is deterministic across runs and SQLite
          versions — important because the path is asserted on in tests.
    """
    if link_type not in _CYCLE_KNOWN_LINK_TYPES:
        raise ValueError(f"Unknown linkType: {link_type!r}")

    family = _CYCLE_TRANSITIVE_FAMILIES.get(link_type)
    if family is None:
        # Symmetric type — cycle check is meaningless. Skip the DB hit.
        return None

    # Canonical edge: for the inverse forms (IS_BLOCKED_BY, CAUSED_BY) the
    # row stored in the family graph is the companion, so the canonical
    # edge flips. Mirrors ``api/relations.py::_canonical_edge``.
    if link_type in ("BLOCKS", "CAUSES"):
        a, b = from_id, to_id
    else:
        a, b = to_id, from_id

    # ``seen`` is a delimiter-bracketed list of node ids visited so far, used
    # to prune any edge that would re-enter a node already on the current
    # path. Without it, the CTE would enumerate every distinct path through
    # the graph (UNION ALL semantics), and a diamond like b→x→y, b→x→z,
    # y→t, z→t blows up exponentially in row count even though each path is
    # short. Depth caps the *length* of a walk; ``seen`` caps the *width* —
    # together they bound work to O(N) rows where N is the reachable
    # node-set size, matching the BFS-with-visited bound used by
    # ``api/relations.py::_has_cycle``.
    #
    # The bracketing (``delim`` on both sides of every id) is what makes the
    # ``instr(seen, delim || id || delim) = 0`` membership test exact —
    # without the leading delim it would match an id that is a suffix of
    # another id; CUIDs make this unlikely but not impossible. Bracketing
    # keeps the test correct regardless of id alphabet.
    #
    # The membership filter never blocks the legitimate cycle close: the
    # walk starts at ``b`` and the proposed edge is ``a → b``, so reaching
    # ``a`` requires arriving at ``a`` for the first time on the walk — the
    # check only blocks *re-entering* a node already on the current path,
    # which is precisely what we want.
    sql = text("""
        WITH RECURSIVE reach(id, depth, path, seen) AS (
            SELECT
                toIssueId,
                1,
                fromIssueId || :delim || toIssueId,
                :delim || fromIssueId || :delim || toIssueId || :delim
            FROM IssueLink
            WHERE fromIssueId = :start
              AND linkType = :family

            UNION ALL

            SELECT
                il.toIssueId,
                r.depth + 1,
                r.path || :delim || il.toIssueId,
                r.seen || il.toIssueId || :delim
            FROM IssueLink il
            INNER JOIN reach r ON il.fromIssueId = r.id
            WHERE il.linkType = :family
              AND r.depth < :depth_cap
              AND instr(r.seen, :delim || il.toIssueId || :delim) = 0
        )
        SELECT path
        FROM reach
        WHERE id = :target
        ORDER BY depth, path
        LIMIT 1
    """)

    result = await db.execute(
        sql,
        {
            "start": b,
            "target": a,
            "family": family,
            "depth_cap": _CYCLE_DEPTH_CAP,
            "delim": _CYCLE_PATH_DELIMITER,
        },
    )
    row = result.first()
    if row is None:
        return None

    # ``row[0]`` is the existing path "b>...>a". Prepend ``a`` so the
    # returned list represents the full closing cycle ``a → b → ... → a``.
    existing_path = row[0].split(_CYCLE_PATH_DELIMITER)
    return [a, *existing_path]
