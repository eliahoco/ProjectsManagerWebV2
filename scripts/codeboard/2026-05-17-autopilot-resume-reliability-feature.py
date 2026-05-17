"""
File FEATURE + 6 child STORIES for the AutoPilot resume/recovery refactor
that emerged from the LINK-124 deep-dive (3 agent reports + Atlas).

Anchor incident: queue 1d0304d2-fa15-4fd0-ad32-529f19dae96f stuck.
- Resume → 400
- 7 tasks failed (undetected token exhaustion)
- Circuit breaker emits event every 60s for 20+ minutes
- recovery-status reports state='running' while DB says waiting_reset
- clear-recovery is a no-op
- 6 confirmed independent root causes, all converged

Order of work (dependency-correct):
  S1 (L2)  Persist auto_resume_attempts to DB
  S2 (L3)  Make circuit-breaker a terminal transition
  S3 (L4)  Resume endpoint contract + retry failed tasks
  S4 (L1)  Canonical state transitions (largest refactor)
  S5 (L6)  Single source of truth for recovery-status state
  S6 (L5)  Token-exhaustion detection robustness
"""
import json, urllib.request, sys

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"


FEATURE_TITLE = (
    "AutoPilot Resume / Recovery Reliability — structural refactor"
)
FEATURE_DESCRIPTION = """## Why

Queue `1d0304d2-fa15-4fd0-ad32-529f19dae96f` (feature LINK-124, sibling
project LinkedInJobHunterProduction) hit token exhaustion mid-run, never
recovered, and now leaks a `auto_resume_circuit_breaker_tripped` event
every 60 seconds. Three independent agent investigations (general-purpose
data-flow map, debugger root-cause graph, code-reviewer structural review)
converged on the same six root causes. This FEATURE delivers the
structural refactor; LINK-124 is unblocked as a side effect of S3.

## Six confirmed root causes

- **RC1** Circuit-breaker trip mutates `pause_reason='manual'` but leaves
  `queue.status=WAITING_RESET`. Tick loop predicate matches forever; event
  re-fires every 60 s. `autopilot_queue_service.py:764-768`.
- **RC2** `auto_resume_attempts` has no DB column. Resets to 0 on every
  backend restart, defeating the circuit breaker entirely. Plus: counter is
  incremented BEFORE the cap check, so it can pass the threshold during a
  single resume attempt. `autopilot_repository.py:save_queue` (column absent)
  and `autopilot_queue_service.py:2354`.
- **RC3** `_find_next_pending` only matches `TaskStatus.PENDING`. When all
  remaining tasks are `FAILED` (7 of 22 on LINK-124), resume returns False
  → API 400. Failed tasks have no retry path through the Resume button.
  `autopilot_queue_service.py:2373-2394`.
- **RC4** `detect_exhaustion_from_session` scans last 4 KB of CLI output.
  Claude CLI dumps 40-200 KB of tool output; token-exhaustion marker
  scrolls out of window. Systemic fallback uses 60s window — tasks run
  2-15 min, so 3 failures in 60s is mathematically impossible.
  `exhaustion_detector.py:432-475` + `autopilot_queue_service.py:347`.
- **RC5** `clear_recovery_state` is a 1-line no-op
  (`self._recovered_queue_ids.discard(qid)`). Doesn't touch DB, doesn't
  cancel timers, doesn't remove from `_zombie_queue_ids` or `_queues`.
  Returns `{ok:true}` while doing nothing. `autopilot_queue_service.py:889-891`.
- **RC6** `recovery-status` hard-codes `"state": "running"` for zombies and
  `"state": "waiting_reset"` for auto-resume-pending, ignoring the actual
  DB row. Three sources of truth for one field. `api/execution.py:1090,1102`.

## Load-bearing assumption that's broken

> "If a queue is in `self._queues`, it's healthy. If a transition function
>  gets called, it succeeds."

Wrong because 16 sites mutate `queue.status = X` directly bypassing
`transition_state()`. Callers wrap `IllegalStateTransitionError` in
`try/except: log+continue`. Memory and DB drift silently. DB is supposed
to be source of truth but is rarely consulted post-startup.

## Out of scope (separate features)

- Multi-project queue isolation (`_active_queue_id` is global today).
- Per-task force-retry UI flow on the AutoPilot panel.
- Webhook-driven resume (e.g. github push triggers resume of a paused
  queue).

## Deliverables (six child STORIES)

S1 → S6 in dependency order. Each STORY has its own acceptance gates:
unit tests for the RC's deterministic repro recipe, code-reviewer gate,
security-auditor gate (where applicable), integration test of the full
"crash → restart → resume → success" flow.

LINK-124 unblock is validated as the end-to-end regression for S3.
"""


STORIES = [
    {
        "title": "S1 — Persist auto_resume_attempts to DB (and fix increment ordering)",
        "priority": "HIGH",
        "assignee": "python-pro",
        "description": """## Bug

`auto_resume_attempts` is a dataclass field that lives only in memory.
There is no column for it in `AutoPilotQueueRecord`. On every backend
restart, `_record_to_queue` rebuilds the queue with `auto_resume_attempts=0`
(dataclass default). Result: the `_AUTO_RESUME_MAX_ATTEMPTS=3` circuit
breaker is **silently defeated** any time the backend restarts during a
waiting_reset.

Compounding: in `resume_queue` the counter is incremented BEFORE the
cap check (line 2354 → 2357). The 4th tick increments to 4, then the
cap check at 2357 catches it — but the increment already happened. The
tick-loop fast path at line 758 also reads `attempts > MAX` after the
increment.

## Scope

1. Add `autoResumeAttempts INTEGER NOT NULL DEFAULT 0` to
   `AutoPilotQueueRecord` (SQLAlchemy + Prisma mirror + migration).
2. `save_queue` writes it. `_record_to_queue` reads it.
3. Move the increment in `resume_queue` to AFTER the cap check. Same for
   `_fire_auto_resume`.
4. Add `recent_failures` and `_appended_count` persistence consideration
   (decide: persist or accept they reset on restart).

## Acceptance criteria

- [ ] Migration created and applied to dev.db (and a backfill safeguard
      for existing rows — default 0).
- [ ] `save_queue → fresh service → rehydrate → queue.auto_resume_attempts
      equals persisted value` — new unit test.
- [ ] Cap check fires AFTER increment, so increment never exceeds the cap.
- [ ] No regression on existing `test_auto_resume_scheduler.py` cases.

## Lineage

Discovered by debugger agent during LINK-124 deep-dive (RC2).
""",
    },
    {
        "title": "S2 — Make circuit-breaker a terminal state transition (stop 60s event spam)",
        "priority": "CRITICAL",
        "assignee": "python-pro",
        "description": """## Bug

When `auto_resume_attempts > _AUTO_RESUME_MAX_ATTEMPTS`, three code paths
(`_recovery_tick_once:764`, `resume_queue:2357`, `_fire_auto_resume:2730`)
set `queue.pause_reason='manual'` but **leave `queue.status` as
WAITING_RESET**. The 60s recovery tick predicate is:

```python
if queue.status != QueueStatus.WAITING_RESET: continue   # line 750
if queue.reset_time > lookahead: continue
if qid in self._resume_handles: continue
if queue.auto_resume_attempts > MAX:
    queue.pause_reason = "manual"
    self._persist_async(queue, "auto_resume_circuit_breaker_tripped", ...)
    continue                                              # never exits the queue from the loop
```

Same queue re-matches on the next tick. Forever. Evidence: LINK-124 has
20+ `auto_resume_circuit_breaker_tripped` events at exact 60s cadence.

## Scope

When the breaker trips:
- Transition `WAITING_RESET → PAUSED` (paired with
  `pause_reason='manual_circuit_breaker'`) via `transition_state`.
- Emit `auto_resume_circuit_breaker_tripped` event EXACTLY ONCE
  (idempotent — guarded on `pause_reason` already being the breaker value).
- Cancel any live `_resume_handles[qid]` timer.
- Tick predicate at 750 stops matching because status is now PAUSED.

## Acceptance criteria

- [ ] After breaker trips, queue.status is `PAUSED` in both memory + DB.
- [ ] Subsequent tick iterations do NOT re-emit the event.
- [ ] Resume from the breaker-tripped state requires user action (manual
      resume), per the runbook.
- [ ] New unit test: `test_circuit_breaker_trip_is_terminal` — simulates
      4 ticks, asserts EXACTLY ONE breaker event and final status=PAUSED.

## Lineage

Discovered by debugger + code-reviewer agents during LINK-124 deep-dive
(RC1).
""",
    },
    {
        "title": "S3 — Resume endpoint contract + retry failed tasks (unblocks LINK-124)",
        "priority": "CRITICAL",
        "assignee": "python-pro",
        "description": """## Bug

Two issues collide:

**(a) `_find_next_pending` only matches `TaskStatus.PENDING`.** With all
remaining tasks `FAILED` (e.g. LINK-124 has 15 completed + 7 failed),
`pending_orders` is `[]`, `_find_next_pending` returns None,
`resume_queue` returns False (line 2394), API returns 400. The user
literally cannot resume their feature without DB surgery.

**(b) Resume endpoint returns 400 for every failure mode.** Missing
queue, wrong state, breaker-tripped, no pending tasks all collapse to
the same generic 400 with no `pause_reason` or `auto_resume_attempts`
in the body. UI cannot tell user *why* and *what to do*.

## Scope

1. New endpoint: `POST /api/execute/queue/{queue_id}/reset-failed-tasks`.
   Marks all `failed` tasks in the queue back to `pending`, clears
   their `failureReason`. Returns `{reset_count, task_ids}`.
2. New endpoint optional flag on resume:
   `POST /api/execute/queue/{queue_id}/resume?retry_failed=true` —
   atomically resets failed → pending, then resumes. Saves a round trip.
3. Resume endpoint contract:
   - 404 NOT_FOUND — queue does not exist in DB.
   - 409 CONFLICT — wrong state or breaker tripped. Body includes
     `pause_reason`, `auto_resume_attempts`, `current_index`,
     `pending_count`, `failed_count`, `suggestion`.
   - 200 OK — resumed.
4. Frontend `AutoPilotFloatingBar.tsx`: when 409 received with non-zero
   `failed_count`, show "X tasks failed — Retry & Resume" button that
   calls `?retry_failed=true`.

## Acceptance criteria

- [ ] LINK-124 queue can be unblocked by clicking Retry & Resume in UI.
- [ ] All 7 failed tasks re-run cleanly to completion (verified by
      monitoring queue events post-resume).
- [ ] `test_resume_with_all_failed_returns_409_with_retry_hint` passes.
- [ ] `test_reset_failed_tasks_endpoint_marks_pending_and_keeps_completed`
      passes.
- [ ] `test_retry_failed_resume_flow` integration test passes
      end-to-end.

## Lineage

Discovered by debugger agent during LINK-124 deep-dive (RC3). This is
the user-facing unblock. Validate by unblocking the real LINK-124 queue
as part of QA.
""",
    },
    {
        "title": "S4 — Canonical state transitions via transition_state() — eliminate 16 direct mutations",
        "priority": "HIGH",
        "assignee": "python-pro",
        "description": """## Bug

`transition_state` (`autopilot_repository.py:374-440`) was introduced as
"the only authorised path to write status". In practice, **16 call sites
in `autopilot_queue_service.py` directly mutate `queue.status = X`**
(lines 1004, 1023, 1034, 1105, 1122, 1163, 1192, 1226, 1258, 1852, 2077,
2089, 2311, 2513, 2607, and `pause_queue:2311`). Every authorised call
is wrapped in `try/except IllegalStateTransitionError: log+continue`.

Result:
- The allow-list at `models/autopilot.py:69-86` enforces nothing.
- In-memory dataclass advances even when DB write fails or transition
  is illegal.
- DB and memory drift silently.
- `pause_queue` skips `transition_state` entirely → no STATE_TRANSITION
  audit event for manual pauses.

## Scope

1. Make `transition_state` write DB FIRST (atomic with event) then mutate
   memory ONLY on success. If DB write fails, memory is NOT mutated.
2. Replace every `queue.status = X` mutation with
   `await self._transition(qid, X, reason)`.
3. `IllegalStateTransitionError` becomes a real failure (not swallowed).
   The 16 callers must either know the transition is legal (most do —
   they're well-defined state-machine moves) or handle the error
   explicitly.
4. `pause_queue` routes through `transition_state` (currently bypasses it).

## Acceptance criteria

- [ ] Zero direct `queue.status = X` mutations remain in `autopilot_queue_service.py`
      (enforced by lint rule or test that greps the file).
- [ ] All state changes appear in `AutoPilotEvent` with type `STATE_TRANSITION`.
- [ ] DB and in-memory `queue.status` agree at all times (verified by
      `test_transition_atomicity` — kill the DB mid-transition, assert
      memory not mutated).
- [ ] `pause_queue` emits a STATE_TRANSITION event.

## Lineage

Discovered by code-reviewer agent during LINK-124 deep-dive. Largest
refactor in this feature — sequenced last among the must-haves so smaller
fixes don't have to land on shifting ground.
""",
    },
    {
        "title": "S5 — Single source of truth for state in recovery-status; fix clear_recovery_state no-op",
        "priority": "MEDIUM",
        "assignee": "python-pro",
        "description": """## Bug

`api/execution.py:1031-1119` (recovery-status endpoint) reports queue
state from three different sources:
- `auto_resume_pending` list hard-codes `"state": "waiting_reset"`
  regardless of actual queue.status (line 1102).
- `zombie` list hard-codes `"state": "running"` (line 1090).
- Backward-compat `queues` list reads `queue.status.value` from memory.

A queue that's `paused` in DB can appear as `running` in `zombie`,
`waiting_reset` in `auto_resume_pending`, and `paused` in `queues` —
all in the same response. UI consumers pick whichever they read first
and misrepresent state.

`clear_recovery_state` (line 889-891) is a one-liner:
```python
self._recovered_queue_ids.discard(queue_id)
```
Doesn't touch DB, doesn't cancel auto-resume timer, doesn't remove from
`_queues` or `_zombie_queue_ids`. Returns `{ok:true}` (line 1126) while
the queue keeps ticking. False UX promise.

## Scope

1. recovery-status: always derive `state` from a single helper
   `_serialize_queue(queue)` that reads `queue.status.value` (in-memory
   after `get_or_load_queue`). No hard-coded overrides.
2. `clear_recovery_state` actually clears: cancel auto-resume timer if
   live, remove from `_recovered_queue_ids` AND `_zombie_queue_ids`,
   transition queue to `paused` with `pause_reason='manual_cleared'`,
   persist.
3. `get_queue_status` adds DB fallback via `get_or_load_queue`
   (currently returns 404 for DB-only queues — line 2226).

## Acceptance criteria

- [ ] `recovery-status` returns the same `state` for a queue across all
      three sub-lists (`recoverable`, `zombie`, `auto_resume_pending`),
      and that state matches the DB row.
- [ ] `clear_recovery_state` post-call: queue is `paused` in DB,
      auto-resume timer cancelled, not in `_zombie_queue_ids`.
- [ ] `get_queue_status(qid)` on DB-only queue returns full status
      (not 404).

## Lineage

Discovered by debugger + code-reviewer during LINK-124 deep-dive (RC5, RC6).
Depends on S4 for the transition primitive.
""",
    },
    {
        "title": "S6 — Token-exhaustion detection robustness (tail-window + systemic-window)",
        "priority": "HIGH",
        "assignee": "python-pro",
        "description": """## Bug

Two windowing problems in token-exhaustion detection:

**(a) Tail-window too small.** `detect_exhaustion_from_session` scans the
last 80 lines / 4 KB of CLI output. Claude CLI can dump 40-200 KB of
tool output AFTER an internal HTTP error. The token-exhaustion marker
(`rate_limit_error`, `usage limit`, `429`, etc.) scrolls out of the window.
Detector returns None. Task is marked `failed` instead of triggering
waiting_reset pause.

**(b) Systemic-failure window too short.** When the primary detector
misses, `_is_systemic_failure` (line 1171-1231) is supposed to catch
"3 identical failures in 60 s" via `_SYSTEMIC_FAILURE_WINDOW_SECONDS=60`.
Tasks run 2-15 minutes. Three failures in 60 s is mathematically
impossible at this cadence. LINK-124 burned through 7 sequential
failures over ~80 minutes; the heuristic never fired.

## Scope

1. `terminal_service` adds an exhaustion-signal buffer per session: any
   line matching the JSON regex `{"type": "error", ...}` OR the
   signal-set regex is appended to a dedicated list regardless of
   position in the stream. Feed THIS to `detect_exhaustion` instead of
   relying on the tail window.
2. Replace the duration-based systemic threshold with a
   **consecutive-failures** heuristic: 3 consecutive failures with the
   same normalised error AND no successes in between → category
   `unknown_systemic`, pause queue. Duration-independent.
3. Keep the duration-based heuristic as a secondary defense — widen
   `_SYSTEMIC_FAILURE_WINDOW_SECONDS` from 60 to 1800 (30 min).

## Acceptance criteria

- [ ] New unit test: `test_exhaustion_detected_when_marker_buried_in_long_output`
      — feed 200 KB of output where the marker is in the first 4 KB,
      assert detection succeeds.
- [ ] `test_systemic_failure_three_consecutive_minutes_apart` — three
      failures 5 minutes apart with no success between, assert detector
      fires.
- [ ] `test_systemic_failure_cleared_by_success` — failure / success /
      failure / failure / failure should NOT trip (success cleared the
      streak).
- [ ] LINK-124 retrospective: re-feed the 7 captured outputs through the
      new detector and verify at least 1 would have triggered
      waiting_reset (proving the fix actually helps).

## Lineage

Discovered by general-purpose + code-reviewer agents during LINK-124
deep-dive (RC4). Most isolated of the six — can ship in parallel with
others once S1 (counter persistence) is in.
""",
    },
]


def call(method, path, body=None):
    headers = {"Content-Type": "application/json"} if body else {}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def main():
    feature = call("POST", f"/projects/{PROJECT_ID}/issues", {
        "title": FEATURE_TITLE,
        "description": FEATURE_DESCRIPTION,
        "type": "FEATURE",
        "priority": "HIGH",
        "labels": "autopilot,resume-recovery,link-124,structural-refactor",
        "assignee": "python-pro",
        "reporter": "AI",
    })
    feature_id = feature["id"]
    print(f"Created FEATURE {feature['key']} (id={feature_id})")

    created = []
    for idx, story in enumerate(STORIES, 1):
        body = {
            "title": story["title"],
            "description": story["description"],
            "type": "STORY",
            "priority": story["priority"],
            "parentId": feature_id,
            "labels": f"autopilot,resume-recovery,link-124,layer-{idx}",
            "assignee": story.get("assignee", "python-pro"),
            "reporter": "AI",
        }
        s = call("POST", f"/projects/{PROJECT_ID}/issues", body)
        created.append((s["key"], story["title"][:60]))
        print(f"  → {s['key']}: {story['title'][:70]}")

    print(f"\nFEATURE: {feature['key']}")
    for k, t in created:
        print(f"  {k}  {t}")
    return feature["key"], feature_id, created


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        sys.exit(1)
