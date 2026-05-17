# Bulletproof AutoPilot — Design Document
**Feature:** CB-2746 (Bulletproof AutoPilot)
**Epic:** CB-2747 (E1 Research + State-Machine Design)
**Author:** llm-architect (Claude Opus 4.7 1M)
**Date:** 2026-05-09
**Status:** READY FOR IMPLEMENTATION
**Audience:** python-pro (E2/E3/E4 implementer), react-specialist (E5 UI), test-engineer (E6 chaos)

---

## 0. Executive Summary

Five repeat regressions in 48 hours (CB-2671, CB-2737, CB-2743, CB-2744, CB-2731/2732)
all share the same root cause: **the AutoPilot state machine is implicit, scattered
across three layers (in-memory dataclass, SQLAlchemy record, frontend state), and
recovery paths only exist for the failure modes we have already seen**. Every new
failure mode requires a custom symptom-fix. The same mode reappears in a
slightly different form (different process-death signal, different API error
phrasing, different race) and a new fix is needed.

This document specifies a **single canonical state machine**, a **closed recovery
matrix** (every (failure × state) cell has an action), **persistence guarantees**
that survive arbitrary process death, and a **chaos-test plan** that proves all of
the above before each release.

The implementation is decomposed into 6 epics under CB-2746 (this is E1; E2-E6
are the others). E2-E4 can land in parallel; E5 depends on E3; E6 depends on
all.

---

## 1. Failure Mode Inventory (16 modes)

Each mode has four columns:
- **Trigger** — concrete action that produces the failure
- **Current** — what AutoPilot does today (verified against code)
- **Required** — what it must do under the new design
- **Recovery** — `auto` (machine recovers without user) or `prompt` (UI banner asks user)

### Mode 1 — Backend graceful shutdown (SIGTERM)

| Field | Detail |
|---|---|
| **Trigger** | `Ctrl-C` in the launch shell, `docker stop`, `kill -TERM <pid>`, `launchctl bootout`. |
| **Current** | FastAPI `lifespan` cancels `process_pending_completions`, `evict_stale_sessions`, `process_doc_retention`, then `cancel_all_background_tasks()`. The autopilot run_queue task IS in `_background_tasks` (created by `create_tracked_task`), so it gets cancelled — but the cancellation propagates as `asyncio.CancelledError` *inside* `_execute_task` while a subprocess is mid-flight. The Claude CLI subprocess **is not awaited or terminated**. The DB row is left at `status=running` with the in-memory `task.status=running`. The `_persist` call inside the task that was about to write `task_completed` never fires. On next boot, `rehydrate_from_db` resets to `paused/crash_recovery` — but the orphaned subprocess may keep running and consuming tokens. |
| **Required** | Lifespan shutdown must (a) signal the queue loop to stop *before* cancellation, (b) wait up to N seconds for the current task to checkpoint a clean `running → pending` (interrupted) state, (c) `terminal_service.stop_execution()` for every session whose task is mid-flight, (d) `_persist` a `shutdown_paused` event with `pauseReason='graceful_shutdown'`. |
| **Recovery** | `auto` — on next boot the queue is in `paused/graceful_shutdown` and resumes automatically (not `crash_recovery`, because we got a clean stop). |

### Mode 2 — Backend SIGKILL (`kill -9`)

| Field | Detail |
|---|---|
| **Trigger** | `kill -KILL <pid>`, `pkill -9`, container OOM-killer with no grace. |
| **Current** | No lifespan shutdown runs. Subprocess is reparented to init/launchd (PID 1). DB row stays `status=running`. The Claude subprocess **continues running** and may complete its work, but the result is lost because no parent is reading stdout. On boot, `rehydrate_from_db` flips to `paused/crash_recovery` and the user must press "Resume". The orphaned subprocess silently consumes tokens. |
| **Required** | Subprocess detection: (a) every `_execute_task` must register an OS PID in the DB row (`AutoPilotTaskRecord.subprocessPid`). On boot, scan PIDs of orphaned tasks; if `os.kill(pid, 0)` succeeds, send SIGTERM; if it doesn't, treat as cleanly dead. (b) DB row marked `status=interrupted_by_crash`, queue → `paused/crash_recovery`. (c) Audit event `crash_recovery_detected` (already exists) extended with PID liveness info. |
| **Recovery** | `prompt` — user banner: "AutoPilot crashed mid-task on CB-XXXX. The previous subprocess was terminated. Resume / Skip / Abort." (kept manual because we cannot trust subprocess output that we never read.) |

### Mode 3 — Backend OOM kill

| Field | Detail |
|---|---|
| **Trigger** | Linux OOM killer, macOS jetsam, container memory limit hit. Identical kernel signal to SIGKILL but precipitating cause is resource exhaustion. |
| **Current** | Identical to Mode 2 — silent crash, queue stuck `running` in DB. **Plus**: no signal to user that the crash was due to memory; they'll just see "crash recovery" and try again. The OOM is likely to recur on the next attempt because the queue depth is the same. |
| **Required** | Mode 2 recovery PLUS: parse `dmesg`/`os.uname` boot time + last log line on startup. If the previous backend exit time + boot evidence suggest OOM, surface it in the recovery banner: "Backend ran out of memory. Consider reducing concurrent tasks (currently N)." Bound `_queues` (max 50 historical, already at 10) and bound `session.output` ring buffer (already exists). |
| **Recovery** | `prompt` — same as Mode 2 but with OOM hint. |

### Mode 4 — Backend uncaught exception in `run_queue`

| Field | Detail |
|---|---|
| **Trigger** | Bug introduced into the loop body (e.g. AttributeError, KeyError on a malformed task), DB connection pool exhaustion mid-loop, asyncio loop closure due to nested asyncio.run(). |
| **Current** | The `try/except Exception` in `run_queue` catches it, sets `queue.status = ABORTED`, calls `_finalize_queue`. The error message is redacted (good) but the queue is **dead** — user sees `aborted` and has to re-create the queue from scratch. No retry, no salvage of completed tasks. |
| **Required** | The bare `except Exception` must distinguish (a) a *task-level* exception (one task broke) from (b) a *loop-level* exception (the orchestrator broke). Loop-level → queue → `paused/loop_crash`, push the failing index forward (skip), audit-log the traceback, surface a "Resume to continue past the crash" prompt. **Never auto-abort**. |
| **Recovery** | `prompt` — "AutoPilot crashed. The error has been logged. Resume to continue with the next task, or Abort." |

### Mode 5 — OS reboot mid-task (power cut, kernel panic)

| Field | Detail |
|---|---|
| **Trigger** | Power loss, hardware fault, kernel panic, accidental reboot. |
| **Current** | Identical to Mode 2 from AutoPilot's perspective — DB on disk has `status=running`, no clean shutdown, on boot `rehydrate_from_db` flips to `crash_recovery`. **However**: SQLite WAL was enabled (`backend/models/database.py:28`) so the DB file itself is consistent. Any `_persist` calls that completed the OS write barrier are durable; ones that didn't are lost. The 2-second poll interval inside `_execute_task` means we may have lost up to ~2s of in-progress task state. |
| **Required** | Mode 2 + checkpoint cadence guarantee. Every task-status transition (`pending → running → completed`) must be a single SQLite transaction. The `save_queue` cadence inside `_persist` is currently best-effort and decoupled from the cascade transaction (see repository docstring). For the persistence-critical fields (`status`, `currentIndex`, `task.status`, `task.attempts`) we need an *atomic* write per state transition: `BEGIN; UPDATE task SET status=...; UPDATE queue SET status=...; INSERT event; COMMIT`. |
| **Recovery** | `prompt` — "Power loss detected (last seen N minutes ago). Resume from last checkpointed task." |

### Mode 6 — Anthropic API token / rate-limit (HTTP 429, 529)

| Field | Detail |
|---|---|
| **Trigger** | Quota exhausted, hourly/daily window hit, server overload (`overloaded_error`). The Claude CLI subprocess emits a `[ERROR]` line containing one of `TOKEN_EXHAUSTION_PATTERNS`. |
| **Current** | `is_token_exhaustion(session)` matches; `extract_reset_time(session)` parses; queue → `WAITING_RESET`, `pause_reason='token_exhaustion'`, `_schedule_auto_resume(reset_time + 60s)` arms timer. Circuit breaker stops at 3 consecutive auto-resumes. Works *most* of the time but: (a) pattern list is a hand-maintained substring match — adding a new Anthropic error phrasing requires a code change (CB-2731 was this); (b) `extract_reset_time` returns `None` on novel formats → defaults to 60min wait → wakes too early → re-fires → eventually circuit-breaks. |
| **Required** | (a) Replace substring match with an `ExhaustionDetector` class with structured matchers: `(error_code: int, error_type: str, body_pattern: regex)` + a fallback heuristic. Each matcher records a hit-count metric so we know which patterns actually fire in production. (b) Reset-time extraction: try parsing the JSON `error` body from the Claude CLI's `stream-json` output (more reliable than regex on a tail of `[ERROR]` lines). (c) When `reset_time is None`, do **exponential backoff** (5min, 15min, 60min) instead of a fixed 60min. (d) Surface every detection as `auto_paused` event with the matched pattern + raw body excerpt (redacted) so we can audit-mine novel patterns. |
| **Recovery** | `auto` — sleep until reset_time, fire timer, re-execute current task. Circuit-break to `prompt` after 3 attempts. |

### Mode 7 — Anthropic API auth/credit failure (HTTP 401, 402, 403)

| Field | Detail |
|---|---|
| **Trigger** | API key rotated, billing payment failed, account suspended, credit balance zero (which is **not** rate-limit — it's structural). |
| **Current** | `TOKEN_EXHAUSTION_PATTERNS` includes `"credit balance is too low"` and `"your account has"` — these match and trigger the **rate-limit** path (auto-resume in 60min). This is wrong: the credit will not magically refill in 60 minutes. The circuit breaker eventually trips, but only after 3 wasted re-runs of the same task → token burn during a billing crisis. CB-2731/2732 today's bug is exactly this. |
| **Required** | Distinguish auth/credit (HTTP 401/402, body keys: `invalid_api_key`, `permission_error`, `credit balance`, `your account has`) from rate-limit (HTTP 429/529, body keys: `rate_limit_error`, `overloaded_error`, `usage limit`). Auth/credit → queue → `paused/credit_exhausted` immediately, **no auto-resume timer**, banner surfaces "Top up credit / fix API key / switch model". |
| **Recovery** | `prompt` (always) — "Anthropic credits exhausted or API key invalid. Top up at console.anthropic.com or switch model. AutoPilot will not retry until you take action." |

### Mode 8 — Network blip mid-API-call

| Field | Detail |
|---|---|
| **Trigger** | Wi-Fi disconnect, DNS failure, transient TLS error, backend running on laptop that switched networks. |
| **Current** | The Claude CLI subprocess returns non-zero with a network error in stderr (e.g. `connection reset`, `getaddrinfo failed`). None of those phrases are in `TOKEN_EXHAUSTION_PATTERNS`, so the failure is treated as a **task failure** → `_apply_failure` runs — `CONTINUE_MARK_FAILED` (default) marks the task FAILED and advances. **A momentary network blip silently fails a task that would have succeeded on retry.** |
| **Required** | `NetworkErrorDetector` class — pattern set: `connection reset`, `getaddrinfo`, `EOF on socket`, `502 Bad Gateway`, `503 Service Unavailable`, `network is unreachable`, `DNS lookup failed`. Match → queue → `paused/network_failure` with **automatic** retry after 30s, 90s, 270s (exponential), max 3 attempts, then circuit-break to manual. |
| **Recovery** | `auto` (with circuit breaker → `prompt`) — "Network error detected, retrying in N seconds." |

### Mode 9 — Disk full during DB write

| Field | Detail |
|---|---|
| **Trigger** | macOS APFS full (Seagate drive at 100%), `errno 28 ENOSPC` from SQLite `WAL` checkpoint. |
| **Current** | `_persist` wraps in `try/except Exception` and **swallows the exception** — logs an exception line, continues. The in-memory queue keeps running but **nothing is durable**. On next backend restart, all the post-disk-full state is gone — recovery banner shows the queue at the position of the *last successful* write. Tasks "completed" between the disk-full and the crash silently re-execute, burning tokens and possibly producing duplicate work. |
| **Required** | `_persist` must classify exceptions: `OperationalError` with `disk I/O error`, `ENOSPC`, or `database is locked` → queue → `paused/disk_full`, **stop the loop immediately**, surface a banner "Disk full — free space and resume". Do NOT continue executing tasks when persistence is broken (that's the failure mode that produces silent duplicate work). |
| **Recovery** | `prompt` — "Disk full. Free up space (currently N% used) and click Resume. AutoPilot is paused to prevent data loss." |

### Mode 10 — Subprocess SIGKILL (claude CLI killed externally)

| Field | Detail |
|---|---|
| **Trigger** | User runs `pkill claude`, Activity Monitor "Force Quit", another tool kills the process tree. |
| **Current** | `terminal_service` polls `process.returncode`; when subprocess dies, marks session `FAILED`. `_poll_session` sees `FAILED`, returns "failed", `_apply_failure` runs (default `CONTINUE_MARK_FAILED`). **Tokens spent on the killed run are lost; task marked failed with no retry.** |
| **Required** | Distinguish: returncode == -9 (SIGKILL) or -15 (SIGTERM) is *external kill*, not task failure. → Treat as Mode 8 (network blip) recovery: queue → `paused/subprocess_killed`, retry up to 2 times with full re-execution. After exhausted, `prompt` for user. |
| **Recovery** | `auto` (limited retries) → `prompt` — "Claude CLI subprocess was killed externally. Retrying." |

### Mode 11 — Frontend disconnect mid-flow (SSE drops)

| Field | Detail |
|---|---|
| **Trigger** | User closes tab, network blip on laptop, browser tab suspended for power saving. |
| **Current** | Backend keeps running — the SSE stream `/api/execute/queue/{id}/stream` is detected as disconnected on next tick (`request.is_disconnected()`) and the stream coroutine exits. The queue itself is **unaffected** (this is correct — the design is server-driven). **But**: the frontend has no robust reconnect — `AutoPilotContext` falls back to 2s polling, and if SSE later recovers, polling stops. State *can* drift if the queue completes between disconnect and reconnect (the `done` event is missed). |
| **Required** | Polling fallback must not be a side-channel — it must always converge to the SSE state. Add a `lastEventId` on the SSE messages so a reconnect can `Last-Event-ID` and resume from the missed event. Frontend `applyQueueStatus` should treat polling responses as authoritative when SSE is unhealthy and visa-versa. Add a "queue completed in another tab" path that surfaces a toast. |
| **Recovery** | `auto` (transparent) — backend keeps running, frontend reconnects via `EventSource` auto-retry + `lastEventId` resumption. No user action needed. |

### Mode 12 — Multiple concurrent resume calls (race)

| Field | Detail |
|---|---|
| **Trigger** | User clicks "Resume" twice rapidly, OR the auto-resume timer fires at the same instant the user clicks Resume, OR two browser tabs both call `/api/queue/{id}/resume`. |
| **Current** | `_ensure_run_queue_task` has a `_launching` boolean flag (CB-2681) which is set sync before `create_tracked_task` and cleared in done-callback. This prevents *two* `run_queue` coroutines from being spawned. **But**: `resume_queue` itself doesn't dedupe — if the queue is already PAUSED→RUNNING transitioning, two concurrent `resume_queue` calls both pass the status check. The pause event being set is idempotent so the *second* set is a no-op. Net effect: usually no harm, but the audit log gets two `resumed` events, and `auto_resume_attempts` may be incremented twice if a manual + auto resume race. |
| **Required** | `resume_queue` and `_fire_auto_resume` must take an `asyncio.Lock` keyed on `queue_id`. The lock must be held across status check + transition + `_pause_event.set()` + `_ensure_run_queue_task`. Idempotency by design. |
| **Recovery** | `auto` (transparent) — second caller is a no-op or returns the same state. |

### Mode 13 — DB row corruption / schema drift

| Field | Detail |
|---|---|
| **Trigger** | Manual DB edit, failed migration, mid-flight `ALTER TABLE` from a different process, `AutoPilotQueueRecord.status` set to a value not in the enum (e.g. `'PAUSED'` capitalized vs `'paused'`). |
| **Current** | `_record_to_queue` has `try: QueueStatus(record.status); except ValueError: QueueStatus.PAUSED` — defaults to PAUSED on bad status. Same for task status. Silent data loss but at least no crash. **But** the unknown status string is lost — the queue silently runs on a different state than what's in the DB. |
| **Required** | Validate-and-quarantine: if `status` is unrecognized, log an `ERROR`, push the row into a `quarantined` set in memory, do NOT auto-load it. Surface in recovery banner: "Queue CB-XXXX has corrupted state and was not loaded. View raw data or delete." |
| **Recovery** | `prompt` (always) — manual cleanup required. |

### Mode 14 — Long-running task exceeds wall-clock timeout

| Field | Detail |
|---|---|
| **Trigger** | A single task runs > 30 minutes, > 1 hour. May be legitimately stuck or genuinely large. |
| **Current** | No timeout. `_poll_session` polls every 2 seconds *forever* until session reports COMPLETED or FAILED. A truly stuck Claude subprocess holds the queue indefinitely. The user only sees "current task running" with no progress for hours. |
| **Required** | Configurable `task_max_runtime_seconds` (default 30min). When exceeded, queue → `paused/task_timeout`, surface banner "CB-XXXX has been running for N minutes (last activity M minutes ago). Continue waiting / Skip / Abort". Add per-task `last_progress_at` timestamp updated whenever `session.files_read|files_written|commands_run` changes — distinguishes "stuck" from "actively working on a large task". |
| **Recovery** | `prompt` — user decides. |

### Mode 15 — Concurrent feature execution (multiple queues created)

| Field | Detail |
|---|---|
| **Trigger** | User opens two browser tabs, starts AutoPilot on Feature A in tab 1 and Feature B in tab 2. Or, `POST /api/execute/queue` race between the active-check (line 930-936) and the create. |
| **Current** | The active-check is a check-then-act with no lock — two concurrent POSTs can both pass `if active and active.status in ('running', 'paused', 'waiting_reset')` returning False, then both create queues. After: `_active_queue_id` ends up pointing at whichever was created second; the first queue still runs but is "orphaned" from the active-pointer perspective. The frontend polls `/queue/active`, sees the second queue, never tracks the first. The first queue **silently runs** until it terminates or crashes. |
| **Required** | Queue creation must be serialized: `asyncio.Lock` around the active-check + create. Returns 409 immediately on the second concurrent POST. DB-level uniqueness: a partial unique index on `AutoPilotQueueRecord.status` IN ('pending','running','paused','waiting_reset') with a single row constraint. SQLite supports this with `CREATE UNIQUE INDEX ... WHERE`. |
| **Recovery** | `auto` (server-side serialization + DB constraint). Surface 409 in UI as toast. |

### Mode 16 — Token exhaustion mid-checkpoint

| Field | Detail |
|---|---|
| **Trigger** | The backend crashes (SIGKILL/OOM/power) **at the same moment** the queue is in `WAITING_RESET` with an auto-resume timer armed. On reboot, the timer is gone (in-memory only) but the DB shows `WAITING_RESET` with a `resetTime` value. |
| **Current** | `rearm_auto_resume_timers` walks `_queues` after `rehydrate_from_db`, finds `WAITING_RESET` queues with valid `reset_time` (within ±12 hours), calls `_schedule_auto_resume`. **Good — already handles this**. But if `reset_time` is in the past (crash lasted longer than the wait), `_schedule_auto_resume` sets delay=0 and fires immediately. If the API is *still* exhausted (rate-limit window not actually open yet), the immediate fire produces another exhaustion → `_fire_auto_resume` re-paused → cycle. Circuit breaker triggers after 3 attempts. **Wasted token burst on every crash recovery during a long exhaustion.** |
| **Required** | Pre-flight before firing auto-resume: send a tiny "ping" Claude CLI invocation (e.g. `--version` won't work, but a 1-token query like "hi" with `--max-tokens 1`) to verify the API is actually open. If it 429s, push the timer out by 5min and try again. (This costs ≤1 token per check — negligible vs a full task re-run.) Fall back to manual resume if 5 ping checks all fail. |
| **Recovery** | `auto` with cheap ping pre-flight. |

---

## 2. Current Code Map

### 2.1 State holders (3 places, must be reconciled)

```
┌─────────────────────────────────────────────────────────────────────┐
│  IN-MEMORY (services/autopilot_queue_service.py)                    │
│  ─────────────────────────────────────────────                      │
│  AutoPilotQueueService._queues: Dict[str, AutoPilotQueue]           │
│  AutoPilotQueueService._active_queue_id: Optional[str]              │
│  AutoPilotQueueService._recovered_queue_ids: set[str]               │
│  AutoPilotQueueService._resume_handles: Dict[str, asyncio.Task]     │
│  AutoPilotQueueService._persistence_enabled: bool                   │
│                                                                     │
│  AutoPilotQueue:                                                    │
│    .status: QueueStatus (pending|running|paused|waiting_reset|...)  │
│    .current_index: int                                              │
│    .pause_reason: Optional[str]                                     │
│    .reset_time: Optional[datetime]                                  │
│    .auto_resume_attempts: int                                       │
│    ._task: Optional[asyncio.Task] (run_queue coroutine handle)      │
│    ._pause_event: asyncio.Event                                     │
│    ._skip_flag: bool                                                │
│    ._stop_flag: bool                                                │
│    ._launching: bool (CB-2681 race guard)                           │
│    ._appended_ids: set                                              │
│    ._appended_count: int                                            │
│    ._rescan_cap_logged: bool                                        │
│                                                                     │
│  QueueTask:                                                         │
│    .status: TaskStatus                                              │
│    .session_id: Optional[str]                                       │
│    .retry_count: int                                                │
│    .started_at, .completed_at, .error                               │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ persist (CB-1951 write-through,
                                    │  decoupled txn — see repository.py:9)
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SQLITE (backend/data/codeboard.db, WAL mode + busy_timeout=30000)  │
│  ─────────────────────────────────────────────────────────────────  │
│  AutoPilotQueueRecord                                               │
│    id (PK), projectId, featureId, status, currentIndex,             │
│    pauseReason, resetTime, config (JSON text), createdAt,           │
│    updatedAt, completedAt                                           │
│                                                                     │
│  AutoPilotTaskRecord                                                │
│    id (PK), queueId (FK CASCADE), sequence, issueId, issueKey,      │
│    issueTitle, status, attempts, sessionId, startedAt,              │
│    completedAt, failureReason                                       │
│                                                                     │
│  AutoPilotEvent (append-only audit log)                             │
│    id (PK), queueId (FK CASCADE), type, payload (JSON ≤8KB),        │
│    createdAt                                                        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ SSE /api/execute/queue/{id}/stream
                                    │ + GET /queue/active on mount
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FRONTEND STATE (contexts/AutoPilotContext.tsx)                     │
│  ───────────────────────────────────────────────                    │
│  isActive, isPaused, isWaitingReset                                 │
│  queueId, featureId, featureKey, featureTitle, projectId            │
│  queueTasks, currentIndex, progress                                 │
│  pauseReason, resetTime                                             │
│  recoveredQueues                                                    │
│  lastError, queueStatus                                             │
│                                                                     │
│  EventSource ref + 2s polling fallback (sseHealthyRef gate)         │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Current state transitions (informal — extracted from code)

```
                          ┌─────────────┐
                          │   PENDING   │  (created, never started)
                          └──────┬──────┘
                                 │ run_queue() launches
                                 ▼
                          ┌─────────────┐
                ┌─────────│   RUNNING   │─────────────┐
                │         └──────┬──────┘             │
                │                │                     │
        pause_queue               │ _execute_task → _poll_session
        (manual)                   │    │      │      │
                │                  │    │      │      │
                ▼                  │    │      │      ▼
        ┌──────────────┐           │    │      │   ┌──────────────┐
        │   PAUSED     │◄──────────┘    │      │   │   ABORTED    │
        │ pauseReason= │                │      │   │ (terminal)   │
        │ 'manual'     │                │      │   └──────────────┘
        └──────┬───────┘                │      │           ▲
               │                        │      │           │ abort_queue
        resume_queue                    │      │           │ OR loop exception
               │                        │      │           │ OR action=TERMINATE
               └────────────────────────┘      │           │
                                                │           │
                                                ▼           │
                                  ┌──────────────────┐     │
                       (token exhaust detected)              │
                                  │                  │     │
                                  ▼                  │     │
                         ┌──────────────────┐        │     │
                         │  WAITING_RESET   │        │     │
                         │  pauseReason=    │        │     │
                         │  'token_exhaust' │        │     │
                         │  resetTime=...   │        │     │
                         └────────┬─────────┘        │     │
                                  │ _schedule_auto_resume  │
                                  │ OR resume_queue (manual)│
                                  └─────────────────────────┘
                                                            │
                                  (all tasks complete)      │
                                            │               │
                                            ▼               │
                                  ┌──────────────────┐     │
                                  │   COMPLETED      │─────┘
                                  │   (terminal)     │
                                  └──────────────────┘

Special states added by rehydration (E2):
  status=paused, pauseReason='crash_recovery'  ← rehydrate_from_db
  status=paused, pauseReason='manual' (downgraded by circuit breaker)
```

### 2.3 Gaps in the current state machine

| # | Gap | Location | Severity |
|---|-----|----------|----------|
| G1 | No "graceful shutdown" pause reason — clean SIGTERM looks like a crash. | `app/main.py:316-330` | HIGH |
| G2 | Subprocess PID not tracked — orphaned subprocesses survive backend death. | `services/terminal_service.py` | HIGH |
| G3 | `_persist` is best-effort (catches all exceptions) — disk full silently advances queue. | `services/autopilot_queue_service.py:1495-1508` | CRITICAL |
| G4 | `TOKEN_EXHAUSTION_PATTERNS` lumps auth/credit (Mode 7) with rate-limit (Mode 6). | `services/autopilot_queue_service.py:71-91` | CRITICAL |
| G5 | No network-error class — Mode 8 is silently treated as task failure. | `services/autopilot_queue_service.py:1290-1293` | HIGH |
| G6 | No per-task wall-clock timeout — Mode 14 hangs forever. | `services/autopilot_queue_service.py:1252-1295` | MEDIUM |
| G7 | `resume_queue` not idempotent under concurrent calls (Mode 12). | `services/autopilot_queue_service.py:1766-1824` | MEDIUM |
| G8 | Active-queue creation race (Mode 15) — no lock between check and create. | `api/execution.py:929-1015` | HIGH |
| G9 | Audit-rescan happens INSIDE the loop body — a crash mid-rescan can leak `_appended_ids` state (in-memory only, not persisted). | `services/autopilot_queue_service.py:705-716` | LOW |
| G10 | `_record_to_queue` defaults unknown status to PAUSED — silently masks DB corruption. | `services/autopilot_queue_service.py:540-542` | MEDIUM |
| G11 | No checksum / write-and-verify on `_persist` — partial writes invisible. | `utils/autopilot_repository.py:65-169` | LOW |
| G12 | Frontend `applyQueueStatus` invalidates React Query caches on state change but not on `lastEventId` gap — missed events leave UI stale. | `contexts/AutoPilotContext.tsx:235-249` | LOW |

---

## 3. Target State Machine

### 3.1 Canonical states + reasons

```
States:    IDLE | RUNNING | PAUSED(reason) | WAITING_RESET | COMPLETED | ABORTED
Reasons:   manual | graceful_shutdown | crash_recovery | loop_crash
           token_exhaustion | credit_exhausted | network_failure
           subprocess_killed | disk_full | task_timeout
```

**State invariants:**
- IDLE — queue exists but never started OR queue completely drained and finalized.
- RUNNING — exactly one `_task` (asyncio.Task) is alive AND `_pause_event.is_set()`.
- PAUSED(*) — `_pause_event.is_clear()`. Queue may have a `_task` that is `await _pause_event.wait()`. Reason describes why and dictates recovery action.
- WAITING_RESET — special PAUSED with `pause_reason='token_exhaustion'`, has a `reset_time`, and may have an armed `_resume_handles[queue_id]` timer.
- COMPLETED, ABORTED — terminal. `_task is None or _task.done()`.

### 3.2 Allowed transitions

```
                         create_queue()
                               │
                               ▼
                            ┌──────┐
                            │ IDLE │
                            └───┬──┘
                                │ run_queue() spawn
                                ▼
       ┌───────────────────► ┌───────┐ ◄────────────────────────────┐
       │                     │RUNNING│                              │
       │                     └───┬───┘                              │
       │      ┌────────┬─────────┼──────────┬────────┬─────────┐   │
       │      │        │         │          │        │         │   │
       │   manual    SIGTERM  loop-exc   token-     net-     disk- │
       │   pause                          exhaust  failure   full  │
       │      │        │         │          │        │         │   │
       ▼      ▼        ▼         ▼          ▼        ▼         ▼   │
    PAUSED PAUSED   PAUSED    PAUSED   WAITING_   PAUSED   PAUSED  │
   (manual)(graceful)(loop_   (crash_   RESET    (network_(disk_full)
            _shutdwn)  crash) recovery)(token_    failure)         │
       │      │        │         │     exhaust)    │         │     │
       │      │        │         │          │      │         │     │
       │ resume()  ────┴─────────┴──────────┼──────┴─────────┘     │
       │                                    │ auto-timer fires      │
       │                          ┌─────────┴──┐                    │
       │                          │            │                    │
       │                          ▼            ▼                    │
       │                     RUNNING     PAUSED(manual)             │
       │                                 (circuit-breaker tripped)  │
       │                                       │                    │
       │                                       └────────────────────┘
       │                                       resume()
       │
       │  abort_queue()  ──┐
       │                   ▼
       │              ┌─────────┐
       └──────────────►│ ABORTED │ (terminal)
                      └─────────┘
                              ▲
                              │ loop done & all tasks terminal
       run_queue exit ────────┤
                              ▼
                      ┌────────────┐
                      │ COMPLETED  │ (terminal)
                      └────────────┘

Special edges (auto-recovery without user):
  WAITING_RESET ──[reset_time + buffer]──► RUNNING (after pre-flight ping)
  PAUSED(network_failure) ──[exp backoff]──► RUNNING (≤3 attempts)
  PAUSED(subprocess_killed) ──[immediate retry]──► RUNNING (≤2 attempts)

Forbidden edges (must be rejected with 409):
  COMPLETED ──*── any state
  ABORTED ──*── any state
  IDLE ──── PAUSED (only RUNNING → PAUSED)
```

### 3.3 Transition table (machine-readable for code generation)

| From | Trigger | To | Side effects |
|---|---|---|---|
| IDLE | `run_queue()` spawn | RUNNING | `_pause_event.set()`, `started_at = now()` |
| RUNNING | `pause_queue()` | PAUSED(manual) | `_pause_event.clear()`, audit `manual_paused` |
| RUNNING | SIGTERM lifespan | PAUSED(graceful_shutdown) | `_pause_event.clear()`, stop subprocess, audit `shutdown_paused` |
| RUNNING | uncaught loop exc | PAUSED(loop_crash) | log traceback, audit `loop_crashed` |
| RUNNING | `is_token_exhaustion(session)` AND credit-pattern | PAUSED(credit_exhausted) | NO timer, banner |
| RUNNING | `is_token_exhaustion(session)` AND rate-limit pattern | WAITING_RESET | arm timer with reset_time, audit `auto_paused` |
| RUNNING | `is_network_error(session)` | PAUSED(network_failure) | arm exp-backoff timer, audit `network_failure` |
| RUNNING | subprocess returncode == -9 | PAUSED(subprocess_killed) | retry counter++, audit |
| RUNNING | `_persist` raises ENOSPC | PAUSED(disk_full) | stop loop, banner |
| RUNNING | task wall-clock > N | PAUSED(task_timeout) | banner |
| RUNNING | `abort_queue()` | ABORTED | `_stop_flag = True`, stop subprocess, finalize |
| RUNNING | all tasks terminal | COMPLETED | finalize, mark feature CWQ |
| PAUSED(*) | `resume_queue()` | RUNNING | `_pause_event.set()`, `_ensure_run_queue_task()` |
| PAUSED(*) | `abort_queue()` | ABORTED | finalize |
| WAITING_RESET | timer fires + ping OK | RUNNING | `auto_resume_attempts++`, `_pause_event.set()` |
| WAITING_RESET | timer fires + ping 429 | WAITING_RESET (push timer +5min) | retry |
| WAITING_RESET | `auto_resume_attempts > 3` | PAUSED(manual) | circuit-break, banner |
| WAITING_RESET | `resume_queue()` | RUNNING | cancel timer, `_pause_event.set()` |
| Backend boot | `rehydrate_from_db()` | PAUSED(crash_recovery) | reset RUNNING tasks → PENDING, banner |

### 3.4 Persisted state shape (additions to existing schema)

`AutoPilotQueueRecord` adds:
```sql
ALTER TABLE AutoPilotQueueRecord
  ADD COLUMN lastShutdownReason TEXT;     -- 'graceful' | 'crash' | NULL (live)
  ADD COLUMN networkRetryCount  INTEGER DEFAULT 0;  -- exp backoff counter
  ADD COLUMN subprocessPid      INTEGER;  -- nullable, current task's PID
```

`AutoPilotTaskRecord` adds:
```sql
ALTER TABLE AutoPilotTaskRecord
  ADD COLUMN lastProgressAt   DATETIME;   -- updated on every files_*/cmd_* tick
  ADD COLUMN runtimeSeconds   INTEGER;    -- accumulated wall-clock for this task
```

`AutoPilotEvent` — no schema change; new event types (string values):
```
shutdown_paused
loop_crashed
credit_exhausted
network_failure
network_retry_scheduled
subprocess_killed
disk_full_detected
task_timeout
ping_preflight_ok
ping_preflight_429
queue_creation_serialized (race avoided)
state_corruption_quarantined (mode 13)
```

---

## 4. Persistence Guarantees

### 4.1 SQLite configuration (already in place — keep)

```python
# backend/models/database.py:24-31  — VERIFIED PRESENT
PRAGMA journal_mode=WAL       # crash-safe, no reader blocking
PRAGMA busy_timeout=30000     # 30s before SQLITE_BUSY
PRAGMA synchronous=NORMAL     # safe with WAL; FULL is overkill
PRAGMA foreign_keys=ON        # enforces queue→task CASCADE
```

**Add** (E3):
```python
PRAGMA wal_autocheckpoint=1000  # force checkpoint every 1000 WAL pages (~1 MB)
                                # bounds .db-wal file growth across long sessions
```

### 4.2 Atomic state transition contract

Every state transition (queue.status change OR task.status change) **must** be a
single SQLite transaction. The current `_persist` helper opens its own
`AsyncSessionLocal` (per repository docstring) which is **good** for failure
isolation but **bad** because the queue update + event insert + task update can
end up in *separate* transactions if the caller writes them across multiple
`_persist` calls.

**E3 contract:**
```python
async def transition(
    queue: AutoPilotQueue,
    new_status: QueueStatus,
    new_pause_reason: Optional[str] = None,
    task_updates: list[QueueTask] = (),
    event_type: str,
    event_payload: dict,
) -> None:
    """Single-transaction state transition. RAISES on failure (caller decides)."""
    async with AsyncSessionLocal() as db:
        async with db.begin():
            queue.status = new_status
            queue.pause_reason = new_pause_reason
            await save_queue(db, queue)
            for t in task_updates:
                await save_task(db, t)
            await record_event(db, queue.id, event_type, event_payload)
        # Implicit commit on context exit; rollback on exception.
```

If the transaction fails:
- `OperationalError` with `disk I/O error` / `ENOSPC` → re-raise as `DiskFullError` so caller can route to PAUSED(disk_full).
- `OperationalError` with `database is locked` → retry up to 3 times with 1s backoff (busy_timeout already gives us 30s on the first attempt).
- Any other → re-raise; the caller (run_queue loop) catches and routes to PAUSED(loop_crash).

### 4.3 Per-task vs per-queue checkpoint

**Per-task checkpoint** (every state transition emits a write):
- `task.status: PENDING → RUNNING` — at start of `_execute_task` (currently exists, but as separate write)
- `task.status: RUNNING → COMPLETED|FAILED|SKIPPED` — at end of `_poll_session` (currently exists)
- `task.lastProgressAt` updated on every tick where `files_*` or `commands_run` changed (NEW)

**Per-queue checkpoint** (less frequent):
- `queue.status` change — every transition listed in §3.3
- `queue.currentIndex` change — when advancing past a completed task

**No checkpoint required for:**
- Output streaming (held in `terminal_service` ring buffer, not durable — by design)
- Auto-resume timer state (re-derivable from `queue.resetTime`)

### 4.4 Recovery after partial write

WAL mode guarantees that any committed transaction is durable. SQLite will replay
WAL on the next open. The only partial-write risk is mid-transaction crash, in
which case the transaction is rolled back atomically — we lose at most the
*current* transition, never a previously committed one.

**Recovery rules** (in `rehydrate_from_db`):
1. Any `task.status='running'` → reset to `pending`, clear `sessionId`, `startedAt`. (CB-2738 — already in place)
2. Any `queue.status` IN ('running','waiting_reset') with `lastShutdownReason IS NULL` → flip to `paused/crash_recovery`. (already in place)
3. Any `queue.status` IN ('running','waiting_reset') with `lastShutdownReason='graceful'` → flip to `paused/graceful_shutdown` and **auto-resume** on next user mount (NEW for E3).
4. Validate every `queue.subprocessPid` — if alive, send SIGTERM; mark queue → `paused/subprocess_killed` if was active. (NEW)
5. Validate every `queue.resetTime` is within ±12h of now (existing CB-1951 E4 sanity check); else downgrade to manual. Re-arm timers for valid ones.
6. Any `queue.status` value outside the enum → quarantine (do not load). Recovery banner shows quarantined queues separately.

### 4.5 Two-phase commit between issue status + queue task status

Current code has known drift potential (repository docstring line 8-16):
> "save_queue does NOT commit — caller commits explicitly. Note that the
> service's `_persist` helper opens its own AsyncSessionLocal so the
> queue snapshot is decoupled from the cascade transaction."

For E3, **task completion** must atomically update:
- `Issue.status` (e.g. → 'COMPLETED_WAITING_QA')
- `AutoPilotTaskRecord.status` (→ 'completed')
- `AutoPilotQueueRecord.currentIndex` (incremented)
- `AutoPilotEvent` (`task_completed`)

All in **one** transaction. If the cascade-to-parents work fails, the task is
**not** marked completed — better to re-execute on resume than to advance with
a half-finished cascade.

---

## 5. Recovery Matrix

Rows = current queue state. Columns = failure mode. Cell = recovery action.

Legend:
- `A` = automatic recovery (no user prompt)
- `P` = user prompt via banner (manual gate)
- `A→P` = auto with circuit-breaker that escalates to prompt after N attempts
- `—` = not possible / out-of-scope (terminal state)

| State \ Failure          | M1 SIGTERM | M2 SIGKILL | M3 OOM | M4 Loop exc | M5 Power | M6 Rate429 | M7 Auth | M8 Net | M9 Disk | M10 Sub-kill | M11 SSE | M12 Race | M13 Corrupt | M14 Timeout | M15 Concurrent | M16 Mid-CP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IDLE                      | A          | A          | P      | —           | A        | —          | —       | —      | P       | —            | A       | A        | P           | —           | A              | —          |
| RUNNING                   | A          | P          | P      | P           | P        | A→P        | P       | A→P    | P       | A→P          | A       | A        | P           | P           | A              | A→P        |
| PAUSED(manual)            | A          | A          | P      | A           | P        | —          | —       | —      | P       | —            | A       | A        | P           | —           | A              | —          |
| PAUSED(graceful_shutdown) | A          | A          | P      | A           | P        | —          | —       | —      | P       | —            | A       | A        | P           | —           | A              | —          |
| PAUSED(crash_recovery)    | A          | P          | P      | A           | P        | —          | —       | —      | P       | —            | A       | A        | P           | —           | A              | —          |
| PAUSED(loop_crash)        | A          | A          | P      | A           | P        | —          | —       | —      | P       | —            | A       | A        | P           | —           | A              | —          |
| PAUSED(credit_exhausted)  | A          | A          | P      | A           | P        | —          | P       | —      | P       | —            | A       | A        | P           | —           | A              | —          |
| PAUSED(network_failure)   | A          | A          | P      | A           | P        | —          | —       | A→P    | P       | —            | A       | A        | P           | —           | A              | —          |
| PAUSED(subprocess_killed) | A          | A          | P      | A           | P        | —          | —       | —      | P       | A→P          | A       | A        | P           | —           | A              | —          |
| PAUSED(disk_full)         | A          | A          | P      | A           | P        | —          | —       | —      | P       | —            | A       | A        | P           | —           | A              | —          |
| PAUSED(task_timeout)      | A          | A          | P      | A           | P        | —          | —       | —      | P       | —            | A       | A        | P           | P           | A              | —          |
| WAITING_RESET             | A          | P          | P      | A           | P        | A→P        | —       | A→P    | P       | —            | A       | A        | P           | —           | A              | A→P        |
| COMPLETED                 | —          | —          | —      | —           | —        | —          | —       | —      | —       | —            | A       | —        | P           | —           | A              | —          |
| ABORTED                   | —          | —          | —      | —           | —        | —          | —       | —      | —       | —            | A       | —        | P           | —           | A              | —          |

### 5.1 Recovery action specifications

For each combination labeled `A` or `A→P`, the implementation must execute:

- **M1 (SIGTERM) + RUNNING** → set `lastShutdownReason='graceful'`, send subprocess SIGTERM, `await` up to 10s for subprocess exit, transition queue → `paused/graceful_shutdown`, persist, exit lifespan.
- **M2 (SIGKILL) + RUNNING** → not catchable; on next boot `rehydrate_from_db` finds `running` task, resets to `pending`, queue → `paused/crash_recovery`, banner.
- **M6 (Rate429) + RUNNING** → `_schedule_auto_resume(reset_time + 60s)`. Pre-flight ping before fire (Mode 16 fix).
- **M6 + WAITING_RESET** → already in WAITING_RESET; if a new exhaustion fires while we're waiting (shouldn't happen, but defensively), update `reset_time` to the later of (current, new), re-arm timer.
- **M8 (Network) + RUNNING** → `networkRetryCount += 1`. Schedule retry at `now + 30s * 3^networkRetryCount`. After 3 attempts, → `paused/manual`.
- **M10 (Sub-kill) + RUNNING** → retry up to 2 times, then → `paused/subprocess_killed`, banner.
- **M11 (SSE drop) + ANY** → no backend action; frontend reconnects automatically.
- **M12 (Race) + ANY** → asyncio.Lock per queue_id serializes; second caller is a no-op.
- **M15 (Concurrent create) + IDLE** → asyncio.Lock + DB-level partial unique index serializes.
- **M16 (Mid-checkpoint) + WAITING_RESET** → on rehydration, ping pre-flight. If ping 429s, push timer +5min and re-arm. After 5 push-outs, → `paused/manual`.

### 5.2 Holes in the matrix (verified — none)

A "hole" would be a `RUNNING × FailureMode` cell with no defined action. Every
cell in the RUNNING row has an action. Every cell in every PAUSED(*) row either
has an action or is "—" (e.g. M6 rate-limit while in PAUSED(disk_full) doesn't
make sense — we're not running). All `—` cells are correctly out-of-scope.

---

## 6. UI Surface

For each recoverable state, the floating bar (`AutoPilotFloatingBar.tsx`) shows
a banner + badge + actions. Spec for E5:

| State | Border color | Badge text | Banner content | Actions |
|---|---|---|---|---|
| RUNNING | amber | (no badge) | (no banner) | Pause, Skip, Abort |
| PAUSED(manual) | zinc | "Paused" | (no banner) | Resume, Skip, Abort |
| PAUSED(graceful_shutdown) | blue | "Auto-paused" | "AutoPilot paused for backend restart. Click Resume to continue." | Resume, Abort |
| PAUSED(crash_recovery) | red | "Crash Recovered" | "AutoPilot recovered after backend restart. The previous run on CB-XXXX was interrupted." | Resume, Skip current, Abort |
| PAUSED(loop_crash) | red | "Internal Error" | "AutoPilot crashed. Error logged. Resume to skip past or Abort." (link to event log) | Resume, Skip, Abort, View error |
| PAUSED(credit_exhausted) | dark-red | "Credits Exhausted" | "Anthropic credits exhausted or API key invalid. Top up credits or switch model. Auto-retry disabled." | Switch model, Abort, (link to console.anthropic.com) |
| PAUSED(network_failure) | yellow | "Network Issue" | "Network error retrying in N seconds (attempt M/3)." | Resume now, Abort |
| PAUSED(subprocess_killed) | yellow | "Subprocess Killed" | "Claude CLI subprocess was killed (attempt M/2)." | Resume, Skip, Abort |
| PAUSED(disk_full) | red | "Disk Full" | "Disk is N% full. Free space and click Resume. AutoPilot is paused to prevent data loss." | Resume (after free), Abort |
| PAUSED(task_timeout) | yellow | "Task Stuck" | "CB-XXXX has been running for N minutes (last activity M minutes ago)." | Continue waiting, Skip task, Abort |
| WAITING_RESET | amber | "Token Exhausted" | Existing — countdown timer + Wait/Switch/Abort | (existing) |
| COMPLETED | green | "Completed" | "AutoPilot finished N tasks successfully." | Dismiss |
| ABORTED | gray | "Aborted" | "AutoPilot stopped. N tasks completed, M remaining." | Dismiss |

### 6.1 Recovery banner unification

All `paused/*` states except `manual` should render through one
`<RecoveryBanner reason={pauseReason} ...>` component. Per-reason copy lives in
a `RECOVERY_COPY` map keyed by reason. This replaces the current ad-hoc
crash-recovery banner so adding a new reason in the future is one map entry, not
a new component.

### 6.2 Toast notifications (via existing SSE event stream)

Already streamed via `/api/execute/queue/events`. New event types from §3.4 should
each have a `useAutoPilotEvents` toast. Recommended copy:

- `shutdown_paused` — "AutoPilot paused — backend is restarting."
- `network_failure` — "Network error — retrying in Ns."
- `network_retry_scheduled` — (silent; only on circuit-break do we toast)
- `subprocess_killed` — "Claude subprocess died — retrying."
- `disk_full_detected` — "Disk full — AutoPilot paused for safety."
- `task_timeout` — "CB-XXXX is taking longer than expected."
- `credit_exhausted` — "Anthropic credits exhausted — manual action required."

---

## 7. Test Matrix (Chaos Tests)

Tests are owned by E6. Each test runs in CI with a real SQLite DB and the
async event loop. `pytest-asyncio` + `pytest-timeout` (5 min cap per test).

### 7.1 Process death tests

| ID | Scenario | Expected | Owner module |
|---|---|---|---|
| C1 | Start queue, kill loop with `task.cancel()`, restart service, call `rehydrate_from_db()` | Queue → `paused/crash_recovery`, RUNNING task reset to PENDING | tests/test_chaos_loop_cancel.py |
| C2 | Start queue, simulate SIGTERM via lifespan call, restart | Queue → `paused/graceful_shutdown` (NOT crash_recovery) | tests/test_chaos_sigterm.py |
| C3 | Start queue, set subprocess PID, simulate `os.kill(pid, 0)` failure on rehydration | Queue → `paused/subprocess_killed` | tests/test_chaos_subprocess_dead.py |
| C4 | Start queue, raise `OperationalError("disk I/O error")` from `_persist` | Queue → `paused/disk_full`, NO further task execution | tests/test_chaos_disk_full.py |
| C5 | Start queue, raise generic exception in loop body | Queue → `paused/loop_crash`, audit event has redacted traceback | tests/test_chaos_loop_exception.py |

### 7.2 API failure tests

| ID | Scenario | Expected | Owner module |
|---|---|---|---|
| C6 | Inject 429 with `rate_limit_error` body → check rate-limit path | Queue → WAITING_RESET, timer armed | tests/test_chaos_rate_limit.py |
| C7 | Inject 401 with `invalid_api_key` body → check auth path | Queue → `paused/credit_exhausted`, NO timer | tests/test_chaos_auth_failure.py |
| C8 | Inject 402 with `credit balance` body → check credit path | Queue → `paused/credit_exhausted` | tests/test_chaos_credit_exhausted.py |
| C9 | Inject `connection reset` in subprocess stderr | Queue → `paused/network_failure`, exp-backoff timer | tests/test_chaos_network_failure.py |
| C10 | Trigger 3 consecutive M6 → assert circuit-break to manual | `pause_reason='manual'`, `auto_resume_attempts=4` | tests/test_chaos_circuit_breaker.py |
| C11 | Trigger M6, restart backend, verify `rearm_auto_resume_timers` | Timer re-armed within ±12h window | tests/test_chaos_rehydrate_waiting_reset.py (exists) |
| C12 | M16 — exhaust → wait → boot crash → reboot, verify ping pre-flight | Pre-flight pings, pushes timer if 429 | tests/test_chaos_ping_preflight.py |

### 7.3 Race condition tests

| ID | Scenario | Expected | Owner module |
|---|---|---|---|
| C13 | Two concurrent `POST /api/queue` for the same project | One succeeds (201), other 409 | tests/test_race_concurrent_create.py |
| C14 | Two concurrent `resume_queue` calls | One transitions, second is no-op, audit log has 1 `resumed` event | tests/test_race_concurrent_resume.py |
| C15 | Manual resume during auto-resume timer fire (within 10ms) | Timer cancelled, manual wins, no double-resume | tests/test_race_manual_vs_auto.py |
| C16 | `abort_queue` called during `_execute_task` mid-poll | Subprocess SIGTERM'd, task → FAILED, queue → ABORTED, no orphan | tests/test_race_abort_during_execute.py |

### 7.4 Timeout / hang tests

| ID | Scenario | Expected | Owner module |
|---|---|---|---|
| C17 | Stuck subprocess (no progress for > task_max_runtime) | Queue → `paused/task_timeout`, banner shown | tests/test_chaos_task_timeout.py |
| C18 | Stuck subprocess but `lastProgressAt` keeps updating | NO timeout (still actively working) | tests/test_chaos_long_running_active.py |

### 7.5 Persistence tests

| ID | Scenario | Expected | Owner module |
|---|---|---|---|
| C19 | Start queue, advance 5 tasks, kill backend mid-task 6, reboot | Tasks 1-5 persisted as COMPLETED, task 6 reset to PENDING | tests/test_persistence_partial.py |
| C20 | Mutate DB row to `status='INVALID_VALUE'`, call rehydrate | Queue quarantined, NOT loaded into _queues, banner shown | tests/test_persistence_corrupt.py |
| C21 | Disk-full simulation during _persist on task 6 commit | Tasks 1-5 still durable, task 6 NOT advanced, queue → paused/disk_full | tests/test_persistence_disk_full_atomic.py |
| C22 | Stress: 100 concurrent transition() calls on the same queue | All serialize via lock, audit log is sequential, no lost events | tests/test_persistence_stress.py |

### 7.6 Frontend reconnect tests (Playwright)

| ID | Scenario | Expected | Owner module |
|---|---|---|---|
| C23 | SSE drop → 30s → reconnect | UI state matches backend, no lost events | frontend/__tests__/e2e/autopilot-reconnect.spec.ts |
| C24 | Queue completes while tab backgrounded → user returns | Toast: "AutoPilot completed N tasks while you were away" | frontend/__tests__/e2e/autopilot-background.spec.ts |
| C25 | Two tabs open same queue, abort in tab 1 | Tab 2 state updates to ABORTED within 3s | frontend/__tests__/e2e/autopilot-multi-tab.spec.ts |

---

## 8. Implementation Order

```
                         ┌─────────────────────────┐
                         │  CB-2747 (E1) — DESIGN  │  ← THIS DOC
                         │  llm-architect          │
                         └──────────┬──────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│  CB-2748 (E2)       │ │  CB-2749 (E3)       │ │  CB-2750 (E4)       │
│  Failure detection  │ │  State machine      │ │  Lifespan +         │
│  classes            │ │  refactor +         │ │  subprocess         │
│  (M6/7/8/10/14)     │ │  atomic transitions │ │  lifecycle          │
│                     │ │  (M3/4/5/9/11/12/   │ │  (M1/M2)            │
│  python-pro         │ │  13/15/16)          │ │                     │
│                     │ │  python-pro         │ │  python-pro         │
│  Output:            │ │  Output:            │ │  Output:            │
│  - ExhaustionDetect │ │  - transition() fn  │ │  - Lifespan hook    │
│  - NetworkErrorDet  │ │  - per-queue Lock   │ │  - SubprocessPidReg │
│  - AuthErrorDet     │ │  - schema migrate   │ │  - ping pre-flight  │
│  - SubprocessKill   │ │  - quarantine logic │ │                     │
│  - TaskTimeout      │ │                     │ │                     │
└─────────┬───────────┘ └─────────┬───────────┘ └─────────┬───────────┘
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │  CB-2751 (E5)       │
                       │  Recovery banner +  │
                       │  toast unification  │
                       │  (depends on E2/E3) │
                       │  react-specialist   │
                       └──────────┬──────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │  CB-2752 (E6)       │
                       │  Chaos test suite   │
                       │  (depends on all)   │
                       │  test-engineer      │
                       │                     │
                       │  - C1-C25 from §7   │
                       └──────────┬──────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │  CB-2753 (E7)       │
                       │  Production         │
                       │  rollout +          │
                       │  monitoring         │
                       │  devops-engineer    │
                       └─────────────────────┘
```

### 8.1 Why E2/E3/E4 are parallel-safe

- **E2** introduces *new classes* (`ExhaustionDetector`, `NetworkErrorDetector`, etc.) that replace `is_token_exhaustion`. The integration point is a single function call site in `run_queue` — minimal merge surface.
- **E3** refactors persistence (`transition()`) and adds Locks. Touches `autopilot_queue_service.py` heavily but the public API surface (`pause_queue`, `resume_queue`, `abort_queue`, etc.) stays the same.
- **E4** adds lifespan + PID tracking. Touches `app/main.py`, `terminal_service.py`, and adds a new `subprocess_pid_registry.py` module. No overlap with E2/E3.

The merge order is E2 → E3 → E4 (alphabetical), conflicts will be in
`autopilot_queue_service.py` and resolvable by hand because E3 owns the
transition mechanics and E2 owns the detection.

### 8.2 What python-pro needs to know about each epic

**E2 (CB-2748):**
- New file: `backend/services/autopilot_failure_detection.py`
- Class hierarchy:
  ```python
  class FailureDetector(Protocol):
      def detect(self, session: TerminalSession) -> Optional[FailureClass]: ...

  class ExhaustionDetector(FailureDetector): ...        # M6, M7
  class NetworkErrorDetector(FailureDetector): ...      # M8
  class SubprocessKillDetector(FailureDetector): ...    # M10
  class TaskTimeoutDetector(FailureDetector): ...       # M14

  class FailureClass(Enum):
      RATE_LIMIT = "rate_limit"
      CREDIT_EXHAUSTED = "credit_exhausted"
      NETWORK = "network"
      SUBPROCESS_KILLED = "subprocess_killed"
      TASK_TIMEOUT = "task_timeout"
      UNKNOWN = "unknown"

  DETECTORS: list[FailureDetector] = [...]  # priority order

  def classify_failure(session: TerminalSession) -> FailureClass: ...
  ```
- Replace `is_token_exhaustion(session)` calls in `run_queue` with `classify_failure(session)`.
- Each detector emits a structured `FailureContext` so the loop can pass it to `transition()`.
- Tests: per-detector unit tests + integration tests with synthetic sessions.

**E3 (CB-2749):**
- Add `_locks: Dict[str, asyncio.Lock]` to `AutoPilotQueueService`.
- Add `transition()` async function — single-transaction state change with rollback semantics.
- Add Alembic-style migration for new columns (or use SQLAlchemy `MetaData.create_all` since this is SQLite).
- Add `_quarantined_queue_ids: set[str]` and quarantine path in `_record_to_queue`.
- Refactor `pause_queue`, `resume_queue`, `skip_current`, `abort_queue` to acquire the per-queue lock.
- Add `RECOVERABLE_PAUSE_REASONS` map → human-readable copy.
- Add DB-level partial unique index for active queue.

**E4 (CB-2750):**
- New file: `backend/services/subprocess_pid_registry.py` — track active PIDs.
- Modify `terminal_service.start_execution` to register PID; `stop_execution` to unregister.
- Modify `app/main.py` lifespan shutdown:
  ```python
  # Before cancel_all_background_tasks:
  await autopilot_queue_service.graceful_shutdown_pause(timeout=10)
  # That method:
  #   - sets queue.lastShutdownReason='graceful'
  #   - calls _stop_flag = True on each active queue
  #   - sends SIGTERM to active subprocess PIDs
  #   - waits for run_queue tasks to exit (with timeout)
  #   - persists final state
  ```
- Add ping pre-flight method to `terminal_service`.

**E5 (CB-2751):**
- New component: `frontend/components/codeboard/RecoveryBanner.tsx`.
- Map: `RECOVERY_COPY` keyed by `pauseReason`.
- Update `AutoPilotFloatingBar` to render `<RecoveryBanner>` instead of inline crash-recovery banner.
- Add toasts for each new event type.

**E6 (CB-2752):**
- See §7. ~25 chaos tests.
- Helper: `tests/utils/chaos.py` with `simulate_sigkill`, `inject_disk_full`, `inject_429_with_body`, etc.

**E7 (CB-2753):**
- Wire metrics to existing `/queue/metrics` endpoint.
- Add Sentry breadcrumbs for each new event type.
- Document runbook updates in `backend/docs/AUTOPILOT_RUNBOOK.md`.

### 8.3 Risk register (read by all implementers)

| # | Risk | Mitigation |
|---|---|---|
| R1 | E3 schema migration on production DB fails halfway | Migration is additive (new nullable columns + new index); old code keeps working with NULLs. Run migration in a transaction. |
| R2 | Per-queue lock causes deadlock if held across awaits that need the lock again | All locked sections are *short* (status check + transition). No nested lock acquisitions. Lint with `asyncio-deadlock-checker` or hand-audit. |
| R3 | E2 detector misclassifies a real task failure as network error → infinite retry | Each detector has an explicit `EXAMPLE_BODIES` test fixture. Integration test: feed real Anthropic error bodies harvested from the audit log; assert correct classification. |
| R4 | E4 graceful shutdown timeout (10s) is too short — subprocess doesn't exit, lifespan hangs | Use `asyncio.wait_for(timeout=10)` and on timeout, send SIGKILL to subprocess and continue shutdown. Better to lose a checkpoint than hang the backend forever. |
| R5 | Pre-flight ping in M16 burns a token per crash recovery | ≤1 token per recovery; negligible vs full task re-run (1k+ tokens). |
| R6 | Rolling out E2/E3/E4 to a live AutoPilot (Eli's machine right now) — currently running queues might break mid-flight | E10 persistence flag still exists. New code respects in-flight queues' existing state; only NEW queues get new transition logic. Migration adds nullable columns. |

---

## 9. Acceptance criteria (for E1 closeout)

- [x] All 16 failure modes documented with trigger / current / required / recovery
- [x] Current code map written (3 state holders + transitions diagram)
- [x] 12 gaps in current state machine identified with severity
- [x] Target state machine diagram + transition table
- [x] Persistence guarantees: WAL config, atomic transition contract, per-task vs per-queue checkpoint, partial-write recovery, two-phase commit between Issue + Task status
- [x] Recovery matrix complete (no holes — every RUNNING × FailureMode cell has an action)
- [x] UI surface spec for every recoverable state
- [x] 25 chaos tests defined (process death, API failure, race, timeout, persistence, frontend reconnect)
- [x] Implementation order with dependency arrows + per-epic notes for python-pro
- [x] Risk register

E1 is **CWQ-ready** when this doc is committed and a comment on CB-2746 links to it.

---

## 10. Appendix — File-level inventory of changes (E2/E3/E4 preview)

```
backend/
  services/
    autopilot_queue_service.py     [E3 heavy refactor; E2 calls; E4 hooks]
    autopilot_failure_detection.py [E2 NEW]
    subprocess_pid_registry.py     [E4 NEW]
    terminal_service.py            [E4 PID register + ping]
  utils/
    autopilot_repository.py        [E3 transition() helper]
  models/
    autopilot.py                   [E3 schema additions]
    database.py                    [E3 PRAGMA wal_autocheckpoint]
  app/
    main.py                        [E4 graceful shutdown hook]
  api/
    execution.py                   [E3 active-queue lock; M15 fix]
  tests/
    test_chaos_*.py                [E6 NEW — 22 files]
    test_persistence_*.py          [E6 NEW — 4 files]
    utils/
      chaos.py                     [E6 NEW]

frontend/
  components/codeboard/
    AutoPilotFloatingBar.tsx       [E5 use RecoveryBanner]
    RecoveryBanner.tsx             [E5 NEW]
  contexts/
    AutoPilotContext.tsx           [E5 lastEventId reconnect]
  hooks/
    useAutoPilotEvents.ts          [E5 new event type toasts]
  __tests__/e2e/
    autopilot-reconnect.spec.ts    [E6 NEW]
    autopilot-background.spec.ts   [E6 NEW]
    autopilot-multi-tab.spec.ts    [E6 NEW]

frontend/prisma/
  schema.prisma                    [E3 mirror of new columns]
  migrations/.../migration.sql     [E3 NEW]

docs/
  plans/
    2026-05-09-bulletproof-autopilot-design.md  [E1 — THIS DOC]

backend/docs/
  AUTOPILOT_RUNBOOK.md             [E7 update]
```

---

**End of design document.** python-pro / react-specialist / test-engineer:
this is the spec. Implement E2-E6 in parallel where the dependency graph allows.
