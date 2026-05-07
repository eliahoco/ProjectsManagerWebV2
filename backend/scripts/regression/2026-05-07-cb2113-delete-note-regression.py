"""CB-2113 regression: DELETE /implementation/notes → 204 → list refreshes.

Acceptance:
  1. POST note → 200 + body
  2. GET list → contains note
  3. DELETE note → 204 (empty body)
  4. GET list → does NOT contain note (refresh post-delete)
  5. GET list AGAIN → still gone (persistence across reload)
  6. DELETE same note again → 404 (idempotency safety)
  7. DELETE with mismatched issue_id → 404 (cross-issue protection)
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

API = "http://localhost:8401/api"
ISSUE_ID = "6d8c189e-8201-42b8-bb48-819e982cf61e"  # CB-2113 itself
OTHER_ISSUE_ID = "00000000-0000-0000-0000-000000000000"  # nonexistent for cross-issue test


def req(method: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    r = urllib.request.Request(f"{API}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    print(f"== CB-2113 regression on issue {ISSUE_ID} ==")

    # 1. Create note
    status, body = req(
        "POST",
        f"/issues/{ISSUE_ID}/documentation/notes",
        {
            "title": "CB-2113 regression marker",
            "content": "Created by automated regression — should be deleted.",
            "category": "GENERAL",
            "importance": "LOW",
            "author": "RegressionBot",
        },
    )
    if status != 201 and status != 200:
        fail(f"POST expected 200/201, got {status}: {body!r}")
    note = json.loads(body)
    note_id = note["id"]
    print(f"  [1] POST → {status} note_id={note_id}")

    # 2. GET list — note present
    status, body = req("GET", f"/issues/{ISSUE_ID}/documentation/notes")
    if status != 200:
        fail(f"GET list expected 200, got {status}")
    notes = json.loads(body)
    if not any(n["id"] == note_id for n in notes):
        fail(f"created note {note_id} missing from list of {len(notes)}")
    print(f"  [2] GET list → {len(notes)} note(s), target present")

    # 3. DELETE → 204
    status, body = req("DELETE", f"/issues/{ISSUE_ID}/documentation/notes/{note_id}")
    if status != 204:
        fail(f"DELETE expected 204, got {status}: {body!r}")
    if body != b"":
        fail(f"DELETE 204 must have empty body, got {body!r}")
    print(f"  [3] DELETE → 204 empty body")

    # 4. GET list refreshes — note absent
    status, body = req("GET", f"/issues/{ISSUE_ID}/documentation/notes")
    if status != 200:
        fail(f"GET refresh expected 200, got {status}")
    notes = json.loads(body)
    if any(n["id"] == note_id for n in notes):
        fail(f"deleted note {note_id} STILL in refreshed list")
    print(f"  [4] GET refresh → {len(notes)} note(s), target absent")

    # 5. Reload (second GET) — still gone
    status, body = req("GET", f"/issues/{ISSUE_ID}/documentation/notes")
    notes = json.loads(body)
    if any(n["id"] == note_id for n in notes):
        fail(f"deleted note {note_id} resurrected on second GET")
    print(f"  [5] GET reload → still absent, persistence confirmed")

    # 6. Idempotent delete → 404
    status, _ = req("DELETE", f"/issues/{ISSUE_ID}/documentation/notes/{note_id}")
    if status != 404:
        fail(f"second DELETE expected 404, got {status}")
    print(f"  [6] DELETE again → 404 (correct)")

    # 7. Cross-issue protection: create a fresh note, try to delete via wrong issue_id
    status, body = req(
        "POST",
        f"/issues/{ISSUE_ID}/documentation/notes",
        {
            "title": "cross-issue protection probe",
            "content": "should not be deletable via wrong issue id",
            "category": "GENERAL",
            "importance": "LOW",
            "author": "RegressionBot",
        },
    )
    probe_id = json.loads(body)["id"]
    status, _ = req(
        "DELETE", f"/issues/{OTHER_ISSUE_ID}/documentation/notes/{probe_id}"
    )
    if status != 404:
        fail(f"cross-issue DELETE expected 404, got {status}")
    print(f"  [7] cross-issue DELETE (fake issue_id) → 404 (correct)")

    # cleanup probe
    cleanup, _ = req("DELETE", f"/issues/{ISSUE_ID}/documentation/notes/{probe_id}")
    if cleanup != 204:
        print(f"  WARN cleanup status {cleanup}")

    print("\nPASS — CB-2113 acceptance met")


if __name__ == "__main__":
    main()
