"""Post CB-2662 close-out audit transcript as a comment on the issue.

Per rule 29: per-project, per-session helper script. Run once after the
COMPLETED_WAITING_QA flip is confirmed.
"""

import json
import urllib.request

ISSUE_ID = "fc9116c7-ca82-4e22-991c-a1ddbfa19e5d"  # CB-2662
URL = f"http://localhost:8401/api/issues/{ISSUE_ID}/comments"

BODY = """## CB-2662 — Close-out (COMPLETED_WAITING_QA)

### What shipped
- New `app/rate_limit.py` exports the slowapi `Limiter` singleton; `app/main.py` now imports it from there (breaks the circular-import risk for router-level decorators).
- `POST /api/features/{issue_id}/documentation/generate` decorated with `@limiter.limit(\"5/minute\")` (constant `_DOC_GEN_RATE_LIMIT` in `api/documentation.py`). Required `request: Request` param added; docstring locked.
- New runbook `backend/docs/DOC_PIPELINE_RUNBOOK.md` covers the rate limit, deploy gates, side-channel awareness, and the long-term job-and-poll plan. AUTOPILOT_RUNBOOK gets a sister-doc cross-reference.

### Test coverage (`backend/tests/test_documentation_api.py`)
- `test_generate_feature_documentation_rate_limit_boundary` — 5 OK + 1 throttled (429) inside the same 60s window.
- `test_generate_feature_documentation_rate_limit_isolated_per_test` — fixture reset gives a fresh bucket each test.
- `test_rate_limit_singleton_identity` — production handler and test fixture operate on the SAME `Limiter` instance.
- Fixture `_shared_limiter.reset()` keeps the bucket from spilling across the ~22 sibling tests that hit `/generate`.

`backend/tests/test_documentation_api.py`: 67 passed in 4.24s. Full suite: 816 passed, 3 pre-existing failures (`test_qa_sequence::test_no_commit_inside_helper`, two `test_schema_validation` cases) — verified pre-existing on a clean tree (`git stash` + rerun).

### Audit gate results

**Code review (code-reviewer agent)** — Ship-as-is. Findings: M1/M2 about reset() under future Redis/xdist (informational); L1–L4 are doc-style nits (private symbol wrap, config-ify cap, decorator-order comment). No CRITICAL / HIGH.

**Security audit (security-auditor agent)** — One HIGH, one MEDIUM addressed in this diff:
- **HIGH-1 (proxy headers)**: `slowapi.util.get_remote_address` reads `request.client.host` only and ignores `X-Forwarded-For`. Behind a reverse proxy / CDN / load-balancer, every request collapses into one bucket. Mitigation in this diff: explicit deploy-gate section in `DOC_PIPELINE_RUNBOOK.md §2a` plus a fail-loud comment block in `app/rate_limit.py`. The runbook prescribes `uvicorn --proxy-headers --forwarded-allow-ips=<proxy-cidr>` (never `*`) and explicitly forbids switching to `slowapi.util.get_ipaddr` (trusts headers unconditionally). The actual uvicorn flag flip is a deploy-config change, not a code change, and is gated on the first non-localhost promotion — the runbook is now the single source of truth for that gate.
- **MEDIUM-1 (multi-worker storage)**: in-memory bucket per worker → effective cap multiplies. Documented in the runbook + the `app/rate_limit.py` comment. `storage_uri=\"redis://…\"` migration prescribed before any `--workers N > 1` or horizontal scale.
- LOW-1 (singleton identity): added `test_rate_limit_singleton_identity` so a future refactor that re-binds the limiter cannot silently bypass the cap.
- LOW-2 (side-channel parity): documented in runbook §2a Gate 3 — IDOR exposure unchanged from CB-2117.

### Acceptance check (from ticket)
- [x] Per-route limit enforced on `POST /features/{id}/documentation/generate` with 429 when exceeded.
- [x] pytest covers the limit boundary (5 successes + 1 throttled in <60s) — see `test_generate_feature_documentation_rate_limit_boundary`.
- [x] Documentation runbook references the limit and the long-term plan — `backend/docs/DOC_PIPELINE_RUNBOOK.md`.

### Pre-deploy checklist (for Eli's QA)
- Promotes safely on localhost / single-tenant — all gates met.
- **Before any public / multi-tenant exposure** — execute `DOC_PIPELINE_RUNBOOK.md §2a` Gates 1 + 2.

Status → COMPLETED_WAITING_QA.
"""

req = urllib.request.Request(
    URL,
    data=json.dumps({"content": BODY, "author": "Jonny"}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    print(resp.status, resp.read().decode("utf-8")[:300])
