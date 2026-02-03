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
from typing import Dict, Optional, List
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


class TerminalService:
    """Service for managing terminal sessions"""

    def __init__(self):
        self._sessions: Dict[str, TerminalSession] = {}
        self._sessions_by_issue: Dict[str, str] = {}  # issue_id -> session_id
        self._pending_completions: Dict[str, bool] = {}  # session_id -> needs_status_update

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        """Get a session by ID"""
        return self._sessions.get(session_id)

    def get_session_by_issue(self, issue_id: str) -> Optional[TerminalSession]:
        """Get active session for an issue"""
        session_id = self._sessions_by_issue.get(issue_id)
        if session_id:
            return self._sessions.get(session_id)
        return None

    def get_all_sessions(self) -> List[TerminalSession]:
        """Get all sessions"""
        return list(self._sessions.values())

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
            )

            os.close(slave_fd)

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
                    session.output.append("[ERROR] Execution timed out after 30 minutes")
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
                self._pending_completions[session_id] = True
                # Call completion callback if registered
                if session.on_complete:
                    try:
                        session.on_complete(session_id, session.issue_id, True)
                    except Exception as cb_error:
                        session.output.append(f"[WARN] Completion callback error: {cb_error}")
            else:
                session.status = ExecutionStatus.FAILED
                session.error = f"Process exited with code {session.exit_code}"
                session.current_action = f"Failed (exit code {session.exit_code})"
                # Call completion callback for failures too
                if session.on_complete:
                    try:
                        session.on_complete(session_id, session.issue_id, False)
                    except Exception as cb_error:
                        session.output.append(f"[WARN] Completion callback error: {cb_error}")

        except Exception as e:
            session.status = ExecutionStatus.FAILED
            session.error = str(e)
            session.output.append(f"[ERROR] {str(e)}")
            session.current_action = f"Error: {str(e)[:50]}"
        finally:
            # Cleanup
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except:
                    pass
            if process is not None and process.poll() is None:
                try:
                    process.kill()
                    process.wait()
                except:
                    pass
            session.completed_at = datetime.utcnow()

    def _process_stream_json_event(self, session: TerminalSession, line: str):
        """Process a stream-json event from Claude CLI"""
        if not line:
            return

        try:
            event = json.loads(line)
            event_type = event.get('type', '')

            if event_type == 'system':
                session.output.append("[START] Claude Code initialized")
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
                            session.output.append(f"[READ] {short_path or 'files'}")
                            session.progress_percent = min(20 + session.files_read * 5, 50)

                        elif tool_name in ['Edit', 'Write']:
                            session.files_written += 1
                            session.phase = ExecutionPhase.WRITING_CODE
                            file_path = tool_input.get('file_path', '')
                            short_path = file_path.split('/')[-1] if file_path else ''
                            session.current_action = f"Writing: {short_path}"
                            session.output.append(f"[WRITE] {short_path or 'file'}")
                            session.progress_percent = min(50 + session.files_written * 10, 80)

                        elif tool_name == 'Bash':
                            session.commands_run += 1
                            session.phase = ExecutionPhase.RUNNING_COMMANDS
                            cmd = tool_input.get('command', '')[:50]
                            session.current_action = f"Running: {cmd}"
                            session.output.append(f"[BASH] {cmd}")
                            session.progress_percent = min(session.progress_percent + 5, 85)

                        elif tool_name == 'TodoWrite':
                            session.phase = ExecutionPhase.PLANNING
                            session.current_action = "Planning tasks..."
                            session.output.append("[PLAN] Updating task list")

                        else:
                            session.output.append(f"[TOOL] {tool_name}")

                    elif block_type == 'text':
                        text_content = block.get('text', '')
                        if text_content:
                            # Split into lines and add to output
                            for text_line in text_content.split('\n'):
                                text_line = text_line.strip()
                                if text_line:
                                    session.output.append(text_line)
                            session.phase = ExecutionPhase.FINALIZING
                            session.progress_percent = 90
                            session.current_action = "Generating response..."

            elif event_type == 'result':
                session.phase = ExecutionPhase.FINALIZING
                session.progress_percent = 95
                session.current_action = "Finalizing..."

            elif event_type == 'error':
                error_msg = event.get('error', {}).get('message', 'Unknown error')
                session.output.append(f"[ERROR] {error_msg}")

        except json.JSONDecodeError:
            # Not JSON - might be plain text or ANSI codes
            # Filter ANSI codes
            clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', line)
            clean = re.sub(r'\x1b\][^\x07]*\x07', '', clean)
            clean = clean.strip()
            if clean and not clean.startswith('['):
                session.output.append(clean)
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
        parent_context: Optional[str] = None,
        on_complete: Optional[CompletionCallback] = None,
    ) -> TerminalSession:
        """Start a new terminal session for executing a task"""

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
                provider=provider,
                status=ExecutionStatus.FAILED,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                error=f"Path validation failed: {e}",
            )
            session.output.append(f"[ERROR] Path validation failed: {e}")
            self._sessions[session_id] = session
            return session

        # Use the validated path
        project_path = validated_path

        # Check if there's already a running session for this issue
        existing = self.get_session_by_issue(issue_id)
        if existing and existing.status == ExecutionStatus.RUNNING:
            return existing

        # GLOBAL CONCURRENCY CHECK: Only allow one execution at a time
        # This prevents issues when frontend crashes and restarts, or when
        # manual execution is started while auto-pilot is running
        running_sessions = [s for s in self._sessions.values() if s.status == ExecutionStatus.RUNNING]
        if running_sessions:
            # Return a "queued" response - don't start a new execution
            running = running_sessions[0]
            session_id = str(uuid.uuid4())
            session = TerminalSession(
                id=session_id,
                issue_id=issue_id,
                issue_key=issue_key,
                issue_title=issue_title,
                provider=provider,
                status=ExecutionStatus.FAILED,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                error=f"Another task is already running: {running.issue_key}. Please wait for it to complete.",
            )
            session.output.append(f"[BLOCKED] Cannot start - {running.issue_key} is still running")
            session.output.append(f"[INFO] Wait for the current task to complete before starting another")
            self._sessions[session_id] = session
            return session

        session_id = str(uuid.uuid4())

        # Build the prompt for Claude Code
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

        prompt = "\n".join(prompt_parts)

        # Create session
        session = TerminalSession(
            id=session_id,
            issue_id=issue_id,
            issue_key=issue_key,
            issue_title=issue_title,
            provider=provider,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.utcnow(),
            on_complete=on_complete,
        )

        self._sessions[session_id] = session
        self._sessions_by_issue[issue_id] = session_id

        # Add initial status message
        session.output.append(f"[INFO] Starting {provider.value} execution...")
        session.output.append(f"[INFO] Task: {issue_key} - {issue_title}")
        session.output.append(f"[INFO] Working directory: {project_path}")
        session.output.append("")

        try:
            if provider == ExecutionProvider.CLAUDE_CODE:
                # Get the full path to claude CLI
                home_dir = os.path.expanduser("~")
                claude_path = os.path.join(home_dir, ".local", "bin", "claude")

                if not os.path.exists(claude_path):
                    claude_path = "claude"

                # Clear Claude's project cache to prevent "duplicate tool_use id" errors
                # This ensures a fresh conversation without corrupted state
                cache_dir = os.path.join(home_dir, ".claude", "projects")
                project_cache_name = project_path.replace("/", "-")
                project_cache_path = os.path.join(cache_dir, project_cache_name)
                if os.path.exists(project_cache_path):
                    import shutil
                    try:
                        shutil.rmtree(project_cache_path)
                        session.output.append("[INFO] Cleared project cache for fresh session")
                    except Exception as e:
                        session.output.append(f"[WARN] Could not clear cache: {e}")

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

                # Run in background thread
                thread = threading.Thread(
                    target=self._run_claude_async,
                    args=(session_id, cmd, project_path, env),
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
                    args=(session_id, cmd, project_path, env),
                    daemon=True
                )
                thread.start()

        except FileNotFoundError as e:
            session.status = ExecutionStatus.FAILED
            session.error = f"Command not found: {str(e)}"
            session.output.append(f"[ERROR] Command not found: {str(e)}")
            session.completed_at = datetime.utcnow()
        except Exception as e:
            session.status = ExecutionStatus.FAILED
            session.error = str(e)
            session.output.append(f"[ERROR] Failed to start: {str(e)}")
            session.completed_at = datetime.utcnow()

        return session

    async def send_input(self, session_id: str, text: str) -> bool:
        """Send input to a running session - not supported in simple mode"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        # In simple mode, we can't send input - just log it
        session.output.append(f"[INPUT] {text}")
        return True

    async def stop_execution(self, session_id: str) -> bool:
        """Stop a running session"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        # Mark as cancelled
        session.status = ExecutionStatus.CANCELLED
        session.completed_at = datetime.utcnow()
        session.output.append("[INFO] Execution cancelled by user")
        return True

    def get_output(self, session_id: str, since_line: int = 0) -> List[str]:
        """Get output lines from a session"""
        session = self._sessions.get(session_id)
        if not session:
            return []

        return session.output[since_line:]

    def cleanup_session(self, session_id: str):
        """Clean up a completed session"""
        session = self._sessions.get(session_id)
        if session:
            if session.issue_id in self._sessions_by_issue:
                del self._sessions_by_issue[session.issue_id]
            del self._sessions[session_id]
            # Also clean up pending completion flag
            self._pending_completions.pop(session_id, None)

    def check_pending_completion(self, session_id: str) -> bool:
        """Check if a session has pending auto-completion (and consume the flag)"""
        return self._pending_completions.pop(session_id, False)

    def get_all_pending_completions(self) -> List[str]:
        """Get all session IDs with pending completions"""
        return list(self._pending_completions.keys())


# Singleton instance
terminal_service = TerminalService()
