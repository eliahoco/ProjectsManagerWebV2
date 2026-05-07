"""
CB-1964: Idempotent migration for IssueGroup + IssueGroupMember (Story CB-1961).

PMv2 has no Alembic, so schema is owned by SQLAlchemy `Base.metadata.create_all`
on backend startup. That path already runs `CREATE TABLE IF NOT EXISTS` and is
the canonical way to add the new tables to a fresh DB.

This script is the *out-of-band* path: an already-running deployment whose
backend was started before the grouping models were registered. Running it on
such a DB adds the missing tables + indexes without requiring a backend
restart, and is safe to re-run (every statement is `IF NOT EXISTS`).

Usage:
    python -m utils.apply_grouping_tables

Behaviour:
1. Reflect existing tables/indexes from SQLite.
2. For each table/index/UNIQUE constraint that does not yet exist, run the
   matching `CREATE ... IF NOT EXISTS` DDL.
3. Print a per-statement [CREATE]/[SKIP] summary, then a totals line.

Mirrors the surface of `apply_indexes.py` so anyone who has run that one
recognises this one. Kept as a separate utility (not folded in) because the
two run for different reasons: indexes are tuning-only, tables are required
schema — operators should be able to read the run log and see which one fired.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports when invoked as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


# Idempotent CREATE TABLE statements. Column types/constraints mirror the
# SQLAlchemy models in `backend/models/grouping.py`. Keep this in sync if the
# models change — the test suite (`test_apply_grouping_tables.py`) compares
# the migrated schema against `Base.metadata.create_all`, so a drift will be
# caught there.
CREATE_TABLE_STATEMENTS: list[tuple[str, str]] = [
    (
        "IssueGroup",
        """
        CREATE TABLE IF NOT EXISTS "IssueGroup" (
            "id" VARCHAR NOT NULL,
            "projectId" VARCHAR NOT NULL,
            "title" VARCHAR NOT NULL,
            "description" TEXT,
            "createdAt" DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            "updatedAt" DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            PRIMARY KEY ("id"),
            FOREIGN KEY ("projectId") REFERENCES "Project" ("id") ON DELETE RESTRICT
        )
        """,
    ),
    (
        "IssueGroupMember",
        """
        CREATE TABLE IF NOT EXISTS "IssueGroupMember" (
            "id" VARCHAR NOT NULL,
            "groupId" VARCHAR NOT NULL,
            "issueId" VARCHAR NOT NULL,
            "position" INTEGER NOT NULL DEFAULT 0,
            "createdAt" DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            CONSTRAINT "IssueGroupMember_groupId_issueId_key" UNIQUE ("groupId", "issueId"),
            PRIMARY KEY ("id"),
            FOREIGN KEY ("groupId") REFERENCES "IssueGroup" ("id") ON DELETE CASCADE,
            FOREIGN KEY ("issueId") REFERENCES "Issue" ("id") ON DELETE CASCADE
        )
        """,
    ),
]


# CB-1965: column-level adjustments for tables already shipped under the
# CB-1964 shape (no `position` column). Each tuple is
# (table, column_name, ddl_fragment).
# The migration applies these via ALTER TABLE ADD COLUMN when the column is
# missing, and reports [SKIP] when it is already present. SQLite's
# ALTER TABLE ADD COLUMN has no `IF NOT EXISTS`, so detection is done in
# Python via PRAGMA table_info.
COLUMN_ADDITIONS: list[tuple[str, str, str]] = [
    (
        "IssueGroupMember",
        "position",
        '"position" INTEGER NOT NULL DEFAULT 0',
    ),
]


# Index definitions matching `models/grouping.py`.
# Format: (table, index_name, columns, unique).
INDEX_DEFINITIONS: list[tuple[str, str, list[str], bool]] = [
    ("IssueGroup", "IssueGroup_projectId_idx", ["projectId"], False),
    ("IssueGroupMember", "IssueGroupMember_groupId_idx", ["groupId"], False),
    ("IssueGroupMember", "IssueGroupMember_issueId_idx", ["issueId"], False),
]


async def _table_exists(engine, table_name: str) -> bool:
    """Return True iff the named table is registered in sqlite_master."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = :name"
            ),
            {"name": table_name},
        )
        return result.scalar() is not None


async def _index_exists(engine, index_name: str) -> bool:
    """Return True iff the named index is registered in sqlite_master."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'index' AND name = :name"
            ),
            {"name": index_name},
        )
        return result.scalar() is not None


async def _column_exists(engine, table: str, column: str) -> bool:
    """Return True iff `table` already has a column named `column`.

    Uses `PRAGMA table_info`; columns appear in row[1]. Identifier passed via
    f-string because PRAGMA does not accept bound parameters in SQLite — the
    inputs come from this module's static `COLUMN_ADDITIONS` list, never user
    input, so injection is not a concern here.
    """
    async with engine.connect() as conn:
        result = await conn.execute(text(f'PRAGMA table_info("{table}")'))
        return any(row[1] == column for row in result.fetchall())


async def _add_column(engine, table: str, ddl_fragment: str) -> None:
    """ALTER TABLE ADD COLUMN. Caller must have verified absence first.

    Identifier `table` and the raw `ddl_fragment` come from this module's
    static `COLUMN_ADDITIONS` constant; no user input reaches this helper.
    SQLite's ALTER ADD COLUMN appends the new column at the end of the
    table's column list (it does not match the position of the column in
    a fresh CREATE TABLE), which is harmless because every accessor in
    this codebase references columns by name, not by ordinal.
    """
    async with engine.begin() as conn:
        await conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {ddl_fragment}'))


async def _create_table(engine, name: str, ddl: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(ddl))


async def _create_index(
    engine, table: str, index_name: str, columns: list[str], unique: bool,
) -> None:
    unique_clause = "UNIQUE " if unique else ""
    cols = ", ".join(f'"{c}"' for c in columns)
    sql = (
        f'CREATE {unique_clause}INDEX IF NOT EXISTS "{index_name}" '
        f'ON "{table}" ({cols})'
    )
    async with engine.begin() as conn:
        await conn.execute(text(sql))


async def apply_grouping_tables() -> int:
    """Apply the CB-1964 grouping schema to the configured database.

    Returns the process exit code (0 on success, 1 on any error).
    """
    print("=" * 60)
    print("CB-1964 Grouping Tables Migration")
    print("=" * 60)
    # Redact credentials in case the URL ever points at a non-SQLite driver
    # whose URL embeds user:password (PostgreSQL/MySQL). Today it is SQLite
    # and the URL is a path, but treating it as sensitive by default avoids
    # leaking secrets via terminal scrollback or captured logs.
    safe_url = make_url(settings.DATABASE_URL).render_as_string(hide_password=True)
    print(f"\nDatabase: {safe_url}\n")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    created = 0
    skipped = 0
    errors = 0

    try:
        # Tables first — indexes reference them.
        print("Tables")
        print("-" * 40)
        for table_name, ddl in CREATE_TABLE_STATEMENTS:
            try:
                already_present = await _table_exists(engine, table_name)
                await _create_table(engine, table_name, ddl)
                if already_present:
                    print(f"  [SKIP]   {table_name}  — already exists")
                    skipped += 1
                else:
                    print(f"  [CREATE] {table_name}")
                    created += 1
            except Exception as e:
                print(f"  [ERROR]  {table_name} — {e}")
                errors += 1

        # Column adjustments — for DBs that already have the CB-1964 tables
        # but pre-date CB-1965's `position` column. ALTER runs only when the
        # column is missing, so first-pass-on-fresh-DB falls through cleanly
        # (the column came in via CREATE TABLE above).
        if COLUMN_ADDITIONS:
            print("\nColumn adjustments")
            print("-" * 40)
            for table, column, ddl in COLUMN_ADDITIONS:
                try:
                    if await _column_exists(engine, table, column):
                        print(f"  [SKIP]   {table}.{column}  — already present")
                        skipped += 1
                    else:
                        await _add_column(engine, table, ddl)
                        print(f"  [ALTER]  {table}.{column}  — added")
                        created += 1
                except Exception as e:
                    print(f"  [ERROR]  {table}.{column} — {e}")
                    errors += 1

        # Indexes — only created after tables exist (above).
        print("\nIndexes")
        print("-" * 40)
        for table, index_name, columns, unique in INDEX_DEFINITIONS:
            try:
                already_present = await _index_exists(engine, index_name)
                await _create_index(engine, table, index_name, columns, unique)
                if already_present:
                    print(f"  [SKIP]   {index_name}  — already exists")
                    skipped += 1
                else:
                    label = "UNIQUE " if unique else ""
                    print(
                        f"  [CREATE] {label}{index_name}"
                        f"  on {table}({', '.join(columns)})"
                    )
                    created += 1
            except Exception as e:
                print(f"  [ERROR]  {index_name} — {e}")
                errors += 1
    finally:
        await engine.dispose()

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Created: {created}")
    print(f"  Skipped: {skipped} (already present)")
    print(f"  Errors:  {errors}")
    print()

    if errors > 0:
        print("WARNING: Some statements failed — see [ERROR] lines above.")
        return 1

    print("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(apply_grouping_tables()))
