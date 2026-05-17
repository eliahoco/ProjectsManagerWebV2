# CB-2750 — Schema Dependencies on CB-2748 (E2)

## Summary

CB-2750 (Recovery Scheduler) gracefully degrades when CB-2748 columns are absent.
All access uses `getattr(record, column_name, None)` so older DB schemas do not crash.

## Required columns (added by CB-2748 / E2)

| Table | Column | Type | Used by CB-2750 for |
|---|---|---|---|
| `AutoPilotQueueRecord` | `recoveryGeneration` | INTEGER DEFAULT 0 | Incremented on each rehydration pass to detect repeated crash cycles |
| `AutoPilotTaskRecord` | `subprocessPid` | INTEGER NULL | PID liveness check (`os.kill(pid, 0)`) during rehydration |
| `AutoPilotQueueRecord` | `subprocess_pid` | INTEGER NULL | Fallback PID if not on task row (design TBD in E2) |

## What happens when columns are absent

- `recoveryGeneration`: the `getattr(record, "recoveryGeneration", None)` returns `None`;
  the increment is skipped inside a bare `except Exception: pass` block. Audit log still
  records the RECOVERY_STARTED event, just without the generation counter.

- `subprocessPid` on tasks: the PID liveness check is skipped entirely. Zombie detection
  still fires via the background tick (Pass 2) once the queue is in RUNNING state with no
  live coroutine.

## Migration path

When CB-2748 ships, `init_db()` via SQLAlchemy `Base.metadata.create_all` will add the
columns to the SQLite schema (using `IF NOT EXISTS` semantics from SQLAlchemy's
`checkfirst=True`). No manual `ALTER TABLE` required for development databases; production
should run the Alembic migration generated in E2.

## Event types

CB-2750 uses two new event type constants defined in `models/autopilot.py` by CB-2748:
- `AutoPilotEventType.RECOVERY_STARTED` — emitted once per queue on rehydration
- `AutoPilotEventType.ZOMBIE_DETECTED` — emitted when orphan PID detected
- `AutoPilotEventType.AUTO_RESUME_FIRED` — emitted by tick loop on auto-resume

These constants already exist in `models/autopilot.py` (shipped with CB-2748 model file).
