"""Resume push: create remaining 8 items under S4.2 + promote starting work to IN_PROGRESS."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, List

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
LABEL = "documentation-surface"

S4_2 = "406c270b-f994-4d48-8dbe-16e4795fc79c"
S4_1 = "a7a712fe-0100-4264-9a31-2f55dc3d9b08"
E4 = "d4ecd76e-31ee-4bb4-9f52-adbd1eda3eb2"
FEATURE = "94aff46e-715b-49cf-8f69-7112be5bd211"


def _request(method: str, path: str, payload: Optional[Dict[str, Any]] = None,
             retries: int = 3) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            f"{BASE}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                if resp.status not in (200, 201, 204):
                    raise RuntimeError(f"HTTP {resp.status} on {path}: {body}")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code} on {path}: {body}") from e
        except (TimeoutError, urllib.error.URLError) as e:
            last_err = e
            print(f"  [retry {attempt}/{retries}] {method} {path} timed out: {e}")
            time.sleep(1.0 * attempt)
    raise RuntimeError(f"All retries exhausted: {last_err}")


def create(title: str, description: str, issue_type: str, priority: str,
           parent_id: Optional[str] = None, assignee: Optional[str] = None,
           extra_labels: Optional[List[str]] = None) -> Dict[str, Any]:
    labels = [LABEL]
    if extra_labels:
        labels.extend(extra_labels)
    payload: Dict[str, Any] = {
        "title": title, "description": description, "type": issue_type,
        "priority": priority, "reporter": "AI", "labels": ",".join(labels),
    }
    if parent_id:
        payload["parentId"] = parent_id
    if assignee:
        payload["assignee"] = assignee
    result = _request("POST", f"/projects/{PROJECT_ID}/issues", payload)
    print(f"  [{result.get('key')}] {issue_type:8s} {title[:80]}")
    return result


def patch(issue_id: str, payload: Dict[str, Any]) -> None:
    _request("PATCH", f"/issues/{issue_id}", payload)


print("\n=== Resuming S4.2 children (T4.2.1 already created as CB-2107) ===")

create("T4.2.2: Commit slice 2 — QA + RAG + terminal hooks (qa_service.py + rag_service.py + terminal_service.py + tests)",
       "Files: backend/services/qa_service.py, backend/services/rag_service.py, backend/services/terminal_service.py, backend/services/ai_service.py (if modified), backend/api/qa.py, backend/api/issues.py, backend/app/main.py, backend/models/schemas.py, all new test_qa_*.py, test_rag_service_*.py, test_terminal_service_doc_capture.py.",
       "TASK", "HIGH", parent_id=S4_2, assignee="git-workflow-manager")

create("T4.2.3: Commit slice 3 — frontend (IssueDetail + IssueDetailModal + ImplementationTab + useCodeBoard)",
       "Files: frontend/components/codeboard/IssueDetail.tsx, frontend/components/codeboard/IssueDetailModal.tsx, frontend/components/codeboard/ImplementationTab.tsx (new), frontend/components/codeboard/index.ts, frontend/hooks/useCodeBoard.ts, frontend/app/codeboard/issues/[id]/page.tsx.",
       "TASK", "HIGH", parent_id=S4_2, assignee="git-workflow-manager")

create("T4.2.4: Cleanup — move loose cb-1612-*.png + watchdog-*.png to docs/research/ or delete",
       "Files in repo root: cb-1612-kanban.png, cb-1612-modal-empty.png, cb-1612-modal-populated.png, cb-1612-slideover.png, cb-1612-standalone.png, cb-1612-view-full.png, watchdog-auto-restarting.png, watchdog-buttons-visible.png, watchdog-toggle-switch.png. Move to docs/research/cb-1612/ and docs/research/watchdog/ or delete if no longer needed. Final commit.",
       "TASK", "MEDIUM", parent_id=S4_2, assignee="general-purpose")

create("[QA] E4-1: Existing ImplementationTab renders ExecutionSummary on real issue",
       "Manual: pick issue with prior exec → Implementation tab → all sections render correctly.",
       "TASK", "HIGH", parent_id=S4_2, assignee="qa", extra_labels=["qa-verification"])

create("[QA] E4-2: Add ImplementationNote → persists → renders",
       "Manual: open Implementation tab → Add Note → fill form → Save → note appears in list → reload → still there.",
       "TASK", "HIGH", parent_id=S4_2, assignee="qa", extra_labels=["qa-verification"])

create("[QA] E4-3: Delete ImplementationNote → 204 → list refreshes",
       "Manual: delete note → list refreshes without it → reload → confirmed gone.",
       "TASK", "MEDIUM", parent_id=S4_2, assignee="qa", extra_labels=["qa-verification"])

create("[QA] E4-4: git status clean after E4.2 commit slices",
       "Manual: run git status after T4.2.1-3 → no uncommitted documentation-feature files. Working tree only contains files unrelated to this feature.",
       "TASK", "HIGH", parent_id=S4_2, assignee="qa", extra_labels=["qa-verification"])

create("[QA] E4-5: Loose screenshots gone from repo root",
       "Manual: ls *.png in repo root → returns nothing.",
       "TASK", "MEDIUM", parent_id=S4_2, assignee="qa", extra_labels=["qa-verification"])

print("\n=== Promoting starting work to IN_PROGRESS ===")
patch(FEATURE, {"status": "IN_PROGRESS"})
print(f"  FEATURE CB-2038 → IN_PROGRESS")
patch(E4, {"status": "IN_PROGRESS"})
print(f"  EPIC CB-2100 (E4) → IN_PROGRESS")
patch(S4_1, {"status": "IN_PROGRESS"})
print(f"  STORY CB-2101 (S4.1) → IN_PROGRESS")

print("\n=== DONE ===")
