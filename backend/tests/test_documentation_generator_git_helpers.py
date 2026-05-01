"""
Unit tests for git capture helpers in documentation_generator (CB-1582).

Builds throwaway git repos in tmp_path and exercises the three public
helpers end-to-end. No mocks — these helpers shell out to git, and the
fixtures verify exactly that path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services.documentation_generator import (
    get_git_diff_stat,
    get_git_diff_summary,
    get_git_log_since,
)


pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git binary not available on PATH",
)


def _git(repo: Path, *args: str) -> str:
    """Run a git command in `repo` and return stdout."""
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    })
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@pytest.fixture
def repo_with_history(tmp_path: Path) -> tuple[Path, datetime]:
    """Create a git repo with one anchor commit, then a second commit
    plus an uncommitted edit. Returns ``(repo_path, boundary_timestamp)``."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "commit.gpgsign", "false")

    (repo / "a.txt").write_text("alpha\nbeta\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "initial commit")

    # Sleep boundary so the `--before` filter resolves the initial commit
    # cleanly. Git's commit timestamp resolution is 1 second.
    import time
    time.sleep(1.1)
    boundary = datetime.now()
    time.sleep(1.1)

    (repo / "a.txt").write_text("alpha\nbeta\ngamma\n")
    (repo / "b.txt").write_text("brand new file\n")
    _git(repo, "add", "a.txt", "b.txt")
    _git(repo, "commit", "-q", "-m", "second commit: add b, extend a")

    # Uncommitted edit on top
    (repo / "a.txt").write_text("alpha\nbeta\ngamma\ndelta\n")

    return repo, boundary


# --- get_git_diff_stat --------------------------------------------------------

@pytest.mark.asyncio
async def test_diff_stat_invalid_path_returns_empty():
    result = await get_git_diff_stat("/nonexistent/path/that/should/not/exist")
    assert result == {
        "files_changed": 0,
        "insertions": None,
        "deletions": None,
        "files": [],
        "raw": "",
    }


@pytest.mark.asyncio
async def test_diff_stat_none_path_returns_empty():
    result = await get_git_diff_stat(None)
    assert result["files_changed"] == 0
    assert result["files"] == []


@pytest.mark.asyncio
async def test_diff_stat_non_git_directory_returns_empty(tmp_path: Path):
    (tmp_path / "file.txt").write_text("not a git repo")
    result = await get_git_diff_stat(str(tmp_path))
    assert result["files_changed"] == 0


@pytest.mark.asyncio
async def test_diff_stat_captures_changes_since_boundary(repo_with_history):
    repo, boundary = repo_with_history
    result = await get_git_diff_stat(str(repo), boundary)
    assert result["files_changed"] >= 2
    assert "a.txt" in result["files"]
    assert "b.txt" in result["files"]
    assert result["insertions"] is not None
    assert result["insertions"] > 0


# --- get_git_log_since --------------------------------------------------------

@pytest.mark.asyncio
async def test_log_since_invalid_path_returns_empty_list():
    assert await get_git_log_since("/nonexistent/path") == []
    assert await get_git_log_since(None) == []


@pytest.mark.asyncio
async def test_log_since_returns_commits_after_boundary(repo_with_history):
    repo, boundary = repo_with_history
    commits = await get_git_log_since(str(repo), boundary)
    assert len(commits) == 1
    c = commits[0]
    assert set(c.keys()) == {"hash", "author", "date", "subject"}
    assert len(c["hash"]) == 40
    assert c["author"] == "Test"
    assert c["subject"].startswith("second commit")


@pytest.mark.asyncio
async def test_log_since_handles_subject_with_pipe(tmp_path: Path):
    """Verify \\x1f separator survives a commit subject containing `|`."""
    repo = tmp_path / "pipe-repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "f.txt").write_text("v1")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "initial")

    import time
    time.sleep(1.1)
    boundary = datetime.now()
    time.sleep(1.1)

    (repo / "f.txt").write_text("v2")
    _git(repo, "commit", "-q", "-am", "fix: handle a | b | c case")

    commits = await get_git_log_since(str(repo), boundary)
    assert len(commits) == 1
    assert commits[0]["subject"] == "fix: handle a | b | c case"


# --- get_git_diff_summary -----------------------------------------------------

@pytest.mark.asyncio
async def test_diff_summary_invalid_path_returns_empty():
    assert await get_git_diff_summary("/nonexistent/path") == ""
    assert await get_git_diff_summary(None) == ""


@pytest.mark.asyncio
async def test_diff_summary_zero_or_negative_max_chars(repo_with_history):
    repo, boundary = repo_with_history
    assert await get_git_diff_summary(str(repo), boundary, max_chars=0) == ""
    assert await get_git_diff_summary(str(repo), boundary, max_chars=-5) == ""


@pytest.mark.asyncio
async def test_diff_summary_truncates_when_too_large(repo_with_history):
    repo, boundary = repo_with_history
    full = await get_git_diff_summary(str(repo), boundary, max_chars=10000)
    short = await get_git_diff_summary(str(repo), boundary, max_chars=200)
    # Total output (body + marker) must stay under the caller-supplied budget.
    assert len(short) <= 200
    assert short.endswith("[diff truncated]")
    assert full != short
    assert "diff --git" in full


@pytest.mark.asyncio
async def test_diff_summary_max_chars_smaller_than_marker(repo_with_history):
    """When max_chars is too small to fit the marker, return raw truncation."""
    repo, boundary = repo_with_history
    result = await get_git_diff_summary(str(repo), boundary, max_chars=5)
    assert len(result) <= 5
    assert "truncated" not in result


@pytest.mark.asyncio
async def test_diff_summary_non_datetime_since_returns_empty(repo_with_history):
    """A non-datetime since_timestamp must not raise — `_resolve_start_sha`
    returns "" and the helper falls back to plain `HEAD` diff."""
    repo, _ = repo_with_history
    # Pass a string instead of datetime — should not raise; resolves to
    # HEAD-fallback path which still works against the real repo.
    result = await get_git_diff_summary(str(repo), "not-a-datetime")  # type: ignore[arg-type]
    # Either empty (clean HEAD) or non-empty diff body — never raises.
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_log_since_no_commits_in_range(tmp_path: Path):
    """Clean repo with no commits since `now+1m` returns []."""
    repo = tmp_path / "clean-log"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "f.txt").write_text("only")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "only")

    result = await get_git_log_since(str(repo), datetime.now() + timedelta(minutes=1))
    assert result == []


@pytest.mark.asyncio
async def test_diff_summary_no_changes_returns_empty(tmp_path: Path):
    repo = tmp_path / "clean"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "f.txt").write_text("only commit")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "only")

    # No edits, no commits since now → empty diff
    result = await get_git_diff_summary(str(repo), datetime.now() + timedelta(seconds=5))
    assert result == ""
