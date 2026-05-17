"""Mark CB-2783 COMPLETED_WAITING_QA after file-level invariant test ships.

CB-2783: backend/tests/test_security.py file-level invariant — every
router-decorated handler in api/search.py must carry InternalAuthDep +
@limiter.limit + @router-above-@limiter source order.

Implementation summary:
- Added module-level helper `_collect_router_handlers(file_path)` that
  AST-walks the target file and returns one record per
  `@router.<verb>(...)`-decorated function (discovery, not enumeration).
- Added test class `TestSearchPyFileLevelInvariant` with four tests:
    1. test_at_least_one_handler_present (sanity floor at >=6)
    2. test_every_handler_has_internal_auth_dep
    3. test_every_handler_has_limiter_limit
    4. test_every_handler_router_above_limiter_in_source

Verification:
- 4 new tests PASS, 102 existing perimeter tests PASS (test_security.py).
- Mutation tested helper against four bad shapes (missing dep, missing
  limit, inverted decorators, non-literal limit) — all caught.
- Full backend suite: 1115 PASS + 3 PRE-EXISTING failures unrelated to
  this change (test_qa_sequence + test_schema_validation, present on
  HEAD without my diff).

Audit gates:
- code-reviewer: SHIP — 4 polish nits, no blockers.
- security-auditor: SHIP — 3 LOW future-drift findings (router/limiter
  alias bypass, non-decorator registration paths) noted as
  recommendations for a complementary runtime-invariant follow-up.

Deferred (NOT in scope of CB-2783):
- Apply the same invariant to api/projects.py. `initialize_sequence`
  there carries InternalAuthDep but no @limiter.limit, so extending
  the invariant requires a decision on whether to add the write-cap
  (10/min) or explicitly exempt the handler. Helper is already
  file-agnostic; extension is one line of parametrize once decided.
"""

import json
import urllib.request

ISSUE_ID = "4411741e-ad16-496c-ba52-cdb83fe07b84"  # CB-2783
BASE = "http://localhost:8401/api"

req = urllib.request.Request(
    f"{BASE}/issues/{ISSUE_ID}",
    method="PATCH",
    headers={"Content-Type": "application/json"},
    data=json.dumps({"status": "COMPLETED_WAITING_QA"}).encode(),
)
with urllib.request.urlopen(req) as resp:
    body = resp.read().decode()
    print(f"HTTP {resp.status}")
    print(body[:500])
