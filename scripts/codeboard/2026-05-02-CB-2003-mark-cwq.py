#!/usr/bin/env python3
"""Mark CB-2003 as COMPLETED_WAITING_QA after Jonny ships AddRelationModal.

Rule 29 — per-project per-session script (no /tmp/ collisions).
"""
import json
import urllib.request

ISSUE_ID = "633929ae-e2cd-4e12-a4dc-0a3678d1cb4a"
URL = f"http://localhost:8401/api/issues/{ISSUE_ID}"

body = json.dumps({"status": "COMPLETED_WAITING_QA"}).encode()
req = urllib.request.Request(
    URL,
    data=body,
    method="PATCH",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read())
    print(f"OK {data.get('key')} → {data.get('status')}")
