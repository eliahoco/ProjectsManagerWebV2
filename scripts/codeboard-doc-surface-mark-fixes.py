"""Mark F1/F3/F4/F5 COMPLETED_WAITING_QA. File F2 deferral follow-up."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
LABEL = "documentation-surface"
FEATURE = "94aff46e-715b-49cf-8f69-7112be5bd211"


def _request(method, path, payload=None, retries=3):
    data = json.dumps(payload).encode() if payload is not None else None
    last_err = None
    for attempt in range(1, retries + 1):
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
            last_err = e
            time.sleep(attempt)
    raise RuntimeError(f"Retries exhausted: {last_err}")


def find_id(key):
    data = _request("GET", f"/projects/{PROJECT_ID}/issues?labels={LABEL}&limit=200")
    items = data if isinstance(data, list) else data.get("issues") or data.get("items") or data.get("data")
    for i in items:
        if i.get("key") == key:
            return i["id"]
    raise RuntimeError(f"Cannot resolve {key}")


def patch(issue_id, payload):
    _request("PATCH", f"/issues/{issue_id}", payload)


def add_comment(issue_id, content):
    _request("POST", f"/issues/{issue_id}/comments", {
        "content": content, "author": "AI",
    })


# --- Mark F1, F3, F4, F5 as COMPLETED_WAITING_QA ---

print("=== Marking fixed BUGs COMPLETED_WAITING_QA ===")
for key, summary in (
    ("CB-2116", "F1 fix: per-session transaction in process_pending_completions; new peek_/clear_ methods on terminal_service; regression test test_completion_loop_atomicity.py (5 tests pass)"),
    ("CB-2118", "F3 fix: per-item caps + URL-scheme validation on ImplementationNote.tags/references; module-level constants (Pydantic v2 ModelPrivateAttr workaround)"),
    ("CB-2119", "F4 fix: _capture_git_changes + _validate_git_repo now use _safe_validate_project_path which calls terminal_service.validate_project_path (lazy import) — applies same allow-list (block /etc, /root, ~/.ssh) as execution path"),
    ("CB-2120", "F5 fix: _run_git_subprocess raises ValueError if cmd is not a list starting with 'git' — defensive shape-check"),
):
    issue_id = find_id(key)
    add_comment(issue_id, summary)
    patch(issue_id, {"status": "COMPLETED_WAITING_QA"})
    print(f"  {key} → COMPLETED_WAITING_QA")

# --- F2: comment + leave in BACKLOG (deferred) ---

print("\n=== F2 deferred — adding comment ===")
f2_id = find_id("CB-2117")
add_comment(f2_id,
    "DEFERRED: full fix requires backend auth layer — out of scope of "
    "CB-2038 Documentation Surface feature. Existing posture acceptable for "
    "single-operator deployment (Eli is sole user). Will be addressed when "
    "auth feature is filed. Single-operator residual risk acknowledged."
)
print(f"  CB-2117 (F2) — deferred comment added, status unchanged (BACKLOG)")

# --- File F2 follow-up ticket as new BUG outside this feature ---

print("\n=== Filing F2 follow-up (auth layer needed) ===")
followup = _request("POST", f"/projects/{PROJECT_ID}/issues", {
    "title": "Add backend auth layer + project scoping to all /api/* endpoints (deferred from CB-2117)",
    "description": (
        "**Source**: deferred from CB-2117 (F2) audit finding on Documentation Surface feature.\n\n"
        "**Issue**: documentation API endpoints (and most other /api/* endpoints) have no per-request "
        "authorization. `_ensure_issue_exists` / `_load_feature_issue` look up by `Issue.id` only, "
        "with no projectId scoping and no caller identity check.\n\n"
        "Currently acceptable for single-operator deployment but blocks multi-tenant use.\n\n"
        "**Scope**: full repo audit + auth layer (likely OAuth/JWT or session cookie + per-project "
        "RBAC). Out of scope of CB-2038 Documentation Surface feature.\n\n"
        "**Affected endpoints** (documentation feature alone):\n"
        "- POST /api/issues/{id}/documentation/notes\n"
        "- DELETE /api/issues/{id}/documentation/notes/{note_id}\n"
        "- GET /api/issues/{id}/documentation\n"
        "- GET /api/issues/{id}/documentation/latest\n"
        "- GET /api/issues/{id}/documentation/notes\n"
        "- GET /api/features/{id}/documentation\n"
        "- POST /api/features/{id}/documentation/generate\n\n"
        "**Priority**: HIGH for multi-tenant deployment, LOW for current single-operator use."
    ),
    "type": "FEATURE",
    "priority": "MEDIUM",
    "reporter": "AI",
    "labels": "auth,security-debt,deferred-from-CB-2117",
})
print(f"  Filed: {followup.get('key')} — {followup.get('title')[:80]}")

print("\n=== DONE ===")
