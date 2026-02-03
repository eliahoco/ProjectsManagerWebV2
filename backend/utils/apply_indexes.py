"""
Database index migration utility.

This script applies new indexes to an existing database without requiring
a full database recreation. Run this after updating model index definitions.

Usage:
    python -m utils.apply_indexes

The script will:
1. Check which indexes from the models already exist
2. Create any missing indexes
3. Report on what was created

This is safe to run multiple times - it will skip indexes that already exist.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


# Index definitions matching the model files
# Format: (table_name, index_name, columns, is_unique)
NEW_INDEXES = [
    # Issue table - new indexes
    ("Issue", "Issue_createdAt_idx", ["createdAt"], False),
    ("Issue", "Issue_updatedAt_idx", ["updatedAt"], False),
    ("Issue", "Issue_projectId_createdAt_idx", ["projectId", "createdAt"], False),
    ("Issue", "Issue_projectId_updatedAt_idx", ["projectId", "updatedAt"], False),
    ("Issue", "Issue_dueDate_idx", ["dueDate"], False),

    # Activity table - new indexes
    ("Activity", "Activity_createdAt_idx", ["createdAt"], False),
    ("Activity", "Activity_issueId_createdAt_idx", ["issueId", "createdAt"], False),

    # QATask table - new indexes
    ("QATask", "QATask_lastExecutedAt_idx", ["lastExecutedAt"], False),
    ("QATask", "QATask_projectId_status_idx", ["projectId", "status"], False),
    ("QATask", "QATask_projectId_lastExecutedAt_idx", ["projectId", "lastExecutedAt"], False),

    # CommitLink table - new indexes
    ("CommitLink", "CommitLink_author_idx", ["author"], False),
    ("CommitLink", "CommitLink_projectId_author_idx", ["projectId", "author"], False),
    ("CommitLink", "CommitLink_committedAt_idx", ["committedAt"], False),
    ("CommitLink", "CommitLink_projectId_committedAt_idx", ["projectId", "committedAt"], False),
]


async def get_existing_indexes(engine, table_name: str) -> set:
    """Get set of existing index names for a table."""
    async with engine.connect() as conn:
        # SQLite-specific query to get indexes
        result = await conn.execute(
            text(f"PRAGMA index_list('{table_name}')")
        )
        rows = result.fetchall()
        return {row[1] for row in rows}  # row[1] is the index name


async def create_index(engine, table_name: str, index_name: str, columns: list, unique: bool):
    """Create an index if it doesn't exist."""
    unique_clause = "UNIQUE" if unique else ""
    columns_str = ", ".join(f'"{col}"' for col in columns)

    sql = f'CREATE {unique_clause} INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({columns_str})'

    async with engine.begin() as conn:
        await conn.execute(text(sql))


async def apply_indexes():
    """Apply all new indexes to the database."""
    print("=" * 60)
    print("Database Index Migration Utility")
    print("=" * 60)
    print(f"\nDatabase: {settings.DATABASE_URL}")
    print()

    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    created = 0
    skipped = 0
    errors = 0

    # Group indexes by table for efficiency
    tables = {}
    for table_name, index_name, columns, unique in NEW_INDEXES:
        if table_name not in tables:
            tables[table_name] = []
        tables[table_name].append((index_name, columns, unique))

    for table_name, indexes in tables.items():
        print(f"\nTable: {table_name}")
        print("-" * 40)

        try:
            existing = await get_existing_indexes(engine, table_name)
        except Exception as e:
            print(f"  ERROR: Could not query indexes - {e}")
            errors += len(indexes)
            continue

        for index_name, columns, unique in indexes:
            if index_name in existing:
                print(f"  [SKIP] {index_name} - already exists")
                skipped += 1
            else:
                try:
                    await create_index(engine, table_name, index_name, columns, unique)
                    print(f"  [CREATE] {index_name} on ({', '.join(columns)})")
                    created += 1
                except Exception as e:
                    print(f"  [ERROR] {index_name} - {e}")
                    errors += 1

    await engine.dispose()

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Created: {created}")
    print(f"  Skipped: {skipped} (already exist)")
    print(f"  Errors:  {errors}")
    print()

    if errors > 0:
        print("WARNING: Some indexes could not be created. Check errors above.")
        return 1

    print("Done!")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(apply_indexes())
    sys.exit(exit_code)
