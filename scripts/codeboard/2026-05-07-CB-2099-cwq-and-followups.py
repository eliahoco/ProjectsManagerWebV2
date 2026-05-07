"""
CB-2099 close-out + follow-up bug filing.

Actions:
  1. Patch CB-2099 -> COMPLETED_WAITING_QA with QA report citation.
  2. File CB-2100 (BUG, MEDIUM): hydration warning - ConfirmDialog
     rendered as <div> direct child of <tbody> in
     frontend/app/settings/documentation/page.tsx (SummaryRow).
  3. File CB-2101 (BUG, LOW): Re-run UX gap - clicking Re-run on a
     CWQ/DONE summary fast-fails with "Dependency check failed".
     Suggest disabling the button or sending force=true / inline
     toast instead of a failed session.

Per Bible Rule 22: only Eli promotes -> DONE. We push to CWQ only.
Per Bible Rule 29: written under <project>/scripts/codeboard/ with
date + key in filename, never /tmp/.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8401/api"
PMV2_PROJECT_ID = "1511e54f71dccd3fa79f67fe"

QA_REPORT_TAIL = (
    "QA report: docs/research/cb-2099-qa-report.md\n\n"
    "Evidence:\n"
    "- docs/research/cb-2099-confirm-dialog.png\n"
    "- docs/research/cb-2099-globalagentstatusbar-shows-retrigger-session.png\n\n"
    "Result: PASS. Re-run button -> ConfirmDialog -> Start -> "
    "POST /api/execute/issue/{id} -> session row -> SSE -> "
    "GlobalAgentStatusBar renders failed-state row "
    "(CB-2370 sentinel; backend dep-check rejects CWQ-status issue, "
    "but session is created and visible in the bar -- acceptance met).\n\n"
    "Side findings filed as CB-2100 (hydration warning) and "
    "CB-2101 (Re-run UX fast-fail)."
)


def http(method: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw.decode(errors="replace")}


def fetch_all_issues() -> dict[str, dict]:
    items: list[dict] = []
    page = 1
    while True:
        with urllib.request.urlopen(
            f"{BASE}/projects/{PMV2_PROJECT_ID}/issues?page={page}&pageSize=200"
        ) as r:
            d = json.load(r)
        items.extend(d["items"])
        if page >= d["totalPages"]:
            break
        page += 1
    return {i["key"]: i for i in items}


def main() -> int:
    print("[1/4] Fetching all PMv2 issues...")
    by_key = fetch_all_issues()
    print(f"      total issues: {len(by_key)}")

    if "CB-2099" not in by_key:
        print("ERROR: CB-2099 not found in PMv2 project.", file=sys.stderr)
        return 1

    cb2099 = by_key["CB-2099"]
    cb2089 = by_key.get("CB-2089")
    print(f"      CB-2099 id={cb2099['id']} status={cb2099['status']}")
    if cb2089:
        print(f"      CB-2089 (parent STORY) id={cb2089['id']}")

    # ------------------------------------------------------------------
    # 1. Push CB-2099 -> COMPLETED_WAITING_QA (idempotent: skip if already CWQ)
    # ------------------------------------------------------------------
    if cb2099["status"] != "COMPLETED_WAITING_QA":
        print("[2/4] Patching CB-2099 -> COMPLETED_WAITING_QA...")
        description = cb2099.get("description") or ""
        new_description = description.rstrip() + "\n\n---\n\n" + QA_REPORT_TAIL
        code, body = http(
            "PATCH",
            f"/issues/{cb2099['id']}",
            {
                "status": "COMPLETED_WAITING_QA",
                "description": new_description,
            },
        )
        print(f"      PATCH -> {code}")
        if code >= 300:
            print("      body:", body)
            return 2
    else:
        print("[2/4] CB-2099 already in COMPLETED_WAITING_QA, skipping PATCH.")

    # ------------------------------------------------------------------
    # 2. File CB-2100 - hydration warning bug
    # ------------------------------------------------------------------
    print("[3/4] Filing follow-up bug: ConfirmDialog inside <tbody>...")
    code, body = http(
        "POST",
        f"/projects/{PMV2_PROJECT_ID}/issues",
        {
            "title": "Hydration warning: ConfirmDialog rendered as <div> child of <tbody> in SummaryRow",
            "type": "BUG",
            "priority": "MEDIUM",
            "status": "BACKLOG",
            "reporter": "AI",
            "assignee": "react-specialist",
            "labels": "docs-settings,cb-2099-followup,hydration",
            "parentId": cb2089["id"] if cb2089 else None,
            "description": (
                "Found during CB-2099 manual QA on 2026-05-07.\n\n"
                "**Symptom**: React hydration warning in console:\n"
                "```\n"
                "<%s> cannot contain a nested %s.\n"
                "tbody <div>\n"
                "```\n\n"
                "**Cause**: `SummaryRow` in "
                "`frontend/app/settings/documentation/page.tsx:322` returns:\n"
                "```tsx\n"
                "<>\n"
                "  {confirming && <ConfirmDialog .../>}\n"
                "  <tr>...</tr>\n"
                "</>\n"
                "```\n"
                "When `confirming === true`, the dialog `<div role=\"dialog\">` "
                "becomes a direct child of `<tbody>`, which is invalid HTML.\n\n"
                "**Fix options**:\n"
                "1. Render `<ConfirmDialog>` from a portal (`createPortal` to `document.body`).\n"
                "2. Lift `confirming` state up to `RecentSummariesPanel` and render the dialog "
                "outside the `<table>` element entirely.\n\n"
                "Option 1 is the simplest and matches how modals are usually rendered in this app.\n\n"
                "**Acceptance**:\n"
                "- No hydration warning in browser console when opening Re-run dialog.\n"
                "- Dialog still renders centered with backdrop and is dismissible.\n\n"
                "Sibling: CB-2099, CB-2101."
            ),
        },
    )
    print(f"      POST CB-2100 -> {code}", body.get("key") if isinstance(body, dict) else "")
    if code >= 300:
        print("      body:", body)
        return 3
    cb2100_key = body.get("key") if isinstance(body, dict) else "?"

    # ------------------------------------------------------------------
    # 3. File CB-2101 - Re-run fast-fail UX
    # ------------------------------------------------------------------
    print("[4/4] Filing follow-up bug: Re-run fast-fails on CWQ/DONE...")
    code, body = http(
        "POST",
        f"/projects/{PMV2_PROJECT_ID}/issues",
        {
            "title": "Re-run button on settings/documentation fast-fails when issue is CWQ/DONE",
            "type": "BUG",
            "priority": "LOW",
            "status": "BACKLOG",
            "reporter": "AI",
            "assignee": "fullstack-developer",
            "labels": "docs-settings,cb-2099-followup,ux",
            "parentId": cb2089["id"] if cb2089 else None,
            "description": (
                "Found during CB-2099 manual QA on 2026-05-07.\n\n"
                "**Symptom**: Clicking Re-run on any summary row whose "
                "underlying issue is in `COMPLETED_WAITING_QA` or `DONE` "
                "creates a session that immediately fails with:\n"
                "```\n"
                "Dependency check failed: CB-XXXX has status COMPLETED_WAITING_QA. "
                "Must be one of BACKLOG, IN_PROGRESS, TODO to execute.\n"
                "```\n\n"
                "Because the Recent Summaries list is mostly populated by "
                "issues that just finished executing (and therefore landed "
                "in CWQ), most rows in the list will fast-fail when Re-run "
                "is used.\n\n"
                "**Fix options** (any one works):\n"
                "1. **Pre-disable**: hide / disable the Re-run button when "
                "the issue's current status is not eligible.\n"
                "2. **Force flag**: send `force: true` from `ConfirmDialog` "
                "so the backend bypasses the dep-check and re-executes the "
                "issue regardless of status. Matches how 'Re-run' is meant "
                "to behave.\n"
                "3. **Inline toast on failure**: catch the dep-check error "
                "and show a toast (`This issue is already in CWQ. Re-open "
                "to re-run.`) instead of leaving a failed session row in "
                "the bar.\n\n"
                "Recommendation: option 2 (force=true) since the user has "
                "already explicitly confirmed re-trigger in the dialog.\n\n"
                "**Acceptance**:\n"
                "- Re-run on a CWQ/DONE summary either (a) is disabled, or "
                "(b) actually re-executes the issue end-to-end.\n"
                "- No silent failed-session noise in GlobalAgentStatusBar.\n\n"
                "Sibling: CB-2099, CB-2100."
            ),
        },
    )
    print(f"      POST CB-2101 -> {code}", body.get("key") if isinstance(body, dict) else "")
    if code >= 300:
        print("      body:", body)
        return 4
    cb2101_key = body.get("key") if isinstance(body, dict) else "?"

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("CB-2099 -> COMPLETED_WAITING_QA")
    print(f"Filed: {cb2100_key} (hydration warning)")
    print(f"Filed: {cb2101_key} (Re-run fast-fail UX)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
