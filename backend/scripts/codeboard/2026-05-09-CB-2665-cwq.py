"""Mark CB-2665 COMPLETED_WAITING_QA + post audit comment."""
import json
import urllib.request

API = "http://localhost:8401/api"
ISSUE_ID = "c480c687-3a99-4d3c-84ba-5d4a792e7ebe"  # CB-2665


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


AUDIT = """**CB-2665 implementation summary**

**Decision:** Option B — flag-day rename, no back-compat alias. The endpoint perimeter (loopback bind in `launch.sh:128-129`, `validate_origin` middleware in `app/main.py:383-400`, single in-tree consumer `service-monitor.tsx`) makes a deprecation window pointless; option A would add a second name on the wire for the redaction reviewer to police on every future change with no external consumer to protect.

**Files changed:**
- `docs/runbooks/2026-05-09-rag-status-host-endpoint-rename.md` (new) — migration note documenting the `host` -> `endpoint` rename, perimeter rationale, the `endpoint`-blank cosmetic failure mode for any stale `host`-keyed consumer, and the revisit conditions (would only re-open if an external consumer ships against `/api/system/rag/status`).
- `backend/api/system.py` — `RagStatusResponse.endpoint` Field description extended with a `CB-2665:` clause pointing at the new runbook. No shape / route / behavior change. OpenAPI description gains a runbook reference; reviewed for disclosure (no abspath, no CUID, no novel attack surface).

**Audit gates:**
- ✅ code-reviewer: zero CRITICAL/HIGH/MEDIUM. One LOW (L1) — runbook wording overstated `extra="forbid"` coverage; tightened to clarify the forbid is on `RagCollectionStatus`, not `RagStatusResponse`. Re-verified clean post-fix.
- ✅ security-auditor: zero CRITICAL/HIGH/MEDIUM/LOW. Verified CB-2216 abspath redaction + CB-2217 collection-name redaction remain intact on the wire; runbook does not re-expose anything those tickets removed; OpenAPI Field description gains only a repo-relative runbook path (INFO-only).
- ✅ Syntax: `python3 -c "import ast; ast.parse(open('api/system.py').read())"` — clean.
- ✅ Cross-checks: `service-monitor.tsx` consumes only `endpoint`; `RagStatusResponse` has no `host` field, no `Field(alias=...)`; `services/rag_service.py` payload builder emits `"endpoint"` key consistently; `launch.sh:128-129` loopback bind claim verified.

→ COMPLETED_WAITING_QA."""


if __name__ == "__main__":
    comment(AUDIT)
    patch({"status": "COMPLETED_WAITING_QA"})
