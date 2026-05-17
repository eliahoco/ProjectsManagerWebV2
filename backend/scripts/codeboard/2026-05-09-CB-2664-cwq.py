"""Mark CB-2664 COMPLETED_WAITING_QA + post audit comment."""
import json
import urllib.request

API = "http://localhost:8401/api"
ISSUE_ID = "556e3eac-3188-4085-8be4-9d599f7c8c04"  # CB-2664


def patch(payload: dict) -> None:
    req = urllib.request.Request(
        f"{API}/issues/{ISSUE_ID}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        print("PATCH", resp.status, resp.read().decode("utf-8")[:200])


def comment(body: str) -> None:
    req = urllib.request.Request(
        f"{API}/issues/{ISSUE_ID}/comments",
        data=json.dumps({"content": body, "author": "AI"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print("COMMENT", resp.status, resp.read().decode("utf-8")[:200])


AUDIT = """**CB-2664 implementation summary**

**Fix:** `frontend/components/service-monitor.tsx` — `RagStatusCard` useEffect now hoists the polling interval into a closure-scoped `intervalRef`. On `visibilitychange` → visible the handler `clearInterval`s the current interval, fires `fetchStatusRef.current()`, then re-arms `setInterval(tick, RAG_STATUS_POLL_MS)`. Visibility-return now re-anchors the 30 s cadence on the refresh fetch, eliminating the prior near-duplicate fetch when returning late in the cycle.

**Regression test:** `frontend/__tests__/RagStatusCard-visibility-reset.test.tsx` — uses `vi.useFakeTimers`, mocks `document.hidden`/`visibilityState`, advances ~29 s, dispatches hidden→visible, asserts:
- visibility-return fires exactly +1 `/api/system/rag/status` fetch
- next scheduled fetch is a full RAG_STATUS_POLL_MS away (no residual ~1 s tick)

**Audit gates:**
- ✅ code-reviewer: no CRITICAL/HIGH/MEDIUM/LOW findings; INFO-only — fix correct, cleanup safe, no leak; pre-existing in-flight overlap noted as out-of-scope cosmetic
- ✅ security-auditor: zero findings (CRITICAL/HIGH/MEDIUM/LOW); attacker cannot script `document.hidden`; new pattern strictly safer than previous on upstream fan-out
- ✅ vitest full run: 477 pass; 2 pre-existing Playwright config failures in `tests/regression/` unrelated
- ✅ new CB-2664 regression test passes
- ✅ `tsc --noEmit` clean for service-monitor.tsx (pre-existing errors elsewhere unrelated)

→ COMPLETED_WAITING_QA."""


if __name__ == "__main__":
    comment(AUDIT)
    patch({"status": "COMPLETED_WAITING_QA"})
