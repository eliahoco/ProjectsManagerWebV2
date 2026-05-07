"""
CB-2001 status flip → COMPLETED_WAITING_QA.

Task: "Empty state: 'No linked issues · + Add relation' centered ghost button"
  - LinkedIssuesPanel empty branch replaced with role=status wrapper +
    optional ghost CTA.
  - 22/22 vitest passing (5 new).
  - code-reviewer + security-auditor CLEAN.

Per Rule 29 — per-project, per-session script path.
"""

import json
import urllib.request

ISSUE_ID = "5f42e996-6d81-4614-b499-dc74cfee9637"
URL = f"http://localhost:8401/api/issues/{ISSUE_ID}"
PAYLOAD = json.dumps({"status": "COMPLETED_WAITING_QA"}).encode()

req = urllib.request.Request(
    URL,
    data=PAYLOAD,
    method="PATCH",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as r:
    body = r.read().decode()
    print(r.status, body[:500])
