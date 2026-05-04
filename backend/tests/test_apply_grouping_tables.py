"""
Regression tests for the CB-1964 grouping-tables migration script.

Three contracts the script must hold:

1. Applied to an empty DB it creates IssueGroup + IssueGroupMember plus the
   three model-defined indexes, with the expected FK + UNIQUE semantics.
2. Re-running it is a no-op — every statement is `IF NOT EXISTS`, so a second
   pass must report 0 created / 0 errors.
3. Tables produced by the script match the shape produced by
   `Base.metadata.create_all`. This locks the script to the SQLAlchemy models
   so any future model change forces an explicit script update via this test.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from models.database import Base
# Import all models so Base.metadata is fully populated for create_all.
from models.issue import Issue, Comment, Activity, IssueLink, IssueSequence, Project  # noqa: F401
from models.grouping import IssueGroup, IssueGroupMember  # noqa: F401
from models.qa import QATask, QATaskIssueLink, QASequence, QASettings  # noqa: F401
from models.documentation import ExecutionSummary, FeatureDocumentation  # noqa: F401
from models.git import CommitLink, GitSyncState  # noqa: F401

from utils.apply_grouping_tables import (
    COLUMN_ADDITIONS,
    CREATE_TABLE_STATEMENTS,
    INDEX_DEFINITIONS,
    _add_column,
    _column_exists,
    _create_index,
    _create_table,
    _index_exists,
    _table_exists,
)


@pytest.fixture
async def file_engine(tmp_path):
    """File-backed sqlite so PRAGMA foreign_key_list survives connection cycling.

    A fresh DB per test — no cross-test bleed.
    """
    db_path = tmp_path / "grouping_migration.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
        future=True,
    )
    yield engine
    await engine.dispose()


async def _apply_migration(engine) -> tuple[int, int, int]:
    """Run the migration's table + column + index passes against the engine.

    Returns (created, skipped, errors). Mirrors the CLI script's loop without
    the print noise so tests can assert numerically. Column adjustments
    (CB-1965) run between tables and indexes — same order as the script.
    """
    created = 0
    skipped = 0
    errors = 0

    for table_name, ddl in CREATE_TABLE_STATEMENTS:
        try:
            already = await _table_exists(engine, table_name)
            await _create_table(engine, table_name, ddl)
            if already:
                skipped += 1
            else:
                created += 1
        except Exception:
            errors += 1

    for table, column, ddl in COLUMN_ADDITIONS:
        try:
            if await _column_exists(engine, table, column):
                skipped += 1
            else:
                await _add_column(engine, table, ddl)
                created += 1
        except Exception:
            errors += 1

    for table, index_name, columns, unique in INDEX_DEFINITIONS:
        try:
            already = await _index_exists(engine, index_name)
            await _create_index(engine, table, index_name, columns, unique)
            if already:
                skipped += 1
            else:
                created += 1
        except Exception:
            errors += 1

    return created, skipped, errors


async def _existing_objects(engine, kind: str) -> set[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type = :k AND name NOT LIKE 'sqlite_%' "
                "AND tbl_name IN ('IssueGroup', 'IssueGroupMember')"
            ),
            {"k": kind},
        )
        return {row[0] for row in result.fetchall()}


@pytest.mark.integration
class TestApplyGroupingTables:
    """Migration must be idempotent and produce the documented schema."""

    async def test_first_pass_creates_all_objects(self, file_engine):
        """Empty DB → 5 objects created (2 tables + 3 indexes), 0 errors.

        The CB-1965 `position` column rides in via CREATE TABLE on a fresh
        DB, so the column-additions pass [SKIP]s it (skipped=1).
        """
        created, skipped, errors = await _apply_migration(file_engine)
        assert (created, skipped, errors) == (5, 1, 0)

        tables = await _existing_objects(file_engine, "table")
        assert {"IssueGroup", "IssueGroupMember"}.issubset(tables)

        indexes = await _existing_objects(file_engine, "index")
        assert {
            "IssueGroup_projectId_idx",
            "IssueGroupMember_groupId_idx",
            "IssueGroupMember_issueId_idx",
        }.issubset(indexes)

    async def test_second_pass_is_noop(self, file_engine):
        """Re-running on the same DB must not create or error — pure SKIP.

        Skipped count = 2 tables + 1 column + 3 indexes = 6.
        """
        await _apply_migration(file_engine)  # warm-up
        created, skipped, errors = await _apply_migration(file_engine)
        assert (created, skipped, errors) == (0, 6, 0)

    async def test_unique_constraint_enforced(self, file_engine):
        """UNIQUE(groupId, issueId) must reject duplicate membership rows."""
        await _apply_migration(file_engine)

        async with file_engine.begin() as conn:
            await conn.execute(text("PRAGMA foreign_keys = OFF"))
            await conn.execute(text(
                "INSERT INTO IssueGroup (id, projectId, title) "
                "VALUES ('g1', 'p1', 't')"
            ))
            await conn.execute(text(
                "INSERT INTO IssueGroupMember (id, groupId, issueId) "
                "VALUES ('m1', 'g1', 'i1')"
            ))

        # Second insert with same (groupId, issueId) must violate UNIQUE.
        with pytest.raises(IntegrityError):
            async with file_engine.begin() as conn:
                await conn.execute(text("PRAGMA foreign_keys = OFF"))
                await conn.execute(text(
                    "INSERT INTO IssueGroupMember (id, groupId, issueId) "
                    "VALUES ('m2', 'g1', 'i1')"
                ))

    async def test_foreign_keys_match_models(self, file_engine):
        """FK on_delete must match grouping.py: RESTRICT on group→project,
        CASCADE on member→group / member→issue."""
        await _apply_migration(file_engine)

        async with file_engine.connect() as conn:
            group_fks = (await conn.execute(
                text("PRAGMA foreign_key_list('IssueGroup')")
            )).fetchall()
            member_fks = (await conn.execute(
                text("PRAGMA foreign_key_list('IssueGroupMember')")
            )).fetchall()

        # Each row: (id, seq, table, from, to, on_update, on_delete, match)
        group_actions = {row[2]: row[6] for row in group_fks}
        member_actions = {row[2]: row[6] for row in member_fks}

        assert group_actions == {"Project": "RESTRICT"}
        assert member_actions == {"IssueGroup": "CASCADE", "Issue": "CASCADE"}

    async def test_script_schema_matches_metadata_create_all(self, tmp_path):
        """Tables produced by the script must match `Base.metadata.create_all`.

        Compares column lists side-by-side: any future divergence between the
        SQLAlchemy models and the raw DDL embedded in the script will fail
        here, forcing an explicit script update.
        """
        # 1. Schema produced by the script.
        script_db = tmp_path / "script.db"
        script_engine = create_async_engine(
            f"sqlite+aiosqlite:///{script_db}", future=True,
        )
        try:
            await _apply_migration(script_engine)
            async with script_engine.connect() as conn:
                script_group_cols = [
                    row[1] for row in (await conn.execute(
                        text("PRAGMA table_info('IssueGroup')")
                    )).fetchall()
                ]
                script_member_cols = [
                    row[1] for row in (await conn.execute(
                        text("PRAGMA table_info('IssueGroupMember')")
                    )).fetchall()
                ]
        finally:
            await script_engine.dispose()

        # 2. Schema produced by Base.metadata.create_all.
        orm_db = tmp_path / "orm.db"
        orm_engine = create_async_engine(
            f"sqlite+aiosqlite:///{orm_db}", future=True,
        )
        try:
            async with orm_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with orm_engine.connect() as conn:
                orm_group_cols = [
                    row[1] for row in (await conn.execute(
                        text("PRAGMA table_info('IssueGroup')")
                    )).fetchall()
                ]
                orm_member_cols = [
                    row[1] for row in (await conn.execute(
                        text("PRAGMA table_info('IssueGroupMember')")
                    )).fetchall()
                ]
        finally:
            await orm_engine.dispose()

        assert sorted(script_group_cols) == sorted(orm_group_cols), (
            f"IssueGroup column drift: script={script_group_cols} vs "
            f"ORM={orm_group_cols}"
        )
        assert sorted(script_member_cols) == sorted(orm_member_cols), (
            f"IssueGroupMember column drift: script={script_member_cols} vs "
            f"ORM={orm_member_cols}"
        )

    async def test_position_column_present_after_first_pass(self, file_engine):
        """CB-1965: a fresh migration must leave `position` on IssueGroupMember
        with NOT NULL + default 0 + INTEGER affinity."""
        await _apply_migration(file_engine)
        async with file_engine.connect() as conn:
            cols = (await conn.execute(
                text("PRAGMA table_info('IssueGroupMember')")
            )).fetchall()
        # Each row: (cid, name, type, notnull, dflt_value, pk)
        position = next((c for c in cols if c[1] == "position"), None)
        assert position is not None, f"position column missing; cols={[c[1] for c in cols]}"
        assert position[2].upper() == "INTEGER"
        assert position[3] == 1, "position must be NOT NULL"
        # SQLite stringifies the default; "0" both for INTEGER literal and the
        # CREATE-TABLE form. Be lenient about quoting/whitespace.
        assert str(position[4]).strip().strip("'\"") == "0"

    async def test_alter_pass_adds_position_to_legacy_db(self, tmp_path):
        """CB-1965: a CB-1964-shaped DB (no position) must get the column via
        ALTER on the next migration run, leaving any existing rows intact."""
        legacy_db = tmp_path / "legacy.db"
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{legacy_db}", future=True,
        )
        try:
            # 1. Build the CB-1964 shape: position-less IssueGroupMember.
            async with engine.begin() as conn:
                await conn.execute(text(
                    'CREATE TABLE "IssueGroup" ('
                    '"id" VARCHAR PRIMARY KEY, '
                    '"projectId" VARCHAR NOT NULL, '
                    '"title" VARCHAR NOT NULL, '
                    '"description" TEXT, '
                    '"createdAt" DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, '
                    '"updatedAt" DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL'
                    ')'
                ))
                await conn.execute(text(
                    'CREATE TABLE "IssueGroupMember" ('
                    '"id" VARCHAR PRIMARY KEY, '
                    '"groupId" VARCHAR NOT NULL, '
                    '"issueId" VARCHAR NOT NULL, '
                    '"createdAt" DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, '
                    'CONSTRAINT "IssueGroupMember_groupId_issueId_key" UNIQUE ("groupId", "issueId")'
                    ')'
                ))
                await conn.execute(text(
                    "INSERT INTO IssueGroup (id, projectId, title) "
                    "VALUES ('grp-legacy', 'proj-legacy', 'Legacy group')"
                ))
                await conn.execute(text(
                    "INSERT INTO IssueGroupMember (id, groupId, issueId) "
                    "VALUES ('mem-legacy', 'grp-legacy', 'issue-legacy')"
                ))

            # 2. Run the migration. Tables already exist (skipped), but the
            #    position column is missing → must be ADDed (created += 1).
            created, skipped, errors = await _apply_migration(engine)
            assert errors == 0
            # 2 tables skipped, 1 column added, 3 indexes added → created=4,
            # skipped=2.
            assert created == 4, f"expected 4 creates (1 column + 3 indexes), got {created}"
            assert skipped == 2, f"expected 2 skips (existing tables), got {skipped}"

            # 3. Pre-existing row must survive with default position=0.
            async with engine.connect() as conn:
                row = (await conn.execute(text(
                    "SELECT id, position FROM IssueGroupMember WHERE id='mem-legacy'"
                ))).fetchone()
            assert row is not None
            assert row[1] == 0, f"legacy row position should default to 0, got {row[1]}"

            # 4. Idempotency: third pass after the ALTER must be pure SKIP.
            created2, skipped2, errors2 = await _apply_migration(engine)
            assert (created2, skipped2, errors2) == (0, 6, 0)
        finally:
            await engine.dispose()

    async def test_position_inserts_persist_and_round_trip(self, file_engine):
        """CB-1965: explicit position values inserted via raw SQL must round-trip
        unchanged, proving the migrated column type is genuinely INTEGER."""
        await _apply_migration(file_engine)
        async with file_engine.begin() as conn:
            await conn.execute(text("PRAGMA foreign_keys = OFF"))
            await conn.execute(text(
                "INSERT INTO IssueGroup (id, projectId, title) "
                "VALUES ('g-pos', 'p-pos', 't')"
            ))
            for n, mid in enumerate(["a", "b", "c"], start=1):
                await conn.execute(text(
                    "INSERT INTO IssueGroupMember (id, groupId, issueId, position) "
                    f"VALUES ('m-{mid}', 'g-pos', 'i-{mid}', {n})"
                ))

        async with file_engine.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT id, position FROM IssueGroupMember "
                "WHERE groupId='g-pos' ORDER BY position"
            ))).fetchall()
        assert [(r[0], r[1]) for r in rows] == [("m-a", 1), ("m-b", 2), ("m-c", 3)]
