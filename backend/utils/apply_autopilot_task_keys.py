"""
Idempotent migration: add issueKey + issueTitle columns to AutoPilotTaskRecord.

CB-2673 fix — run once after deploying the updated SQLAlchemy model.

Usage:
    python backend/utils/apply_autopilot_task_keys.py

The script is safe to run multiple times: it checks for each column's
existence before issuing ALTER TABLE, so re-running is a no-op once the
columns exist.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Resolve DB path relative to this file's location (backend/utils/ → project root).
# The backend's SQLAlchemy engine uses the Prisma dev.db (shared single SQLite file).
# See backend/app/config.py: DATABASE_URL = "sqlite+aiosqlite:///../frontend/prisma/dev.db"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = _PROJECT_ROOT / "frontend" / "prisma" / "dev.db"


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Return True if *column* is present in *table*."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def migrate(db_path: Path = DB_PATH) -> None:
    """Add issueKey and issueTitle columns to AutoPilotTaskRecord if absent."""
    if not db_path.exists():
        logger.error("Database not found at %s — aborting", db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    try:
        added: list[str] = []

        if not _column_exists(conn, "AutoPilotTaskRecord", "issueKey"):
            conn.execute(
                "ALTER TABLE AutoPilotTaskRecord ADD COLUMN issueKey VARCHAR(64)"
            )
            added.append("issueKey")
            logger.info("Added column AutoPilotTaskRecord.issueKey")
        else:
            logger.info("Column AutoPilotTaskRecord.issueKey already exists — skipping")

        if not _column_exists(conn, "AutoPilotTaskRecord", "issueTitle"):
            conn.execute(
                "ALTER TABLE AutoPilotTaskRecord ADD COLUMN issueTitle TEXT"
            )
            added.append("issueTitle")
            logger.info("Added column AutoPilotTaskRecord.issueTitle")
        else:
            logger.info("Column AutoPilotTaskRecord.issueTitle already exists — skipping")

        conn.commit()
        if added:
            logger.info("Migration complete — added columns: %s", ", ".join(added))
        else:
            logger.info("Migration complete — no changes required (idempotent run)")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
