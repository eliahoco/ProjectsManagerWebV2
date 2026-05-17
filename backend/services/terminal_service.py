"""
Terminal Service - Manages terminal sessions for AI execution
Uses PTY for real-time streaming output from Claude Code
"""

import asyncio
import subprocess
import os
import sys
import signal
import pty
import select
import fcntl
import errno
import logging
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
import uuid
import threading
import json
import re
import struct
import termios

from services.session_pool import session_pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CB-2799: Exhaustion-signal buffer — compiled regex that matches any line
# containing a token-exhaustion or error-type signal.  Lines that match are
# captured in TerminalSession.exhaustion_signal_lines regardless of how much
# subsequent output is produced (fixing the tail-window problem).
# ---------------------------------------------------------------------------

# Matches the JSON error envelope emitted by the Claude CLI stream-json mode.
_JSON_ERROR_SIGNAL_RE = re.compile(r'\{"type"\s*:\s*"error"', re.IGNORECASE)

# All signal substrings from exhaustion_detector — collapsed into one
# alternation for a single-pass match per output line.
_EXHAUSTION_SIGNAL_SUBSTRINGS: tuple[str, ...] = (
    # _AUTH_SIGNALS
    "invalid_api_key", "authentication_error", "invalid x-api-key",
    "invalid api key", "unauthorized", "not authenticated", "permission_error",
    # _CREDIT_SIGNALS
    "out of credits", "out of extra usage", "billing issue",
    "credit balance is too low", "insufficient_quota",
    "your account has insufficient", "exceeded your current quota",
    "payment required",
    # _5H_SIGNALS
    "5 hour", "5-hour", "five hour", "5h limit", "5h reset",
    "usage limit", "usage_limit",
    # _WEEKLY_SIGNALS
    "weekly limit", "weekly usage", "per week", "week limit",
    # _OVERLOADED_SIGNALS
    "overloaded_error", "overloaded", "529",
    # _GENERIC_429_SIGNALS
    "rate_limit_error", "rate limit exceeded", "rate limit",
    "too many requests", "429", "quota exceeded",
    "resets at", "resets in", "retry after", "retry-after",
)

# Build a single compiled alternation — join longest-first to avoid shadowing.
_EXHAUSTION_SIGNAL_RE = re.compile(
    "|".join(re.escape(s) for s in _EXHAUSTION_SIGNAL_SUBSTRINGS),
    re.IGNORECASE,
)

_EXHAUSTION_SIGNAL_BUFFER_CAP = 100


class PathValidationError(Exception):
    """Raised when path validation fails"""
    pass


def validate_project_path(path: str) -> str:
    """
    Validate and normalize a project path for security.
    Prevents path traversal attacks and ensures the path is safe.

    Args:
        path: The project path to validate

    Returns:
        The validated, normalized absolute path

    Raises:
        PathValidationError: If the path is invalid or unsafe
    """
    if not path:
        raise PathValidationError("Project path cannot be empty")

    # Resolve to absolute path and normalize
    try:
        resolved_path = Path(path).resolve()
    except (OSError, ValueError) as e:
        raise PathValidationError(f"Invalid path: {e}")

    # Check that the path exists and is a directory
    if not resolved_path.exists():
        raise PathValidationError(f"Path does not exist: {resolved_path}")

    if not resolved_path.is_dir():
        raise PathValidationError(f"Path is not a directory: {resolved_path}")

    # Prevent access to sensitive system directories
    sensitive_paths = [
        "/etc", "/var", "/usr", "/bin", "/sbin", "/lib", "/lib64",
        "/boot", "/root", "/proc", "/sys", "/dev", "/run",
        str(Path.home() / ".ssh"),
        str(Path.home() / ".gnupg"),
        str(Path.home() / ".aws"),
        str(Path.home() / ".config" / "gcloud"),
    ]

    resolved_str = str(resolved_path)
    for sensitive in sensitive_paths:
        if resolved_str == sensitive or resolved_str.startswith(sensitive + "/"):
            raise PathValidationError(f"Access to sensitive path not allowed: {resolved_str}")

    return str(resolved_path)


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionPhase(str, Enum):
    """Phases of Claude Code execution for progress tracking"""
    INITIALIZING = "initializing"
    READING_FILES = "reading_files"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    WRITING_CODE = "writing_code"
    RUNNING_COMMANDS = "running_commands"
    TESTING = "testing"
    FINALIZING = "finalizing"
    COMPLETED = "completed"


class ExecutionProvider(str, Enum):
    CLAUDE_CODE = "claude_code"
    LOCAL_AI = "local_ai"


# Type for completion callback
from typing import Callable
CompletionCallback = Callable[[str, str, bool], None]  # session_id, issue_id, success


@dataclass
class TerminalSession:
    """Represents an active terminal session"""
    id: str
    issue_id: str
    issue_key: str
    issue_title: str
    project_id: str
    provider: ExecutionProvider
    status: ExecutionStatus
    process: Optional[subprocess.Popen] = None
    output: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None
    # Progress tracking
    phase: ExecutionPhase = ExecutionPhase.INITIALIZING
    progress_percent: int = 0
    current_action: str = "Starting..."
    files_read: int = 0
    files_written: int = 0
    commands_run: int = 0
    # Completion callback
    on_complete: Optional[CompletionCallback] = None
    # Project filesystem path (used for cache/worktree cleanup)
    project_path: Optional[str] = None
    # CB-2799: rolling buffer of lines that matched exhaustion/error signals.
    # Captured independently of session.output so early-arriving markers survive
    # even when the Claude CLI dumps hundreds of KB of tool output afterwards.
    exhaustion_signal_lines: List[str] = field(default_factory=list)
    # Thread safety for output list
    _output_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def _append_output(self, line: str) -> None:
        """Thread-safe append to output with 5000-line cap.

        CB-2799: Also checks each line against the exhaustion-signal regex and,
        when matched, appends to ``exhaustion_signal_lines`` (capped at
        ``_EXHAUSTION_SIGNAL_BUFFER_CAP``).  This preserves early-arriving
        exhaustion markers even when the CLI later dumps hundreds of KB of tool
        output that would otherwise scroll the tail-window past the signal.
        """
        with self._output_lock:
            self.output.append(line)
            # Cap at 5000 lines to prevent unbounded memory growth
            if len(self.output) > 5000:
                dropped = len(self.output) - 5000 + 1
                self.output = [f"[... {dropped} lines truncated ...]"] + self.output[-4999:]
            # CB-2799: capture lines that contain an exhaustion/error signal.
            if _JSON_ERROR_SIGNAL_RE.search(line) or _EXHAUSTION_SIGNAL_RE.search(line):
                self.exhaustion_signal_lines.append(line)
                if len(self.exhaustion_signal_lines) > _EXHAUSTION_SIGNAL_BUFFER_CAP:
                    self.exhaustion_signal_lines = self.exhaustion_signal_lines[-_EXHAUSTION_SIGNAL_BUFFER_CAP:]

    def get_output_snapshot(self, since_line: int = 0) -> List[str]:
        """Thread-safe snapshot of output lines from a given offset."""
        with self._output_lock:
            return list(self.output[since_line:])


class TerminalService:
    """Service for managing terminal sessions"""

    def __init__(self):
        self._sessions: Dict[str, TerminalSession] = {}
        self._sessions_by_issue: Dict[str, str] = {}  # issue_id -> session_id
        self._pending_completions: Dict[str, bool] = {}  # session_id -> needs_status_update
        # CB-1585/CB-1586: doc-generation jobs queued by _run_claude_async
        # (in a thread) for the async lifespan loop to consume. Captured
        # BEFORE cleanup so the output snapshot, started_at/completed_at
        # timestamps, and cwd survive even if cleanup_session races ahead.
        self._pending_doc_jobs: Dict[str, Dict[str, Any]] = {}
        # Cache preservation: track which feature's cache is loaded per project
        self._active_feature_by_project: Dict[str, str] = {}  # project_path -> feature_issue_id
        # Protects all five dicts above from concurrent mutation
        self._sessions_lock = threading.Lock()

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        """Get a session by ID"""
        with self._sessions_lock:
            return self._sessions.get(session_id)

    def get_session_by_issue(self, issue_id: str) -> Optional[TerminalSession]:
        """Get active session for an issue"""
        with self._sessions_lock:
            session_id = self._sessions_by_issue.get(issue_id)
            if session_id:
                return self._sessions.get(session_id)
            return None

    def get_all_sessions(self) -> List[TerminalSession]:
        """Get all sessions — returns a snapshot copy, safe to iterate outside the lock"""
        with self._sessions_lock:
            return list(self._sessions.values())

    def get_running_sessions(self) -> List[TerminalSession]:
        """Get all currently running sessions"""
        with self._sessions_lock:
            return [s for s in self._sessions.values() if s.status == ExecutionStatus.RUNNING]

    def get_running_count(self) -> int:
        """Get the number of currently running sessions"""
        return len(self.get_running_sessions())

    def _parse_progress(self, session: TerminalSession, line: str):
        """Parse Claude Code output to track progress and phase"""
        line_lower = line.lower()

        # Detect file reads
        if any(x in line_lower for x in ['reading', 'read file', 'cat ', 'examining']):
            session.files_read += 1
            session.phase = ExecutionPhase.READING_FILES
            session.current_action = f"Reading files ({session.files_read} read)"
            session.progress_percent = min(20 + session.files_read * 2, 40)

        # Detect analysis/thinking
        elif any(x in line_lower for x in ['analyzing', 'thinking', 'understanding', 'looking at']):
            session.phase = ExecutionPhase.ANALYZING
            session.current_action = "Analyzing codebase..."
            session.progress_percent = max(session.progress_percent, 30)

        # Detect planning
        elif any(x in line_lower for x in ['plan', 'approach', 'strategy', 'will ']):
            session.phase = ExecutionPhase.PLANNING
            session.current_action = "Planning implementation..."
            session.progress_percent = max(session.progress_percent, 40)

        # Detect code writing
        elif any(x in line_lower for x in ['writing', 'creating', 'editing', 'edit ', 'write ', 'adding']):
            session.files_written += 1
            session.phase = ExecutionPhase.WRITING_CODE
            session.current_action = f"Writing code ({session.files_written} files)"
            session.progress_percent = min(50 + session.files_written * 5, 80)

        # Detect command execution
        elif any(x in line_lower for x in ['running', 'executing', 'bash', 'npm ', 'pip ', 'git ']):
            session.commands_run += 1
            session.phase = ExecutionPhase.RUNNING_COMMANDS
            session.current_action = f"Running commands ({session.commands_run} run)"
            session.progress_percent = max(session.progress_percent, 70)

        # Detect testing
        elif any(x in line_lower for x in ['test', 'checking', 'verifying', 'validating']):
            session.phase = ExecutionPhase.TESTING
            session.current_action = "Testing changes..."
            session.progress_percent = max(session.progress_percent, 85)

        # Detect completion signals
        elif any(x in line_lower for x in ['complete', 'done', 'finished', 'summary', 'implemented']):
            session.phase = ExecutionPhase.FINALIZING
            session.current_action = "Finalizing..."
            session.progress_percent = 95

    def _run_claude_async(self, session_id: str, cmd: List[str], cwd: str, env: dict):
        """Run Claude CLI with PTY and stream-json for real-time output"""
        with self._sessions_lock:
            session = self._sessions.get(session_id)
        if not session:
            return

        master_fd = None
        process = None

        try:
            # Create PTY for proper terminal emulation
            master_fd, slave_fd = pty.openpty()

            # Set terminal size
            winsize = struct.pack('HHHH', 50, 200, 0, 0)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

            # Start process with PTY
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                start_new_session=True,  # process group for clean SIGTERM
            )

            os.close(slave_fd)
            session.process = process   # make reachable from stop_execution

            # Set non-blocking
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            session.phase = ExecutionPhase.INITIALIZING
            session.current_action = "Claude Code starting..."
            session.progress_percent = 5

            start_time = datetime.utcnow()
            timeout_seconds = 1800  # 30 minutes
            buffer = ""

            while True:
                # Check timeout
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                if elapsed > timeout_seconds:
                    process.kill()
                    session.status = ExecutionStatus.FAILED
                    session.error = "Execution timed out after 30 minutes"
                    session._append_output("[ERROR] Execution timed out after 30 minutes")
                    session.phase = ExecutionPhase.COMPLETED
                    break

                # Check if process is still running
                poll_result = process.poll()

                # Read available output
                try:
                    ready, _, _ = select.select([master_fd], [], [], 0.3)
                    if ready:
                        try:
                            data = os.read(master_fd, 16384)
                            if data:
                                text = data.decode('utf-8', errors='replace')
                                buffer += text

                                # Process complete JSON lines
                                while '\n' in buffer:
                                    line, buffer = buffer.split('\n', 1)
                                    self._process_stream_json_event(session, line.strip())
                        except OSError as e:
                            if e.errno not in (errno.EIO, errno.EAGAIN):
                                raise
                except (OSError, ValueError):
                    pass

                if poll_result is not None:
                    # Process has exited, read any remaining output
                    try:
                        while True:
                            data = os.read(master_fd, 16384)
                            if not data:
                                break
                            buffer += data.decode('utf-8', errors='replace')
                    except OSError:
                        pass

                    # Process remaining buffer
                    for line in buffer.split('\n'):
                        if line.strip():
                            self._process_stream_json_event(session, line.strip())
                    break

            session.exit_code = process.returncode

            if session.exit_code == 0:
                session.status = ExecutionStatus.COMPLETED
                session.phase = ExecutionPhase.COMPLETED
                session.progress_percent = 100
                session.current_action = "Completed successfully"
                # CB-1585/CB-1586: capture snapshot for documentation
                # generation BEFORE cleanup_session (the eviction loop) can
                # run. The async completion loop in app/main.py picks this up
                # and invokes documentation_generator.generate_from_execution.
                # `completed_at` is stamped BEFORE the snapshot under the same
                # lock so the doc-gen job carries an authoritative completion
                # time and so other threads observing the session see a fully
                # published value. The finally block below only writes
                # completed_at when still None, preserving this value.
                try:
                    output_snapshot = session.get_output_snapshot(0)
                    with self._sessions_lock:
                        session.completed_at = datetime.utcnow()
                        self._pending_doc_jobs[session_id] = {
                            "output_snapshot": output_snapshot,
                            "started_at": session.started_at,
                            "completed_at": session.completed_at,
                            "project_path": cwd,
                            "issue_id": session.issue_id,
                        }
                except Exception as snap_err:
                    # Never let snapshot capture break the completion path.
                    logger.warning(
                        "Failed to enqueue doc-gen job for session %s: %s",
                        session_id, snap_err,
                    )
                with self._sessions_lock:
                    self._pending_completions[session_id] = True
                # Call completion callback if registered
                if session.on_complete:
                    try:
                        session.on_complete(session_id, session.issue_id, True)
                    except Exception as cb_error:
                        session._append_output(f"[WARN] Completion callback error: {cb_error}")
            else:
                session.status = ExecutionStatus.FAILED
                session.error = f"Process exited with code {session.exit_code}"
                session.current_action = f"Failed (exit code {session.exit_code})"
                # Call completion callback for failures too
                if session.on_complete:
                    try:
                        session.on_complete(session_id, session.issue_id, False)
                    except Exception as cb_error:
                        session._append_output(f"[WARN] Completion callback error: {cb_error}")

        except Exception as e:
            session.status = ExecutionStatus.FAILED
            session.error = str(e)
            session._append_output(f"[ERROR] {str(e)}")
            session.current_action = f"Error: {str(e)[:50]}"
        finally:
            # Cleanup
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError as e:
                    logger.debug(f"PTY close error (expected on shutdown): {e}")
            if process is not None and process.poll() is None:
                try:
                    process.kill()
                    process.wait()
                except (OSError, subprocess.TimeoutExpired) as e:
                    logger.warning(f"Process cleanup error: {e}")
            # CB-1586: backstop for timeout/error/cancel paths. The success
            # branch sets completed_at earlier (alongside the doc-gen
            # snapshot) — don't overwrite that authoritative timestamp.
            if session.completed_at is None:
                session.completed_at = datetime.utcnow()

            # Release the pool slot (cleans up worktree if one was created)
            # _run_claude_async runs in a thread, so use the sync variant
            session_pool.release_sync(session_id)

    def _process_stream_json_event(self, session: TerminalSession, line: str):
        """Process a stream-json event from Claude CLI"""
        if not line:
            return

        try:
            event = json.loads(line)
            event_type = event.get('type', '')

            if event_type == 'system':
                session._append_output("[START] Claude Code initialized")
                session.phase = ExecutionPhase.INITIALIZING
                session.progress_percent = 10

            elif event_type == 'assistant':
                message = event.get('message', {})
                content = message.get('content', [])

                for block in content:
                    block_type = block.get('type')

                    if block_type == 'tool_use':
                        tool_name = block.get('name', 'unknown')
                        tool_input = block.get('input', {})

                        # Update progress based on tool
                        if tool_name in ['Read', 'Glob', 'Grep']:
                            session.files_read += 1
                            session.phase = ExecutionPhase.READING_FILES
                            file_path = tool_input.get('file_path', tool_input.get('pattern', ''))
                            short_path = file_path.split('/')[-1] if file_path else ''
                            session.current_action = f"Reading: {short_path}"
                            session._append_output(f"[READ] {short_path or 'files'}")
                            session.progress_percent = min(20 + session.files_read * 5, 50)

                        elif tool_name in ['Edit', 'Write']:
                            session.files_written += 1
                            session.phase = ExecutionPhase.WRITING_CODE
                            file_path = tool_input.get('file_path', '')
                            short_path = file_path.split('/')[-1] if file_path else ''
                            session.current_action = f"Writing: {short_path}"
                            session._append_output(f"[WRITE] {short_path or 'file'}")
                            session.progress_percent = min(50 + session.files_written * 10, 80)

                        elif tool_name == 'Bash':
                            session.commands_run += 1
                            session.phase = ExecutionPhase.RUNNING_COMMANDS
                            cmd = tool_input.get('command', '')[:50]
                            session.current_action = f"Running: {cmd}"
                            session._append_output(f"[BASH] {cmd}")
                            session.progress_percent = min(session.progress_percent + 5, 85)

                        elif tool_name == 'TodoWrite':
                            session.phase = ExecutionPhase.PLANNING
                            session.current_action = "Planning tasks..."
                            session._append_output("[PLAN] Updating task list")

                        else:
                            session._append_output(f"[TOOL] {tool_name}")

                    elif block_type == 'text':
                        text_content = block.get('text', '')
                        if text_content:
                            # Split into lines and add to output
                            for text_line in text_content.split('\n'):
                                text_line = text_line.strip()
                                if text_line:
                                    session._append_output(text_line)
                            session.phase = ExecutionPhase.FINALIZING
                            session.progress_percent = 90
                            session.current_action = "Generating response..."

            elif event_type == 'result':
                session.phase = ExecutionPhase.FINALIZING
                session.progress_percent = 95
                session.current_action = "Finalizing..."

            elif event_type == 'error':
                error_msg = event.get('error', {}).get('message', 'Unknown error')
                session._append_output(f"[ERROR] {error_msg}")

        except json.JSONDecodeError:
            # Not JSON - might be plain text or ANSI codes
            # Filter ANSI codes
            clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', line)
            clean = re.sub(r'\x1b\][^\x07]*\x07', '', clean)
            clean = clean.strip()
            if clean and not clean.startswith('['):
                session._append_output(clean)
                self._parse_progress(session, clean)

    async def start_execution(
        self,
        issue_id: str,
        issue_key: str,
        issue_title: str,
        issue_description: str,
        issue_type: str,
        provider: ExecutionProvider,
        project_path: str,
        project_id: str = "",
        parent_context: Optional[str] = None,
        prompt_override: Optional[str] = None,
        feature_id: Optional[str] = None,
        on_complete: Optional[CompletionCallback] = None,
        db: Optional[object] = None,
        force: bool = False,
    ) -> TerminalSession:
        """Start a new terminal session for executing a task.

        Args:
            db: Optional AsyncSession for dependency checking. When provided,
                the dependency_analyzer verifies this task's blocking
                constraints before allowing execution. When None, dependency
                checks are skipped (backward-compatible).
            force: When True, bypass the status check in dependency_analyzer
                (for audit/rewrite execution modes on completed tasks).
        """

        # Validate the project path for security
        try:
            validated_path = validate_project_path(project_path)
        except PathValidationError as e:
            # Create a failed session with the error
            session_id = str(uuid.uuid4())
            session = TerminalSession(
                id=session_id,
                issue_id=issue_id,
                issue_key=issue_key,
                issue_title=issue_title,
                project_id=project_id,
                provider=provider,
                status=ExecutionStatus.FAILED,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                error=f"Path validation failed: {e}",
            )
            session._append_output(f"[ERROR] Path validation failed: {e}")
            with self._sessions_lock:
                self._sessions[session_id] = session
            return session

        # Use the validated path
        project_path = validated_path

        # Check if there's already a running session for this issue
        existing = self.get_session_by_issue(issue_id)
        if existing and existing.status == ExecutionStatus.RUNNING:
            return existing

        # DEPENDENCY CHECK: If a db session is provided, verify this task's
        # blocking dependencies are satisfied before allowing execution.
        # This enables parallel execution of independent tasks while
        # respecting BLOCKS/IS_BLOCKED_BY link constraints.
        if db is not None:
            from services.dependency_analyzer import dependency_analyzer
            can_run, reason = await dependency_analyzer.can_execute(db, issue_id, force=force)
            if not can_run:
                session_id = str(uuid.uuid4())
                session = TerminalSession(
                    id=session_id,
                    issue_id=issue_id,
                    issue_key=issue_key,
                    issue_title=issue_title,
                    project_id=project_id,
                    provider=provider,
                    status=ExecutionStatus.FAILED,
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    error=f"Dependency check failed: {reason}",
                )
                session._append_output(f"[BLOCKED] {reason}")
                with self._sessions_lock:
                    self._sessions[session_id] = session
                return session

        # POOL CONCURRENCY CHECK: Use session pool to manage concurrent slots
        # The pool enforces max_sessions limit (default 3). When full, new
        # executions are rejected with a clear error.
        if session_pool.is_full:
            active_keys = [s.issue_key for s in session_pool.get_active_sessions()]
            session_id = str(uuid.uuid4())
            session = TerminalSession(
                id=session_id,
                issue_id=issue_id,
                issue_key=issue_key,
                issue_title=issue_title,
                project_id=project_id,
                provider=provider,
                status=ExecutionStatus.FAILED,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                error=f"Session pool is full ({session_pool.max_sessions} max). Active: {', '.join(active_keys)}",
            )
            session._append_output(f"[BLOCKED] Session pool full - {', '.join(active_keys)} are running")
            session._append_output(f"[INFO] Wait for a task to complete before starting another")
            with self._sessions_lock:
                self._sessions[session_id] = session
            return session

        session_id = str(uuid.uuid4())

        # Jonny invocation prefix — guarantees the global ~/.claude/skills/jonny
        # SKILL.md auto-fires in spawned subprocesses by including its trigger
        # phrases (Bible, VP R&D, CodeBoard, feature plan, audit, regression test).
        # Without this, PMv2-spawned Claude Code sessions skip the bible discipline
        # and dive straight into implementation, violating Rule 4 + Rule 23.
        # See JM-F1 (Jonny-Methodology) — JM-T7.5.3.2 / JM-T6.4.x.
        JONNY_PREFIX = (
            "/jonny — engage VP-R&D bible. Plan and implement this feature using "
            "your CodeBoard-first discipline and the pre/post checklist. Apply the "
            "audit gates (code review + security audit + regression test) before "
            "marking the work COMPLETED_WAITING_QA.\n\n"
        )

        # Build the prompt for Claude Code
        if prompt_override:
            # Use the rich context prompt from context_builder
            prompt = JONNY_PREFIX + prompt_override
        else:
            # Fallback: basic prompt (for backward compatibility)
            prompt_parts = [
                f"I need you to implement the following {issue_type}:",
                f"",
                f"**{issue_key}: {issue_title}**",
                f"",
            ]

            if parent_context:
                prompt_parts.append(f"Context: {parent_context}")
                prompt_parts.append("")

            if issue_description:
                prompt_parts.append("Description:")
                prompt_parts.append(issue_description)
                prompt_parts.append("")

            prompt_parts.append("Please implement this task. When you're done, summarize what you did.")
            prompt = JONNY_PREFIX + "\n".join(prompt_parts)

        # Create session
        session = TerminalSession(
            id=session_id,
            issue_id=issue_id,
            issue_key=issue_key,
            issue_title=issue_title,
            project_id=project_id,
            provider=provider,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.utcnow(),
            on_complete=on_complete,
            project_path=project_path,
        )

        with self._sessions_lock:
            self._sessions[session_id] = session
            self._sessions_by_issue[issue_id] = session_id

        # Acquire a pool slot for concurrency tracking
        try:
            pool_slot = session_pool.acquire(session_id, issue_id, issue_key)
        except RuntimeError as e:
            # Pool became full between our check and acquire (race condition)
            session.status = ExecutionStatus.FAILED
            session.error = str(e)
            session.completed_at = datetime.utcnow()
            session._append_output(f"[BLOCKED] {e}")
            return session

        # Create isolated worktree if multiple sessions are active
        working_dir = await session_pool.create_worktree(session_id, project_path)

        # Add initial status message
        session._append_output(f"[INFO] Starting {provider.value} execution...")
        session._append_output(f"[INFO] Task: {issue_key} - {issue_title}")
        session._append_output(f"[INFO] Working directory: {working_dir}")
        if working_dir != project_path:
            session._append_output(f"[INFO] Isolated worktree: {pool_slot.branch_name}")
        session._append_output(f"[INFO] Pool: {session_pool.active_count}/{session_pool.max_sessions} slots used")
        session._append_output("")

        try:
            if provider == ExecutionProvider.CLAUDE_CODE:
                # Get the full path to claude CLI
                home_dir = os.path.expanduser("~")
                claude_path = os.path.join(home_dir, ".local", "bin", "claude")

                if not os.path.exists(claude_path):
                    claude_path = "claude"

                # Cache preservation: only clear cache when switching features
                # If executing tasks within the same feature, keep the cache
                # so Claude retains context from prior tasks in the same feature
                cache_dir = os.path.join(home_dir, ".claude", "projects")
                project_cache_name = project_path.replace("/", "-")
                project_cache_path = os.path.join(cache_dir, project_cache_name)

                prev_feature = self._active_feature_by_project.get(project_path)
                same_feature = feature_id and prev_feature == feature_id

                if os.path.exists(project_cache_path) and not same_feature:
                    import shutil
                    try:
                        shutil.rmtree(project_cache_path)
                        session._append_output("[INFO] Cleared project cache (new feature context)")
                    except Exception as e:
                        session._append_output(f"[WARN] Could not clear cache: {e}")
                elif same_feature:
                    session._append_output("[INFO] Keeping cache (same feature context)")

                # Track the active feature for this project
                if feature_id:
                    self._active_feature_by_project[project_path] = feature_id

                # Build command - use stream-json for real-time output streaming
                # Note: Requires Claude Code 2.0.76 (2.1.19 has duplicate tool_use ID bug)
                cmd = [
                    claude_path,
                    "-p", prompt,
                    "--output-format", "stream-json",
                    "--verbose",
                    "--no-chrome",
                    "--dangerously-skip-permissions",
                ]

                # Set environment
                env = os.environ.copy()
                env['NO_COLOR'] = '1'
                env['PATH'] = f"{home_dir}/.local/bin:{env.get('PATH', '')}"
                env.pop('CLAUDECODE', None)
                env.pop('CLAUDE_CODE_ENTRYPOINT', None)
                # Remove ANTHROPIC_API_KEY so Claude Code CLI uses the user's
                # subscription auth instead of API key auth (which may have
                # insufficient credits on the API billing side)
                env.pop('ANTHROPIC_API_KEY', None)

                # Run in background thread (use working_dir for worktree isolation)
                thread = threading.Thread(
                    target=self._run_claude_async,
                    args=(session_id, cmd, working_dir, env),
                    daemon=True
                )
                thread.start()

            elif provider == ExecutionProvider.LOCAL_AI:
                # For local AI, use Ollama
                cmd = ["ollama", "run", "llama3.2:1b", prompt]

                env = os.environ.copy()
                env['NO_COLOR'] = '1'

                thread = threading.Thread(
                    target=self._run_claude_async,
                    args=(session_id, cmd, working_dir, env),
                    daemon=True
                )
                thread.start()

        except FileNotFoundError as e:
            session.status = ExecutionStatus.FAILED
            session.error = f"Command not found: {str(e)}"
            session._append_output(f"[ERROR] Command not found: {str(e)}")
            session.completed_at = datetime.utcnow()
            await session_pool.release(session_id)
        except Exception as e:
            session.status = ExecutionStatus.FAILED
            session.error = str(e)
            session._append_output(f"[ERROR] Failed to start: {str(e)}")
            session.completed_at = datetime.utcnow()
            await session_pool.release(session_id)

        return session

    async def send_input(self, session_id: str, text: str) -> bool:
        """Send input to a running session - not supported in simple mode"""
        with self._sessions_lock:
            session = self._sessions.get(session_id)
        if not session:
            return False

        # In simple mode, we can't send input - just log it
        session._append_output(f"[INPUT] {text}")
        return True

    async def stop_execution(self, session_id: str) -> bool:
        """Stop a running session"""
        with self._sessions_lock:
            session = self._sessions.get(session_id)
        if not session:
            return False

        session.status = ExecutionStatus.CANCELLED
        session.completed_at = datetime.utcnow()
        session._append_output("[INFO] Execution cancelled by user")

        # Kill the subprocess group if still running
        if session.process and session.process.poll() is None:
            try:
                os.killpg(os.getpgid(session.process.pid), signal.SIGTERM)
                # Wait up to 2s for graceful exit
                for _ in range(20):
                    if session.process.poll() is not None:
                        break
                    await asyncio.sleep(0.1)
                # SIGKILL if still alive
                if session.process.poll() is None:
                    logger.warning(f"Session {session_id} didn't respond to SIGTERM, sending SIGKILL")
                    os.killpg(os.getpgid(session.process.pid), signal.SIGKILL)
                    try:
                        session.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        logger.error(f"Session {session_id} subprocess failed to die after SIGKILL")
            except (ProcessLookupError, OSError) as e:
                logger.debug(f"Process already gone for session {session_id}: {e}")

        # Release pool slot (the async runner's finally block may also call this,
        # but release() is idempotent - second call is a no-op)
        await session_pool.release(session_id)
        return True

    def get_output(self, session_id: str, since_line: int = 0) -> List[str]:
        """Get output lines from a session"""
        with self._sessions_lock:
            session = self._sessions.get(session_id)
        if not session:
            return []

        return session.get_output_snapshot(since_line)

    def cleanup_session(self, session_id: str):
        """Clean up a completed session"""
        with self._sessions_lock:
            session = self._sessions.pop(session_id, None)
            if not session:
                return
            if session.issue_id in self._sessions_by_issue:
                del self._sessions_by_issue[session.issue_id]
            # Also clean up pending completion flag
            self._pending_completions.pop(session_id, None)
            # CB-1585: drop any unconsumed doc-gen job (best-effort enrichment)
            self._pending_doc_jobs.pop(session_id, None)

            # Prune project→feature map if no other sessions reference this project path
            if session.project_path:
                has_other = any(
                    s.project_path == session.project_path
                    for s in self._sessions.values()
                )
                if not has_other:
                    self._active_feature_by_project.pop(session.project_path, None)

        # Defensive: release pool slot if still held (normally released in _run_claude_async)
        session_pool.release_sync(session_id)

    def check_pending_completion(self, session_id: str) -> bool:
        """Check if a session has pending auto-completion (and consume the flag).

        DEPRECATED for completion-loop use — pop-on-read makes per-session
        retries impossible. New callers should use `peek_pending_completion`
        + `clear_pending_completion` so a transaction can roll back without
        losing the pending flag (CB-2116 / F1).
        """
        with self._sessions_lock:
            return self._pending_completions.pop(session_id, False)

    def peek_pending_completion(self, session_id: str) -> bool:
        """Read pending-completion flag WITHOUT consuming it (CB-2116)."""
        with self._sessions_lock:
            return self._pending_completions.get(session_id, False)

    def clear_pending_completion(self, session_id: str) -> None:
        """Drop the pending-completion flag after a successful commit (CB-2116)."""
        with self._sessions_lock:
            self._pending_completions.pop(session_id, None)

    def get_all_pending_completions(self) -> List[str]:
        """Get all session IDs with pending completions — returns a snapshot copy"""
        with self._sessions_lock:
            return list(self._pending_completions.keys())

    def consume_pending_doc_job(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Pop the queued documentation-generation job for `session_id`.

        Returns None when the session never produced one (failed runs, or the
        capture step itself raised). Callers MUST treat this as best-effort
        enrichment — never raise from a missing/empty job.

        DEPRECATED for completion-loop use — pop-on-read sacrifices the job
        on transaction rollback. New callers should use `peek_pending_doc_job`
        + `clear_pending_doc_job` (CB-2116 / F1).
        """
        with self._sessions_lock:
            return self._pending_doc_jobs.pop(session_id, None)

    def peek_pending_doc_job(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Read the queued doc-gen job WITHOUT consuming it (CB-2116)."""
        with self._sessions_lock:
            return self._pending_doc_jobs.get(session_id)

    def clear_pending_doc_job(self, session_id: str) -> None:
        """Drop the queued doc-gen job after a successful commit (CB-2116)."""
        with self._sessions_lock:
            self._pending_doc_jobs.pop(session_id, None)


# Singleton instance
terminal_service = TerminalService()
