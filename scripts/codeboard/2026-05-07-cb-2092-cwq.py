#!/usr/bin/env python3
"""CB-2092 — mark COMPLETED_WAITING_QA + comment with QA artifacts."""
import urllib.request, json, sys

API = "http://localhost:8401/api"
ISSUE_ID = "a246782f-b573-48d4-b741-38777b48ed9c"

def req(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=10) as resp:
        return json.loads(resp.read())

# 1. PATCH status → COMPLETED_WAITING_QA
patched = req("PATCH", f"/issues/{ISSUE_ID}", {"status": "COMPLETED_WAITING_QA"})
print(f"status -> {patched.get('status')}")

# 2. Comment with artifact references
comment_body = (
    "**Chrome visual QA — PASS**\n\n"
    "Tested: settings page render, toggle ON/OFF visual, recent summaries list "
    "(populated, DESC), keyboard nav (Tab order + Space activates toggle, focus rings present).\n\n"
    "**Artifacts** (in `docs/research/`):\n"
    "- `cb-2092-settings-initial.png` — initial render\n"
    "- `cb-2092-settings-toggle-off.png` — toggle OFF (gray + focus ring)\n"
    "- `cb-2092-recent-summaries.png` — 17+ rows DESC, Re-run on hover\n"
    "- `cb-2092-keyboard-focus-toggle.png` — toggle focused\n"
    "- `cb-2092-keyboard-focus-link.png` — Tab reaches CB-2077 issue link\n"
    "- `cb-2092-chrome-qa-report.md` — full report\n\n"
    "Tab order verified: Toggle → retentionDays → maxPerIssue → Save → first issue link. "
    "Space activates toggle (label + bg flip via DOM diff). One unrelated 500 on "
    "`/api/projects/status` — not Documentation-related.\n\n"
    "Ready for CB-2093 functional regression."
)
commented = req(
    "POST",
    f"/issues/{ISSUE_ID}/comments",
    {"content": comment_body, "author": "Jonny"},
)
print(f"comment id: {commented.get('id')}")
