"""Mark CB-2043 COMPLETED_WAITING_QA — Rule 29 per-project per-session script."""

import json
import urllib.request

ISSUE_ID = "cef85795-69e3-4012-b016-d212469ca264"  # CB-2043
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
