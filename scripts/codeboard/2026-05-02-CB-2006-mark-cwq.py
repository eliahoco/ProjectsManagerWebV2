"""
CB-2006 status flip → COMPLETED_WAITING_QA.

Task: "Hooks in frontend/hooks/useIssueRelations.ts" (STORY CB-2005, EPIC CB-1996, FEATURE CB-1955).
  - New module `frontend/hooks/useIssueRelations.ts` w/ useIssueRelations,
    useAddRelation, useAddRelationBulk, useDeleteRelation.
  - Shared `frontend/lib/api/api-client.ts` (APIError + apiFetch) extracted
    to break import cycle + dedupe.
  - useCodeBoard.ts re-exports under legacy names for AddRelationModal compat.
  - Cache fan-out: invalidates ['issue-relations', id] AND ['issue', id]
    for both ends; bulk fan-out clamped at MAX_INVALIDATE_FANOUT=101.
  - 12/12 vitest passing for new file; AddRelationModal (17) + useCodeBoard
    (15) compat tests still green (44 total).
  - Code-reviewer + security-auditor agents: 0 CRITICAL / 0 HIGH after fixes.

Per Rule 29 — per-project, per-session script path.
"""

import json
import urllib.request

ISSUE_ID = "f4d481c3-fabe-4843-ba78-58ae113316ca"
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
