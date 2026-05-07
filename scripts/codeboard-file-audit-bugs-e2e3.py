"""File E2+E3 audit MEDIUM findings as BUGs. Close audit tasks."""

from __future__ import annotations
import json, time, urllib.error, urllib.request
from typing import Optional, Dict

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
LABEL = "documentation-surface"
FEATURE = "94aff46e-715b-49cf-8f69-7112be5bd211"
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


def _build_cache():
    if _id_cache:
        return
    items = _request("GET", f"/issues/{FEATURE}/descendants")
    items = items if isinstance(items, list) else items.get("issues") or items.get("items") or items.get("data") or []
    for i in items:
        if isinstance(i, dict) and i.get("key") and i.get("id"):
            _id_cache[i["key"]] = i["id"]


def find_id(key):
    if not _id_cache:
        _build_cache()
    return _id_cache[key]


def patch(key, status, comment=None):
    issue_id = find_id(key)
    if comment:
        _request("POST", f"/issues/{issue_id}/comments", {"content": comment, "author": "AI"})
    _request("PATCH", f"/issues/{issue_id}", {"status": status})
    print(f"  {key} → {status}")


def create_bug(title, description, priority, assignee=None):
    payload = {
        "title": title, "description": description,
        "type": "BUG", "priority": priority, "reporter": "AI",
        "labels": f"{LABEL},audit-finding,e2e3-audit", "parentId": FEATURE,
    }
    if assignee:
        payload["assignee"] = assignee
    result = _request("POST", f"/projects/{PROJECT_ID}/issues", payload)
    print(f"  [{result.get('key')}] BUG-{priority:8s} {title[:80]}")
    return result


print("=== Marking E2+E3 audit tasks COMPLETED_WAITING_QA ===")
patch("CB-2068", "COMPLETED_WAITING_QA", "code-reviewer audit complete on E2 frontend + E3 backend. Findings filed as separate BUGs where applicable.")
patch("CB-2069", "COMPLETED_WAITING_QA", "security-auditor: 0 CRITICAL, 0 HIGH, 2 MEDIUM (DoS-only, filed as BUGs). Markdown sanitization verified (defaultUrlTransform, no rehype-raw, no dangerouslySetInnerHTML). Pydantic bounds confirmed. SQL parameterized. Safe to deploy.")
patch("CB-2090", "COMPLETED_WAITING_QA", "code-reviewer audit on E3 backend complete.")
patch("CB-2091", "COMPLETED_WAITING_QA", "security-auditor: same findings as E2 audit. 0 CRITICAL, 0 HIGH, 2 MEDIUM operational (filed as BUGs). PATCH bounds + parameterized SQL verified.")

print("\n=== Filing MEDIUM findings as BUGs ===")

create_bug(
    "M1 [MEDIUM]: apply_retention notin_(keep_ids) may hit SQLite variable limit on legacy SQLite",
    """**File**: `backend/services/doc_settings_service.py:76-89`

**Issue**: Per-issue retention cap builds `keep_ids` set (up to maxPerIssue=1000 elements) then passes to `delete().where(notin_(keep_ids))`. SQLAlchemy expands to `NOT IN (?, ?, ...)` parameter list. SQLite default `SQLITE_MAX_VARIABLE_NUMBER` is 999 on legacy builds (3.32+ raises to 32766).

**Effect**: With maxPerIssue=1000 on legacy SQLite, DELETE throws `OperationalError: too many SQL variables`. The retention loop's outer except swallows it, so cap silently fails to apply for that issue.

**Fix options**:
1. Chunk the `notin_` set (delete in batches of 500)
2. Invert the predicate: query oldest_keep_executedAt, then `delete().where(executedAt < oldest_keep_executedAt)` — uses 1 parameter instead of N

**Severity**: MEDIUM — DoS-via-disk-exhaustion over time (cap silently fails so old rows accumulate).

Source: security-auditor CB-2091.""",
    "MEDIUM",
    assignee="python-pro",
)

create_bug(
    "M2 [MEDIUM]: apply_retention walks all distinct issueIds in single transaction without batching",
    """**File**: `backend/services/doc_settings_service.py:70-90`

**Issue**: With N issues × 2 queries each, retention pass holds long-running write transaction on SQLite. Whole API blocks during the pass on disk lock.

**Effect**: If issue count grows to 50k, retention freezes backend for the duration. Not exploitable cross-tenant (single-operator) but DoS surface.

**Fix**: Periodic commit-per-batch (e.g., commit every 100 issues) + asyncio.sleep(0) yield to event loop between batches.

**Severity**: MEDIUM — operational DoS at scale only.

Source: security-auditor CB-2091.""",
    "MEDIUM",
    assignee="python-pro",
)

print("\n=== DONE ===")
