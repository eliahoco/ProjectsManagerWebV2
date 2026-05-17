"""CB-2730 close-out — flip to COMPLETED_WAITING_QA + post evidence comment.

CB-2730: [CB-2377 follow-up] Audit + tz-aware sweep of remaining
datetime.utcnow() callers in documentation pipeline.

Per Rule 29 — per-project per-session script path. Do NOT move to /tmp/.
"""

import json
import sys
import urllib.error
import urllib.request

API = "http://localhost:8401/api"
ISSUE_ID = "d3e23026-0c0a-4464-bead-444ea88e3181"  # CB-2730

EVIDENCE = """**Implementation complete (CB-2377 pattern, doc-pipeline sweep)**

**Backend changes**
- `backend/models/documentation.py` — `_utc_now()` → `datetime.now(timezone.utc)` (added `timezone` to import). Used as SQLAlchemy default/onupdate for `ImplementationNote`, `ExecutionSummary`, `FeatureDocumentation` createdAt/updatedAt.
- `backend/models/doc_settings.py` — same conversion for `DocSettings` createdAt/updatedAt.
- `backend/services/documentation_generator.py:515` — fallback `executed_at` uses `datetime.now(timezone.utc)` (terminal_service still naive — explicitly out of scope per ticket).
- `backend/services/doc_settings_service.py` — `cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=...)`. The explicit tzinfo strip is **load-bearing**: `executedAt` is a naive `DateTime` column and SQLite TEXT comparison is shape-sensitive (`'…00'` vs `'…00+00:00'` lex-sort differently). Confirmed in code-review I3.
- `backend/models/schemas.py` — `field_serializer(..., when_used="json")` calling existing `_isoformat_utc_z` added to:
  - `ExecutionSummaryResponse` (`executedAt`, `createdAt`, `updatedAt`) — inherited by `ExecutionSummaryWithKeyResponse` (CB-2087 cross-project endpoint).
  - `ImplementationNoteResponse` (`createdAt`, `updatedAt`).
  - `DocSettingsResponse` (`createdAt`, `updatedAt`).

**Frontend changes**
- `frontend/lib/utils.ts` — promoted `_toUtcIso(iso)` from `FeatureDocumentationView.tsx` to the shared util module (single source of truth).
- `frontend/components/codeboard/FeatureDocumentationView.tsx` — replaced inline def with `import { _toUtcIso } from '@/lib/utils'` + named re-export so the CB-2377 test contract (`import { _toUtcIso } from '.../FeatureDocumentationView'`) stays green without churn.
- `frontend/app/settings/documentation/page.tsx` — `formatDate(iso)` now wraps with `_toUtcIso`. Exported for direct Vitest coverage.
- `frontend/components/codeboard/ImplementationTab.tsx` — `formatTimestamp(iso)` now wraps with `_toUtcIso`. Exported for direct Vitest coverage.

**Tests**
- `frontend/tests/lib/utils.test.ts` — 7 new direct `_toUtcIso` assertions (canonical contract; TZ-independent).
- `frontend/tests/components/DocumentationTimestampsTzGuard.test.tsx` — 6 new TZ-independent assertions: naive ISO and Z-suffixed ISO produce identical output via `formatDate` + `formatTimestamp`. Also covers `+HH:MM` offset and invalid-ISO branches.

**Audit gates passed**
- code-reviewer: **no CRITICAL/HIGH/MEDIUM**. 2 LOW (informational): the `_utc_now` belt-and-suspenders Python+SQL default pattern is preserved (Python wins on ORM inserts; `server_default` only fires on raw SQL/Prisma); the `field_serializer` on `Response` is correctly inherited by `ExecutionSummaryWithKeyResponse` per Pydantic v2 MRO. All 5 design questions confirmed favorably (serializer inheritance, SQLite bind processor strips tzinfo cleanly, `.replace(tzinfo=None)` is load-bearing, no missed response models, re-export is the right call).
- security-auditor: **no findings**. ReDoS analysis on `/Z|[+-]\\d{2}:?\\d{2}$/` — bounded quantifiers, end-anchored, O(n). No new injection / auth / authz / IDOR / XSS surface. Pydantic `_isoformat_utc_z` short-circuits `None`, only assigns UTC tzinfo to naive (matches documented backend convention), `when_used="json"` confines change to HTTP responses. All OWASP Top 10 categories N/A.
- Backend pytest: **81/81** in `tests/test_documentation_api.py` + `tests/test_doc_settings.py`.
- Vitest: **61/61** across `tests/lib/utils.test.ts` (35) + `tests/components/FeatureDocumentationView.test.tsx` (19) + `tests/components/DocumentationSettingsRerun.test.tsx` (1) + `tests/components/DocumentationTimestampsTzGuard.test.tsx` (6).
- Diff stats: 10 files, +222 / −30.

**Smoke-test deferred (backend restart required)**
The running uvicorn at port 8401 was launched without `--reload`. Confirmed pre-restart that `/api/documentation/settings` and `/api/documentation/summaries` still return naive ISO (no `Z`) — the new serializer code is on disk but not loaded. Eli to restart the backend (or it will pick up on next `launch.sh` cycle), then verify:

```bash
curl -sS http://localhost:8401/api/documentation/settings | jq .createdAt   # expect "...Z"
curl -sS 'http://localhost:8401/api/documentation/summaries?limit=1' | jq '.[0] | {executedAt, createdAt, updatedAt}'
# All three expected to end in "Z".
```

CB-2377 followed the same restart-after-merge cadence and verified live `Z`-suffix successfully — same fix shape applies here.

**Acceptance traced**
- ✅ Grep all `datetime.utcnow()` callers under `backend/services/` + `backend/models/` whose values reach a frontend response — 4 sites converted (documentation.py, doc_settings.py, documentation_generator.py:515, doc_settings_service.py:80).
- ✅ Pydantic `field_serializer` with `_isoformat_utc_z` on every doc-pipeline response model exposing a derived datetime — `ExecutionSummaryResponse`, `ExecutionSummaryWithKeyResponse` (inherits), `ImplementationNoteResponse`, `DocSettingsResponse`. (`FeatureDocumentationResponse` already covered by CB-2377.)
- ✅ Vitest cases for the affected formatters mirror the CB-2377 pattern (helper-level + per-component formatter assertions).
- ⏸ Live `curl | jq` smoke-test pending backend restart (see above).

**Out of scope (per ticket)**
- Migrating SQLAlchemy `DateTime` → `DateTime(timezone=True)` (Prisma-owned schema, requires Prisma migration first).
- Sweep of `datetime.utcnow()` outside the documentation pipeline (would file a separate epic). Audit found callers in `commit_link_service.py`, `autopilot_queue_service.py`, `terminal_service.py`, etc — not a CB-2730 deliverable.

Status: COMPLETED_WAITING_QA. Eli to (1) restart backend, (2) run the curl smoke-tests above, (3) Chrome-QA the docs settings page + ImplementationTab in Asia/Jerusalem to confirm no off-by-3h drift, (4) promote to DONE.
"""


def post_comment() -> str:
    body = json.dumps({"content": EVIDENCE, "author": "Jonny"}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/issues/{ISSUE_ID}/comments",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read())
    return d.get("id") or ""


def patch_status() -> str:
    body = json.dumps({"status": "COMPLETED_WAITING_QA"}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/issues/{ISSUE_ID}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read())
    return d.get("status") or ""


def main() -> int:
    try:
        cid = post_comment()
        print(f"Comment posted (id={cid})")
        st = patch_status()
        print(f"CB-2730 status -> {st}")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
