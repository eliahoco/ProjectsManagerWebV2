"""
Push CB-XXXX: Bulletproof AutoPilot — comprehensive resilience FEATURE.

Supersedes CB-1951 scope (which was too narrow). Goal: once AutoPilot starts,
it survives ANY interruption (power cut, OS reboot, backend restart, token
exhaustion, network blip, OOM kill, disk full, signal kill, unhandled
exception) and completes the work.

Eli explicit approval (2026-05-09): "I want a fix for that. Implement it
and run it. I'm leaving the computer. I'm gonna come back when everything
is perfectly working. Don't forget to audit code, security audit, and also
Chrome user experience testing."
"""
from __future__ import annotations
import json, urllib.request, urllib.error

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
LABELS_BASE = "🚀-bulletproof-autopilot,resilience,supersedes-cb-1951"


def http(m, p, b=None):
    data = json.dumps(b).encode() if b else None
    req = urllib.request.Request(f"{BASE}{p}", data=data,
                                  headers={"Content-Type": "application/json"}, method=m)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:300]}")
        raise


def find_id(key):
    for page in range(1, 50):
        r = http("GET", f"/projects/{PROJECT_ID}/issues?page={page}&pageSize=200")
        for x in r.get("items", []):
            if x.get("key") == key:
                return x["id"]
        if page >= r.get("totalPages", 1):
            break
    return None


def create(parent_id, type_, title, desc, priority, assignee, extra_label=""):
    labels = LABELS_BASE + ("," + extra_label if extra_label else "")
    body = {
        "title": title, "description": desc, "type": type_, "priority": priority,
        "reporter": "AI", "labels": labels, "status": "BACKLOG",
        "assignee": assignee,
    }
    if parent_id:
        body["parentId"] = parent_id
    return http("POST", f"/projects/{PROJECT_ID}/issues", body)


FEATURE_DESC = """## Mission

Once AutoPilot starts, it MUST survive any interruption and complete the work.
No more "queue disappeared" / "stuck in failed" / "ghost running" moments.

## Failure modes to survive (all)

1. Backend graceful shutdown (SIGTERM)
2. Backend SIGKILL (force)
3. Backend OOM kill
4. Backend uncaught exception
5. OS reboot mid-task (power cut, kernel panic, scheduled restart)
6. Anthropic API token exhaustion / rate limit (429, 529)
7. Anthropic API auth/credit failure (401)
8. Network blip (ECONNREFUSED, timeout)
9. Disk full during DB write
10. Subprocess SIGKILL (claude CLI killed externally)
11. Frontend disconnect mid-flow (SSE drops)
12. Multiple concurrent resume calls (race)

For each: queue state must be **recoverable + resumable** with a single user action (Resume button) or auto-recovery on backend startup.

## Why this supersedes CB-1951

CB-1951 was scoped to "pause/resume + crash recovery" but in production has failed multiple times:
- CB-2671: empty key/title on rehydrate (fixed)
- CB-2671 follow-up: same bug in create-queue path (fixed)
- CB-2737/CB-2743/CB-2744/CB-2745: reset endpoint, current_index, in-memory-only lookups, get_or_load_queue (fixed)
- TODAY (2026-05-09): credit exhaustion → tasks marked failed (not WAITING_RESET) → queue zombie running with no live coroutine → invisible to recovery-status

Pattern: each fix solved the immediate symptom but never the systemic guarantee. This feature fixes the guarantee.

## High-level scope

- E1 Research + state-machine design (formal model — no code)
- E2 Persistence overhaul (atomic writes, journal mode, write-ahead log, crash-safe checkpoints)
- E3 Token/credit exhaustion detection (broad pattern matching, exit code + output)
- E4 Recovery scheduler (rehydrate ALL non-terminal queues; scan zombie running; auto-resume after token reset)
- E5 UI surface (banner for every recoverable state; status badges; retry per-task; force-recover)
- E6 Chaos test suite (kill -9 mid-task; OOM; disk full simulation; token exhaust simulation; SSE drop)
- E7 Audits (code-reviewer + security-auditor)
- E8 Chrome QA full regression (every banner state + recovery action)
- E9 Rollout (migration + 24h soak)

Sequencing: E1 → E2/E3/E4 (parallel) → E5 → E6 → E7 → E8 → E9.

## Bible compliance

- Rule 18: 4-gate audit mandatory
- Rule 22: never DONE except by Eli
- Rule 23: full plan before any code (THIS ticket)
- Rule 25: full chaos regression mandatory before CWQ — no whack-a-mole
- Rule 27: durable artifacts in docs/plans/
- Rule 29: scripts in backend/scripts/codeboard/

## Linked

- Supersedes scope of CB-1951 (CWQ — keeps as historical reference)
- Closes (operationally) CB-2671, CB-2737, CB-2743, CB-2744, CB-2745, CB-2683 (security follow-ups)
- Blocks CB-2384 confidence (workspace can't ship until autopilot is bulletproof)
"""


def main():
    print("Creating bulletproof FEATURE...")
    f = create(None, "FEATURE",
               "Bulletproof AutoPilot — survive ANY interruption + complete work (supersedes CB-1951 scope)",
               FEATURE_DESC, "CRITICAL", "Eli", extra_label="feature-root")
    print(f"FEATURE → {f['key']} (id={f['id']})")
    fid = f["id"]

    # IssueLink to CB-1951 (supersedes scope)
    cb1951 = find_id("CB-1951")
    if cb1951:
        try:
            http("POST", f"/issues/{fid}/relations", {"toIssueId": cb1951, "linkType": "RELATES_TO"})
            print("Linked RELATES_TO → CB-1951")
        except Exception as e:
            print(f"  (link skip: {e})")

    epics = [
        ("[E1] Research + State-Machine Design — no code, output is design doc", "CRITICAL", "llm-architect",
         "Map ALL failure modes (12 listed in feature). Map current state machine vs target state machine. Document persistence guarantees needed. Output: design doc at docs/plans/2026-05-09-bulletproof-autopilot-design.md. NO code in this epic."),
        ("[E2] Persistence overhaul — atomic writes, WAL, crash-safe checkpoints", "CRITICAL", "python-pro",
         "Audit current AutoPilotQueueRecord + AutoPilotTaskRecord write paths. Ensure: SQLite WAL mode enabled; every state transition flushed before next step; checkpoint per task completion (not just queue-level). Survive OS-level kill at any point."),
        ("[E3] Token/credit exhaustion detection — broad pattern matching", "CRITICAL", "python-pro",
         "Current is_token_exhaustion() patterns missed today's case (CB-2731/2732 both got 'Process exited with code 1'). Broaden detection: exit code 1 + scan last N lines of subprocess stdout/stderr for: rate_limit_error, overloaded_error, 429, 529, 401, credit balance, anthropic.RateLimitError, etc. On match: pause queue with WAITING_RESET, schedule auto-resume."),
        ("[E4] Recovery scheduler — rehydrate ALL non-terminal queues", "CRITICAL", "python-pro",
         "On backend startup: load EVERY non-terminal queue (running, paused, WAITING_RESET) into memory. Scan for zombie 'running' queues with no live coroutine → reclassify as paused/recovery. Background scheduler ticks every 60s: check WAITING_RESET queues for reset-time elapsed → auto-resume."),
        ("[E5] UI surface — banner for every recoverable state", "HIGH", "react-specialist",
         "Recovery banner must show for: paused/manual, paused/crash_recovery, paused/token_exhaustion (with countdown), zombie/no-coroutine, partial-failure-stuck. Each with appropriate action: Resume / Wait+AutoResume / Recover / Retry-Failed / Abort. Plus status badge per queue showing current resilience state."),
        ("[E6] Chaos test suite", "HIGH", "debugger",
         "Test harness that simulates: kill -9 backend mid-task, kill -9 claude CLI mid-task, simulated OOM via memory pressure, simulated disk full via mock, token exhaust via mock anthropic 429 response, SSE drop via network mock, double-resume race. For each: assert queue self-recovers + completes. Mandatory before CWQ."),
        ("[E7] Audits — code-reviewer + security-auditor", "HIGH", "code-reviewer",
         "Standard 2-gate audit per Rule 18. Findings filed as child BUGs."),
        ("[E8] Chrome QA full UI regression — every banner state", "HIGH", "debugger",
         "End-to-end via chrome-devtools-mcp: trigger each failure mode → confirm UI banner shows correctly → click action → confirm queue state advances. Mandatory before CWQ. Eli's bar: 'I'm coming back when everything is perfectly working.'"),
        ("[E9] Rollout — migration + 24h soak + flag-removal", "MEDIUM", "devops-engineer",
         "Apply any new migrations idempotently. Run 24h soak (normal usage); fix any regressions found. Remove WORKSPACE_ENABLED-style flag if used."),
    ]

    epic_keys = []
    for title, prio, assignee, desc in epics:
        e = create(fid, "EPIC", title, desc, prio, assignee, extra_label="epic")
        epic_keys.append((title.split("]")[0].lstrip("["), e["key"]))
        print(f"  EPIC {e['key']}: {title[:70]}")

    print()
    print(f"FEATURE: {f['key']}")
    print(f"EPICS: {len(epic_keys)}")
    for code, key in epic_keys:
        print(f"  {code} = {key}")


if __name__ == "__main__":
    main()
