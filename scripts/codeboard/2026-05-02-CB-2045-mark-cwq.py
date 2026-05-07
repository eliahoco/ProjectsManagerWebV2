"""Mark CB-2045 COMPLETED_WAITING_QA — Rule 29 per-project per-session script.

Task: T1.2.1: Endpoint GET /api/system/rag/status
"""

import json
import urllib.request

ISSUE_ID = "cc9e2e63-c903-402e-ba25-324b726c5a8f"  # CB-2045
URL = f"http://localhost:8401/api/issues/{ISSUE_ID}"

payload = json.dumps({"status": "COMPLETED_WAITING_QA"}).encode()
req = urllib.request.Request(
    URL,
    data=payload,
    method="PATCH",
    headers={
        "Content-Type": "application/json",
        "Origin": "http://localhost:3601",
    },
)
with urllib.request.urlopen(req) as resp:
    body = resp.read().decode()
    print(resp.status, body[:400])
