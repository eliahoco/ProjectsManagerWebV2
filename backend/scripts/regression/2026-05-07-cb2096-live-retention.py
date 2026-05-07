"""CB-2096 live-DB retention acceptance trace.

Inserts a 100-day-old ExecutionSummary with a sentinel issueId into the
running backend's SQLite, runs `apply_retention` via the same service
import the asyncio loop uses, and verifies the old row is gone while a
1-day-old control row from the same sentinel survives.

Sentinel issueId is unique per run so we never collide with real data
even if two operators run this concurrently. Both inserts target the same
sentinel issueId so the per-issue cap (default 20) cannot fire.

Run:
    cd backend
    ./venv/bin/python scripts/regression/2026-05-07-cb2096-live-retention.py

Exit 0 = PASS, 1 = FAIL.
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


SENTINEL = f"cb2096-trace-{uuid.uuid4().hex[:8]}"
SENTINEL_PROJECT_ID = f"{SENTINEL}-proj"
SENTINEL_ISSUE_ID = f"{SENTINEL}-issue"
SENTINEL_ISSUE_KEY = f"CB-2096-TRACE-{SENTINEL[-8:]}"


def _summary(id_: str, executed_at: datetime) -> ExecutionSummary:
    return ExecutionSummary(
        id=id_,
        issueId=SENTINEL_ISSUE_ID,
        summary="cb-2096 live retention trace",
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
        name=f"cb2096-trace-{SENTINEL[-8:]}",
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
        title="CB-2096 live retention trace sentinel",
        type="TASK",
        status="DONE",
        priority="LOW",
        updatedAt=datetime.utcnow(),
    )
    return project, issue


async def main() -> int:
    print(f"[cb-2096] sentinel issueId = {SENTINEL_ISSUE_ID}")

    # --- Snapshot existing settings so we can restore --------------------
    async with AsyncSessionLocal() as db:
        settings = await get_or_create_settings(db)
        original_retention = settings.retentionDays
        original_cap = settings.maxPerIssue
        await db.commit()
    print(
        f"[cb-2096] live DocSettings — retentionDays={original_retention}, "
        f"maxPerIssue={original_cap}"
    )

    fresh_id = f"{SENTINEL}-fresh"
    old_id = f"{SENTINEL}-old"

    try:
        # --- Seed sentinel Project + Issue (FK target) -------------------
        async with AsyncSessionLocal() as db:
            project, issue = _seed_project_and_issue()
            db.add(project)
            await db.flush()
            db.add(issue)
            await db.commit()
        print(
            f"[cb-2096] seeded sentinel project={SENTINEL_PROJECT_ID} "
            f"issue={SENTINEL_ISSUE_ID}"
        )

        # --- Set retentionDays=90, insert fresh + old rows ---------------
        async with AsyncSessionLocal() as db:
            settings = await get_or_create_settings(db)
            settings.retentionDays = 90
            now = datetime.utcnow()
            db.add(_summary(old_id, now - timedelta(days=100)))
            db.add(_summary(fresh_id, now - timedelta(days=1)))
            await db.commit()
        print("[cb-2096] inserted: old (now - 100d), fresh (now - 1d)")

        # --- Run retention via the same code path as the loop -----------
        async with AsyncSessionLocal() as db:
            purged_age, purged_cap = await apply_retention(db)
            await db.commit()
        print(
            f"[cb-2096] apply_retention → purged_by_age={purged_age}, "
            f"purged_by_cap={purged_cap}"
        )

        # --- Verify ------------------------------------------------------
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(ExecutionSummary)
                    .where(ExecutionSummary.issueId == SENTINEL_ISSUE_ID)
                )
            ).scalars().all()
            ids = {r.id for r in rows}

        print(f"[cb-2096] post-retention sentinel rows: {ids}")

        ok = (ids == {fresh_id})
        if not ok:
            print(
                f"[cb-2096] FAIL — expected only {fresh_id!r}, got {ids}",
                file=sys.stderr,
            )
            return 1
        print("[cb-2096] PASS — 100-day-old row purged, 1-day-old row survived")
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
                print(f"[cb-2096] cleanup ok: {stage}")
            except Exception as e:  # noqa: BLE001
                print(f"[cb-2096] cleanup FAILED ({stage}): {e!r}", file=sys.stderr)

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
            f"[cb-2096] cleanup done — DocSettings target: "
            f"retentionDays={original_retention}, maxPerIssue={original_cap}"
        )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
