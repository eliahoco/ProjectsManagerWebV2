"""File audit findings as BUG tickets under FEATURE CB-2038. Mark audit tasks COMPLETED_WAITING_QA."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, List

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
LABEL = "documentation-surface"

FEATURE = "94aff46e-715b-49cf-8f69-7112be5bd211"  # CB-2038
# Audit tasks that ran:
T_CODE_REVIEW = None  # CB-2102 — fetch id at runtime
T_SEC_AUDIT = None    # CB-2103 — fetch id at runtime


def _request(method: str, path: str, payload: Optional[Dict[str, Any]] = None,
             retries: int = 3) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            f"{BASE}{path}", data=data,
            headers={"Content-Type": "application/json"}, method=method,
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
            print(f"  [retry {attempt}/{retries}] {method} {path}: {e}")
            time.sleep(1.0 * attempt)
    raise RuntimeError(f"Retries exhausted: {last_err}")


def find_id_by_key(key: str) -> str:
    """Resolve issue UUID by CB-key via project listing (filtered)."""
    data = _request("GET", f"/projects/{PROJECT_ID}/issues?labels={LABEL}&limit=200")
    items = data if isinstance(data, list) else data.get("issues") or data.get("items") or data.get("data")
    for i in items:
        if isinstance(i, dict) and i.get("key") == key:
            return i["id"]
    raise RuntimeError(f"Could not resolve {key}")


def create_bug(title: str, description: str, priority: str,
               assignee: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        "title": title,
        "description": description,
        "type": "BUG",
        "priority": priority,
        "reporter": "AI",
        "labels": f"{LABEL},audit-finding",
        "parentId": FEATURE,
    }
    if assignee:
        payload["assignee"] = assignee
    result = _request("POST", f"/projects/{PROJECT_ID}/issues", payload)
    print(f"  [{result.get('key')}] BUG-{priority:8s} {title[:80]}")
    return result


def patch(issue_id: str, payload: Dict[str, Any]) -> None:
    _request("PATCH", f"/issues/{issue_id}", payload)


print("=== Resolving audit task ids ===")
T_CODE_REVIEW = find_id_by_key("CB-2102")
T_SEC_AUDIT = find_id_by_key("CB-2103")
print(f"  T4.1.1 (CB-2102) = {T_CODE_REVIEW}")
print(f"  T4.1.2 (CB-2103) = {T_SEC_AUDIT}")

print("\n=== Filing CRITICAL/HIGH findings as BUGs ===")

create_bug(
    "F1 [CRITICAL]: Completion loop atomicity — batch failure loses ExecutionSummaries + status updates",
    """**File**: `backend/app/main.py:122-134` (process_pending_completions)

**Issue**: `process_pending_completions` iterates all `pending_session_ids` inside ONE `AsyncSessionLocal()` and calls `db.commit()` only once at the end. If any iteration raises uncaught exception (flush IntegrityError, transient driver error), the outer `except Exception` skips commit — but `terminal_service.check_pending_completion()` already POPPED the pending flag (terminal_service.py:888) and `consume_pending_doc_job()` POPPED the doc-job (terminal_service.py:903). Net: those sessions' status updates and ExecutionSummary rows are lost AND will never be retried. Doc-jobs are unrecoverable (in-memory only).

**Reproduction**:
1. 3 AI executions complete in same 2-second loop tick
2. Session 2's flush raises IntegrityError (e.g., race on Issue.implementationSummary)
3. Outer except catches, skips commit
4. Sessions 1, 2, 3 ALL lose status update + summary + doc-job — never retried

**Fix**: Either (a) wrap each `_process_completion_for_session` in its own transaction (begin/commit/rollback per session) or (b) re-enqueue pending flags + doc-jobs on outer-except instead of just logging. Preferred: (a).

**Severity**: CRITICAL — silent data loss.

Source: code-reviewer audit CB-2102.""",
    "CRITICAL",
    assignee="python-pro",
)

create_bug(
    "F2 [HIGH]: No authz / rate-limit on /api/issues/{id}/documentation/* + /api/features/{id}/documentation/*",
    """**File**: `backend/api/documentation.py` (entire router)

**Issue**: `_ensure_issue_exists` and `_load_feature_issue` query only by `Issue.id` with no `projectId` constraint and no caller scoping. There is NO auth layer in the backend (`validate_origin` is CSRF defense, not authz). Any caller reachable on port 8401 can:
- POST /issues/{id}/documentation/notes → write 100 KB content per request, fill SQLite rapidly
- POST /features/{id}/documentation/generate → trigger AI call (most expensive endpoint), walk descendant tree (capped 5000)
- DELETE /issues/{id}/documentation/notes/{note_id} → silent deletion if note_id known/guessed

**Severity**: HIGH for multi-tenant, MEDIUM in current single-operator deployment. Existing comment in `models/schemas.py:589-591` already acknowledges "endpoint is unauthenticated".

**Fix options**:
1. Accept residual risk (single-operator) → document in comment, no code change
2. Add `projectId` scope to all `_ensure_*` lookups (cheap, doesn't add auth but reduces blast radius)
3. Full auth layer (out of scope of this feature, file separately)

**Recommendation**: Option 2 minimum — adds project-scoping which prevents cross-project IDOR even without user auth.

Source: code-reviewer (H1) + security-auditor (H-1).""",
    "HIGH",
    assignee="python-pro",
)

create_bug(
    "F3 [HIGH]: ImplementationNote.tags/references accept any JSON-array of strings, no per-item cap or URL validation",
    """**File**: `backend/models/schemas.py:600-613`

**Issue**: Pydantic validator only enforces top-level shape (≤10 KB JSON array of strings). No per-item length cap. The `references` column comment says "JSON array of file paths or URLs" but no URL validation — a `javascript:` URL stored here and later rendered without `defaultUrlTransform` would XSS.

Currently dormant: `ImplementationTab.tsx` does NOT render `tags` or `references`. Next consumer that renders these without `urlTransform` will be vulnerable.

**Fix**:
1. Add per-item length cap (e.g., 1000 chars per tag, 2000 per reference)
2. Add URL-shape validator to `references` (allow http://, https://, relative paths, reject javascript:/vbscript:/data:)
3. Document the contract on the column

Source: code-reviewer (H2).""",
    "HIGH",
    assignee="python-pro",
)

create_bug(
    "F4 [HIGH]: _capture_git_changes doesn't call validate_project_path — arbitrary-dir git execution",
    """**File**: `backend/services/documentation_generator.py:209-272`

**Issue**: `_capture_git_changes` consumes `project_path` from `TerminalSession.project_path` or doc-job snapshot, runs `os.path.realpath` + `os.path.isdir(.git)` checks, then runs git commands. There is NO allow-list check. The comment at lines 213-217 explicitly defers to "whatever wrote the Project record".

`terminal_service.validate_project_path` (lines 38-83) DOES block `/etc`, `/root`, `~/.ssh` etc. — but only at execution start. Doc generator does NOT call it.

**Risk**: If a Project record has malicious `path=/Users/eli/.ssh` (or any sensitive git repo), doc generator will:
- run `git diff HEAD` there
- include up to 6 KB raw diff body in AI prompt
- ship to external LLM (Anthropic/Ollama)
- persist portion to ExecutionSummary.summary, displayed to anyone viewing issue

**Fix**: Import `validate_project_path` from `terminal_service` and call at top of `_capture_git_changes`. Reject sensitive directories at doc-gen time, not just at exec start.

**Severity**: HIGH multi-tenant, MEDIUM single-operator.

Source: code-reviewer (H4) + security-auditor (H-2).""",
    "HIGH",
    assignee="python-pro",
)

create_bug(
    "F5 [HIGH]: _run_git_subprocess has no cmd[0] == 'git' shape-check",
    """**File**: `backend/services/documentation_generator.py:701-709`

**Issue**: `_run_git_subprocess` calls `subprocess.run(cmd, ...)` with `shell=False` and a list argv (safe today). All current call sites pass `["git", ...]`. But the function has no shape-check — a future caller passing a single string or different binary would silently work.

Defense-in-depth gap. Not exploitable today.

**Fix**: Add at function entry:
```python
if not isinstance(cmd, list) or not cmd or cmd[0] != "git":
    raise ValueError(f"_run_git_subprocess requires list argv starting with 'git', got: {cmd!r}")
```

Source: code-reviewer (H3).""",
    "HIGH",
    assignee="python-pro",
)

print("\n=== Marking audit tasks COMPLETED_WAITING_QA ===")
patch(T_CODE_REVIEW, {"status": "COMPLETED_WAITING_QA"})
print(f"  CB-2102 (T4.1.1 code-reviewer) → COMPLETED_WAITING_QA")
patch(T_SEC_AUDIT, {"status": "COMPLETED_WAITING_QA"})
print(f"  CB-2103 (T4.1.2 security-auditor) → COMPLETED_WAITING_QA")

print("\n=== DONE ===")
