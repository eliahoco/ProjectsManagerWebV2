"""
CB-2748 — Persistence Overhaul Schema Migration.

Adds the following columns to the live SQLite database:

  AutoPilotQueueRecord:
    state             TEXT
    stateReason       TEXT
    lastCheckpointAt  DATETIME
    recoveryGeneration INTEGER DEFAULT 0

  AutoPilotTaskRecord:
    lastProgressAt  DATETIME
    subprocessPid   INTEGER

This script is **idempotent**: running it twice produces no error.
It uses "ALTER TABLE … ADD COLUMN IF NOT EXISTS"-style logic by catching
OperationalError when the column already exists.

Usage:
    cd backend
    PYTHONPATH=. python scripts/codeboard/2026-05-09-cb-2748-schema-migration.py

The script connects to the same DB path used by the application
(resolved from app.config.settings.DATABASE_URL or the CODEBOARD_DB env var).
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys


def _resolve_db_path() -> str:
    """Resolve the SQLite file path from settings or environment."""
    db_url_env = os.environ.get("DATABASE_URL", "")
    if db_url_env:
        # Strip SQLAlchemy URL prefixes: sqlite:///... or sqlite+aiosqlite:///...
        m = re.match(r"sqlite(?:\+\w+)?:///(.+)", db_url_env)
        if m:
            return m.group(1)

    # Fall back to the project-standard path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_root = os.path.normpath(os.path.join(script_dir, "..", ".."))
    default_path = os.path.join(backend_root, "data", "codeboard.db")
    return default_path


def _add_column_if_missing(
    cursor: sqlite3.Cursor,
    table: str,
    column: str,
    column_def: str,
) -> bool:
    """Add a column to a table if it does not already exist.

    Returns True if the column was added, False if it was already present.
    """
    # PRAGMA table_info returns rows: (cid, name, type, notnull, dflt_value, pk)
    cursor.execute(f"PRAGMA table_info({table})")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if column in existing_columns:
        return False
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
    return True


def run_migration(db_path: str) -> None:
    """Apply CB-2748 schema additions to the SQLite database at db_path."""
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path!r}", file=sys.stderr)
        print(
            "Start the backend at least once to create the DB, then re-run this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Connecting to: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    cursor = conn.cursor()

    migrations: list[tuple[str, str, str]] = [
        # (table, column_name, column_definition)
        # AutoPilotQueueRecord additions
        ("AutoPilotQueueRecord", "state",              "TEXT"),
        ("AutoPilotQueueRecord", "stateReason",        "TEXT"),
        ("AutoPilotQueueRecord", "lastCheckpointAt",   "DATETIME"),
        ("AutoPilotQueueRecord", "recoveryGeneration", "INTEGER DEFAULT 0 NOT NULL"),
        # AutoPilotTaskRecord additions
        ("AutoPilotTaskRecord",  "lastProgressAt",     "DATETIME"),
        ("AutoPilotTaskRecord",  "subprocessPid",      "INTEGER"),
    ]

    added: list[str] = []
    skipped: list[str] = []

    for table, column, col_def in migrations:
        if _add_column_if_missing(cursor, table, column, col_def):
            added.append(f"  + {table}.{column} ({col_def})")
        else:
            skipped.append(f"  . {table}.{column} (already exists)")

    conn.commit()
    conn.close()

    if added:
        print("Added columns:")
        for line in added:
            print(line)
    if skipped:
        print("Already present (skipped):")
        for line in skipped:
            print(line)

    print(f"\nMigration complete. {len(added)} column(s) added, {len(skipped)} skipped.")


if __name__ == "__main__":
    db_path = _resolve_db_path()
    run_migration(db_path)
