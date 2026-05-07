"""
CB-2008 status flip → COMPLETED_WAITING_QA.

Task: "Add IssueLink + LinkType types in codeboard.ts" (STORY CB-2007,
EPIC CB-1996, FEATURE CB-1955).
  - frontend/types/codeboard.ts now mirrors backend Pydantic shapes from
    backend/models/schemas.py for the issue-link / relation primitives:
    LinkType, IssueSummary, IssueLinkResponse, IssueRelationsListResponse,
    IssueLinkCreatePayload, IssueLinkBulkCreatePayload, IssueLinkBulkSkipped
    (+ IssueLinkBulkSkipReason), IssueLinkBulkResponse.
  - This change adds IssueLinkDeleteResponse for full DELETE-endpoint parity
    (backend IssueLinkDeleteResponse, schemas.py:305-322).
  - tsc passes for the new types (the lone pre-existing error in
    app/api/docker/metrics/route.ts is unrelated to this task).
  - code-reviewer + security-auditor agents: 0 CRITICAL / 0 HIGH; verdict
    LGTM / APPROVED.

Per Rule 29 — per-project, per-session script path.
"""

import json
import urllib.request

ISSUE_ID = "8c7824a2-f4a1-4f27-b18f-4c36ae079baf"
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
