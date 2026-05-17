CB-2749 — Fields / helpers deferred to CB-2748 (E2)

## Context

CB-2749 (E3) adds categorised exhaustion detection and wires it into
`run_queue`.  Some state transitions could be made more robust with schema
or helper additions that are CB-2748's territory.  This file records what
E3 needs and how E3 works around their absence today.

---

## 1. `transition_state` atomic helper (design doc §4.2)

**Needed:** A single-transaction helper that updates `queue.status`,
`queue.pause_reason`, inserts an `AutoPilotEvent`, and updates the relevant
`AutoPilotTaskRecord`, all in one `BEGIN ... COMMIT`.

**Current workaround (E3):** `_persist(queue, event_type, payload)` is
called immediately after setting `queue.status` / `queue.pause_reason` in
memory.  This is two separate writes (state + event) but is still correct
because the queue loop is single-threaded (asyncio).  Mark the call site
with `# CB-2748-pending` if E2 provides the helper.

---

## 2. `AutoPilotQueueRecord.pauseReason` extended value set

**Needed:** The new categories `credit_exhaustion` and `auth_failure`
(plus `overloaded`, `rate_limit_5h`, `rate_limit_weekly`, `unknown_429`)
should be stored in `pauseReason`.  The current column is `TEXT` with no
enum constraint, so any string value persists fine.

**Current workaround (E3):** Values are stored as-is (plain string).  No
schema migration is needed for CB-2749 alone.  E2 may want to document the
extended value set in a migration note.

---

## 3. `AutoPilotQueueRecord.lastShutdownReason` (design doc §3.4)

**Needed:** To distinguish graceful SIGTERM from SIGKILL/OOM crashes on
rehydration.  E3 does not set this field.

**Current workaround (E3):** Not applicable — E3 only handles the
exhaustion path, not shutdown.  E2 owns this column.

---

## 4. `AutoPilotTaskRecord.lastProgressAt` / `runtimeSeconds`

**Needed:** Per-task wall-clock for Mode 14 (timeout detection).

**Current workaround (E3):** Not applicable — E3 does not implement
timeout detection (that is E4/E6 territory).

---

## Summary of E3 deferred items

| Item | Owner | Impact on E3 |
|---|---|---|
| `transition_state` atomic helper | CB-2748 (E2) | Low — two writes are logically equivalent under single-threaded asyncio |
| `pauseReason` extended enum doc | CB-2748 (E2) | None — TEXT column accepts any string |
| `lastShutdownReason` column | CB-2748 (E2) | None — E3 does not touch shutdown paths |
| `lastProgressAt` / `runtimeSeconds` | CB-2748 / E4 | None — timeout not in E3 scope |
