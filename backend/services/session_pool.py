"""
Session Pool Manager - Manages concurrent execution sessions with isolated workspaces.

Tracks active AI execution slots and creates git worktrees for workspace isolation
when multiple sessions run in parallel. Falls back to the main project directory
when only one session is active (no isolation needed).
"""

import os
import subprocess
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


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
        self._worktree_base = "/tmp/codeboard-worktrees"

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

    def release(self, session_id: str):
        """Release a slot and clean up its worktree if one was created.

        Safe to call even if the session_id doesn't exist in the pool.
        """
        slot = self._active.pop(session_id, None)
        if not slot:
            return

        if slot.worktree_path:
            self._cleanup_worktree(slot)

        logger.info(
            f"Pool slot released for {slot.issue_key} "
            f"({self.active_count}/{self.max_sessions} slots used)"
        )

    def create_worktree(self, session_id: str, project_path: str) -> str:
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

        # Create worktree for isolation
        branch = f"codeboard/{slot.issue_key.lower()}-{session_id[:8]}"
        worktree_path = os.path.join(self._worktree_base, session_id[:12])

        try:
            os.makedirs(self._worktree_base, exist_ok=True)

            # Create a new branch based on HEAD in a new worktree
            result = subprocess.run(
                ["git", "worktree", "add", "-b", branch, worktree_path, "HEAD"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            slot.worktree_path = worktree_path
            slot.branch_name = branch
            logger.info(f"Created worktree for {slot.issue_key}: {worktree_path}")
            return worktree_path

        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Failed to create worktree for {slot.issue_key}: {e.stderr.strip()}. "
                f"Using main directory."
            )
            return project_path
        except subprocess.TimeoutExpired:
            logger.warning(
                f"Worktree creation timed out for {slot.issue_key}. Using main directory."
            )
            return project_path
        except OSError as e:
            logger.warning(
                f"OS error creating worktree for {slot.issue_key}: {e}. Using main directory."
            )
            return project_path

    def _cleanup_worktree(self, slot: PooledSession):
        """Clean up a git worktree and its associated branch.

        Best-effort cleanup; logs warnings on failure but never raises.
        """
        if not slot.worktree_path or not os.path.exists(slot.worktree_path):
            return

        try:
            # Remove the worktree
            subprocess.run(
                ["git", "worktree", "remove", "--force", slot.worktree_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            logger.info(f"Removed worktree for {slot.issue_key}: {slot.worktree_path}")
        except Exception as e:
            logger.warning(f"Failed to remove worktree for {slot.issue_key}: {e}")

        # Delete the branch (separate try so worktree removal failure doesn't block this)
        if slot.branch_name:
            try:
                subprocess.run(
                    ["git", "branch", "-D", slot.branch_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                logger.debug(f"Deleted branch {slot.branch_name}")
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
