"""CB-2378 closeout + a11y follow-up.

- Mark CB-2378 (Hydration warning portal fix) -> COMPLETED_WAITING_QA.
- File new BUG under STORY CB-2089 capturing pre-existing a11y gaps in the
  doc-settings ConfirmDialog (no focus trap, no Escape handler, no body
  scroll lock, no aria-labelledby) — surfaced by code-reviewer during the
  CB-2378 portal fix audit on 2026-05-09.

Run: python backend/scripts/codeboard/2026-05-09-cb-2378-cwq-and-a11y-followup.py
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

API = "http://localhost:8401/api"
PROJECT = "1511e54f71dccd3fa79f67fe"
CB_2378_ID = "2f57e0aa-87ce-4dfa-bd34-f5770ad36ba0"
PARENT_STORY = "CB-2089"  # S3.3: E3 audit + regression + Chrome QA


def http(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} on {method} {path}: {e.read().decode()[:300]}")
        raise


def find_parent_id(key: str) -> str:
    for page in range(1, 60):
        r = http("GET", f"/projects/{PROJECT}/issues?page={page}&pageSize=200")
        for i in r.get("items", []):
            if i.get("key") == key:
                return i["id"]
    raise SystemExit(f"{key} not found")


def main() -> None:
    parent_id = find_parent_id(PARENT_STORY)
    print(f"parent {PARENT_STORY} = {parent_id}")

    # 1) Mark CB-2378 CWQ
    http(
        "PATCH",
        f"/issues/{CB_2378_ID}",
        {"status": "COMPLETED_WAITING_QA"},
    )
    print("CB-2378 -> COMPLETED_WAITING_QA")

    # 2) File a11y follow-up
    body = {
        "title": "ConfirmDialog (settings/documentation): a11y gaps (focus trap, Esc, scroll lock, aria-labelledby)",
        "description": (
            "Surfaced by code-reviewer during the CB-2378 portal-fix audit on 2026-05-09.\n\n"
            "Pre-existing — not introduced by CB-2378 — but newly visible now that the dialog is a true top-level overlay.\n\n"
            "**Gaps:**\n"
            "- No focus trap (Tab can escape the dialog into the background page).\n"
            "- No initial focus on Confirm/Cancel button when dialog opens.\n"
            "- No Escape-key handler to close the dialog.\n"
            "- No body scroll lock — background page scrolls behind backdrop.\n"
            "- No `aria-labelledby` linking the heading to the dialog.\n"
            "- Backdrop has no `onClick={onCancel}` (debatable — depends on UX policy).\n\n"
            "**File**: `frontend/app/settings/documentation/page.tsx` — `ConfirmDialog` (~line 254).\n\n"
            "**Suggested fix**: extract a reusable `<Modal>` primitive in `frontend/components/ui/` "
            "(focus trap via `react-focus-lock` or homegrown, scroll lock via `overflow:hidden` on body, "
            "Escape handler via `useEffect` keydown listener, aria attributes wired up).\n\n"
            "**Acceptance**:\n"
            "- Tab-cycle stays inside the dialog while open.\n"
            "- Escape closes the dialog.\n"
            "- Body does not scroll while dialog is open.\n"
            "- Screen reader announces the dialog title.\n"
        ),
        "type": "BUG",
        "priority": "MEDIUM",
        "parentId": parent_id,
        "labels": "a11y,doc-settings,follow-up",
        "assignee": "react-specialist",
        "reporter": "AI",
    }
    created = http("POST", f"/projects/{PROJECT}/issues", body)
    print(f"created a11y follow-up: {created.get('key')} ({created.get('id')})")


if __name__ == "__main__":
    main()
