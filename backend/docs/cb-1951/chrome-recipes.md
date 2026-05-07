# CB-1951 Chrome UI Test Recipes

Manual recipes the runner points to for QA-C01..C12. Execute via the
`mcp__claude-in-chrome__*` tools from a fresh Claude session, then mark
PASS/FAILED via the runner's `report()` callable or directly through the
QA Board UI.

**Setup (do this once):**
```python
# In the Claude Code session running these tests:
from cb_1951_qa_runner import report  # add `from scripts.codeboard...`

# After each test, call:
report("QA-C01", "PASS", "What you observed; one line")
# or
report("QA-C01", "FAILED", "What broke; relevant snapshot path")
```

**Common preconditions for every test:**
1. Backend running on `http://localhost:8401` (check `curl -s http://localhost:8401/api/execute/queue/active`)
2. Frontend running on `http://localhost:3601`
3. At least one open AutoPilot queue or the ability to create one

---

## QA-C01 — Floating bar renders RUNNING state correctly

**Setup:** start AutoPilot via the CodeBoard UI on any feature.

**Steps:**
1. `mcp__claude-in-chrome__tabs_context_mcp` — confirm we have a usable tab
2. `mcp__claude-in-chrome__navigate` → `http://localhost:3601/codeboard`
3. `mcp__claude-in-chrome__take_screenshot` (name: `qa-c01-running.png`)
4. `mcp__claude-in-chrome__find` for selector `[data-testid="autopilot-floating-bar"]` (or just text "AutoPilot")
5. Read console messages: `mcp__claude-in-chrome__read_console_messages`

**Pass criteria:**
- Floating bar visible in bottom-right
- Spinner / running icon present
- Current task title shown
- No console errors

---

## QA-C02 — Manual PAUSED state

**Setup:** continuing from C01, click Pause inside the floating bar.

**Steps:**
1. `mcp__claude-in-chrome__click` the Pause button
2. Wait 1s
3. Snapshot: `qa-c02-paused.png`

**Pass criteria:**
- Bar shows gray border
- Resume button replaces Pause
- Pause icon visible

---

## QA-C03 — WAITING_RESET with countdown

**Setup:** force the queue into WAITING_RESET via API:
```sh
# Find the queue id, then:
curl -X POST http://localhost:8401/api/execute/queue/$QID/wait-for-reset \
  -H "Content-Type: application/json" \
  -d '{"reset_time_str":"3:00 PM"}'
```

**Steps:**
1. Navigate to /codeboard
2. Snapshot: `qa-c03-waiting-reset.png`
3. Wait 5s
4. Snapshot again: `qa-c03-waiting-reset-tick.png`
5. Compare countdown values

**Pass criteria:**
- Amber border on bar
- Countdown text (e.g. "Auto-resumes at 15:00 (X minutes left)")
- Countdown value DECREASED across the two snapshots
- "Resume now" button visible and enabled

---

## QA-C04 — crash_recovery banner after backend restart

**Setup:**
1. Start AutoPilot with at least one task running.
2. Kill the backend: `kill -9 $(pgrep -f "uvicorn.*8401")`
3. Wait for the watchdog to restart it (~5-10s).

**Steps:**
1. Navigate to /codeboard
2. Snapshot: `qa-c04-crash-recovery.png`
3. Read console for any boot-time errors

**Pass criteria:**
- Red banner with "AutoPilot recovered after backend restart" copy
- Three buttons visible: Resume, Skip current task, Abort
- Bar still rendered in bottom-right with red border

---

## QA-C05 — Resume now button click resumes queue

**Setup:** continuing from C03.

**Steps:**
1. Click "Resume now"
2. Wait 2s
3. Snapshot: `qa-c05-resumed.png`
4. Read console for errors

**Pass criteria:**
- Bar transitions to running state (amber border, spinner)
- No console errors
- Backend log shows `Queue ... resumed`

---

## QA-C06 — Sonner toast on auto-pause

**Setup:** start AutoPilot with a mock CLI that returns `rate limit exceeded`. (See `tests/test_token_exhaustion_detection.py` for fixture seeds.)

**Steps:**
1. Trigger first task to fail
2. Within 3s of the failure, snapshot the toast container

**Pass criteria:**
- Toast appears in bottom-right with title "AutoPilot paused — token exhaustion"
- Toast auto-dismisses after ~5s

---

## QA-C07 — Sonner toast on auto-resume

**Setup:** force WAITING_RESET with `reset_time = now + 10s` (so total wait ≈ 70s with 60s buffer).

**Steps:**
1. Start a screen recording or take snapshots every 10s for 90s
2. Look for a toast saying "AutoPilot auto-resumed"

**Pass criteria:**
- Toast fires at approx `reset_time + 60s` ± 5s
- Bar transitions to RUNNING

---

## QA-C08 — Settings toggle for AUTOPILOT_PERSISTENCE_ENABLED

**Note:** the Settings page UI toggle (E10.1.2) is DEFERRED. The backend
endpoint works:
```sh
curl http://localhost:8401/api/execute/queue/settings/persistence-enabled
curl -X POST http://localhost:8401/api/execute/queue/settings/persistence-enabled \
  -H "Content-Type: application/json" -d '{"enabled":false}'
```

**Pass criteria for now:** API toggles flag in/out as expected. Mark this
test as `MANUAL` PASS after API verification, with note "UI toggle deferred
to follow-up; API works".

---

## QA-C09 — Metrics tile shows live counts

**Note:** Settings page metrics tile (E6.3.2) is DEFERRED. The backend
endpoint works:
```sh
curl http://localhost:8401/api/execute/queue/metrics
```

**Pass criteria for now:** API returns correct counts (running / paused /
waiting_reset / completed / aborted / autoPause24h / circuitBreakerTrips24h
/ crashRecovery24h). Tile UI is a follow-up.

---

## QA-C10 — Watchdog page shows recovery event

**Note:** Watchdog integration (E6.2) is DEFERRED — schema mismatch. The
AutoPilotEvent table records the recovery; verify there:
```sh
sqlite3 frontend/prisma/dev.db \
  "SELECT type, payload, createdAt FROM AutoPilotEvent \
   WHERE type='crash_recovery_detected' ORDER BY createdAt DESC LIMIT 5"
```

**Pass criteria:** at least one row exists matching the most recent C04
trigger.

---

## QA-C11 — CodeBoard back-button preserves URL state after AutoPilot interactions

**Setup:** open `http://localhost:3601/codeboard`, ensure some filters are set.

**Steps:**
1. Click into an issue detail
2. Open AutoPilot floating bar (interact with it once)
3. Click browser Back
4. Snapshot: `qa-c11-back.png`
5. Click browser Forward
6. Click browser Back again

**Pass criteria:**
- Filters / project / view all preserved on each back/forward step
- Matches CB-1921 baseline behaviour

---

## QA-C12 — AutoPilot survives full page reload mid-queue

**Setup:** start AutoPilot with a long-running task. Wait for it to begin executing.

**Steps:**
1. Hard-reload (`Cmd-Shift-R` or programmatically)
2. Wait 2s
3. Snapshot: `qa-c12-reload.png`

**Pass criteria:**
- Floating bar reappears within ~2s of reload
- `currentIndex` and progress bar match pre-reload values
- No console errors
