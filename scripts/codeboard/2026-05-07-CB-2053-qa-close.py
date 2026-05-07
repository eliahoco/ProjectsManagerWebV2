"""CB-2053 QA close — Service Monitor RAG card visual verification.

Posts QA evidence comment + flips status to COMPLETED_WAITING_QA.
Per-project per-session path (Bible Rule 29). Run once.
"""
import json
import urllib.request

BASE = "http://localhost:8401/api"
ISSUE_ID = "ad1b3654-5c8e-400b-b528-f2464eab153d"  # CB-2053

QA_COMMENT = """## QA Evidence — CB-2053 [QA] E1-3 Service Monitor RAG card

**Date:** 2026-05-07
**Tester:** Jonny (VP-R&D agent, automated)

### Acceptance criteria
- [x] RAG card visible at bottom-left of frontend
- [x] Mode badge = HTTP (green dot)
- [x] Total docs > 0
- [x] Endpoint = `localhost:8402`
- [x] Top collections rendered with counts

### Verification steps
1. Confirmed services up: backend (8401), frontend (3601), chromadb heartbeat (8402).
2. `GET http://localhost:8401/api/system/rag/status` → `mode=HTTP`, `healthy=true`, `total_docs=3516`, 8 collections.
3. `GET http://localhost:3601/api/system/rag/status` (Next proxy, CB-2211 fix) → 200, payload identical to backend.
4. Navigated to `http://localhost:3601/` via Playwright/Chromium.
5. RAG card rendered with green dot, label "RAG HTTP", count "3,516 docs".
6. Expanded card → Endpoint `localhost:8402`, top 3 collections: `project_1511e54f` (1,989), `project_cmkims9r` (796), `project_linkedin` (730).

### Evidence
- `docs/research/cb-2053-rag-card-collapsed.png` — collapsed state, green badge + count
- `docs/research/cb-2053-rag-card-expanded.png` — expanded state, endpoint + top collections

Status moved to `COMPLETED_WAITING_QA` for Eli's manual sign-off (Bible Rule 22).
"""


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def patch(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


if __name__ == "__main__":
    comment = post(
        f"/issues/{ISSUE_ID}/comments",
        {"author": "Jonny", "content": QA_COMMENT},
    )
    print("comment posted:", comment.get("id"))

    updated = patch(f"/issues/{ISSUE_ID}", {"status": "COMPLETED_WAITING_QA"})
    print("status:", updated.get("status"))
