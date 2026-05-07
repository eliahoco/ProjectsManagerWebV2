"""Post QA verdict comment + flip CB-2113 to COMPLETED_WAITING_QA.

Per Rule 23: NEW BUG ticket for missing delete UI is NOT auto-pushed —
draft included in comment for Eli's approval.
"""
from __future__ import annotations
import json
import urllib.request

API = "http://localhost:8401/api"
ISSUE_ID = "6d8c189e-8201-42b8-bb48-819e982cf61e"  # CB-2113

COMMENT = """## CB-2113 QA Verdict — Backend PASS, UI gap flagged

**Acceptance**: \"Manual: delete note → list refreshes without it → reload → confirmed gone.\"

### Backend regression (PASS — 7/7)
Script: `backend/scripts/regression/2026-05-07-cb2113-delete-note-regression.py`

```
[1] POST → 201 note_id=8bf9bdd5-54ce-4532-b491-1fb8a21c0ff2
[2] GET list → 1 note(s), target present
[3] DELETE → 204 empty body
[4] GET refresh → 0 note(s), target absent
[5] GET reload → still absent, persistence confirmed
[6] DELETE again → 404 (correct)
[7] cross-issue DELETE (fake issue_id) → 404 (correct)
```

Endpoint contract:
- `DELETE /api/issues/{issue_id}/documentation/notes/{note_id}` → 204 No Content (empty body)
- 404 if note absent or issue_id mismatch (cross-issue protection)
- List refresh on next GET shows note removed; persistence confirmed across two consecutive GETs

### UI gap (separate concern — needs Eli's call)
Screenshot: `docs/research/cb-2113-impl-notes-no-delete-button.png`

`frontend/components/codeboard/ImplementationTab.tsx` `NoteCard` renders:
- Category badge, importance badge, title
- Markdown content, author, timestamp
- **Zero buttons** — no Delete, no Edit

`hooks/useCodeBoard.ts` exposes only `useImplementationNotes` + `useCreateImplementationNote`. No `useDeleteImplementationNote`.

Backend DELETE endpoint exists and works; the existing committed WIP (slice 3 / CB-2109) shipped without exposing it in the UI. This is consistent with the parent epic CB-2100 scope (\"audit + commit existing WIP\") — adding the delete UI is a follow-up, not part of E4.

### Recommendation
- Mark CB-2113 **COMPLETED_WAITING_QA**: backend acceptance fully met, regression test committed.
- File a separate BUG under CB-2038 (parent feature) for the missing delete UI. Draft below — awaiting Eli's approval to push (Rule 23):

> **Title**: ImplementationNote UI lacks delete button — backend endpoint exists
> **Type**: BUG
> **Priority**: MEDIUM
> **Description**: Implementation Notes section in ImplementationTab.tsx renders notes read-only. Backend `DELETE /api/issues/{id}/documentation/notes/{note_id}` works correctly (verified by CB-2113 regression). Frontend needs: (a) `useDeleteImplementationNote` mutation in `hooks/useCodeBoard.ts`, (b) delete button on `NoteCard` with confirmation, (c) optimistic UI update via React Query invalidation.
> **Labels**: documentation-surface, ui-gap

— Jonny
"""

def req(method, path, body):
    data = json.dumps(body).encode()
    r = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r) as resp:
        return resp.status, json.loads(resp.read())

# 1. Comment
status, payload = req(
    "POST",
    f"/issues/{ISSUE_ID}/comments",
    {"author": "Jonny", "content": COMMENT},
)
print(f"comment → {status} id={payload['id']}")

# 2. Flip to COMPLETED_WAITING_QA
status, payload = req(
    "PATCH",
    f"/issues/{ISSUE_ID}",
    {"status": "COMPLETED_WAITING_QA"},
)
print(f"status patch → {status} new_status={payload['status']}")
