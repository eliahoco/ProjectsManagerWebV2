"""
Git Service - Repository operations and status
"""

import asyncio
import os
import re
import subprocess
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime


# Commit patterns for status transitions
COMMIT_PATTERNS = {
    # Work in progress
    r'^wip\b': 'IN_PROGRESS',
    r'\[wip\]': 'IN_PROGRESS',

    # Feature work (conventional commits)
    r'^feat(\(.+\))?:': 'IN_PROGRESS',
    r'^fix(\(.+\))?:': 'IN_PROGRESS',
    r'^refactor(\(.+\))?:': 'IN_PROGRESS',

    # Completion indicators
    r'^done\b': 'DONE',
    r'\[done\]': 'DONE',
    r'^complete\b': 'DONE',
    r'closes?\s+#?\d+': 'DONE',
    r'fixes?\s+#?\d+': 'DONE',
}


def get_status_from_commit(message: str) -> Optional[str]:
    """Get status transition based on commit message patterns.

    Analyzes a commit message to determine if it should trigger
    an automatic status update for linked issues.

    Args:
        message: The commit message to analyze.

    Returns:
        Status string ('IN_PROGRESS' or 'DONE') if a pattern matches,
        None otherwise.
    """
    message_lower = message.lower()
    for pattern, status in COMMIT_PATTERNS.items():
        if re.search(pattern, message_lower):
            return status
    return None


@dataclass
class GitCommit:
    """Represents a git commit"""
    hash: str
    short_hash: str
    author: str
    email: str
    date: datetime
    message: str
    branch: Optional[str] = None


@dataclass
class GitBranch:
    """Represents a git branch"""
    name: str
    is_current: bool
    tracking: Optional[str] = None
    ahead: int = 0
    behind: int = 0


@dataclass
class GitStatus:
    """Repository status"""
    is_repo: bool
    branch: Optional[str] = None
    clean: bool = True
    staged: List[str] = None
    modified: List[str] = None
    untracked: List[str] = None
    ahead: int = 0
    behind: int = 0

    def __post_init__(self):
        if self.staged is None:
            self.staged = []
        if self.modified is None:
            self.modified = []
        if self.untracked is None:
            self.untracked = []


class GitService:
    """Service for Git repository operations"""

    def __init__(self):
        pass

    async def _run_git(
        self,
        args: List[str],
        cwd: str,
        timeout: int = 30,
    ) -> tuple[bool, str, str]:
        """
        Run a git command asynchronously and return (success, stdout, stderr).
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                'git', *args,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            stdout = stdout_bytes.decode(errors='replace')
            stderr = stderr_bytes.decode(errors='replace')
            return proc.returncode == 0, stdout, stderr
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return False, '', 'Command timed out'
        except Exception as e:
            return False, '', str(e)

    async def is_git_repo(self, path: str) -> bool:
        """Check if path is a git repository"""
        if not os.path.isdir(path):
            return False
        success, _, _ = await self._run_git(['rev-parse', '--is-inside-work-tree'], path)
        return success

    async def get_status(self, path: str) -> GitStatus:
        """Get repository status"""
        if not await self.is_git_repo(path):
            return GitStatus(is_repo=False)

        # Get current branch
        success, branch, _ = await self._run_git(
            ['rev-parse', '--abbrev-ref', 'HEAD'], path
        )
        branch = branch.strip() if success else None

        # Get porcelain status
        success, output, _ = await self._run_git(
            ['status', '--porcelain=2', '--branch'], path
        )

        staged = []
        modified = []
        untracked = []
        ahead = 0
        behind = 0

        if success:
            for line in output.split('\n'):
                if line.startswith('# branch.ab'):
                    # Parse ahead/behind info
                    parts = line.split()
                    for part in parts:
                        if part.startswith('+'):
                            ahead = int(part[1:])
                        elif part.startswith('-'):
                            behind = int(part[1:])
                elif line.startswith('1 ') or line.startswith('2 '):
                    # Changed entry
                    parts = line.split()
                    if len(parts) >= 2:
                        xy = parts[1]
                        filename = parts[-1]
                        if xy[0] != '.':  # Staged
                            staged.append(filename)
                        if xy[1] != '.':  # Unstaged modification
                            modified.append(filename)
                elif line.startswith('? '):
                    # Untracked
                    untracked.append(line[2:])

        clean = len(staged) == 0 and len(modified) == 0 and len(untracked) == 0

        return GitStatus(
            is_repo=True,
            branch=branch,
            clean=clean,
            staged=staged,
            modified=modified,
            untracked=untracked,
            ahead=ahead,
            behind=behind,
        )

    async def get_branches(self, path: str, limit: int = 20) -> List[GitBranch]:
        """Get list of branches"""
        if not await self.is_git_repo(path):
            return []

        success, output, _ = await self._run_git(
            ['branch', '-vv', '--format=%(HEAD) %(refname:short) %(upstream:short) %(upstream:track)'],
            path
        )

        branches = []
        if success:
            for line in output.strip().split('\n'):
                if not line:
                    continue

                is_current = line.startswith('*')
                parts = line[2:].split()
                if not parts:
                    continue

                name = parts[0]
                tracking = parts[1] if len(parts) > 1 and not parts[1].startswith('[') else None

                # Parse ahead/behind from track info
                ahead = behind = 0
                for part in parts:
                    if part.startswith('[ahead'):
                        try:
                            ahead = int(part.replace('[ahead', '').replace(']', '').replace(',', ''))
                        except ValueError:
                            pass
                    if 'behind' in part:
                        try:
                            behind = int(part.replace('behind', '').replace(']', '').strip())
                        except ValueError:
                            pass

                branches.append(GitBranch(
                    name=name,
                    is_current=is_current,
                    tracking=tracking,
                    ahead=ahead,
                    behind=behind,
                ))

                if len(branches) >= limit:
                    break

        return branches

    async def get_commits(
        self,
        path: str,
        branch: Optional[str] = None,
        limit: int = 20,
    ) -> List[GitCommit]:
        """Get recent commits"""
        if not await self.is_git_repo(path):
            return []

        args = [
            'log',
            f'-{limit}',
            '--format=%H|%h|%an|%ae|%at|%s',
        ]
        if branch:
            args.append(branch)

        success, output, _ = await self._run_git(args, path)

        commits = []
        if success:
            for line in output.strip().split('\n'):
                if not line:
                    continue
                parts = line.split('|', 5)
                if len(parts) >= 6:
                    commits.append(GitCommit(
                        hash=parts[0],
                        short_hash=parts[1],
                        author=parts[2],
                        email=parts[3],
                        date=datetime.fromtimestamp(int(parts[4])),
                        message=parts[5],
                        branch=branch,
                    ))

        return commits

    async def get_diff(
        self,
        path: str,
        staged: bool = False,
        file_path: Optional[str] = None,
    ) -> str:
        """Get diff for changes"""
        if not await self.is_git_repo(path):
            return ''

        args = ['diff']
        if staged:
            args.append('--cached')
        if file_path:
            args.extend(['--', file_path])

        success, output, _ = await self._run_git(args, path)
        return output if success else ''

    async def get_remote_url(self, path: str, remote: str = 'origin') -> Optional[str]:
        """Get remote URL"""
        if not await self.is_git_repo(path):
            return None

        success, output, _ = await self._run_git(
            ['remote', 'get-url', remote], path
        )
        return output.strip() if success else None

    async def get_commit_for_issue(
        self,
        path: str,
        issue_key: str,
        limit: int = 10,
    ) -> List[GitCommit]:
        """Find commits that reference an issue key"""
        if not await self.is_git_repo(path):
            return []

        args = [
            'log',
            f'-{limit}',
            f'--grep={issue_key}',
            '--format=%H|%h|%an|%ae|%at|%s',
        ]

        success, output, _ = await self._run_git(args, path)

        commits = []
        if success:
            for line in output.strip().split('\n'):
                if not line:
                    continue
                parts = line.split('|', 5)
                if len(parts) >= 6:
                    commits.append(GitCommit(
                        hash=parts[0],
                        short_hash=parts[1],
                        author=parts[2],
                        email=parts[3],
                        date=datetime.fromtimestamp(int(parts[4])),
                        message=parts[5],
                    ))

        return commits

    async def repo_summary(self, path: str) -> Dict[str, Any]:
        """Get a summary of repository state"""
        status = await self.get_status(path)
        if not status.is_repo:
            return {'is_repo': False}

        branches = await self.get_branches(path, limit=5)
        recent_commits = await self.get_commits(path, limit=5)
        remote_url = await self.get_remote_url(path)

        return {
            'is_repo': True,
            'branch': status.branch,
            'clean': status.clean,
            'changes': {
                'staged': len(status.staged),
                'modified': len(status.modified),
                'untracked': len(status.untracked),
            },
            'sync': {
                'ahead': status.ahead,
                'behind': status.behind,
            },
            'branches': [b.name for b in branches],
            'recent_commits': [
                {
                    'hash': c.short_hash,
                    'message': c.message[:80],
                    'author': c.author,
                    'date': c.date.isoformat(),
                }
                for c in recent_commits
            ],
            'remote_url': remote_url,
        }


# Singleton instance
git_service = GitService()
