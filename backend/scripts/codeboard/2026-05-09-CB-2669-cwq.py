"""CB-2669 → COMPLETED_WAITING_QA push.

Per Rule 29: per-project, per-session script path. Do NOT move to /tmp/.

Run:
    venv/bin/python backend/scripts/codeboard/2026-05-09-CB-2669-cwq.py
"""

import json
import urllib.request
import urllib.error

ISSUE_ID = "e8a63af8-0cab-4b10-aee0-af55b019caf8"
ISSUE_KEY = "CB-2669"
API_BASE = "http://localhost:8401/api"

COMMENT = """## CB-2669 — COMPLETED_WAITING_QA

### What changed

**`backend/services/rag_service.py`**

1. `describe_mode()` PERSISTENT branch (lines 301-351): replaced
   `path={self._endpoint}` with
   `path_hash={blake2s(endpoint, digest_size=4).hexdigest()}`. The 4-byte
   digest preserves boot-log diagnostic value (operators can compare
   `path_hash` across boots) without revealing the abspath that
   CB-2216 already redacted from `/api/system/rag/status`. Boot log line
   in `app/main.py:272` (`logger.info("[startup] %s", rag.describe_mode())`)
   no longer re-discloses the abspath off-band.
2. `_compute_status_payload()` count() failure DEBUG log
   (formerly at lines 504-508): switched the format string from
   `count() failed for collection %s … name, exc` to
   `count() failed for collection #%d … idx, exc`. The collection-name
   that CB-2217 banned from the HTTP payload is no longer recoverable
   from `logs/backend.log` if a future operator flips the logger to
   DEBUG. Loop now uses `enumerate(collections)`; the local `name`
   binding was dropped (it had no other consumer).
3. (Code-review M-1 follow-up) Empty-`_endpoint` branch in
   `describe_mode()` PERSISTENT now emits a `logger.warning` calling out
   the half-init invariant break (CB-2213/CB-2669) instead of silently
   returning `path_hash=?`. A future invariant regression now produces a
   loud signal rather than a silent lie.

### Tests

**`backend/tests/test_rag_service_describe_mode.py`**

- `test_describe_mode_persistent_after_fallback` — now asserts
  `path_hash=<expected blake2s 8-hex>`, AND asserts the literal abspath
  is not anywhere in the log line, AND asserts `path=` does NOT appear
  (only `path_hash=`). Belt+suspenders against any future regression
  that re-introduces `path=<abspath>` alongside the hash.
- `test_describe_mode_swallows_collection_count_failure` — regex
  `^RAG mode=PERSISTENT path_hash=[0-9a-f]{8} collections=\\?$`, plus
  abspath-not-in-line guard.
- Module docstring updated with CB-2669 rationale.

**`backend/tests/test_rag_service_status_payload.py`**

- New: `test_status_payload_count_failure_log_uses_index_not_name` —
  uses `caplog` at DEBUG to assert the collection name does NOT appear
  in the failure log line, AND asserts the loop-index token `#0` does.

### Audit gates passed

- **code-reviewer**: ship-able. M-1 (empty-endpoint silent-`?`) addressed.
  L-1/L-2/L-3 noted as follow-up improvements (non-blocking).
- **security-auditor**: no CRITICAL/HIGH. M-1 — 32-bit blake2s vs
  deterministic-input wordlist attack — flagged as a hardening idea
  beyond the ticket scope. The ticket explicitly accepts blake2s
  digest_size=4 as the recommended fix, so the in-scope mitigation
  (raise the bar above grep, eliminate INFO-level abspath emission) is
  achieved. A persisted per-install salt for `path_hash` is captured
  here as a candidate follow-up if the threat model widens.
- **regression**: 24/24 pass on
  `test_rag_service_describe_mode.py` +
  `test_rag_service_status_payload.py` +
  `test_rag_service_half_init_invariant.py`. 60/60 on `-k rag`.

### Belt+suspenders (out of scope, candidate follow-up tickets)

- File rotation (`logging.handlers.RotatingFileHandler`) on
  `logs/backend.log`.
- Restrictive permissions (`chmod 600`) on `logs/backend.log`.
- Persisted per-install salt for `path_hash` if cross-host log
  comparison is ever required (security-auditor M-1).
- Caplog regression test on the actual `app/main.py:272` lifespan
  emission point (code-reviewer L-3).
- Lifespan `except` around `_construct_persistent_client_locked()` —
  if added later, ensure the chained `OSError` repr (which contains the
  abspath) is NOT logged verbatim (security-auditor L-1).

CB-2669 in scope: closed.
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
