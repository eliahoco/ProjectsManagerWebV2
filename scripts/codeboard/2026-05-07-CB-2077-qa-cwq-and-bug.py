"""
CB-2077 (E2-6: last-indexed timestamp updates after regenerate) QA wrap-up.

What this script does (idempotent, single-run):

1. File a companion BUG: FeatureDocumentation lastIndexedAt rendered ~3h
   off because backend emits a naive UTC ISO without `Z` suffix and JS
   `new Date(iso)` parses missing-tz as local time. Bug is parented under
   STORY CB-2067 (E2 audit + regression + Chrome QA) so the audit trail
   stays in the same epic.

2. Append a QA-evidence comment to CB-2077 with the before/after
   timestamps, the screenshot path, the QA report path, and the link to
   the new BUG.

3. Mark CB-2077 -> COMPLETED_WAITING_QA. Bible Rule 22: only Eli
   promotes to DONE.

Per Bible Rule 23/28: bug FOUND during QA -> file ticket FIRST, do not
write the fix in the same session. The fix lives in a future ticket.

Per Bible Rule 29: per-project per-session script path under
<project>/scripts/codeboard/<YYYY-MM-DD>-<key>-<slug>.py.
"""

import json
import urllib.request
import urllib.error

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"

CB_2077_ID = "1496cbb3-c7da-44ba-a2fa-992592b713aa"
CB_2067_ID = "85fb17a4-773b-414b-8498-ec1aef083f5c"  # parent STORY (E2 audit)

LABEL = "cb-2077-qa"


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def patch(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ---------- 1. File the companion BUG ----------

bug_body = {
    "title": "[CB-2077 F-1] MEDIUM: FeatureDocumentation lastIndexedAt renders 'Xh ago' off by browser TZ offset (naive UTC ISO from backend)",
    "type": "BUG",
    "priority": "MEDIUM",
    "parentId": CB_2067_ID,
    "labels": LABEL,
    "assignee": "python-pro",
    "reporter": "AI",
    "description": """**Severity:** MEDIUM. The visible relative-time on the Documentation tab is wrong by exactly the user's UTC offset for every freshly-indexed FeatureDocumentation row. In Asia/Jerusalem (UTC+3 IDT) a regenerate that just finished renders as `3h ago`. Misleading UX; users will think the indexer is stale or broken. Acceptance for CB-2077 itself still passes because the underlying `datetime` attribute on `<time>` is correct and the DB row's `lastIndexedAt` does advance — but the human-readable string is wrong.

**Found during:** Manual QA of CB-2077 (E2-6: timestamp updates after regenerate). See `docs/research/cb-2077-qa-report.md` for full procedure + evidence.

**Reproduction**

1. Browser TZ != UTC (Eli's machine is `Asia/Jerusalem`).
2. Open any FEATURE issue with an existing FeatureDocumentation row.
3. Click Regenerate. Wait for response.
4. Observe: `Indexed Xh ago` and `Last updated Xh ago` where X = absolute value of the local UTC offset (3 in IDT, 2 in IST). Expected: `just now` / `<1m ago`.

**Root cause**

`backend/services/documentation_generator.py:1725`:
```py
row.lastIndexedAt = datetime.utcnow()
```

`datetime.utcnow()` returns a *naive* datetime. SQLAlchemy stores it; Pydantic serializes it as ISO 8601 **without** a `Z` suffix (e.g. `2026-05-06T22:46:59.675402`).

`frontend/components/codeboard/FeatureDocumentationView.tsx:66-86` (`formatIndexedAt`):
```ts
const then = new Date(iso).getTime();
```

Per ECMA-262 §21.4.3.2: an ISO string with no time-zone designator is interpreted as **local** time. With browser TZ = UTC+3, the string `22:46:59` parses to 19:46:59 UTC. Compared against `Date.now()` (true UTC), the diff is the browser's offset → 3 hours.

Verified live in the running browser via `page.evaluate`:
```
iso          = "2026-05-06T22:46:59.675402"
parsed_utc   = "2026-05-06T19:46:59.675Z"   <- shifted by -3h
now_utc      = "2026-05-06T22:48:17.106Z"
diff_sec     = 10877   (== 3h2m)
tz           = "Asia/Jerusalem"   tz_offset_min = -180
```

The `<time datetime="...">` attribute itself carries the correct ISO string, so machine-readable consumers (screen readers, copy-paste) get the right value. Only the human-readable relative text is wrong.

**Fix candidates**

**Option A (preferred — backend correctness):** make all server-emitted timestamps tz-aware UTC so JSON output gets the `Z` suffix.
- `documentation_generator.py:1725` -> `datetime.now(timezone.utc)`.
- Audit other `datetime.utcnow()` callers in the documentation pipeline (and elsewhere that gets serialized to the frontend) for the same bug; sweep with grep.
- Verify SQLAlchemy column type / Pydantic model output emits the `Z` suffix.

**Option B (frontend defensive):** in `formatIndexedAt`, treat a missing tz designator as UTC by appending `Z` before constructing `Date`. One-line guard. Useful as defense-in-depth even after Option A lands.

**Option C (both):** Option A primary, Option B as belt-and-suspenders so future regressions on the backend don't silently re-introduce the same bug.

**Acceptance**

- Regenerate from Asia/Jerusalem browser → `Indexed just now` (within 60 s of the regenerate response).
- 5 minutes later → `Indexed 5m ago`.
- Test must run with browser TZ explicitly set to a non-UTC zone (Playwright `tz_id` option) so the bug cannot hide behind a UTC-only test environment.
- Add a Vitest case in `frontend/tests/components/FeatureDocumentationView.test.tsx` that mocks `Date.now()`, passes a no-tz ISO, and asserts `just now` (not `Xh ago`) — this would have caught the bug.

**Out of scope**

A full sweep of every `datetime.utcnow()` in the backend is out of scope for this ticket — file follow-ups if the audit reveals other surfaces (ExecutionSummary, ImplementationNote may have the same shape).
""",
}


def main() -> None:
    # 1. File the bug
    try:
        bug = post(f"/projects/{PROJECT_ID}/issues", bug_body)
    except urllib.error.HTTPError as exc:
        print(f"FAILED to file bug: {exc} {exc.read()!r}")
        raise
    bug_key = bug.get("key")
    bug_id = bug.get("id")
    print(f"filed companion bug: {bug_key} (id {bug_id})")

    # 2. Append QA-evidence comment to CB-2077
    comment_body = (
        "## QA — CB-2077 (E2-6) — VERDICT: PASS (data layer)\n\n"
        "**Procedure:** GET doc -> POST /generate -> GET doc.\n\n"
        "**Before:** `lastIndexedAt = 2026-05-06T22:14:06.024676`\n"
        "**After:**  `lastIndexedAt = 2026-05-06T22:46:59.675402`  (delta ~33 min, NEWER)\n\n"
        "`embeddingId` unchanged (`f6e011d460598184e3d8951747516f13`) -> deterministic id, "
        "upsert path, no Chroma duplicate (corroborates sibling CB-2075).\n\n"
        f"**UI bug found** (does not invalidate this acceptance): UI relative-time renders "
        f"`3h ago` instead of `just now` on Asia/Jerusalem browser, because backend emits a "
        f"naive UTC ISO with no `Z` suffix and JS parses it as local time. Filed as **{bug_key}** "
        f"under STORY CB-2067. The `datetime` attribute on the `<time>` element is correct, so "
        f"only the human-readable text is wrong.\n\n"
        "**Evidence:**\n"
        "- Full QA report: `docs/research/cb-2077-qa-report.md`\n"
        "- Screenshot: `docs/research/cb-2077-doc-page-after-regenerate.png`\n\n"
        "Marking COMPLETED_WAITING_QA. Bible Rule 22: only Eli promotes to DONE."
    )
    try:
        post(
            f"/issues/{CB_2077_ID}/comments",
            {"content": comment_body, "author": "Jonny"},
        )
        print("QA comment appended to CB-2077")
    except urllib.error.HTTPError as exc:
        print(f"FAILED to add comment: {exc} {exc.read()!r}")
        raise

    # 3. Mark CB-2077 COMPLETED_WAITING_QA
    patch(f"/issues/{CB_2077_ID}", {"status": "COMPLETED_WAITING_QA"})
    print("CB-2077 -> COMPLETED_WAITING_QA")


if __name__ == "__main__":
    main()
