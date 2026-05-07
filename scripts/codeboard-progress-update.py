"""Bulk-update CodeBoard ticket statuses as work progresses."""

from __future__ import annotations
import json, sys, time, urllib.error, urllib.request
from typing import Any, Dict, Optional

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
LABEL = "documentation-surface"

# Cached id resolver — uses /api/issues/{epic_id}/descendants for each epic
# since label-based listing caps at 50 (can't reach older keys).
_FEATURE_ID = "94aff46e-715b-49cf-8f69-7112be5bd211"  # CB-2038
_id_cache: Dict[str, str] = {}


def _request(method, path, payload=None, retries=3):
    data = json.dumps(payload).encode() if payload is not None else None
    last = None
    for n in range(1, retries + 1):
        req = urllib.request.Request(
            f"{BASE}{path}", data=data,
            headers={"Content-Type": "application/json"}, method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode()
                if resp.status not in (200, 201, 204):
                    raise RuntimeError(f"HTTP {resp.status}: {body}")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')}")
        except (TimeoutError, urllib.error.URLError) as e:
            last = e
            time.sleep(n)
    raise RuntimeError(f"Retries exhausted: {last}")


def _build_id_cache():
    """Walk descendants of FEATURE CB-2038 once + cache key→id."""
    if _id_cache:
        return
    items = _request("GET", f"/issues/{_FEATURE_ID}/descendants")
    items = items if isinstance(items, list) else items.get("issues") or items.get("items") or items.get("data") or []
    for i in items:
        if isinstance(i, dict) and i.get("key") and i.get("id"):
            _id_cache[i["key"]] = i["id"]


def find_id(key: str) -> str:
    if key in _id_cache:
        return _id_cache[key]
    _build_id_cache()
    if key in _id_cache:
        return _id_cache[key]
    raise RuntimeError(f"Cannot resolve {key}")


def patch(key: str, status: str, comment: Optional[str] = None):
    issue_id = find_id(key)
    if comment:
        _request("POST", f"/issues/{issue_id}/comments",
                 {"content": comment, "author": "AI"})
    _request("PATCH", f"/issues/{issue_id}", {"status": status})
    print(f"  {key} → {status}")


mode = sys.argv[1] if len(sys.argv) > 1 else "default"

if mode == "e4-commits-done":
    print("=== E4.2 commit slices → COMPLETED_WAITING_QA ===")
    patch("CB-2106", "COMPLETED_WAITING_QA", "4 commit slices landed on main: T4.2.1 backend doc generator, T4.2.2 hooks, T4.2.3 frontend, T4.2.4 cleanup + scripts.")
    patch("CB-2107", "COMPLETED_WAITING_QA", "Commit 2cbc0a0 on main: 8 files, +3916 -7. Backend doc generator + tests.")
    patch("CB-2108", "COMPLETED_WAITING_QA", "Commit on main: 17 files, +2724 -42. QA + RAG + terminal hooks + completion loop atomicity fix.")
    patch("CB-2109", "COMPLETED_WAITING_QA", "Commit c4e8560 on main: 6 files, +1143 -4. ImplementationTab.tsx + hooks.")
    patch("CB-2110", "COMPLETED_WAITING_QA", "Commit on main: 13 files, +879 -0. Screenshots moved to docs/research/, plan scripts shipped.")
    patch("CB-2114", "COMPLETED_WAITING_QA", "Verified: git status clean of doc-feature WIP.")
    patch("CB-2115", "COMPLETED_WAITING_QA", "Verified: ls *.png in repo root returns nothing.")

elif mode == "e1-1-1-blocked":
    print("=== T1.1.1 blocked on docker daemon ===")
    patch("CB-2041", "BACKLOG", "BLOCKED: docker daemon unreachable. Resuming once Eli's AutoPilot session ends and `colima restart` runs.")

elif mode == "e2-start":
    print("=== E2 frontend dispatched (background agent) ===")
    patch("CB-2054", "IN_PROGRESS", "Dispatched react-specialist agent for full E2 slice (hooks + page + view + tab integration).")
    patch("CB-2055", "IN_PROGRESS")
    patch("CB-2059", "IN_PROGRESS")
    patch("CB-2064", "IN_PROGRESS")
    patch("CB-2067", "IN_PROGRESS")

elif mode == "e3-backend-done":
    print("=== E3 backend tasks → COMPLETED_WAITING_QA ===")
    commit_msg = (
        "Commit on main: 8 files, +583 -7. DocSettings model + GET/PATCH endpoint + retention service + "
        "autoGenerate gate in completion hook + 6h retention background task. 8/8 tests pass."
    )
    patch("CB-2078", "IN_PROGRESS", "E3 backend complete. Frontend (S3.2, S3.3) pending.")
    patch("CB-2079", "COMPLETED_WAITING_QA", commit_msg)
    patch("CB-2080", "COMPLETED_WAITING_QA", "DocSettings model added at backend/models/doc_settings.py with singleton key='global'.")
    patch("CB-2081", "COMPLETED_WAITING_QA", "GET/PATCH /api/documentation/settings — Pydantic bounds 1..1825 days, 1..1000 per issue. test_doc_settings.py covers GET creates default, PATCH update, PATCH out-of-range rejection, empty-body no-op.")
    patch("CB-2082", "COMPLETED_WAITING_QA", "_process_completion_for_session reads DocSettings, skips doc-gen when autoGenerate=False (still flips Issue → COMPLETED_WAITING_QA). Failure to load settings defaults to ON.")
    patch("CB-2083", "COMPLETED_WAITING_QA", "process_doc_retention background task — runs every 6h, two-phase purge (by age then per-issue cap) via apply_retention. Tests cover both phases.")

print("=== DONE ===")

if mode == "e2-frontend-done":
    print("=== E2 frontend → COMPLETED_WAITING_QA ===")
    msg = "Commit 655ff46 on main: 9 files, +847 -43. FeatureDocumentation page + view + button + hooks + tab integration."
    patch("CB-2054", "IN_PROGRESS", "E2 frontend slice landed. S2.4 audits next.")
    patch("CB-2055", "COMPLETED_WAITING_QA", msg)
    patch("CB-2056", "COMPLETED_WAITING_QA", "useFeatureDocumentation hook in useCodeBoard.ts")
    patch("CB-2057", "COMPLETED_WAITING_QA", "useGenerateFeatureDocumentation mutation in useCodeBoard.ts")
    patch("CB-2058", "COMPLETED_WAITING_QA", "FeatureDocumentationData type in useCodeBoard.ts")
    patch("CB-2059", "COMPLETED_WAITING_QA", msg)
    patch("CB-2060", "COMPLETED_WAITING_QA", "app/codeboard/features/[id]/documentation/page.tsx")
    patch("CB-2061", "COMPLETED_WAITING_QA", "FeatureDocumentationView.tsx — 6 sections + metrics + techStack badges")
    patch("CB-2062", "COMPLETED_WAITING_QA", "GenerateFeatureDocButton.tsx — POST + spinner + toast")
    patch("CB-2063", "COMPLETED_WAITING_QA", "lastIndexedAt timestamp + green/amber dot in FeatureDocumentationView")
    patch("CB-2064", "COMPLETED_WAITING_QA", msg)
    patch("CB-2065", "COMPLETED_WAITING_QA", "Documentation link unconditionally visible on FEATURE-type issues in IssueDetail + IssueDetailModal")
    patch("CB-2066", "COMPLETED_WAITING_QA", "Empty state with Sparkles icon + Generate CTA in features/[id]/documentation/page.tsx")
