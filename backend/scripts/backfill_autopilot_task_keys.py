"""
Backfill issueKey + issueTitle on AutoPilotTaskRecord rows where they are NULL.

CB-2675 fix — run after applying the schema migration (apply_autopilot_task_keys.py).

Usage:
    python backend/scripts/backfill_autopilot_task_keys.py

The script:
1. Finds AutoPilotTaskRecord rows where issueKey IS NULL OR issueKey = ''
2. JOINs with the Issue table via issueId to retrieve key + title
3. Updates the rows in place
4. Reports updated / not-found counts

Idempotent: running again when all rows are already populated updates 0 rows.

Target DB: frontend/prisma/dev.db (the shared SQLite used by both SQLAlchemy and Prisma).
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Resolve DB path: backend/scripts/ → project root → frontend/prisma/dev.db
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = _PROJECT_ROOT / "frontend" / "prisma" / "dev.db"


def backfill(db_path: Path = DB_PATH) -> None:
    """Update issueKey + issueTitle on all AutoPilotTaskRecord rows missing them."""
    if not db_path.exists():
        logger.error("Database not found at %s — aborting", db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        # Find all task rows with missing issueKey, join to Issue for the data.
        rows = conn.execute(
            """
            SELECT t.id        AS task_id,
                   t.issueId   AS issue_id,
                   i.key       AS issue_key,
                   i.title     AS issue_title
            FROM   AutoPilotTaskRecord t
            LEFT   JOIN Issue i ON i.id = t.issueId
            WHERE  t.issueKey IS NULL
               OR  t.issueKey = ''
            """
        ).fetchall()

        if not rows:
            logger.info("No rows need backfill — already complete.")
            return

        updated = 0
        not_found = 0

        for row in rows:
            if row["issue_key"] is None:
                logger.warning(
                    "Task %s references issueId %s which was NOT FOUND in Issue table — skipping",
                    row["task_id"],
                    row["issue_id"],
                )
                not_found += 1
                continue

            conn.execute(
                "UPDATE AutoPilotTaskRecord SET issueKey = ?, issueTitle = ? WHERE id = ?",
                (row["issue_key"], row["issue_title"] or "", row["task_id"]),
            )
            updated += 1
            logger.info(
                "Backfilled task %s → issueKey=%s title=%r",
                row["task_id"],
                row["issue_key"],
                (row["issue_title"] or "")[:60],
            )

        conn.commit()
        logger.info(
            "Backfill complete — updated: %d, not_found: %d (out of %d candidates)",
            updated,
            not_found,
            len(rows),
        )

    finally:
        conn.close()


def verify(db_path: Path = DB_PATH) -> None:
    """Print the current state of AutoPilotTaskRecord rows after backfill."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT t.id, t.issueId, t.issueKey, t.issueTitle, t.status,
                   t.sequence, t.queueId
            FROM   AutoPilotTaskRecord t
            ORDER  BY t.queueId, t.sequence
            """
        ).fetchall()

        if not rows:
            logger.info("No AutoPilotTaskRecord rows found.")
            return

        logger.info("AutoPilotTaskRecord state after backfill (%d rows):", len(rows))
        for row in rows:
            logger.info(
                "  seq=%d  status=%-12s  issueKey=%-12s  title=%r",
                row["sequence"],
                row["status"],
                row["issueKey"] or "(null)",
                (row["issueTitle"] or "(null)")[:50],
            )
    finally:
        conn.close()


if __name__ == "__main__":
    backfill()
    verify()
