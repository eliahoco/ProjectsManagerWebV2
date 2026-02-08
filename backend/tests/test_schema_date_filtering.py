"""
Date field and date range filtering tests for database schema.

Specifically targets the CB-1112 story: "User can Filter Results by Date Range".
Validates that date columns are present, queryable, and that date range filtering
works correctly at the database level for all relevant date fields.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import select, and_

from models.issue import Issue, Activity, Project
from models.qa import QATask
from models.git import CommitLink

from tests.schema_test_utils import (
    create_test_engine,
    setup_test_db,
    teardown_test_db,
    create_test_session_factory,
    make_project,
    make_issue,
    make_activity,
    make_qa_task,
    get_table_info,
    get_index_info,
)


# ============================================
# Fixtures
# ============================================

@pytest.fixture
async def db_session():
    """Provide a fresh database session."""
    engine = create_test_engine()
    await setup_test_db(engine)
    session_factory = create_test_session_factory(engine)
    async with session_factory() as session:
        yield session
    await teardown_test_db(engine)
    await engine.dispose()


@pytest.fixture
async def test_engine():
    """Provide a test engine for schema inspection."""
    engine = create_test_engine()
    await setup_test_db(engine)
    yield engine
    await teardown_test_db(engine)
    await engine.dispose()


@pytest.fixture
async def date_seeded_session(db_session):
    """
    Session with issues across a date range for filter testing.

    Creates 5 issues with staggered dates:
    - issue-old:  created 30 days ago, started 28 days ago, completed 20 days ago
    - issue-mid1: created 15 days ago, started 14 days ago, due in 10 days
    - issue-mid2: created 10 days ago, started 9 days ago
    - issue-recent: created 3 days ago, due tomorrow
    - issue-today: created today
    """
    project = make_project()
    db_session.add(project)
    await db_session.flush()

    now = datetime.now()

    issues = [
        make_issue(
            id="issue-old", key="CB-1", sequence=1, title="Old Issue",
            status="DONE",
            startedAt=now - timedelta(days=28),
            completedAt=now - timedelta(days=20),
            dueDate=now - timedelta(days=22),
        ),
        make_issue(
            id="issue-mid1", key="CB-2", sequence=2, title="Mid Issue 1",
            status="IN_PROGRESS",
            startedAt=now - timedelta(days=14),
            dueDate=now + timedelta(days=10),
        ),
        make_issue(
            id="issue-mid2", key="CB-3", sequence=3, title="Mid Issue 2",
            status="IN_REVIEW",
            startedAt=now - timedelta(days=9),
        ),
        make_issue(
            id="issue-recent", key="CB-4", sequence=4, title="Recent Issue",
            status="TODO",
            dueDate=now + timedelta(days=1),
        ),
        make_issue(
            id="issue-today", key="CB-5", sequence=5, title="Today Issue",
            status="BACKLOG",
        ),
    ]

    # Manually set createdAt since server_default won't let us backdate easily
    issues[0].createdAt = now - timedelta(days=30)
    issues[1].createdAt = now - timedelta(days=15)
    issues[2].createdAt = now - timedelta(days=10)
    issues[3].createdAt = now - timedelta(days=3)
    issues[4].createdAt = now

    db_session.add_all(issues)
    await db_session.commit()

    return db_session


# ============================================
# Date column existence tests
# ============================================

@pytest.mark.unit
class TestDateColumnExistence:
    """Verify all date columns needed for date filtering exist."""

    async def test_issue_date_columns(self, test_engine):
        """Issue table should have all filterable date columns."""
        columns = await get_table_info(test_engine, "Issue")
        date_cols = ["createdAt", "updatedAt", "dueDate", "startedAt", "completedAt"]
        for col in date_cols:
            assert col in columns, f"Date column '{col}' missing from Issue table"

    async def test_activity_date_column(self, test_engine):
        """Activity table should have createdAt for time-range filtering."""
        columns = await get_table_info(test_engine, "Activity")
        assert "createdAt" in columns

    async def test_qa_task_date_columns(self, test_engine):
        """QATask table should have date columns for filtering."""
        columns = await get_table_info(test_engine, "QATask")
        for col in ["lastExecutedAt", "createdAt", "updatedAt"]:
            assert col in columns, f"Date column '{col}' missing from QATask table"

    async def test_commit_link_date_column(self, test_engine):
        """CommitLink should have committedAt for date filtering."""
        columns = await get_table_info(test_engine, "CommitLink")
        assert "committedAt" in columns


# ============================================
# Date column index tests (performance)
# ============================================

@pytest.mark.unit
class TestDateColumnIndexes:
    """Verify date columns have appropriate indexes for query performance."""

    async def test_issue_createdat_indexed(self, test_engine):
        """Issue.createdAt should be indexed for date range queries."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("createdAt",) in idx_cols

    async def test_issue_updatedat_indexed(self, test_engine):
        """Issue.updatedAt should be indexed for date range queries."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("updatedAt",) in idx_cols

    async def test_issue_duedate_indexed(self, test_engine):
        """Issue.dueDate should be indexed for due date filtering."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("dueDate",) in idx_cols

    async def test_issue_composite_project_createdat_indexed(self, test_engine):
        """Composite (projectId, createdAt) should be indexed for project-scoped date queries."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("projectId", "createdAt") in idx_cols

    async def test_issue_composite_project_updatedat_indexed(self, test_engine):
        """Composite (projectId, updatedAt) should be indexed for project-scoped date queries."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("projectId", "updatedAt") in idx_cols

    async def test_activity_createdat_indexed(self, test_engine):
        """Activity.createdAt should be indexed for time-range filtering."""
        indexes = await get_index_info(test_engine, "Activity")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("createdAt",) in idx_cols

    async def test_activity_composite_indexed(self, test_engine):
        """Activity (issueId, createdAt) should be indexed."""
        indexes = await get_index_info(test_engine, "Activity")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("issueId", "createdAt") in idx_cols

    async def test_qa_task_last_executed_indexed(self, test_engine):
        """QATask.lastExecutedAt should be indexed."""
        indexes = await get_index_info(test_engine, "QATask")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("lastExecutedAt",) in idx_cols

    async def test_commit_link_committedat_indexed(self, test_engine):
        """CommitLink.committedAt should be indexed."""
        indexes = await get_index_info(test_engine, "CommitLink")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("committedAt",) in idx_cols


# ============================================
# Date range filtering query tests
# ============================================

@pytest.mark.integration
class TestDateRangeFilteringCreatedAt:
    """Test filtering issues by createdAt date range."""

    async def test_filter_last_7_days(self, date_seeded_session):
        """Should return issues created in the last 7 days."""
        cutoff = datetime.now() - timedelta(days=7)
        result = await date_seeded_session.execute(
            select(Issue).where(Issue.createdAt >= cutoff)
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-recent" in ids
        assert "issue-today" in ids
        assert "issue-old" not in ids
        assert "issue-mid1" not in ids

    async def test_filter_last_14_days(self, date_seeded_session):
        """Should return issues created in the last 14 days."""
        cutoff = datetime.now() - timedelta(days=14)
        result = await date_seeded_session.execute(
            select(Issue).where(Issue.createdAt >= cutoff)
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-mid2" in ids
        assert "issue-recent" in ids
        assert "issue-today" in ids
        assert "issue-old" not in ids

    async def test_filter_exact_date_range(self, date_seeded_session):
        """Should return issues within an exact date range."""
        now = datetime.now()
        start = now - timedelta(days=16)
        end = now - timedelta(days=8)
        result = await date_seeded_session.execute(
            select(Issue).where(
                and_(Issue.createdAt >= start, Issue.createdAt <= end)
            )
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-mid1" in ids
        assert "issue-mid2" in ids
        assert "issue-old" not in ids
        assert "issue-today" not in ids

    async def test_filter_empty_range(self, date_seeded_session):
        """Should return empty result for a date range with no matches."""
        now = datetime.now()
        start = now + timedelta(days=100)
        end = now + timedelta(days=200)
        result = await date_seeded_session.execute(
            select(Issue).where(
                and_(Issue.createdAt >= start, Issue.createdAt <= end)
            )
        )
        issues = result.scalars().all()
        assert len(issues) == 0


@pytest.mark.integration
class TestDateRangeFilteringDueDate:
    """Test filtering issues by dueDate."""

    async def test_filter_overdue(self, date_seeded_session):
        """Should find issues with dueDate in the past (overdue)."""
        now = datetime.now()
        result = await date_seeded_session.execute(
            select(Issue).where(
                and_(Issue.dueDate.isnot(None), Issue.dueDate < now)
            )
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-old" in ids  # dueDate was 22 days ago

    async def test_filter_upcoming_due(self, date_seeded_session):
        """Should find issues with dueDate in the future."""
        now = datetime.now()
        result = await date_seeded_session.execute(
            select(Issue).where(
                and_(Issue.dueDate.isnot(None), Issue.dueDate >= now)
            )
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-mid1" in ids  # due in 10 days
        assert "issue-recent" in ids  # due tomorrow

    async def test_filter_due_within_week(self, date_seeded_session):
        """Should find issues due within the next 7 days."""
        now = datetime.now()
        week_from_now = now + timedelta(days=7)
        result = await date_seeded_session.execute(
            select(Issue).where(
                and_(
                    Issue.dueDate.isnot(None),
                    Issue.dueDate >= now,
                    Issue.dueDate <= week_from_now,
                )
            )
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-recent" in ids  # due tomorrow
        assert "issue-mid1" not in ids  # due in 10 days

    async def test_filter_no_due_date(self, date_seeded_session):
        """Should find issues with no due date set."""
        result = await date_seeded_session.execute(
            select(Issue).where(Issue.dueDate.is_(None))
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-mid2" in ids
        assert "issue-today" in ids


@pytest.mark.integration
class TestDateRangeFilteringStartedAt:
    """Test filtering issues by startedAt date."""

    async def test_filter_started_issues(self, date_seeded_session):
        """Should find issues that have been started."""
        result = await date_seeded_session.execute(
            select(Issue).where(Issue.startedAt.isnot(None))
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-old" in ids
        assert "issue-mid1" in ids
        assert "issue-mid2" in ids
        assert "issue-recent" not in ids
        assert "issue-today" not in ids

    async def test_filter_started_in_range(self, date_seeded_session):
        """Should find issues started within a specific range."""
        now = datetime.now()
        start = now - timedelta(days=15)
        end = now - timedelta(days=8)
        result = await date_seeded_session.execute(
            select(Issue).where(
                and_(Issue.startedAt >= start, Issue.startedAt <= end)
            )
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-mid1" in ids
        assert "issue-mid2" in ids
        assert "issue-old" not in ids


@pytest.mark.integration
class TestDateRangeFilteringCompletedAt:
    """Test filtering issues by completedAt date."""

    async def test_filter_completed_issues(self, date_seeded_session):
        """Should find issues that have been completed."""
        result = await date_seeded_session.execute(
            select(Issue).where(Issue.completedAt.isnot(None))
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-old" in ids
        assert len(ids) == 1  # Only the old issue was completed

    async def test_filter_completed_in_range(self, date_seeded_session):
        """Should find issues completed within a specific range."""
        now = datetime.now()
        start = now - timedelta(days=25)
        end = now - timedelta(days=15)
        result = await date_seeded_session.execute(
            select(Issue).where(
                and_(Issue.completedAt >= start, Issue.completedAt <= end)
            )
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-old" in ids  # completed 20 days ago


# ============================================
# Combined filter tests (date + status/type)
# ============================================

@pytest.mark.integration
class TestCombinedDateFilters:
    """Test combining date filters with other field filters."""

    async def test_filter_by_status_and_created_date(self, date_seeded_session):
        """Should filter by both status and createdAt."""
        cutoff = datetime.now() - timedelta(days=20)
        result = await date_seeded_session.execute(
            select(Issue).where(
                and_(
                    Issue.status == "IN_PROGRESS",
                    Issue.createdAt >= cutoff,
                )
            )
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-mid1" in ids
        assert len(ids) == 1

    async def test_filter_by_project_and_date_range(self, date_seeded_session):
        """Should filter by projectId and date range."""
        now = datetime.now()
        result = await date_seeded_session.execute(
            select(Issue).where(
                and_(
                    Issue.projectId == "test-project-1",
                    Issue.createdAt >= now - timedelta(days=11),
                    Issue.createdAt <= now,
                )
            )
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-mid2" in ids
        assert "issue-recent" in ids
        assert "issue-today" in ids
        assert "issue-old" not in ids

    async def test_filter_active_with_due_date(self, date_seeded_session):
        """Should find active issues with upcoming due dates."""
        now = datetime.now()
        result = await date_seeded_session.execute(
            select(Issue).where(
                and_(
                    Issue.status.notin_(["DONE", "CANCELLED"]),
                    Issue.dueDate.isnot(None),
                    Issue.dueDate >= now,
                )
            )
        )
        issues = result.scalars().all()
        ids = {i.id for i in issues}
        assert "issue-mid1" in ids  # IN_PROGRESS, due in 10 days
        assert "issue-recent" in ids  # TODO, due tomorrow


# ============================================
# Date sorting tests
# ============================================

@pytest.mark.integration
class TestDateSorting:
    """Test sorting issues by date fields."""

    async def test_sort_by_created_at_asc(self, date_seeded_session):
        """Should sort issues by createdAt ascending (oldest first)."""
        result = await date_seeded_session.execute(
            select(Issue).order_by(Issue.createdAt.asc())
        )
        issues = result.scalars().all()
        assert issues[0].id == "issue-old"
        assert issues[-1].id == "issue-today"

    async def test_sort_by_created_at_desc(self, date_seeded_session):
        """Should sort issues by createdAt descending (newest first)."""
        result = await date_seeded_session.execute(
            select(Issue).order_by(Issue.createdAt.desc())
        )
        issues = result.scalars().all()
        assert issues[0].id == "issue-today"
        assert issues[-1].id == "issue-old"

    async def test_sort_by_due_date(self, date_seeded_session):
        """Should sort issues by dueDate, with NULLs last."""
        result = await date_seeded_session.execute(
            select(Issue)
            .where(Issue.dueDate.isnot(None))
            .order_by(Issue.dueDate.asc())
        )
        issues = result.scalars().all()
        # Oldest dueDate first
        assert issues[0].id == "issue-old"  # due 22 days ago


# ============================================
# Activity date filtering tests
# ============================================

@pytest.mark.integration
class TestActivityDateFiltering:
    """Test filtering activities by date (audit log time ranges)."""

    async def test_activity_date_range_query(self, db_session):
        """Should filter activities by createdAt date range."""
        project = make_project()
        db_session.add(project)
        await db_session.flush()

        issue = make_issue()
        db_session.add(issue)
        await db_session.flush()

        now = datetime.now()
        activities = [
            Activity(
                id="act-old", issueId="test-issue-1",
                actor="user", action="CREATED",
            ),
            Activity(
                id="act-recent", issueId="test-issue-1",
                actor="user", action="STATUS_CHANGED",
                field="status", oldValue="BACKLOG", newValue="TODO",
            ),
        ]
        activities[0].createdAt = now - timedelta(days=10)
        activities[1].createdAt = now - timedelta(days=1)

        db_session.add_all(activities)
        await db_session.commit()

        # Filter for last 5 days
        cutoff = now - timedelta(days=5)
        result = await db_session.execute(
            select(Activity).where(Activity.createdAt >= cutoff)
        )
        acts = result.scalars().all()
        ids = {a.id for a in acts}
        assert "act-recent" in ids
        assert "act-old" not in ids


# ============================================
# QA Task date filtering tests
# ============================================

@pytest.mark.integration
class TestQATaskDateFiltering:
    """Test filtering QA tasks by date fields."""

    async def test_qa_task_filter_by_last_executed(self, db_session):
        """Should filter QA tasks by lastExecutedAt."""
        project = make_project()
        db_session.add(project)
        await db_session.flush()

        now = datetime.now()
        qa1 = make_qa_task(id="qa-1", key="QA-001", sequence=1, lastExecutedAt=now - timedelta(days=10))
        qa2 = make_qa_task(id="qa-2", key="QA-002", sequence=2, lastExecutedAt=now - timedelta(days=1))
        qa3 = make_qa_task(id="qa-3", key="QA-003", sequence=3)  # Never executed

        db_session.add_all([qa1, qa2, qa3])
        await db_session.commit()

        # Find recently executed (last 5 days)
        cutoff = now - timedelta(days=5)
        result = await db_session.execute(
            select(QATask).where(
                and_(QATask.lastExecutedAt.isnot(None), QATask.lastExecutedAt >= cutoff)
            )
        )
        tasks = result.scalars().all()
        ids = {t.id for t in tasks}
        assert "qa-2" in ids
        assert "qa-1" not in ids
        assert "qa-3" not in ids

    async def test_qa_task_filter_never_executed(self, db_session):
        """Should find QA tasks that have never been executed."""
        project = make_project()
        db_session.add(project)
        await db_session.flush()

        now = datetime.now()
        qa1 = make_qa_task(id="qa-1", key="QA-001", sequence=1, lastExecutedAt=now)
        qa2 = make_qa_task(id="qa-2", key="QA-002", sequence=2)  # Never executed

        db_session.add_all([qa1, qa2])
        await db_session.commit()

        result = await db_session.execute(
            select(QATask).where(QATask.lastExecutedAt.is_(None))
        )
        tasks = result.scalars().all()
        ids = {t.id for t in tasks}
        assert "qa-2" in ids
        assert "qa-1" not in ids
