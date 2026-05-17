"""Mark CB-2219 COMPLETED_WAITING_QA + post completion comment.

CB-2219: chroma migration runbook tar extraction not hardened.
Doc-only change to docs/runbooks/2026-05-02-chroma-volume-migration.md.
"""
import json
import urllib.request

API = "http://localhost:8401/api"
ISSUE_ID = "de62660e-2649-49b5-bb62-88349c64ef57"  # CB-2219

COMMENT = """### CB-2219 — Hardened — ready for QA

**Change:** `docs/runbooks/2026-05-02-chroma-volume-migration.md` step 3.

**What changed**
- Added `apk add --no-cache tar` to the alpine helper so GNU tar replaces BusyBox tar before extraction (BusyBox errors out on the long options below, doesn't honour them).
- Extraction line now: `tar xf - -C /dest --no-same-owner --no-overwrite-dir --anchored`.
- Added a comment block above the invocation explaining BusyBox vs GNU tar permissiveness and what each flag mitigates.

**No change to the already-executed run** — the original migration was a copy, not a move; the source `backend/data/chroma/` is untouched and rollback path in §Rollback is unaffected.

**Audit gates**
- Functional dry-run: `docker run --rm alpine:3.20 sh -c 'apk add --no-cache tar >/dev/null && tar --version'` → GNU tar 1.35; all four flags accepted with no parse errors against a sample tarball.
- code-reviewer: passed after a tightening pass — softened the BusyBox `..` claim, dropped overstated "silently ignores" wording, replaced `--anchored` justification with an honest "no-op today, future-proofing" line.
- security-auditor: not re-run — this ticket IS the response to security-auditor's L-1 finding on CB-2049.
- Chrome / regression: N/A — docs-only.

**Notes for QA**
1. Re-read the comment block lines 66-91 — verify the wording matches what you'd expect a future operator to need to know before re-using the runbook.
2. If you re-execute the runbook against a fresh empty volume (rollback drill), step 3 should now print `(1/1) Installing tar (1.35-r2)` and complete with no traversal warnings.
"""

def patch_status(issue_id: str, status: str) -> dict:
    req = urllib.request.Request(
        f"{API}/issues/{issue_id}",
        data=json.dumps({"status": status}).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def post_comment(issue_id: str, body: str) -> dict:
    req = urllib.request.Request(
        f"{API}/issues/{issue_id}/comments",
        data=json.dumps({"content": body, "author": "Jonny"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

if __name__ == "__main__":
    try:
        c = post_comment(ISSUE_ID, COMMENT)
        print("comment posted:", c.get("id"))
    except Exception as exc:
        print("comment post failed:", exc)
    s = patch_status(ISSUE_ID, "COMPLETED_WAITING_QA")
    print("status now:", s.get("status"))
