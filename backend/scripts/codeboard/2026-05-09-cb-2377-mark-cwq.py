"""CB-2377 close-out — flip to COMPLETED_WAITING_QA + post evidence comment."""

import json
import sys
import urllib.error
import urllib.request

API = "http://localhost:8401/api"
ISSUE_ID = "3f682a54-800f-4337-bd90-f0d0a9acbb4a"  # CB-2377

EVIDENCE = """**Implementation complete (Option C — backend correctness + frontend defense-in-depth)**

**Changes**
- `backend/services/documentation_generator.py:1727` — `datetime.utcnow()` → `datetime.now(timezone.utc)` (added `timezone` to the import).
- `backend/models/schemas.py` — added `_isoformat_utc_z()` helper + `field_serializer("lastIndexedAt", "createdAt", "updatedAt", when_used="json")` on `FeatureDocumentationResponse`. Naive datetimes are now treated as UTC and serialized with the explicit `Z` suffix at the JSON boundary; SQLAlchemy round-trips through naive `DateTime` columns no longer break the wire format.
- `frontend/components/codeboard/FeatureDocumentationView.tsx` — added exported `_toUtcIso()` guard inside `formatIndexedAt`. Treats any ISO with no `Z`/offset designator as UTC. Skips date-only ISOs (`YYYY-MM-DD`) since those are already spec-defined as UTC midnight. Both the relative-time math and the >30-day `toLocaleDateString` fallback go through the guard.
- `frontend/tests/components/FeatureDocumentationView.test.tsx` — 11 new Vitest cases: 4 `formatIndexedAt` cases (mocked `Date.now()`, naive ISO → "just now"/"5m ago", explicit Z, explicit `+03:00`) + 7 direct `_toUtcIso` assertions that pass regardless of the test runner's TZ (covers the security-auditor L1 finding — would have failed in CI even when CI runs in UTC).

**Audit gates passed**
- code-reviewer: no CRITICAL/HIGH; 2 follow-ups applied in same patch (date-only guard + direct `_toUtcIso` assertions). 1 follow-up filed as **CB-2730** (audit `ExecutionSummary` / `ImplementationNote` for the same naive-ISO surface — explicitly out-of-scope here per ticket).
- security-auditor: clean. No CRITICAL/HIGH/MEDIUM. ReDoS analysis: regex `/Z|[+-]\\d{2}:?\\d{2}$/` is end-anchored with bounded quantifiers, O(n) worst case. No new auth/SQL/injection surface.
- Vitest: **19/19 passing** (8 prior `techStack` + 11 new CB-2377).
- Backend: **67/67** in `tests/test_documentation_api.py` passing.
- Live API smoke (after backend restart): `curl /api/features/{CB-2038}/documentation?projectId=...` returns `lastIndexedAt: "2026-05-08T22:29:01.008925Z"` (note `Z`).
- Chrome visual QA in Asia/Jerusalem (`Intl.DateTimeFormat().resolvedOptions().timeZone === "Asia/Jerusalem"`, `getTimezoneOffset() === -180`):
  - Pre-regenerate: stored `2026-05-07T17:35:30.675101Z` → renders `1d ago` (correct).
  - POST `/documentation/generate` → fresh `lastIndexedAt = 2026-05-08T22:29:01.008925Z`.
  - Post-regenerate: both `<time>` elements (Indexing header + bottom "Last updated") render **`just now`** with `title="5/9/2026, 1:29:01 AM"` (correct local IDT representation of the UTC instant).
  - Pre-fix this would have read `3h ago`. Bug fixed end-to-end.
- Screenshot: `docs/research/2026-05-09-cb-2377-just-now-after-fix.png`.

**Acceptance traced**
- ✅ Regenerate from Asia/Jerusalem browser → `Indexed just now` (verified live, within 4s of the regenerate response).
- ✅ Vitest case mocks `Date.now()`, passes a no-tz ISO, asserts `just now` not `Xh ago` — would have caught the original bug.
- ✅ Vitest case at `_toUtcIso` level is TZ-independent — would catch a regression even on a UTC-only CI host.
- ✅ Backend Pydantic JSON output now carries the `Z` suffix on `lastIndexedAt`, `createdAt`, `updatedAt` for `FeatureDocumentationResponse`.

**Out-of-scope follow-up filed:** CB-2730 — sweep remaining `datetime.utcnow()` callers in `ExecutionSummary` (line 515) + `ImplementationNote` for the same shape, with the same Pydantic serializer fix where their response models are exposed.

Status: COMPLETED_WAITING_QA. Eli to QA on his own machine and promote to DONE.
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
        print(f"CB-2377 status -> {st}")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
