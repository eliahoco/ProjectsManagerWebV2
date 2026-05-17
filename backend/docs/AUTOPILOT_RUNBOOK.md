# AutoPilot Operational Runbook (CB-1951)

This runbook covers diagnosis and recovery procedures for the AutoPilot
queue subsystem after the CB-1951 persistence + crash recovery work.

> Sister runbook: see `backend/docs/DOC_PIPELINE_RUNBOOK.md` for the
> FeatureDocumentation pipeline, including the per-route rate limit on
> `POST /api/features/{id}/documentation/generate` (CB-2662).

## TL;DR — common emergencies

| Symptom | Section |
|---|---|
| "Backend just crashed mid-AutoPilot" | [§1 Crash recovery](#1-crash-recovery-after-backend-restart) |
| "Queue stuck in WAITING_RESET forever" | [§2 Stuck WAITING_RESET](#2-queue-stuck-in-waiting_reset) |
| "Auto-resume keeps firing on a bad API key" | [§3 Circuit-breaker / runaway loop](#3-runaway-auto-resume-loop) |
| "I want to force-resume past the safety check" | [§4 Force-resume override](#4-force-resume-override) |
| "Need to inspect AutoPilot DB state" | [§5 SQL recipes](#5-sql-recipes) |

---

## 1. Crash recovery after backend restart

When the backend is killed mid-run (SIGKILL, OOM, manual stop), the
in-memory `_queues` dict is lost. On restart, the FastAPI lifespan hook
calls `autopilot_queue_service.rehydrate_from_db()` which:

1. Loads every non-terminal queue record from `AutoPilotQueueRecord`
2. Marks every `running` task as `failed` with reason `backend_crash_recovery`
3. Flips the queue itself to `paused` with `pauseReason='crash_recovery'`
4. Adds the queue to `get_recovered_queues()` so the frontend banner shows it

**The user must explicitly resume.** Crash recovery never auto-resumes
(we can't trust the subprocess actually died cleanly).

### Procedure

1. Open the dashboard. The AutoPilotFloatingBar should show an amber
   "AutoPilot recovered after backend restart" banner.
2. Click **Resume** to re-run the current task (it was marked failed at
   recovery; it will be retried fresh), **Skip** to advance to the next
   task, or **Abort** to terminate the queue.
3. If the banner doesn't appear: hit `GET /api/execute/queue/recovery-status`
   to confirm the backend has the queue in its recovery set.

### If the banner is wrong

If the banner shows but the queue should NOT be recovered (e.g. you
manually decided to abort), `POST /api/execute/queue/{id}/clear-recovery`
drops it from the recovery set.

---

## 2. Queue stuck in WAITING_RESET

Symptoms: AutoPilotFloatingBar shows the amber "Auto-resumes at HH:MM"
banner forever, or the countdown ticked past zero without resuming.

### Diagnose

```sh
sqlite3 frontend/prisma/dev.db "
SELECT id, status, pauseReason, resetTime, currentIndex, updatedAt
FROM AutoPilotQueueRecord
WHERE status = 'waiting_reset'
ORDER BY updatedAt DESC;
"
```

Check the latest events for that queue:

```sh
sqlite3 frontend/prisma/dev.db "
SELECT type, payload, createdAt FROM AutoPilotEvent
WHERE queueId = '<QUEUE_ID>'
ORDER BY createdAt DESC LIMIT 20;
"
```

Look for `auto_resume_scheduled` — its payload contains `fire_at`. If
`fire_at` was in the past and no `auto_resume_fired` event followed, the
timer was lost (e.g. a backend restart cancelled it before the auto-resume
loop fired).

### Fix

- If `auto_resume_circuit_breaker_tripped` is the latest event → the
  queue gave up after `_AUTO_RESUME_MAX_ATTEMPTS=3` consecutive auto-resumes.
  See [§3](#3-runaway-auto-resume-loop).
- Otherwise: click the **Resume now** button on the banner (or `POST
  /api/execute/queue/{id}/resume`). This cancels any pending timer and
  re-enters the run loop.

---

## 3. Runaway auto-resume loop

The circuit breaker (`_AUTO_RESUME_MAX_ATTEMPTS = 3` in
`backend/services/autopilot_queue_service.py`) prevents a queue from
auto-resuming forever on a persistently-failing API key. After 3
consecutive auto-resume attempts, the queue's `pauseReason` is downgraded
to `manual` and the user must explicitly resume.

### Verify the breaker tripped

```sh
sqlite3 frontend/prisma/dev.db "
SELECT type, payload, createdAt FROM AutoPilotEvent
WHERE queueId='<QUEUE_ID>' AND type='auto_resume_circuit_breaker_tripped'
ORDER BY createdAt DESC LIMIT 1;
"
```

### Reset the counter

The counter resets on successful task completion. If the failing task
keeps the queue in WAITING_RESET, you need to either:

- Fix the underlying API key / quota issue, then click Resume (counter
  is reset by the next successful task)
- OR skip the task: `POST /api/execute/queue/{id}/skip-current` then resume

There is no API to reset `auto_resume_attempts` directly without going
through the queue lifecycle. If absolutely needed, drop into a Python
shell on the running backend:

```python
from services.autopilot_queue_service import autopilot_queue_service
q = autopilot_queue_service.get_queue("<QUEUE_ID>")
q.auto_resume_attempts = 0
```

(This won't survive a restart; the persisted record may show stale
counter, but the live queue is what counts.)

---

## 4. Force-resume override

Sometimes the safety checks legitimately need to be bypassed:

- `_resume_preflight` skipped a task because the issue was already CWQ —
  but you actually want to re-run it
- The circuit breaker tripped but you've fixed the upstream issue and
  need to retry now

### For preflight-skipped tasks

Re-open the issue first (move it from CWQ back to TODO) via CodeBoard,
then click Resume. The preflight will see TODO and proceed.

### For circuit-breaker downgrade

`POST /api/execute/queue/{id}/resume` works — `pauseReason='manual'`
queues are still resumable through the manual path. The circuit breaker
only blocks the auto-resume timer, not user-initiated resume.

---

## 5. SQL recipes

All queries run against `frontend/prisma/dev.db` (the Prisma SQLite store).

### Active AutoPilot state

```sql
SELECT q.id, q.status, q.pauseReason, q.resetTime, q.currentIndex,
       (SELECT count(*) FROM AutoPilotTaskRecord t WHERE t.queueId = q.id) AS total_tasks,
       (SELECT count(*) FROM AutoPilotTaskRecord t WHERE t.queueId = q.id AND t.status = 'completed') AS completed
FROM AutoPilotQueueRecord q
WHERE q.status NOT IN ('completed', 'aborted')
ORDER BY q.updatedAt DESC;
```

### Recent events for a queue

```sql
SELECT type, payload, createdAt
FROM AutoPilotEvent
WHERE queueId = '<QUEUE_ID>'
ORDER BY createdAt DESC LIMIT 50;
```

### All queues recovered after a crash

```sql
SELECT id, projectId, currentIndex, updatedAt
FROM AutoPilotQueueRecord
WHERE status = 'paused' AND pauseReason = 'crash_recovery';
```

### Auto-pause counts in the last 24h

```sql
SELECT count(*) FROM AutoPilotEvent
WHERE type = 'auto_paused' AND createdAt > datetime('now', '-1 day');
```

### Tasks reverted by crash recovery

```sql
SELECT id, queueId, sequence, issueId, failureReason, completedAt
FROM AutoPilotTaskRecord
WHERE failureReason = 'backend_crash_recovery'
ORDER BY completedAt DESC LIMIT 50;
```

---

## Reference: state machine

```
PENDING → RUNNING ⇄ PAUSED (manual)
            │
            ├─ token-exhaust → WAITING_RESET → (auto-resume timer +60s) → RUNNING
            │                                       │
            │                                       └─ circuit-breaker trip (≥3 attempts)
            │                                          → pauseReason=manual, await user
            │
            └─ crash → on next startup → PAUSED(crash_recovery), await manual resume

Terminal: COMPLETED | ABORTED
```

## Reference: key constants

In `backend/services/autopilot_queue_service.py`:

| Constant | Value | Purpose |
|---|---|---|
| `_AUTO_RESUME_BUFFER_SECONDS` | 60 | Padding added to parsed reset_time before firing |
| `_AUTO_RESUME_MAX_ATTEMPTS` | 3 | Circuit-breaker threshold for consecutive auto-resumes |
| `_REHYDRATION_RESET_WINDOW_HOURS` | 12 | Rejects rehydrated reset_time outside ±12h as corrupted |
| `_MAX_PAYLOAD_BYTES` (in `utils/autopilot_repository.py`) | 8192 | AutoPilotEvent payload size cap |
| `_POLL_INTERVAL_SECONDS` | 2.0 | terminal_service polling interval inside the queue loop |

## Reference: event types (AutoPilotEvent.type)

| Type | When emitted |
|---|---|
| `created` | `create_queue` returned |
| `task_started` | `_execute_task` entered run state |
| `task_completed` | `_apply_success` finished |
| `task_failed` | `_apply_failure` branch (retry / max-retries / skip / continue) |
| `auto_paused` | Token exhaustion detected |
| `auto_resume_scheduled` | Timer armed for `fire_at` |
| `auto_resume_fired` | Timer fired; resume attempted |
| `auto_resume_circuit_breaker_tripped` | Circuit breaker hit, queue downgraded to manual |
| `manual_paused` | User clicked Pause |
| `resumed` | `resume_queue` succeeded (manual or timer-driven) |
| `aborted` | `abort_queue` finished |
| `crash_recovery_detected` | `rehydrate_from_db` saw a non-terminal queue from a previous run |
| `finalized` | `_finalize_queue` ran (terminal state persisted) |
| `task_appended` | Audit-rescan added a new BUG/TASK discovered mid-run (CB-2382) |

---

## 6. Re-scan during run (CB-2382)

### What it does

At the top of each loop iteration in `run_queue()`, the service calls
`_rescan_subtree_for_new_tasks(queue)`. This method BFS-walks the feature's
descendant tree and looks for issues that match **all** of:

- `type IN ('BUG', 'TASK')`
- `status = 'BACKLOG'`
- `createdAt > queue.started_at` (only issues born after the queue kicked off)
- `id NOT IN` the tasks already in the queue (original + previously appended)

Matching issues are appended to `queue.tasks` as `PENDING` tasks with
`execution_mode='implement'`. A `task_appended` audit event is written for
each appended issue (payload contains `issueId`, `issueKey`, `source='audit_rescan'`,
`sequence`).

### Idempotency

`AutoPilotQueue._appended_ids` (a `set`) tracks every issue ID appended by
the rescan. Subsequent loop iterations skip IDs already in this set, so the
same issue is never double-queued even if the DB query returns it again.

### Failure behaviour

Rescan errors are caught and logged via `self._logger.exception` but do NOT
abort the queue. The rescan is best-effort; a DB hiccup on one iteration
just means that BUG gets picked up on the next iteration (or not at all if
the queue finishes first).

### Diagnosing skipped audit bugs

If a queue finishes and you notice BACKLOG BUGs in the feature subtree:

1. Check whether their `createdAt` is after `queue.started_at`. If not, they
   predate the queue and the rescan intentionally ignored them.
2. Query the audit log: `SELECT * FROM "AutoPilotEvent" WHERE type='task_appended'
   AND "queueId"='<id>'` to see which issues were picked up.
3. If `task_appended` events are absent and the bugs are post-start, check
   backend logs for `"rescan failed"` lines around the relevant iteration times.
