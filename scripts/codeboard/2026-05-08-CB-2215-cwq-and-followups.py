"""
CB-2215 (E1 polish bundle F-5..F-9) wrap-up.

1. File LOW follow-up bugs from the code-reviewer + security-auditor pass on
   the CB-2215 diff (the polish-bundle audit). Two items worth tracking:
   - F-6 follow-up: visibility-return doesn't reset setInterval phase
   - F-5 follow-up: OpenAPI breaking change (`host` -> `endpoint`) without
     a back-compat alias / changelog note
   Other LOWs from the review (F-8 branch-keys advisory, F-7 amber-for-
   PERSISTENT future config flag) are advisory-only / future feature work
   and are intentionally not filed.

2. Append audit-summary block to CB-2215 description.

3. Mark CB-2215 -> COMPLETED_WAITING_QA so Eli's manual QA promotes it
   to DONE per Bible Rule 22.

Per Bible Rule 29: per-project per-session script path. Per Bible Rule 22:
never push to DONE from code.
"""

import json
import urllib.request
import urllib.error

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"

CB_2047_ID = "c5f70d1e-9043-417a-b204-f2c653e9d743"  # parent STORY (S1.3)
CB_2215_ID = "b65625e9-fc26-43ba-b486-f230e250ca03"  # this BUG

LABEL = "e1-audit-cb-2215"


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


follow_ups = [
    {
        "title": (
            "[CB-2215 F-6 follow-up] LOW: visibility-return refresh "
            "doesn't reset setInterval phase"
        ),
        "type": "BUG",
        "priority": "LOW",
        "parentId": CB_2047_ID,
        "labels": LABEL,
        "assignee": "react-specialist",
        "reporter": "AI",
        "description": """**Severity:** LOW (over-fetch on every tab return; cosmetic)

**Location:** `frontend/components/service-monitor.tsx` — `RagStatusCard`
useEffect with `visibilitychange` listener (CB-2215 F-6 fix).

**Problem**

CB-2215 added a `visibilitychange` handler that fires an immediate
`fetchStatusRef.current()` when the tab becomes visible again. This is
correct for "card is current the moment user looks at it" but the existing
`setInterval` continues on its original 30 s phase. So if the tab returns
29 s into the cycle, you get an immediate refresh and another fetch 1 s
later — a tiny per-tab over-fetch.

Today the impact is minimal (one extra fetch per visibility return per
tab). But on a heavy multi-tab dev workstation it's avoidable churn, and
it'll matter more once CB-2218 lands the heartbeat / list_collections /
per-collection-count fan-out fix.

**Fix**

Inside `onVisibility`, when becoming visible:

```ts
if (intervalRef.current) clearInterval(intervalRef.current);
fetchStatusRef.current();
intervalRef.current = setInterval(tick, RAG_STATUS_POLL_MS);
```

Requires hoisting `interval` into a ref so it's reachable from the
visibility handler. Alternatively, migrate the card to React Query as
the original F-6 finding suggested — RQ handles this natively.

**Found in:** code-reviewer pass on CB-2215 (F-6 follow-up).
""",
    },
    {
        "title": (
            "[CB-2215 F-5 follow-up] LOW: OpenAPI breaking change `host` -> "
            "`endpoint` without back-compat alias / changelog"
        ),
        "type": "BUG",
        "priority": "LOW",
        "parentId": CB_2047_ID,
        "labels": LABEL,
        "assignee": "api-designer",
        "reporter": "AI",
        "description": """**Severity:** LOW (internal-only API; consumers limited to one frontend)

**Location:** `backend/api/system.py` — `RagStatusResponse.endpoint`
(renamed from `host` per CB-2215 F-5).

**Problem**

CB-2215 (F-5) renamed the Pydantic field `host` -> `endpoint` on the
`/api/system/rag/status` response. The internal frontend was updated in
the same commit, but:

1. The change is published in the OpenAPI spec — any third party (or
   stale browser tab loaded from the old bundle) keying on `host` will
   silently see `undefined`. The client coercer
   (`normalizeRagStatus` in `service-monitor.tsx`) defaults missing
   `endpoint` to `''`, so the failure mode is "endpoint shows blank"
   rather than an exception. Acceptable but worth visibility.

2. No back-compat alias was added (e.g., `host: str = Field(alias=...)`
   or duplicate field on the response).

3. No CHANGELOG entry / migration note was written.

**Fix (pick one)**

A. Add a deprecation-window alias on the response model emitting both
   `host` (deprecated) and `endpoint` for one release, then drop. Most
   conservative; preserves any external consumer.

B. Document the breaking change in `docs/runbooks/` (or whatever the
   project uses for API-change notes) and let it ride. The endpoint is
   internal-only per `system.py:10-17` (loopback bind, no auth, no
   public consumers besides Service Monitor) — the cost of a flag-day
   rename is essentially zero.

Recommend B given the perimeter, but file this so the decision is
deliberate rather than implicit.

**Found in:** code-reviewer pass on CB-2215 (F-5 follow-up).
""",
    },
]


def main() -> None:
    created = []
    for body in follow_ups:
        try:
            resp = post(f"/projects/{PROJECT_ID}/issues", body)
        except urllib.error.HTTPError as exc:
            print(f"FAILED to create '{body['title'][:60]}': {exc} {exc.read()!r}")
            continue
        created.append((resp.get("key"), resp.get("id"), body["priority"]))
        print(f"created {resp.get('key')} ({body['priority']}): {body['title'][:80]}")

    # Append audit summary to CB-2215 description.
    summary_lines = [
        "",
        "---",
        "",
        "## Implementation complete (2026-05-08)",
        "",
        "**All 5 findings fixed in one bundle:**",
        "- F-5: renamed `host` → `endpoint` (Pydantic response, `_mode_detail` → `_endpoint`, payload key, `RagStatusPayload` interface, `normalizeRagStatus`, `endpointDisplay`); added Pydantic `Field(description=...)` documenting dual semantics; updated 4 backend tests + frontend route test + regression probe.",
        "- F-6: Page Visibility API gating in `RagStatusCard` — `setInterval` ticks skip on `document.hidden`; `visibilitychange` listener fires one immediate refresh on tab return; symmetric add/removeEventListener cleanup.",
        "- F-7: PERSISTENT-mode hint softened to *running on local PersistentClient (chromadb container not in use)*.",
        "- F-8: hoisted `<RagStatusCard />` to single fragment-index-0 render in `ServiceMonitor`; alert overlay built into a `let alertOverlay: React.ReactNode` and rendered alongside, so card fiber position is stable across all branches (docker-paused / alerts / quiet).",
        "- F-9: state-edge log gating — WARN once on healthy→unhealthy transition, INFO once on recovery, DEBUG for steady-state. Replaced the originally-planned flat DEBUG downgrade after code-reviewer + security-auditor convergent feedback that flat DEBUG would lose the first-failure / recovery edges.",
        "",
        "**Audit gates passed:**",
        "- code-reviewer: 1 HIGH (straggler `_mode_detail` reference in `scripts/regression/2026-05-02-cb2050-embed-probe.py:24` — fixed in this commit), 1 MEDIUM (flat DEBUG → state-edge — fixed in this commit), 4 LOW (2 filed as follow-ups, 2 advisory-only).",
        "- security-auditor: 0 CRITICAL / HIGH / MEDIUM / LOW. 1 INFO observation about host-log signal during outages was the same MEDIUM both auditors converged on; addressed by state-edge gating.",
        "",
        "**Tests:**",
        "- 24 backend tests pass (was 20; +4 new state-edge log gating tests in `test_rag_service_status_payload.py`).",
        "- 5 frontend route tests pass.",
        "- Full backend suite: 800 pass / 3 pre-existing unrelated failures (`test_qa_sequence`, `test_schema_validation` — schema-drift on AgentProfile + aiContext, untouched by this diff).",
        "",
        "**LOW follow-ups filed under CB-2047:**",
    ]
    for key, _id, sev in created:
        summary_lines.append(f"- {key} [{sev}]")
    summary_lines.append("")
    summary_lines.append(
        "Other LOWs from the review (F-8 branch-keys advisory, F-7 amber-for-PERSISTENT future config flag) are advisory-only / future feature work — intentionally not filed."
    )
    summary_lines.append("")
    summary = "\n".join(summary_lines)

    with urllib.request.urlopen(f"{BASE}/issues/{CB_2215_ID}") as r:
        current = json.loads(r.read())
    new_desc = (current.get("description") or "") + summary
    patch(f"/issues/{CB_2215_ID}", {"description": new_desc})
    print(f"updated CB-2215 description ({len(summary)} chars appended)")

    patch(f"/issues/{CB_2215_ID}", {"status": "COMPLETED_WAITING_QA"})
    print("CB-2215 -> COMPLETED_WAITING_QA")


if __name__ == "__main__":
    main()
