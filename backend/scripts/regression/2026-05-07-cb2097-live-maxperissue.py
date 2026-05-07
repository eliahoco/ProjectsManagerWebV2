"""CB-2097 live-DB per-issue cap acceptance trace.

Inserts 25 ExecutionSummary rows on a single sentinel issueId (newest at
index 0, oldest at index 24, separated by 1 minute), pins
DocSettings.maxPerIssue=20 (and bumps retentionDays high so the per-age
phase cannot fire), runs `apply_retention` via the same import the
asyncio loop uses, and verifies exactly the 20 newest rows survive while
the 5 oldest are purged.

Sentinel issueId is unique per run so we never collide with real data
even if two operators run this concurrently.

Run:
    cd backend
    ./venv/bin/python scripts/regression/2026-05-07-cb2097-live-maxperissue.py

Exit 0 = PASS, 1 = FAIL.

Operator note (SIGKILL recovery):
    The script pins DocSettings to retentionDays=10000, maxPerIssue=20 for
    the duration of the run, then restores the snapshot in `finally`. If
    the Python process is SIGKILLed between the pin and the finally block,
    DocSettings will be left in the pinned state. The snapshot is logged
    on the second line of stdout (`live DocSettings — retentionDays=...,
    maxPerIssue=...`); recover by PATCHing /api/documentation/settings
    back to the logged values.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.chdir(_BACKEND)

from sqlalchemy import select, delete  # noqa: E402

from models import AsyncSessionLocal, ExecutionSummary  # noqa: E402
from models.issue import Issue, Project  # noqa: E402
from services.doc_settings_service import (  # noqa: E402
    apply_retention,
    get_or_create_settings,
)


SENTINEL = f"cb2097-trace-{uuid.uuid4().hex[:8]}"
SENTINEL_PROJECT_ID = f"{SENTINEL}-proj"
SENTINEL_ISSUE_ID = f"{SENTINEL}-issue"
SENTINEL_ISSUE_KEY = f"CB-2097-TRACE-{SENTINEL[-8:]}"

TOTAL_ROWS = 25
CAP = 20
EXPECTED_PURGED = TOTAL_ROWS - CAP  # 5


def _row_id(idx: int) -> str:
    return f"{SENTINEL}-r{idx:02d}"


def _summary(id_: str, executed_at: datetime) -> ExecutionSummary:
    return ExecutionSummary(
        id=id_,
        issueId=SENTINEL_ISSUE_ID,
        summary="cb-2097 per-issue cap trace",
        executedAt=executed_at,
        executionTime=0.0,
        provider="claude_code",
        componentsModified="[]",
        filesTouched="[]",
        commitHashes="[]",
    )


def _seed_project_and_issue() -> tuple[Project, Issue]:
    import time as _time
    now_ms = int(_time.time() * 1000)
    project = Project(
        id=SENTINEL_PROJECT_ID,
        name=f"cb2097-trace-{SENTINEL[-8:]}",
        path=f"/tmp/{SENTINEL_PROJECT_ID}",
        status="ACTIVE",
        createdAt=now_ms,
        updatedAt=now_ms,
    )
    issue = Issue(
        id=SENTINEL_ISSUE_ID,
        projectId=SENTINEL_PROJECT_ID,
        key=SENTINEL_ISSUE_KEY,
        sequence=1,
        title="CB-2097 per-issue cap trace sentinel",
        type="TASK",
        status="DONE",
        priority="LOW",
        updatedAt=datetime.utcnow(),
    )
    return project, issue


async def main() -> int:
    print(f"[cb-2097] sentinel issueId = {SENTINEL_ISSUE_ID}")

    # --- Snapshot existing settings so we can restore --------------------
    async with AsyncSessionLocal() as db:
        settings = await get_or_create_settings(db)
        original_retention = settings.retentionDays
        original_cap = settings.maxPerIssue
        await db.commit()
    print(
        f"[cb-2097] live DocSettings — retentionDays={original_retention}, "
        f"maxPerIssue={original_cap}"
    )

    try:
        # --- Seed sentinel Project + Issue (FK target) -------------------
        async with AsyncSessionLocal() as db:
            project, issue = _seed_project_and_issue()
            db.add(project)
            await db.flush()
            db.add(issue)
            await db.commit()
        print(
            f"[cb-2097] seeded sentinel project={SENTINEL_PROJECT_ID} "
            f"issue={SENTINEL_ISSUE_ID}"
        )

        # --- Pin retentionDays high (age phase a no-op), maxPerIssue=20 -
        async with AsyncSessionLocal() as db:
            settings = await get_or_create_settings(db)
            settings.retentionDays = 10_000
            settings.maxPerIssue = CAP
            await db.commit()
        print(
            f"[cb-2097] pinned DocSettings — retentionDays=10000, maxPerIssue={CAP}"
        )

        # --- Insert 25 rows: newest=now, oldest=now-24min ----------------
        now = datetime.utcnow()
        async with AsyncSessionLocal() as db:
            for i in range(TOTAL_ROWS):
                db.add(_summary(_row_id(i), now - timedelta(minutes=i)))
            await db.commit()
        print(f"[cb-2097] inserted {TOTAL_ROWS} sentinel summaries (1-min spacing)")

        # --- Pre-condition sanity: confirm 25 rows present ---------------
        async with AsyncSessionLocal() as db:
            pre_rows = (
                await db.execute(
                    select(ExecutionSummary)
                    .where(ExecutionSummary.issueId == SENTINEL_ISSUE_ID)
                )
            ).scalars().all()
        if len(pre_rows) != TOTAL_ROWS:
            print(
                f"[cb-2097] FAIL — pre-condition: expected {TOTAL_ROWS} rows, "
                f"got {len(pre_rows)}",
                file=sys.stderr,
            )
            return 1
        print(f"[cb-2097] pre-condition ok — {len(pre_rows)} sentinel rows present")

        # --- Run retention via the same code path as the loop -----------
        async with AsyncSessionLocal() as db:
            purged_age, purged_cap = await apply_retention(db)
            await db.commit()
        print(
            f"[cb-2097] apply_retention → purged_by_age={purged_age}, "
            f"purged_by_cap={purged_cap}"
        )

        # --- Verify ------------------------------------------------------
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(ExecutionSummary)
                    .where(ExecutionSummary.issueId == SENTINEL_ISSUE_ID)
                    .order_by(ExecutionSummary.executedAt.desc())
                )
            ).scalars().all()
        ids = [r.id for r in rows]
        expected_ids = [_row_id(i) for i in range(CAP)]  # newest 20 (indices 0..19)
        purged_expected = {_row_id(i) for i in range(CAP, TOTAL_ROWS)}  # 20..24

        print(f"[cb-2097] post-retention sentinel row count: {len(ids)}")
        print(f"[cb-2097] surviving newest: {ids[:3]} ... oldest: {ids[-3:]}")

        ok = (
            len(ids) == CAP
            and ids == expected_ids
            and not (set(ids) & purged_expected)
        )
        if not ok:
            print(
                f"[cb-2097] FAIL — expected exactly {CAP} newest rows {expected_ids[:3]}.."
                f"{expected_ids[-3:]}, got {len(ids)} rows {ids[:3]}..{ids[-3:]}",
                file=sys.stderr,
            )
            return 1
        if purged_cap != EXPECTED_PURGED:
            print(
                f"[cb-2097] FAIL — apply_retention reported "
                f"purged_by_cap={purged_cap}, expected {EXPECTED_PURGED}",
                file=sys.stderr,
            )
            return 1
        print(
            f"[cb-2097] PASS — newest {CAP} rows survived, oldest "
            f"{EXPECTED_PURGED} purged by per-issue cap"
        )
        return 0

    finally:
        # --- Cleanup: each stage in its own session so a single failure
        # cannot block the others. Restoring DocSettings is the most
        # important — it touches the system-layer (Bible rule 21) — so it
        # runs last in its own transaction even if every prior stage
        # raised. Failures are logged, not raised, so the script exits
        # with the original PASS/FAIL signal.
        async def _safe(stage: str, coro_fn):
            try:
                async with AsyncSessionLocal() as db:
                    await coro_fn(db)
                    await db.commit()
                print(f"[cb-2097] cleanup ok: {stage}")
            except Exception as e:  # noqa: BLE001
                print(f"[cb-2097] cleanup FAILED ({stage}): {e!r}", file=sys.stderr)

        async def _del_summaries(db):
            await db.execute(
                delete(ExecutionSummary)
                .where(ExecutionSummary.issueId == SENTINEL_ISSUE_ID)
            )

        async def _del_issue(db):
            await db.execute(delete(Issue).where(Issue.id == SENTINEL_ISSUE_ID))

        async def _del_project(db):
            await db.execute(
                delete(Project).where(Project.id == SENTINEL_PROJECT_ID)
            )

        async def _restore_settings(db):
            settings = await get_or_create_settings(db)
            settings.retentionDays = original_retention
            settings.maxPerIssue = original_cap

        await _safe("delete sentinel summaries", _del_summaries)
        await _safe("delete sentinel issue", _del_issue)
        await _safe("delete sentinel project", _del_project)
        await _safe("restore DocSettings", _restore_settings)
        print(
            f"[cb-2097] cleanup done — DocSettings target: "
            f"retentionDays={original_retention}, maxPerIssue={original_cap}"
        )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
