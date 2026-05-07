"""Mark CB-2004 (bulk-add modal) COMPLETED_WAITING_QA.

Per Bible Rule 22: code complete → COMPLETED_WAITING_QA, never DONE.
Per Bible Rule 29: per-project per-session script path (not /tmp/).
"""
import json
import urllib.request

API = "http://localhost:8401/api"
ISSUE_ID = "45697c19-5774-407c-abc5-8e6976fb8ff7"  # CB-2004

payload = json.dumps({
    "status": "COMPLETED_WAITING_QA",
    "implementationSummary": (
        "Extended AddRelationModal with multi-select bulk-add "
        "(CB-2004). Routes by selection count: n=1 keeps the single "
        "/relations endpoint (preserves CYCLE/DUPLICATE error mapping); "
        "n>=2 fires POST /relations/bulk via new useCreateRelationsBulk "
        "hook, which fans out cache invalidation across every requested "
        "target. Bulk responses with any skipped row stay open and "
        "render the skipped chips inline grouped by reason "
        "(DUPLICATE / CYCLE). Hardened the close+reopen race with a "
        "per-mutation submitTokenRef and capped client-side at 100 "
        "targets to mirror the backend cap. 17 unit tests "
        "(11 pre-existing + 6 new for bulk paths) all green."
    ),
    "technicalApproach": (
        "Files changed: "
        "frontend/components/codeboard/AddRelationModal.tsx (rewrite), "
        "frontend/hooks/useCodeBoard.ts (added useCreateRelationsBulk), "
        "frontend/types/codeboard.ts (bulk request/response types), "
        "frontend/tests/components/AddRelationModal.test.tsx "
        "(extended to 17 tests). "
        "Code review: 2 HIGH findings (close→reopen stale closure + "
        "double onSuccess in mixed bulk) — both fixed pre-CWQ. "
        "Security audit: clean, no CRITICAL/HIGH; one LOW (chip width "
        "bound) addressed. Backend bulk endpoint already shipped under "
        "CB-1972 — no backend changes."
    ),
}).encode()

req = urllib.request.Request(
    f"{API}/issues/{ISSUE_ID}",
    data=payload,
    method="PATCH",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as r:
    body = r.read().decode()
    print(f"HTTP {r.status}")
    print(body[:600])
