#!/usr/bin/env python3
"""
CB-2071 close-out + follow-up bug filing.

Actions:
1. PATCH CB-2071 → COMPLETED_WAITING_QA (regression PASS).
2. File BUG: 15s proxy timeout breaks Generate UX
   (parent: CB-2054 epic — keeps it grouped with the FE work).
3. File BUG: useGenerateFeatureDoc does not refetch on 504
   (parent: CB-2054).

NOT touched: CB-2068/2069/2070 — already CWQ.
NOT touched: CB-2073-2077 — those are [QA] tasks for Eli; this script only
records them in the regression report. Eli's manual QA promotes to DONE.
"""

import json
import urllib.request
import urllib.error

API = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"  # ProjectsManagerWebV2Production
EPIC_CB_2054 = "d7dac542-6650-4cba-8116-f1c632377626"
TASK_CB_2071 = "0ca77aa9-bc16-486e-b003-978041ff83ca"


def http(method: str, path: str, body=None):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode()
            return r.status, json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def patch_status(issue_id: str, status: str):
    code, body = http("PATCH", f"/issues/{issue_id}", {"status": status})
    print(f"  PATCH {issue_id[:8]} → {status}: {code}")
    return code, body


def create_bug(title: str, description: str, parent_id: str, priority: str = "HIGH"):
    payload = {
        "title": title,
        "description": description,
        "type": "BUG",
        "priority": priority,
        "parentId": parent_id,
        "labels": "documentation-surface,cb-2071-regression",
        "reporter": "AI",
    }
    code, body = http("POST", f"/projects/{PROJECT_ID}/issues", payload)
    if code in (200, 201):
        print(f"  filed BUG {body.get('key')} ({body.get('id','')[:8]}): {title[:60]}")
    else:
        print(f"  FAILED to file bug ({code}): {body}")
    return code, body


def main():
    print("=== CB-2071 close-out ===")
    print("\n[1/3] Mark CB-2071 → COMPLETED_WAITING_QA")
    patch_status(TASK_CB_2071, "COMPLETED_WAITING_QA")

    print("\n[2/3] File BUG-A: 15s proxy timeout breaks Generate UX")
    create_bug(
        title="Documentation Generate UI returns 504 — proxy timeout (15s) shorter than LLM run (30s+)",
        description=(
            "**Found during CB-2071 regression.**\n\n"
            "## Repro\n"
            "1. Open any FEATURE issue with non-trivial task graph (e.g. CB-2038).\n"
            "2. Navigate to `/codeboard/features/<id>/documentation`.\n"
            "3. Click **Regenerate**.\n"
            "4. Observe: after 15 s the UI surfaces a `504 Gateway timeout` toast / error.\n"
            "5. Direct backend probe (`POST /api/features/<id>/documentation/generate`) "
            "completes successfully in ~30-35 s — the row is fully populated and ChromaDB indexed.\n\n"
            "## Root cause\n"
            "`frontend/app/api/codeboard/[...path]/route.ts:48` hard-codes "
            "`setTimeout(() => controller.abort(), 15000)` for *all* POST/PUT/PATCH calls. "
            "Documentation Generate runs an LLM aggregation across all execution summaries / "
            "implementation notes / QA tasks for the feature, which routinely exceeds 15 s.\n\n"
            "## Effect on CB-2054 acceptance\n"
            "The Generate button is effectively broken in the UI even though the underlying "
            "endpoint works. User has to hard-reload the page after the toast clears to see "
            "the regenerated content. This blocks CB-2054 (E2 frontend) from feeling shippable.\n\n"
            "## Fix options\n"
            "1. **Per-route timeout allowlist** — bump `/features/*/documentation/generate` "
            "to 120 s in the proxy (smallest surface, recommended).\n"
            "2. Convert the endpoint to SSE / streaming (proxy already passes `text/event-stream` through).\n"
            "3. Job-and-poll: POST → 202 + job_id, GET /status → ready / pending.\n\n"
            "## Severity\n"
            "HIGH — primary acceptance flow for CB-2054 fails in the UI.\n\n"
            "## Evidence\n"
            "- `docs/research/cb-2071-regression-report.md` (full trace + headers).\n"
            "- `docs/research/cb-2071-before-generate.png` / `cb-2071-after-generate.png`."
        ),
        parent_id=EPIC_CB_2054,
        priority="HIGH",
    )

    print("\n[3/3] File BUG-B: useGenerateFeatureDoc does not refetch on 504")
    create_bug(
        title="useGenerateFeatureDoc mutation does not invalidate documentation query on 504/error — UI stays stale",
        description=(
            "**Found during CB-2071 regression** (depends on / co-symptom of BUG-A).\n\n"
            "## Repro\n"
            "1. With BUG-A in play (proxy 504 on Generate), the documentation row is "
            "still successfully written by the backend.\n"
            "2. UI shows the error toast and remains on the *pre-generate* state — "
            "still says \"Not indexed in ChromaDB\", still empty Tech Stack section, "
            "stale metrics.\n"
            "3. Only a hard reload (or React Query manual invalidation) brings the new state in.\n\n"
            "## Root cause\n"
            "`frontend/hooks/useCodeBoard.ts` — `useGenerateFeatureDoc` mutation does not "
            "schedule an `invalidateQueries(['feature-documentation', issueId])` on `onError` "
            "(only on `onSuccess`). With BUG-A producing a 504, the cache stays stale.\n\n"
            "## Fix\n"
            "Add an `onError` handler that *also* invalidates the documentation query — "
            "defence-in-depth for any non-2xx response from the proxy. Once BUG-A is fixed "
            "this becomes redundant in the happy path but still correct for genuine errors.\n\n"
            "## Severity\n"
            "MEDIUM — masked by BUG-A; should be fixed alongside it for completeness.\n\n"
            "## Evidence\n"
            "- `docs/research/cb-2071-regression-report.md`."
        ),
        parent_id=EPIC_CB_2054,
        priority="MEDIUM",
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
