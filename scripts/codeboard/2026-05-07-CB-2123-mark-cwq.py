"""CB-2123 — apply_retention batched commit fix → COMPLETED_WAITING_QA.

Per-project per-session script (Bible Rule 29). Marks CB-2123 as
COMPLETED_WAITING_QA after the implementation pass + audits.
"""

from __future__ import annotations

import json
import urllib.request

ISSUE_ID = "31577eee-8519-45e8-ba02-2019784405bd"  # CB-2123
API_BASE = "http://localhost:8401/api"

UPDATE_BODY = {
    "status": "COMPLETED_WAITING_QA",
}

req = urllib.request.Request(
    f"{API_BASE}/issues/{ISSUE_ID}",
    method="PATCH",
    data=json.dumps(UPDATE_BODY).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)

with urllib.request.urlopen(req) as resp:
    body = resp.read().decode("utf-8")
    print(f"[CB-2123] HTTP {resp.status}")
    print(body[:400])
