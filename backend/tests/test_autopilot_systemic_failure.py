"""
CB-2799: Tests for the consecutive-failure systemic-failure heuristic.

Validates ``_is_consecutive_systemic_failure`` and ``_reset_consecutive_failure_streak``
— the duration-independent fallback introduced to catch slow queues like LINK-124
where tasks run 2-15 minutes each and 3 failures in 60 s was impossible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from services.autopilot_queue_service import (
    AutoPilotQueue,
    QueueConfig,
    QueueStatus,
    _is_consecutive_systemic_failure,
    _reset_consecutive_failure_streak,
    _normalize_error_for_systemic,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_queue() -> AutoPilotQueue:
    """Minimal AutoPilotQueue with CB-2799 streak fields at their defaults."""
    return AutoPilotQueue(
        id="test-queue-id",
        feature_id="feat-1",
        feature_key="CB-100",
        project_id="proj-1",
        project_path="/tmp/proj",
    )


# ---------------------------------------------------------------------------
# _is_consecutive_systemic_failure tests
# ---------------------------------------------------------------------------


def test_consecutive_systemic_three_in_a_row_far_apart():
    """RC4b regression: 3 identical failures spread 10 min apart (no successes)
    must trip the streak-based heuristic even though no window check would fire.

    Simulates LINK-124 queue: tasks ran 2-15 min, 7 failures over ~80 min.
    """
    queue = _make_queue()
    error = "Process exited with code 1"

    # Three failures, each supposedly 10 minutes apart — the window check with
    # the old 60 s window would never fire; the streak check must.
    result1 = _is_consecutive_systemic_failure(queue, error)
    assert result1 is False, "should not fire after only 1 failure"
    assert queue.consecutive_failure_count == 1

    result2 = _is_consecutive_systemic_failure(queue, error)
    assert result2 is False, "should not fire after only 2 failures"
    assert queue.consecutive_failure_count == 2

    result3 = _is_consecutive_systemic_failure(queue, error)
    assert result3 is True, (
        "_is_consecutive_systemic_failure should return True after 3 identical "
        "consecutive failures regardless of elapsed time (CB-2799 RC4b regression)"
    )
    assert queue.consecutive_failure_count == 3


def test_consecutive_systemic_reset_by_success():
    """A task success between failures must reset the streak.

    Sequence: fail / fail / SUCCESS (reset) / fail / fail — should NOT trip
    the heuristic because the success cleared the streak.
    """
    queue = _make_queue()
    error = "Process exited with code 1"

    _is_consecutive_systemic_failure(queue, error)  # count=1
    _is_consecutive_systemic_failure(queue, error)  # count=2

    # Simulate task success — queue loop calls this on every completed task.
    _reset_consecutive_failure_streak(queue)
    assert queue.consecutive_failure_count == 0
    assert queue.consecutive_failure_signature is None

    # Two more failures after the reset — streak restarts from 1.
    _is_consecutive_systemic_failure(queue, error)  # count=1
    result = _is_consecutive_systemic_failure(queue, error)  # count=2
    assert result is False, (
        "Only 2 failures after success reset — heuristic must NOT fire "
        "(streak was reset by the intervening success)"
    )
    assert queue.consecutive_failure_count == 2


def test_consecutive_systemic_signature_mismatch():
    """Three failures with DIFFERENT error strings must NOT trip the heuristic.

    Each failure resets the signature, so the count never reaches the threshold.
    """
    queue = _make_queue()

    result1 = _is_consecutive_systemic_failure(queue, "Process exited with code 1")
    assert result1 is False

    result2 = _is_consecutive_systemic_failure(queue, "Timeout after 1800 seconds")
    assert result2 is False

    result3 = _is_consecutive_systemic_failure(queue, "FileNotFoundError: missing dep")
    assert result3 is False, (
        "Three failures with distinct error signatures must not trip the streak "
        "heuristic — each resets the counter to 1"
    )
    # Each mismatch resets the count, so count should be 1 (the last failure).
    assert queue.consecutive_failure_count == 1


def test_consecutive_systemic_empty_error_does_not_trip():
    """An unclassifiable (empty after normalisation) error resets the streak."""
    queue = _make_queue()
    error = "Process exited with code 1"

    _is_consecutive_systemic_failure(queue, error)  # count=1
    _is_consecutive_systemic_failure(queue, error)  # count=2

    # Empty error — should reset streak rather than accumulate.
    result = _is_consecutive_systemic_failure(queue, "")
    assert result is False
    assert queue.consecutive_failure_count == 0
    assert queue.consecutive_failure_signature is None


def test_consecutive_systemic_exact_threshold():
    """Verify the threshold is exactly 3 — fires AT 3, not before."""
    queue = _make_queue()
    error = "Process exited with code 1"

    assert _is_consecutive_systemic_failure(queue, error) is False  # 1
    assert _is_consecutive_systemic_failure(queue, error) is False  # 2
    assert _is_consecutive_systemic_failure(queue, error) is True   # 3 — fires


def test_consecutive_systemic_continues_past_threshold():
    """After threshold is tripped, subsequent calls with the same error still
    return True (streak not auto-reset by the check itself)."""
    queue = _make_queue()
    error = "Process exited with code 1"

    _is_consecutive_systemic_failure(queue, error)  # 1
    _is_consecutive_systemic_failure(queue, error)  # 2
    assert _is_consecutive_systemic_failure(queue, error) is True  # 3
    # The queue loop resets the streak on systemic pause — but calling the
    # function a 4th time without a reset should still return True.
    assert _is_consecutive_systemic_failure(queue, error) is True  # 4


# ---------------------------------------------------------------------------
# _reset_consecutive_failure_streak tests
# ---------------------------------------------------------------------------


def test_reset_clears_both_fields():
    """Reset must zero the count and None the signature."""
    queue = _make_queue()
    queue.consecutive_failure_count = 5
    queue.consecutive_failure_signature = "some normalised error"

    _reset_consecutive_failure_streak(queue)

    assert queue.consecutive_failure_count == 0
    assert queue.consecutive_failure_signature is None


def test_reset_idempotent_on_fresh_queue():
    """Resetting a fresh queue with zero count must not raise."""
    queue = _make_queue()
    _reset_consecutive_failure_streak(queue)  # should not raise
    assert queue.consecutive_failure_count == 0
    assert queue.consecutive_failure_signature is None
