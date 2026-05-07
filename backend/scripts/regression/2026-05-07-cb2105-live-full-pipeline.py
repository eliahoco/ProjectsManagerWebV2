"""CB-2105 (T4.1.4) live full-pipeline regression.

End-to-end verification of the auto-documentation pipeline against the
running stack:

  exec(simulated) → documentation_generator.generate_from_execution
                  → ExecutionSummary row persisted to live SQLite
                  → Issue.implementationSummary populated
                  → embed_execution_summary into live ChromaDB
                  → /api/issues/{id}/documentation returns the row
                    (the endpoint ImplementationTab consumes)
                  → /api/issues/{id}/documentation/notes returns []

Sentinel issue is created in the live ProjectsManagerWebV2 project, all
artifacts are deleted at the end (DB rows + Chroma doc), regardless of
PASS/FAIL.

The AI summary path is short-circuited by leaving generate_text mocked
to return "" so the deterministic fallback summary is used (no external
network call). Git capture is skipped via project_path=None. Everything
else exercises live code.

Run:
    cd backend
    ./venv/bin/python scripts/regression/2026-05-07-cb2105-live-full-pipeline.py

Exit 0 = PASS, 1 = FAIL.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.chdir(_BACKEND)

from sqlalchemy import select, delete  # noqa: E402

from models import AsyncSessionLocal, ExecutionSummary  # noqa: E402
from models.issue import Issue  # noqa: E402
from models.documentation import ImplementationNote  # noqa: E402
from services.documentation_generator import documentation_generator  # noqa: E402
from services.rag_service import RAGService  # noqa: E402
from services.terminal_service import (  # noqa: E402
    ExecutionPhase,
    ExecutionProvider,
    ExecutionStatus,
    TerminalSession,
)


PROJECT_ID = "1511e54f71dccd3fa79f67fe"  # ProjectsManagerWebV2 (live)
API_BASE = "http://localhost:8401/api"
SENTINEL = uuid.uuid4().hex[:8]
SENTINEL_TITLE = f"CB-2105 regression sentinel {SENTINEL} — DELETE ME"


def _api_post(path: str, body: dict, timeout: int = 10) -> tuple[int, dict]:
    req = urllib.request.Request(
        API_BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def _api_get(path: str, timeout: int = 10) -> tuple[int, object]:
    req = urllib.request.Request(API_BASE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "null")


def _api_delete(path: str, timeout: int = 10) -> int:
    req = urllib.request.Request(API_BASE + path, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def _build_session(issue_id: str, issue_key: str, project_path: str) -> TerminalSession:
    """Build a TerminalSession that mimics a successful Claude exec."""
    started = datetime.utcnow()
    s = TerminalSession(
        id=f"sess-{SENTINEL}",
        issue_id=issue_id,
        issue_key=issue_key,
        issue_title=SENTINEL_TITLE,
        project_id=PROJECT_ID,
        provider=ExecutionProvider.CLAUDE_CODE,
        status=ExecutionStatus.COMPLETED,
        started_at=started,
        completed_at=started,
        exit_code=0,
        phase=ExecutionPhase.COMPLETED,
        progress_percent=100,
        current_action="Completed successfully",
        files_read=2,
        files_written=1,
        commands_run=3,
        project_path=project_path,
    )
    s._append_output("[INFO] CB-2105 regression: simulated successful exec")
    s._append_output("[INFO] Modified: backend/services/example.py")
    s._append_output("[INFO] All checks passed.")
    return s


async def main() -> int:
    print(f"[cb-2105] sentinel={SENTINEL}")

    # --- Wire RAGService into the live generator (matches lifespan path) ---
    rag = RAGService()
    try:
        await asyncio.to_thread(rag._init_client_blocking)
    except Exception as exc:
        print(
            f"[cb-2105] ChromaDB unreachable on HTTP — falling back to persistent: {exc}"
        )
        rag._fallback_to_persistent()
    documentation_generator._rag = rag
    print(f"[cb-2105] RAG mode: {rag.describe_mode()}")

    # Mock AI to keep the run hermetic — deterministic fallback summary path.
    from services.ai_service import ai_service as _ai_singleton
    original_generate = _ai_singleton.generate_text
    _ai_singleton.generate_text = AsyncMock(return_value="")

    issue_id: str | None = None
    issue_key: str | None = None
    summary_id: str | None = None
    failures: list[str] = []

    try:
        # --- Create sentinel TASK via the live API ----------------------------
        status_code, created = _api_post(
            f"/projects/{PROJECT_ID}/issues",
            {
                "title": SENTINEL_TITLE,
                "description": "Auto-created by CB-2105 regression. Safe to delete.",
                "type": "TASK",
                "priority": "LOW",
                "reporter": "AI",
                "labels": json.dumps(["cb-2105-regression", f"sentinel-{SENTINEL}"]),
            },
        )
        if status_code != 201:
            print(f"[cb-2105] FAIL create issue → status={status_code} body={created}")
            return 1
        issue_id = created["id"]
        issue_key = created["key"]
        print(f"[cb-2105] created sentinel issue id={issue_id} key={issue_key}")

        # --- Run generate_from_execution against live DB + live Chroma -------
        async with AsyncSessionLocal() as db:
            issue_row = (
                await db.execute(select(Issue).where(Issue.id == issue_id))
            ).scalar_one()
            session = _build_session(issue_id, issue_key, project_path=None)
            summary_row = await documentation_generator.generate_from_execution(
                session=session,
                issue=issue_row,
                project_path=None,  # skip git capture
                db=db,
            )
            if summary_row is None:
                print("[cb-2105] FAIL — generate_from_execution returned None")
                return 1
            summary_id = summary_row.id
            await db.commit()
        print(f"[cb-2105] persisted ExecutionSummary id={summary_id}")

        # --- Pillar 1: ExecutionSummary row exists in DB ----------------------
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(ExecutionSummary)
                    .where(ExecutionSummary.id == summary_id)
                )
            ).scalar_one_or_none()
            if row is None:
                failures.append("DB pillar: ExecutionSummary row not found")
            else:
                print(
                    f"[cb-2105] DB OK — issueId={row.issueId} "
                    f"provider={row.provider} executionTime={row.executionTime}"
                )
            issue_after = (
                await db.execute(select(Issue).where(Issue.id == issue_id))
            ).scalar_one()
            if not (issue_after.implementationSummary and issue_after.implementationSummary.strip()):
                failures.append(
                    "DB pillar: Issue.implementationSummary not populated"
                )
            else:
                print(
                    f"[cb-2105] DB OK — Issue.implementationSummary len="
                    f"{len(issue_after.implementationSummary)}"
                )

        # --- Pillar 2: ImplementationTab API surface --------------------------
        sc, body = _api_get(f"/issues/{issue_id}/documentation")
        if sc != 200 or not isinstance(body, list) or len(body) != 1:
            failures.append(
                f"API pillar: GET /issues/{{id}}/documentation → "
                f"status={sc} body={body}"
            )
        else:
            api_row = body[0]
            if api_row.get("id") != summary_id:
                failures.append(
                    f"API pillar: returned summary id={api_row.get('id')} "
                    f"!= persisted id={summary_id}"
                )
            else:
                print(
                    f"[cb-2105] API OK — /documentation returned "
                    f"summary id={api_row['id']}"
                )

        sc_latest, latest = _api_get(f"/issues/{issue_id}/documentation/latest")
        if sc_latest != 200 or not isinstance(latest, dict) or latest.get("id") != summary_id:
            failures.append(
                f"API pillar: /documentation/latest status={sc_latest} body={latest}"
            )
        else:
            print(f"[cb-2105] API OK — /documentation/latest returned id={latest['id']}")

        sc_notes, notes = _api_get(f"/issues/{issue_id}/documentation/notes")
        if sc_notes != 200 or not isinstance(notes, list) or len(notes) != 0:
            failures.append(
                f"API pillar: /documentation/notes (empty initial) "
                f"status={sc_notes} body={notes}"
            )
        else:
            print("[cb-2105] API OK — /documentation/notes returns [] (empty initial)")

        # --- Pillar 3: ChromaDB embedding -------------------------------------
        try:
            collection = rag.get_collection(PROJECT_ID)
            doc_id = rag.generate_doc_id(issue_id, content_type="execution_summary")
            got = collection.get(ids=[doc_id])
            ids_back = got.get("ids") or []
            metas_back = got.get("metadatas") or []
            if not ids_back or ids_back[0] != doc_id:
                failures.append(
                    f"Chroma pillar: doc_id={doc_id} not retrievable "
                    f"(got={ids_back})"
                )
            else:
                meta = metas_back[0] if metas_back else {}
                if (
                    meta.get("issue_id") != issue_id
                    or meta.get("key") != issue_key
                    or meta.get("content_type") != "execution_summary"
                ):
                    failures.append(
                        f"Chroma pillar: metadata mismatch — got {meta}"
                    )
                else:
                    print(
                        f"[cb-2105] Chroma OK — collection="
                        f"project_{PROJECT_ID[:8]} doc_id={doc_id} meta={meta}"
                    )
        except Exception as exc:
            failures.append(f"Chroma pillar: query raised {exc!r}")

        # --- Result -----------------------------------------------------------
        if failures:
            print("[cb-2105] FAIL — pillar failures:")
            for f in failures:
                print(f"  - {f}")
            return 1
        print("[cb-2105] PASS — DB + API + Chroma all green")
        return 0

    finally:
        # Restore AI mock first (system-layer state, Bible rule 21)
        _ai_singleton.generate_text = original_generate

        async def _safe(stage: str, coro_fn):
            try:
                async with AsyncSessionLocal() as db:
                    await coro_fn(db)
                    await db.commit()
                print(f"[cb-2105] cleanup ok: {stage}")
            except Exception as e:  # noqa: BLE001
                print(f"[cb-2105] cleanup FAILED ({stage}): {e!r}", file=sys.stderr)

        if summary_id:
            async def _del_summary(db):
                await db.execute(
                    delete(ExecutionSummary).where(ExecutionSummary.id == summary_id)
                )
            await _safe("delete sentinel ExecutionSummary", _del_summary)

        if issue_id:
            async def _del_notes(db):
                await db.execute(
                    delete(ImplementationNote).where(
                        ImplementationNote.issueId == issue_id
                    )
                )
            await _safe("delete sentinel ImplementationNotes", _del_notes)

            # Use the API for issue delete so cascade matches normal behavior
            sc = _api_delete(f"/issues/{issue_id}")
            print(f"[cb-2105] cleanup api delete issue → status={sc}")

        # Drop sentinel doc from Chroma (best-effort)
        if issue_id:
            try:
                collection = rag.get_collection(PROJECT_ID)
                doc_id = rag.generate_doc_id(issue_id, content_type="execution_summary")
                collection.delete(ids=[doc_id])
                print(f"[cb-2105] cleanup ok: deleted Chroma doc {doc_id}")
            except Exception as e:  # noqa: BLE001
                print(f"[cb-2105] cleanup FAILED (chroma doc): {e!r}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
