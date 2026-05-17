"""
CB-2748 — Persistence Overhaul Tests.

Covers:
  1. WAL mode is confirmed at runtime on a real engine.
  2. transition_state rejects illegal transitions (terminal states, bad pairs).
  3. transition_state accepts legal transitions and emits STATE_TRANSITION event.
  4. _persist re-raises OperationalError (disk-full) and emits PERSIST_FAILED/DISK_FULL_DETECTED.
  5. _persist re-raises generic exceptions and emits PERSIST_FAILED.
  6. checkpoint() writes lastCheckpointAt and emits CHECKPOINT_WRITTEN event.
  7. Schema migration script runs idempotently (twice without error).
  8. set_subprocess_pid round-trips PID through DB and emits SUBPROCESS_PID_RECORDED.
  9. set_subprocess_pid clears PID on completion (pid=None).
 10. State machine table has no holes — all 6 states reachable.
 11. classify_operational_error correctly categorises disk-full messages.
 12. transition_state raises ValueError on unknown queue_id.
 13. AutoPilotEventType constants all exist and are non-empty strings.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.autopilot import (
    AutoPilotEventType,
    AutoPilotQueueRecord,
    AutoPilotTaskRecord,
    _ALLOWED_TRANSITIONS,
    is_transition_allowed,
)
from models.database import Base
from models import Project
from utils.autopilot_repository import (
    classify_operational_error,
    checkpoint,
    list_events,
    load_queue,
    record_event,
    save_queue,
    set_subprocess_pid,
    transition_state,
    IllegalStateTransitionError,
)
from services.autopilot_queue_service import (
    AutoPilotQueue,
    AutoPilotQueueService,
    QueueConfig,
    QueueStatus,
    QueueTask,
    TaskStatus,
)


# ---------------------------------------------------------------------------
# Shared in-memory engine + session factory patched into AsyncSessionLocal
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mem_engine():
    """Create an in-memory SQLite engine with WAL-mode pragmas and all tables."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
    )
    async with engine.begin() as conn:
        # Enable WAL on in-memory DB (won't persist, but tests the pragma path)
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(mem_engine):
    """Return an async_sessionmaker bound to the in-memory engine."""
    return async_sessionmaker(mem_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory):
    """Open a single session for assertion-level reads."""
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def seeded_session(session_factory):
    """Session with a Project row so FK constraints are satisfied."""
    async with session_factory() as s:
        s.add(
            Project(
                id="p-test",
                name="test-project",
                path="/tmp/test",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            )
        )
        await s.commit()
        yield s


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_queue(
    queue_id: str | None = None,
    status: QueueStatus = QueueStatus.RUNNING,
    n_tasks: int = 2,
) -> AutoPilotQueue:
    qid = queue_id or str(uuid.uuid4())
    tasks = [
        QueueTask(
            issue_id=f"issue-{i}",
            issue_key=f"CB-{1000 + i}",
            issue_title=f"Task {i}",
            order=i,
            status=TaskStatus.PENDING,
        )
        for i in range(n_tasks)
    ]
    return AutoPilotQueue(
        id=qid,
        feature_id="feat-1",
        feature_key="CB-9999",
        project_id="p-test",
        project_path="/tmp/test",
        status=status,
        tasks=tasks,
        config=QueueConfig(),
        current_index=0,
        created_at=datetime.utcnow(),
    )


async def _seed_queue(session_factory, queue_id: str, status: str = "running") -> str:
    """Insert an AutoPilotQueueRecord row with one task; return task id."""
    task_id = str(uuid.uuid4())
    async with session_factory() as db:
        db.add(
            AutoPilotQueueRecord(
                id=queue_id,
                projectId="p-test",
                featureId="feat-1",
                status=status,
                state=status,
                currentIndex=0,
                config="{}",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
                recoveryGeneration=0,
            )
        )
        db.add(
            AutoPilotTaskRecord(
                id=task_id,
                queueId=queue_id,
                sequence=0,
                issueId="issue-0",
                status="pending",
            )
        )
        await db.commit()
    return task_id


# ---------------------------------------------------------------------------
# Test 1 — WAL mode confirmed on a file-backed engine
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wal_mode_enabled(tmp_path):
    """Confirm that WAL journal mode is applied on a file-backed SQLite engine.

    In-memory SQLite always reports 'memory' for PRAGMA journal_mode regardless
    of what you set; WAL only takes effect on file-backed databases.
    """
    db_file = tmp_path / "wal_test.db"
    file_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        future=True,
    )

    # Apply WAL pragma the same way database.py does it
    from sqlalchemy import event as sa_event

    @sa_event.listens_for(file_engine.sync_engine, "connect")
    def set_wal(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    async with file_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with file_engine.connect() as conn:
        result = await conn.execute(text("PRAGMA journal_mode"))
        row = result.fetchone()
        assert row is not None
        assert row[0].lower() == "wal", f"Expected WAL, got {row[0]!r}"

    await file_engine.dispose()


# ---------------------------------------------------------------------------
# Test 2 — transition_state rejects illegal transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_state_rejects_illegal(session_factory):
    """terminal states must reject all outgoing transitions."""
    queue_id = str(uuid.uuid4())

    # Seed the project first
    async with session_factory() as db:
        db.add(
            Project(
                id="p-test",
                name="test-project",
                path="/tmp/test",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            )
        )
        await db.commit()

    # Seed a completed queue
    async with session_factory() as db:
        db.add(
            AutoPilotQueueRecord(
                id=queue_id,
                projectId="p-test",
                status="completed",
                state="completed",
                currentIndex=0,
                config="{}",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
                recoveryGeneration=0,
            )
        )
        await db.commit()

    with patch("utils.autopilot_repository.AsyncSessionLocal", session_factory):
        with pytest.raises(IllegalStateTransitionError):
            await transition_state(queue_id, "running")


@pytest.mark.asyncio
async def test_transition_state_rejects_idle_to_paused(session_factory):
    """IDLE → PAUSED is forbidden; only RUNNING → PAUSED is allowed."""
    queue_id = str(uuid.uuid4())

    async with session_factory() as db:
        db.add(
            Project(
                id="p-test2",
                name="test-project2",
                path="/tmp/test2",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            )
        )
        await db.commit()

    async with session_factory() as db:
        db.add(
            AutoPilotQueueRecord(
                id=queue_id,
                projectId="p-test2",
                status="pending",
                state="pending",
                currentIndex=0,
                config="{}",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
                recoveryGeneration=0,
            )
        )
        await db.commit()

    with patch("utils.autopilot_repository.AsyncSessionLocal", session_factory):
        with pytest.raises(IllegalStateTransitionError):
            await transition_state(queue_id, "paused", "manual")


# ---------------------------------------------------------------------------
# Test 3 — transition_state accepts legal transitions + emits event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_state_legal_running_to_paused(session_factory):
    """RUNNING → PAUSED is legal; should update DB and emit STATE_TRANSITION event."""
    queue_id = str(uuid.uuid4())

    async with session_factory() as db:
        db.add(
            Project(
                id="p-t3",
                name="test-p3",
                path="/tmp/t3",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            )
        )
        await db.commit()

    async with session_factory() as db:
        db.add(
            AutoPilotQueueRecord(
                id=queue_id,
                projectId="p-t3",
                status="running",
                state="running",
                currentIndex=0,
                config="{}",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
                recoveryGeneration=0,
            )
        )
        await db.commit()

    with patch("utils.autopilot_repository.AsyncSessionLocal", session_factory):
        await transition_state(queue_id, "paused", "crash_recovery")

    async with session_factory() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(AutoPilotQueueRecord).where(AutoPilotQueueRecord.id == queue_id)
        )
        record = result.scalar_one()
        assert record.state == "paused"
        assert record.stateReason == "crash_recovery"
        assert record.status == "paused"
        assert record.pauseReason == "crash_recovery"

    # Verify STATE_TRANSITION event was emitted
    async with session_factory() as db:
        events = await list_events(db, queue_id)
        assert any(e.type == AutoPilotEventType.STATE_TRANSITION for e in events)


# ---------------------------------------------------------------------------
# Test 4 — _persist re-raises OperationalError (disk full)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_reraises_operational_error_disk_full():
    """_persist must re-raise OperationalError for disk-full conditions (CB-2748 G3)."""
    service = AutoPilotQueueService.__new__(AutoPilotQueueService)
    service._logger = MagicMock()
    service._persistence_enabled = True

    queue = _make_queue()

    disk_full_exc = OperationalError(
        "statement", {}, Exception("disk I/O error: no space left on device")
    )

    # save_queue raises when called inside _persist
    mock_save = AsyncMock(side_effect=disk_full_exc)

    with patch("services.autopilot_queue_service.save_queue", mock_save):
        with patch(
            "services.autopilot_queue_service.emit_persist_failed_event",
            new_callable=AsyncMock,
        ) as mock_emit:
            with pytest.raises(OperationalError):
                await service._persist(queue, "test_event", {})

            # emit_persist_failed_event should have been called with DISK_FULL_DETECTED
            mock_emit.assert_called_once()
            call_args = mock_emit.call_args
            assert call_args[0][1] == AutoPilotEventType.DISK_FULL_DETECTED


# ---------------------------------------------------------------------------
# Test 5 — _persist re-raises generic exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_reraises_generic_exception():
    """_persist must re-raise unexpected exceptions (not just swallow them)."""
    service = AutoPilotQueueService.__new__(AutoPilotQueueService)
    service._logger = MagicMock()
    service._persistence_enabled = True

    queue = _make_queue()

    generic_exc = RuntimeError("something unexpected")
    mock_save = AsyncMock(side_effect=generic_exc)

    with patch("services.autopilot_queue_service.save_queue", mock_save):
        with patch(
            "services.autopilot_queue_service.emit_persist_failed_event",
            new_callable=AsyncMock,
        ) as mock_emit:
            with pytest.raises(RuntimeError):
                await service._persist(queue, "test_event", {})

            mock_emit.assert_called_once()
            call_args = mock_emit.call_args
            assert call_args[0][1] == AutoPilotEventType.PERSIST_FAILED


# ---------------------------------------------------------------------------
# Test 6 — checkpoint writes timestamp + emits CHECKPOINT_WRITTEN
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkpoint_writes_timestamp_and_event(session_factory):
    """checkpoint() must update lastCheckpointAt and emit CHECKPOINT_WRITTEN."""
    queue_id = str(uuid.uuid4())

    async with session_factory() as db:
        db.add(
            Project(
                id="p-t6",
                name="test-p6",
                path="/tmp/t6",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            )
        )
        await db.commit()

    async with session_factory() as db:
        db.add(
            AutoPilotQueueRecord(
                id=queue_id,
                projectId="p-t6",
                status="running",
                state="running",
                currentIndex=0,
                config="{}",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
                lastCheckpointAt=None,
                recoveryGeneration=0,
            )
        )
        await db.commit()

    with patch("utils.autopilot_repository.AsyncSessionLocal", session_factory):
        await checkpoint(queue_id)

    async with session_factory() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(AutoPilotQueueRecord).where(AutoPilotQueueRecord.id == queue_id)
        )
        record = result.scalar_one()
        assert record.lastCheckpointAt is not None, "lastCheckpointAt must be set"

    async with session_factory() as db:
        events = await list_events(db, queue_id)
        checkpoint_events = [
            e for e in events if e.type == AutoPilotEventType.CHECKPOINT_WRITTEN
        ]
        assert len(checkpoint_events) == 1


# ---------------------------------------------------------------------------
# Test 7 — migration script is idempotent
# ---------------------------------------------------------------------------


def test_migration_script_idempotent(tmp_path):
    """Running the migration script twice must not raise errors."""
    import sqlite3
    import subprocess
    import sys

    db_path = str(tmp_path / "test_migrate.db")

    # Create minimal schema matching what the backend creates
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE Project (id TEXT PRIMARY KEY, name TEXT, path TEXT, "
        "status TEXT, createdAt TEXT, updatedAt TEXT)"
    )
    conn.execute(
        "CREATE TABLE AutoPilotQueueRecord ("
        "id TEXT PRIMARY KEY, projectId TEXT, featureId TEXT, status TEXT, "
        "currentIndex INTEGER DEFAULT 0, pauseReason TEXT, resetTime TEXT, "
        "config TEXT, createdAt TEXT, updatedAt TEXT, completedAt TEXT)"
    )
    conn.execute(
        "CREATE TABLE AutoPilotTaskRecord ("
        "id TEXT PRIMARY KEY, queueId TEXT, sequence INTEGER, issueId TEXT, "
        "issueKey TEXT, issueTitle TEXT, status TEXT, attempts INTEGER DEFAULT 0, "
        "sessionId TEXT, startedAt TEXT, completedAt TEXT, failureReason TEXT)"
    )
    conn.commit()
    conn.close()

    script_path = (
        "/Volumes/Seagate/Claude/ProjectsManagerWebV2Production/backend/scripts/"
        "codeboard/2026-05-09-cb-2748-schema-migration.py"
    )

    env = {"DATABASE_URL": f"sqlite:///{db_path}", "PATH": "/usr/bin:/bin"}

    # First run
    result1 = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result1.returncode == 0, f"First run failed:\n{result1.stdout}\n{result1.stderr}"
    assert "Migration complete" in result1.stdout

    # Second run — must be idempotent
    result2 = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result2.returncode == 0, f"Second run failed:\n{result2.stdout}\n{result2.stderr}"
    assert "Migration complete" in result2.stdout
    assert "added" in result2.stdout.lower() or "skipped" in result2.stdout.lower()

    # Verify all new columns exist
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(AutoPilotQueueRecord)")
    queue_cols = {row[1] for row in cur.fetchall()}
    cur.execute("PRAGMA table_info(AutoPilotTaskRecord)")
    task_cols = {row[1] for row in cur.fetchall()}
    conn.close()

    assert "state" in queue_cols
    assert "stateReason" in queue_cols
    assert "lastCheckpointAt" in queue_cols
    assert "recoveryGeneration" in queue_cols
    assert "lastProgressAt" in task_cols
    assert "subprocessPid" in task_cols


# ---------------------------------------------------------------------------
# Test 8 — set_subprocess_pid round-trips PID + emits event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_subprocess_pid_roundtrip(session_factory):
    """set_subprocess_pid stores PID and emits SUBPROCESS_PID_RECORDED event."""
    queue_id = str(uuid.uuid4())

    async with session_factory() as db:
        db.add(
            Project(
                id="p-t8",
                name="test-p8",
                path="/tmp/t8",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            )
        )
        await db.commit()

    task_id = await _seed_queue(session_factory, queue_id)

    with patch("utils.autopilot_repository.AsyncSessionLocal", session_factory):
        await set_subprocess_pid(task_id, 12345, queue_id=queue_id)

    async with session_factory() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(AutoPilotTaskRecord).where(AutoPilotTaskRecord.id == task_id)
        )
        task_record = result.scalar_one()
        assert task_record.subprocessPid == 12345

    # Verify SUBPROCESS_PID_RECORDED event
    async with session_factory() as db:
        events = await list_events(db, queue_id)
        pid_events = [e for e in events if e.type == AutoPilotEventType.SUBPROCESS_PID_RECORDED]
        assert len(pid_events) == 1


# ---------------------------------------------------------------------------
# Test 9 — set_subprocess_pid clears PID on None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_subprocess_pid_clear(session_factory):
    """Passing pid=None clears the subprocessPid column."""
    queue_id = str(uuid.uuid4())

    async with session_factory() as db:
        db.add(
            Project(
                id="p-t9",
                name="test-p9",
                path="/tmp/t9",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            )
        )
        await db.commit()

    task_id = await _seed_queue(session_factory, queue_id)

    with patch("utils.autopilot_repository.AsyncSessionLocal", session_factory):
        # Set then clear
        await set_subprocess_pid(task_id, 99999, queue_id=queue_id)
        await set_subprocess_pid(task_id, None)

    async with session_factory() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(AutoPilotTaskRecord).where(AutoPilotTaskRecord.id == task_id)
        )
        task_record = result.scalar_one()
        assert task_record.subprocessPid is None


# ---------------------------------------------------------------------------
# Test 10 — State machine table covers all 6 states (no holes)
# ---------------------------------------------------------------------------


def test_state_machine_all_states_reachable():
    """All reachable states appear in _ALLOWED_TRANSITIONS; terminal states are sinks."""
    # PENDING is the initial state — it appears as a source but may not be a
    # destination (nothing transitions INTO pending at the queue level; task-level
    # resets go through a different path). The test validates structural integrity.
    source_states = {from_state for from_state, _ in _ALLOWED_TRANSITIONS}
    destination_states = {to_state for _, to_state in _ALLOWED_TRANSITIONS}

    # Non-initial states must all be reachable as destinations
    non_initial_states = {"running", "paused", "waiting_reset", "completed", "aborted"}
    missing_destinations = non_initial_states - destination_states
    assert not missing_destinations, (
        f"Non-initial states not reachable as destinations: {missing_destinations}"
    )

    # PENDING must appear as a source (queue starts here)
    assert "pending" in source_states, "PENDING state must have outgoing transitions"

    # Terminal states must NOT appear as a source
    terminal_states = {"completed", "aborted"}
    illegal_sources = terminal_states & source_states
    assert not illegal_sources, (
        f"Terminal states should not have outgoing edges: {illegal_sources}"
    )

    # is_transition_allowed must respect the table
    assert is_transition_allowed("pending", "running") is True
    assert is_transition_allowed("running", "paused") is True
    assert is_transition_allowed("completed", "running") is False
    assert is_transition_allowed("aborted", "paused") is False


# ---------------------------------------------------------------------------
# Test 11 — classify_operational_error categorises correctly
# ---------------------------------------------------------------------------


def test_classify_operational_error_disk_full():
    """disk I/O error must classify as disk_full."""
    exc = OperationalError("stmt", {}, Exception("disk I/O error"))
    assert classify_operational_error(exc) == "disk_full"


def test_classify_operational_error_enospc():
    """ENOSPC must classify as disk_full."""
    exc = OperationalError("stmt", {}, Exception("no space left on device (ENOSPC)"))
    assert classify_operational_error(exc) == "disk_full"


def test_classify_operational_error_locked():
    """database is locked must classify as db_locked."""
    exc = OperationalError("stmt", {}, Exception("database is locked"))
    assert classify_operational_error(exc) == "db_locked"


def test_classify_operational_error_other():
    """Unknown messages classify as other."""
    exc = OperationalError("stmt", {}, Exception("some random sql error"))
    assert classify_operational_error(exc) == "other"


# ---------------------------------------------------------------------------
# Test 12 — transition_state raises ValueError on unknown queue_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_state_unknown_queue(session_factory):
    """transition_state must raise ValueError when queue_id is not in DB."""
    async with session_factory() as db:
        db.add(
            Project(
                id="p-t12",
                name="test-p12",
                path="/tmp/t12",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            )
        )
        await db.commit()

    with patch("utils.autopilot_repository.AsyncSessionLocal", session_factory):
        with pytest.raises(ValueError, match="not found in DB"):
            await transition_state("nonexistent-queue-id", "running")


# ---------------------------------------------------------------------------
# Test 13 — AutoPilotEventType constants all exist and are non-empty strings
# ---------------------------------------------------------------------------


def test_autopilot_event_type_constants():
    """All 11 new CB-2748 event type constants must be non-empty strings."""
    new_types = [
        AutoPilotEventType.STATE_TRANSITION,
        AutoPilotEventType.CHECKPOINT_WRITTEN,
        AutoPilotEventType.RECOVERY_STARTED,
        AutoPilotEventType.RECOVERY_COMPLETED,
        AutoPilotEventType.ZOMBIE_DETECTED,
        AutoPilotEventType.TOKEN_EXHAUSTION_DETECTED,
        AutoPilotEventType.AUTO_RESUME_SCHEDULED,
        AutoPilotEventType.AUTO_RESUME_FIRED,
        AutoPilotEventType.PERSIST_FAILED,
        AutoPilotEventType.DISK_FULL_DETECTED,
        AutoPilotEventType.SUBPROCESS_PID_RECORDED,
    ]
    for event_type in new_types:
        assert isinstance(event_type, str), f"{event_type!r} is not a string"
        assert len(event_type) > 0, f"Event type constant is empty"

    # All must be unique
    assert len(set(new_types)) == len(new_types), "Duplicate event type constants found"
