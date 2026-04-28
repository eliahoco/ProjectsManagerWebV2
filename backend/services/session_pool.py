"""
Session Pool Manager - Manages concurrent execution sessions with isolated workspaces.

Tracks active AI execution slots and creates git worktrees for workspace isolation
when multiple sessions run in parallel. Falls back to the main project directory
when only one session is active (no isolation needed).
"""

import asyncio
import os
import stat
import tempfile
import logging
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# Worktree base: prefer env var, fall back to project-local .worktrees dir (not world-writable /tmp)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKTREE_BASE = os.environ.get("WORKTREE_BASE", str(_REPO_ROOT / ".worktrees"))


class SecurityError(RuntimeError):
    """Raised when a security invariant is violated (e.g. untrusted worktree base dir)."""


def _ensure_secure_worktree_base(base: Path) -> None:
    """Create and verify the worktree base directory is trustworthy.

    Raises SecurityError if the path is a symlink or owned by another user,
    preventing symlink-race / TOCTOU attacks on the worktree location.
    """
    base.mkdir(mode=0o700, exist_ok=True)
    st = base.lstat()
    if stat.S_ISLNK(st.st_mode):
        raise SecurityError(f"Worktree base is a symlink — aborting: {base}")
    if st.st_uid != os.getuid():
        raise SecurityError(
            f"Worktree base owned by uid {st.st_uid}, expected {os.getuid()}: {base}"
        )


@dataclass
class PooledSession:
    """A session slot in the pool with its isolated workspace."""
    session_id: str
    issue_id: str
    issue_key: str
    worktree_path: Optional[str] = None  # None = using main directory
    branch_name: Optional[str] = None
    started_at: Optional[datetime] = None


class SessionPool:
    """Manages concurrent execution sessions with isolated workspaces.

    When multiple sessions are active simultaneously, each gets a git worktree
    so they can modify files without conflicting. When only one session is active,
    it uses the main project directory directly (no overhead).
    """

    def __init__(self, max_sessions: int = 3):
        self.max_sessions = max_sessions
        self._active: Dict[str, PooledSession] = {}  # session_id -> PooledSession
        self._worktree_base = Path(WORKTREE_BASE)

    @property
    def available_slots(self) -> int:
        """Number of open slots in the pool."""
        return self.max_sessions - len(self._active)

    @property
    def is_full(self) -> bool:
        """Whether the pool has reached its max capacity."""
        return len(self._active) >= self.max_sessions

    @property
    def active_count(self) -> int:
        """Number of currently active sessions."""
        return len(self._active)

    def acquire(self, session_id: str, issue_id: str, issue_key: str) -> PooledSession:
        """Acquire a slot in the pool.

        Args:
            session_id: Unique session identifier
            issue_id: The issue being worked on
            issue_key: Human-readable issue key (e.g. CB-1234)

        Returns:
            The allocated PooledSession

        Raises:
            RuntimeError: If the pool is full
        """
        if self.is_full:
            active_keys = [s.issue_key for s in self._active.values()]
            raise RuntimeError(
                f"Session pool is full ({self.max_sessions} max). "
                f"Active: {', '.join(active_keys)}"
            )

        slot = PooledSession(
            session_id=session_id,
            issue_id=issue_id,
            issue_key=issue_key,
            started_at=datetime.utcnow(),
        )
        self._active[session_id] = slot
        logger.info(
            f"Pool slot acquired for {issue_key} "
            f"({self.active_count}/{self.max_sessions} slots used)"
        )
        return slot

    async def release(self, session_id: str):
        """Release a slot and clean up its worktree if one was created.

        Safe to call even if the session_id doesn't exist in the pool.
        Prefer this from async contexts; use release_sync() from threads.
        """
        slot = self._active.pop(session_id, None)
        if not slot:
            return

        if slot.worktree_path:
            await self._cleanup_worktree(slot)

        logger.info(
            f"Pool slot released for {slot.issue_key} "
            f"({self.active_count}/{self.max_sessions} slots used)"
        )

    def release_sync(self, session_id: str):
        """Release a slot from a synchronous (non-async) context.

        Pops the session immediately; schedules any worktree cleanup as a
        fire-and-forget asyncio task on the running event loop (if one exists).
        Safe to call from threads or sync methods.
        """
        slot = self._active.pop(session_id, None)
        if not slot:
            return

        logger.info(
            f"Pool slot released (sync) for {slot.issue_key} "
            f"({self.active_count}/{self.max_sessions} slots used)"
        )

        if slot.worktree_path:
            try:
                # Prefer the already-running loop (avoids deprecated get_event_loop()).
                # If called from a non-async thread, fall back to asyncio.run().
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.run_coroutine_threadsafe(
                        self._cleanup_worktree(slot), loop
                    )
                except RuntimeError:
                    # No running loop — execute synchronously in this thread.
                    asyncio.run(self._cleanup_worktree(slot))
            except Exception as e:
                logger.warning(
                    f"Could not schedule worktree cleanup for {slot.issue_key}: {e}"
                )

    async def create_worktree(self, session_id: str, project_path: str) -> str:
        """Create a git worktree for isolated execution.

        Only creates a worktree when multiple sessions are active. If only
        one session is running, returns the main project_path directly.

        Args:
            session_id: The session to create a worktree for
            project_path: The main project directory (must be a git repo)

        Returns:
            The working directory path (worktree path or original project_path)
        """
        slot = self._active.get(session_id)
        if not slot:
            logger.warning(f"create_worktree called for unknown session {session_id[:8]}")
            return project_path

        # If only one session active, use main directory (no isolation needed)
        if len(self._active) <= 1:
            logger.debug(f"Single session active, using main directory for {slot.issue_key}")
            return project_path

        # Create worktree for isolation.
        # Use a project-local base dir (not /tmp) with mode 0o700, then atomically
        # allocate a unique directory via mkdtemp to eliminate symlink-race attacks.
        branch = f"codeboard/{slot.issue_key.lower()}-{session_id[:8]}"

        try:
            _ensure_secure_worktree_base(self._worktree_base)
            worktree_path = tempfile.mkdtemp(
                prefix=f"session-{session_id[:8]}-",
                dir=str(self._worktree_base),
            )

            # Create a new branch based on HEAD in a new worktree (async subprocess)
            proc = await asyncio.create_subprocess_exec(
                "git", "worktree", "add", "-b", branch, worktree_path, "HEAD",
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode != 0:
                stderr = stderr_bytes.decode(errors='replace').strip()
                logger.warning(
                    f"Failed to create worktree for {slot.issue_key}: {stderr}. "
                    f"Using main directory."
                )
                return project_path

            slot.worktree_path = worktree_path
            slot.branch_name = branch
            logger.info(f"Created worktree for {slot.issue_key}: {worktree_path}")
            return worktree_path

        except asyncio.TimeoutError:
            logger.warning(
                f"Worktree creation timed out for {slot.issue_key}. Using main directory."
            )
            return project_path
        except SecurityError:
            # Re-raise — this is a hard security violation, not a soft fallback.
            raise
        except OSError as e:
            logger.warning(
                f"OS error creating worktree for {slot.issue_key}: {e}. Using main directory."
            )
            return project_path
        except Exception as e:
            logger.warning(
                f"Unexpected error creating worktree for {slot.issue_key}: {e}. Using main directory."
            )
            return project_path

    async def _cleanup_worktree(self, slot: PooledSession):
        """Clean up a git worktree and its associated branch.

        Best-effort cleanup; logs warnings on failure but never raises.
        """
        if not slot.worktree_path or not os.path.exists(slot.worktree_path):
            return

        try:
            # Remove the worktree (async subprocess)
            proc = await asyncio.create_subprocess_exec(
                "git", "worktree", "remove", "--force", slot.worktree_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
            logger.info(f"Removed worktree for {slot.issue_key}: {slot.worktree_path}")
        except asyncio.TimeoutError:
            logger.warning(f"Timed out removing worktree for {slot.issue_key}")
        except Exception as e:
            logger.warning(f"Failed to remove worktree for {slot.issue_key}: {e}")

        # Delete the branch (separate try so worktree removal failure doesn't block this)
        if slot.branch_name:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "git", "branch", "-D", slot.branch_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=10)
                logger.debug(f"Deleted branch {slot.branch_name}")
            except asyncio.TimeoutError:
                logger.warning(f"Timed out deleting branch {slot.branch_name}")
            except Exception as e:
                logger.warning(f"Failed to delete branch {slot.branch_name}: {e}")

    def get_active_sessions(self) -> List[PooledSession]:
        """Return all currently active pooled sessions."""
        return list(self._active.values())

    def get_session(self, session_id: str) -> Optional[PooledSession]:
        """Look up a pooled session by ID."""
        return self._active.get(session_id)

    def get_pool_status(self) -> dict:
        """Return a status summary of the pool for API responses."""
        return {
            "max_sessions": self.max_sessions,
            "active_count": self.active_count,
            "available_slots": self.available_slots,
            "is_full": self.is_full,
            "active_sessions": [
                {
                    "session_id": s.session_id,
                    "issue_key": s.issue_key,
                    "has_worktree": s.worktree_path is not None,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                }
                for s in self._active.values()
            ],
        }


# Singleton instance
session_pool = SessionPool(max_sessions=3)
