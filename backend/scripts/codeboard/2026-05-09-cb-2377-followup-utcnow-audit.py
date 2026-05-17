"""CB-2377 follow-up — file the wider `datetime.utcnow()` audit ticket.

Out of scope for CB-2377 (per ticket text): a full sweep of every
`datetime.utcnow()` call in the backend that gets serialized to the frontend.
At minimum two surfaces are suspected to have the same naive-ISO bug as
FeatureDocumentation.lastIndexedAt did:

  - ExecutionSummary.* (documentation_generator.py:515 still uses utcnow)
  - ImplementationNote.* (Prisma-owned columns, naive DateTime, same column
    type as FeatureDocumentation; createdAt/updatedAt populated by the same
    `_utc_now` helper in models/documentation.py)

Frontend `formatIndexedAt` already has the Z guard from CB-2377, so any
caller piping through it is safe — but other surfaces that build their own
`new Date(iso)` paths (ImplementationNote panel, ExecutionSummary timeline)
will reproduce the bug verbatim.

Push as a TASK under STORY CB-2067 (same parent as CB-2377) so the audit
sits in the same E2 audit story that surfaced the original bug.
"""

import json
import sys
import urllib.error
import urllib.request

API = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"  # ProjectsManagerWebV2
PARENT_STORY_ID = "85fb17a4-773b-414b-8498-ec1aef083f5c"  # CB-2067 (S2.4)


PAYLOAD = {
    "title": (
        "[CB-2377 follow-up] Audit + tz-aware sweep of remaining "
        "datetime.utcnow() callers in documentation pipeline"
    ),
    "description": """**Source**: CB-2377 (FeatureDocumentation lastIndexedAt TZ bug).

CB-2377 fixed *one* surface — `FeatureDocumentation.lastIndexedAt` — by
combining (a) tz-aware UTC at write, (b) Pydantic `field_serializer` that
emits `Z` suffix, and (c) frontend `_toUtcIso` defense-in-depth guard.

The same naive-ISO bug pattern is *suspected* on two other surfaces in the
documentation pipeline that were explicitly out-of-scope for CB-2377:

1. **ExecutionSummary timestamps**
   - `backend/services/documentation_generator.py:515` still calls
     `datetime.utcnow()` for `executed_at`.
   - `ExecutionSummary.executedAt`, `createdAt`, `updatedAt` columns are
     naive `DateTime` (Prisma-owned schema, SQLite).
   - `ExecutionSummaryResponse` has no `Z`-emitting serializer.
   - Any frontend surface that builds `new Date(iso)` directly off these
     fields will under-/over-shoot by the browser TZ offset.

2. **ImplementationNote timestamps**
   - `models/documentation.py` defines `_utc_now()` returning naive
     `datetime.utcnow()`.
   - `createdAt` / `updatedAt` columns also naive `DateTime`.
   - Same Prisma-owned schema; same JSON serialization shape.

**Acceptance**

- Grep all `datetime.utcnow()` callers under `backend/services/` and
  `backend/models/` whose values reach a frontend response.
- Convert each call site to `datetime.now(timezone.utc)`.
- Add (or reuse) Pydantic `field_serializer` with `_isoformat_utc_z` from
  `models/schemas.py` on every response model that exposes a datetime
  derived from one of those columns. Specifically:
  - `ExecutionSummaryResponse`
  - `ImplementationNoteResponse`
  - any other response model the audit surfaces.
- Smoke-test each affected response with `curl | jq` and confirm every
  datetime field ends in `Z`.
- Add a Vitest case for any frontend component that renders one of these
  timestamps via `new Date(iso)`, mirroring the CB-2377 pattern.

**Out of scope**

- Migrating the underlying SQLAlchemy column to `DateTime(timezone=True)`
  (Prisma owns the schema; would require a Prisma migration first).
- Sweep of `datetime.utcnow()` outside the documentation pipeline (file a
  separate epic if other surfaces are affected).

**Why MEDIUM not HIGH**: same severity profile as CB-2377 — wrong relative
time string is misleading but the underlying ISO attribute is correct, so
machine-readable consumers (screen readers, copy-paste, analytics) get the
right value. UX-only impact.
""",
    "type": "TASK",
    "priority": "MEDIUM",
    "status": "BACKLOG",
    "reporter": "AI",
    "assignee": "Jonny",
    "labels": "cb-2377-followup",
    "parentId": PARENT_STORY_ID,
}


def main() -> int:
    body = json.dumps(PAYLOAD).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/projects/{PROJECT_ID}/issues",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}")
        return 1
    print(f"Created {payload.get('key')} ({payload.get('id')}) — "
          f"status={payload.get('status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
