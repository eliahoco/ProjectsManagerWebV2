#!/usr/bin/env python3
"""
Restructure CB-1955 regression follow-ups per Eli's 2026-05-05 directive:

  Regressions live as TOP-LEVEL BUGs (no FEATURE/EPIC/STORY parent),
  with TASK children for the fix work, and non-hierarchical typed
  IssueLinks (RELATES_TO / CAUSED_BY) back to the originating feature
  + the introducing implementation.

  Eats the dogfood of CB-1955 — uses the IssueLink + relations API
  shipped today to express the bug↔feature relationship without
  polluting the parent-child tree.

Concrete operations:
  1. Set parentId=null on CB-2363, CB-2364, CB-2365 (currently still
     under CB-2027 from a prior cleanup — promote to top-level).
  2. Re-parent CB-2366 (the fix-TASK) under CB-2363 (the bug it fixes).
  3. File 2 new fix-TASKs:
       - under CB-2364 — add extra="forbid" + audit other schemas
       - under CB-2365 — implement /api/system/rag/status or remove poller
  4. Create IssueLinks:
       - CB-2363 CAUSED_BY  CB-2018
       - CB-2363 RELATES_TO CB-1955
       - CB-2364 RELATES_TO CB-1955
       (CB-2365 has no link — pre-existing, not a CB-1955 regression)
  5. CB-2367 / CB-2368 stay standalone (dev tooling, not regressions).
  6. CB-2027 + CB-1955 stay at CWQ — once the regressions are no
     longer under EPIC 7, the cascade gate is intact.

Idempotent — safe to re-run.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8401/api"
PMV2_PROJECT_ID = "1511e54f71dccd3fa79f67fe"
LABEL = "cb-1955-regression-postmortem"


def http(method: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None


def fetch_all_issues() -> dict:
    items = []
    page = 1
    while True:
        d = json.load(urllib.request.urlopen(
            f"{BASE}/projects/{PMV2_PROJECT_ID}/issues?page={page}&pageSize=200"
        ))
        items.extend(d["items"])
        if page >= d["totalPages"]:
            break
        page += 1
    return {i["key"]: i for i in items}


by_key = fetch_all_issues()


def patch_issue(key: str, payload: dict) -> int:
    iid = by_key[key]["id"]
    s, _ = http("PATCH", f"/issues/{iid}", payload)
    return s


def create_link(from_key: str, to_key: str, link_type: str) -> tuple[int, dict | None]:
    """Idempotent — backend returns 409 ALREADY_EXISTS on duplicate, which we treat as success."""
    from_id = by_key[from_key]["id"]
    to_id = by_key[to_key]["id"]
    s, body = http(
        "POST",
        f"/issues/{from_id}/relations",
        {"toIssueId": to_id, "linkType": link_type},
    )
    return s, body


def create_task(*, parent_key: str, title: str, description: str,
                priority: str = "MEDIUM", extra_labels: str = "") -> dict:
    parent_id = by_key[parent_key]["id"]
    payload = {
        "type": "TASK",
        "title": title,
        "description": description,
        "priority": priority,
        "reporter": "AI",
        "labels": LABEL + (f",{extra_labels}" if extra_labels else ""),
        "status": "BACKLOG",
        "parentId": parent_id,
    }
    s, body = http("POST", f"/projects/{PMV2_PROJECT_ID}/issues", payload)
    if s not in (200, 201):
        print(f"  FAIL create TASK under {parent_key}: HTTP {s}", file=sys.stderr)
        sys.exit(2)
    return body


# ============================================================
# Step 1 — Promote regression BUGs to top-level
# ============================================================
print("Step 1: promote regression BUGs to top-level (parentId=null)")
for k in ["CB-2363", "CB-2364", "CB-2365"]:
    s = patch_issue(k, {"parentId": None})
    print(f"  {k} parentId → null: HTTP {s}")
print()


# ============================================================
# Step 2 — Re-parent the existing fix-TASK under its bug
# ============================================================
print("Step 2: re-parent CB-2366 (fix) under CB-2363 (bug)")
s = patch_issue("CB-2366", {"parentId": by_key["CB-2363"]["id"]})
print(f"  CB-2366 → parent=CB-2363: HTTP {s}")
print()


# ============================================================
# Step 3 — File new fix-TASKs under CB-2364 and CB-2365
# ============================================================
print("Step 3: file new fix-TASKs under CB-2364 and CB-2365")

t_2364_fix = create_task(
    parent_key="CB-2364",
    priority="MEDIUM",
    extra_labels="backend,schema,security-hardening",
    title='Add extra="forbid" to IssueGroupCreate + audit other input schemas',
    description="""## Scope (fix-task for CB-2364)

Parent BUG CB-2364 documented the silent-field-drop class issue (`memberIssueIds` was sent, backend wanted `issueIds`, schema lacked `extra="forbid"` so the field was discarded with no error).

## What to do

1. Add `model_config = ConfigDict(extra="forbid")` to `IssueGroupCreate` in `backend/models/schemas.py`.
2. Sweep all other request-input schemas in the same file (every `*Create` / `*Update` / `*Add` / `*Remove`) and add the same hardening where missing.
3. Add a regression test under `backend/tests/`: send a request with an unknown field, expect `422 VALIDATION_ERROR`.
4. Verify all existing tests still pass.

## Files

- `backend/models/schemas.py`
- `backend/tests/test_schema_extra_forbid.py` (NEW)

## Acceptance

- POST `/api/projects/{id}/groups` with `{"title":"x","memberIssueIds":["a"]}` returns `422 VALIDATION_ERROR` (not `201`).
- Existing tests stay green.
- Audit complete: every input schema in `schemas.py` either has `extra="forbid"` or a comment justifying its absence.""",
)
print(f"  CREATED {t_2364_fix['key']} under CB-2364 — schema hardening")

t_2365_fix = create_task(
    parent_key="CB-2365",
    priority="LOW",
    extra_labels="frontend,console-noise,backend",
    title="Implement /api/system/rag/status OR remove RagStatusCard poller",
    description="""## Scope (fix-task for CB-2365)

Parent BUG CB-2365 documented the RagStatusCard 404 flood (5+ console errors per page mount).

## Decision needed

Two paths:
- (a) **Implement** `/api/system/rag/status` on the backend — return RAG service health (presumably the original intent).
- (b) **Remove** the `RagStatusCard` polling — if RAG status surfacing is no longer planned.

Eli to decide. Once decided, this task is the implementation.

## Files (path-a)

- `backend/api/system.py` — add the route
- Possibly `backend/services/rag_service.py` — expose health check

## Files (path-b)

- `frontend/components/RagStatusCard.tsx` — remove or stub
- Wherever it's mounted in the layout

## Acceptance

- Page mount produces zero `[RagStatusCard]` errors in browser console.
- Network tab does not show repeated 404s on `/api/system/rag/status`.""",
)
print(f"  CREATED {t_2365_fix['key']} under CB-2365 — RagStatusCard fix")
print()


# ============================================================
# Step 4 — Create IssueLinks (eat-our-own-dogfood for CB-1955)
# ============================================================
print("Step 4: create IssueLinks (uses CB-1955 relations API — dogfood)")

# CB-2363 was caused by CB-2018 (the SCard wrapper commit lived in the CB-2018 implementation)
s, body = create_link("CB-2363", "CB-2018", "CAUSED_BY")
if s == 201:
    print(f"  CB-2363 CAUSED_BY CB-2018: created")
elif s == 409:
    print(f"  CB-2363 CAUSED_BY CB-2018: already exists (idempotent skip)")
else:
    print(f"  CB-2363 CAUSED_BY CB-2018: HTTP {s} — {body}")

# CB-2363 also relates to the parent feature CB-1955
s, body = create_link("CB-2363", "CB-1955", "RELATES_TO")
if s == 201:
    print(f"  CB-2363 RELATES_TO CB-1955: created")
elif s == 409:
    print(f"  CB-2363 RELATES_TO CB-1955: already exists (idempotent skip)")
else:
    print(f"  CB-2363 RELATES_TO CB-1955: HTTP {s} — {body}")

# CB-2364 relates to CB-1955 (surfaced during its implementation; the schema gap is broader)
s, body = create_link("CB-2364", "CB-1955", "RELATES_TO")
if s == 201:
    print(f"  CB-2364 RELATES_TO CB-1955: created")
elif s == 409:
    print(f"  CB-2364 RELATES_TO CB-1955: already exists (idempotent skip)")
else:
    print(f"  CB-2364 RELATES_TO CB-1955: HTTP {s} — {body}")

# CB-2365 is pre-existing (RagStatusCard predates CB-1955 — no link)
print(f"  CB-2365 — no link (pre-existing, not a CB-1955 regression)")

print()
print("=" * 60)
print("Restructure complete. Final shape:")
print()
print("  BUG  CB-2363 (top-level) — SCard wrapper regression")
print(f"  └── TASK CB-2366 — re-implement kanban multi-select via Context")
print(f"      ╞═ CAUSED_BY → CB-2018")
print(f"      ╞═ RELATES_TO → CB-1955")
print()
print("  BUG  CB-2364 (top-level) — IssueGroupCreate missing extra=forbid")
print(f"  └── TASK {t_2364_fix['key']} — add extra=forbid + audit input schemas")
print(f"      ╞═ RELATES_TO → CB-1955")
print()
print("  BUG  CB-2365 (top-level) — RagStatusCard 404 flood")
print(f"  └── TASK {t_2365_fix['key']} — implement endpoint or remove poller")
print(f"      (no link — pre-existing, not a regression)")
print()
print("  TASK CB-2367 (standalone) — Playwright networkidle fix")
print("  TASK CB-2368 (standalone) — SSE endpoints investigation")
print()
print("  CB-2027 EPIC 7 + CB-1955 FEATURE stay clean at CWQ.")
print("=" * 60)
