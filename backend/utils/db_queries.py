"""
Optimized database query utilities.

This module provides efficient query patterns for common operations,
replacing recursive Python loops with single SQL queries.
"""

from sqlalchemy import select, text, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Set
from datetime import datetime


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
