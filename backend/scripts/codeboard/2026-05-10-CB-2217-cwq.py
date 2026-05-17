"""CB-2217 → COMPLETED_WAITING_QA push.

Per Rule 29: per-project, per-session script path. Do NOT move to /tmp/.

Run:
    venv/bin/python backend/scripts/codeboard/2026-05-10-CB-2217-cwq.py
"""

import json
import urllib.error
import urllib.request

ISSUE_ID = "37e98bcc-be73-4b3e-81a9-32eb12938077"
ISSUE_KEY = "CB-2217"
API_BASE = "http://localhost:8401/api"

COMMENT = """## CB-2217 — COMPLETED_WAITING_QA

### Problem (recap)

`/api/system/rag/status` echoed `collections[].name = project_<cuid_prefix>`
plus per-collection doc count. Any local Origin-less caller could enumerate:
how many projects exist, which CUID prefixes are active, approximate content
volume per project. Combined with M-1 (no real auth), this was reconnaissance
material for any post-foothold attacker.

### What changed

**`backend/api/system.py` — `RagCollectionStatus` model**

- `name: Optional[str]` removed from the response model. Per-collection rows
  now carry only `count: Optional[int]`.
- `model_config = ConfigDict(extra="forbid")` added (code-reviewer M-2 pin):
  Pydantic v2's default `extra="ignore"` would silently let a future
  name-shaped field (id/slug/label/hashed-name) through `get_status_payload()`.
  `extra="forbid"` rejects undeclared fields at validation time so the
  contract fails fast at model layer, not just regex-on-serialized-JSON.
- Module + class docstrings document the redaction rationale and the
  rank-as-identity contract: `collections[i]` is NOT a stable per-project
  pointer across polls — consumers must not treat array position as identity.

**`backend/services/rag_service.py` — `_compute_status_payload()`**

- `collections_payload.append({"count": count})` — only `count` crosses the
  HTTP boundary. Internal callers (`get_collection`, `describe_mode`) keep
  using the real collection name on the service side; redaction is
  payload-only.
- Per-collection `count()` failure log line now uses `enumerate()` index
  (`#%d`) instead of the name (CB-2669 follow-up): name in a DEBUG log
  re-discloses the same `project_<cuid_prefix>` string off-band to anyone
  with log access.
- Docstring updates trace the M-2 fix (collection redaction) alongside M-1
  (CB-2216 abspath redaction) and M-3 (CB-2218 DoS amplifier).

### Tests

**`backend/tests/test_system_rag_status.py`**

- `test_endpoint_returns_http_payload_with_collection_counts` — asserts
  `data["collections"] == [{"count": 7}]` (no `name` key) AND
  `"project_aaaaaa" not in response.text` AND a defence-in-depth regex
  `project_\\w{4,}` finds no match in serialized JSON. Catches a future
  regression that re-introduces the name under a different field shape.
- `test_endpoint_returns_persistent_payload_without_leaking_abspath` — same
  three-layer assertion against `project_zzzzzz`. The regex pin is the
  CB-2217 line of defence; the abspath assertion is the CB-2216 line of
  defence; both must hold simultaneously.
- `test_rag_collection_status_model_forbids_extra_fields` — model-level
  contract test. `RagCollectionStatus(count=5)` accepted; `name=...`,
  `id=...`, `slug=...`, `label=...`, `project_id=...` all raise
  `ValidationError`. Pins `extra="forbid"` at the layer that matters.

**`backend/tests/test_rag_service_status_payload.py`**

- `test_status_payload_count_failure_log_uses_index_not_name` — `caplog` at
  DEBUG asserts the literal collection-name string is NOT in the failure
  log line, AND the loop-index token `#0` IS present. Pins the CB-2669
  belt+suspenders fix (no off-band re-disclosure via debug logs).

### Audit gates

- **code-reviewer**: ran on the diff. M-2 (`extra="forbid"` model pin) was
  applied and tested. Other findings filed as follow-up tickets: none
  required a re-pass before CWQ on CB-2217 itself.
- **security-auditor**: ran on the diff. Findings filed as separate
  follow-ups, all already in WAITING QA:
    - CB-2666 (HIGH H-1): /api/projects enumerates project CUID + path
    - CB-2667 (HIGH H-2): /api/search/{project_id}/stats discloses doc count
    - CB-2668 (MEDIUM M-1): /docs + /openapi.json publish full route map
    - CB-2669 (LOW L-2): describe_mode startup INFO log emits abspath
  All four close other disclosure surfaces that, once CB-2217 redacted
  `collections[].name`, became the next-best foothold for the same
  reconnaissance objective. None are regressions of CB-2217 itself.
- **regression**: `pytest tests/test_system_rag_status.py` 5/5 pass;
  `pytest tests/test_rag_service_status_payload.py` 18/18 pass.

### Out of scope (not blockers)

- Real auth surface for `/api/system/rag/*` — tracked under the broader
  multi-tenant story that CB-2666/2667/2786 belong to.
- Per-call admin context flag to switch the response shape (full vs
  redacted): not needed once names are removed unconditionally — the
  fix took the simpler "always redact" path the ticket explicitly called
  out as the second fix option.

CB-2217 in scope: closed.
"""


def patch_status(issue_id: str, status: str) -> None:
    body = json.dumps({"status": status}).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/issues/{issue_id}",
        data=body,
        method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"PATCH status={status}: HTTP {resp.status}")
        print(resp.read().decode("utf-8")[:300])


def post_comment(issue_id: str, body: str) -> None:
    payload = json.dumps({"content": body, "author": "AI"}).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/issues/{issue_id}/comments",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"POST comment: HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        print(f"POST comment failed: HTTP {exc.code} {exc.read().decode()[:200]}")


if __name__ == "__main__":
    print(f"Marking {ISSUE_KEY} ({ISSUE_ID}) → COMPLETED_WAITING_QA")
    post_comment(ISSUE_ID, COMMENT)
    patch_status(ISSUE_ID, "COMPLETED_WAITING_QA")
