"""
Token-exhaustion detection tests (CB-1951 E3.1.4).

Covers ``is_token_exhaustion`` against the documented Anthropic API and
Claude CLI error corpus, validating both the original 8 patterns and the
new patterns added in E3.1.2 (audited from logs by the debugger agent on
2026-05-03).

CB-2799: Additional tests for the exhaustion-signal buffer introduced to fix
the tail-window problem (RC4a).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pytest

from services.autopilot_queue_service import (
    TOKEN_EXHAUSTION_PATTERNS,
    is_token_exhaustion,
)
from utils.exhaustion_detector import detect_exhaustion_from_session


# Lightweight fake to avoid pulling the full TerminalSession dependency tree.
@dataclass
class _FakeSession:
    exit_code: int = 1
    error: Optional[str] = None
    output: List[str] = field(default_factory=list)
    # CB-2799: optional exhaustion signal buffer (mirrors TerminalSession field)
    exhaustion_signal_lines: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pattern hits: each must trigger detection
# ---------------------------------------------------------------------------


def test_pattern_out_of_extra_usage():
    s = _FakeSession(error="Out of extra usage. Reset at 5 PM.")
    assert is_token_exhaustion(s) is True


def test_pattern_credit_low():
    s = _FakeSession(error="Your credit balance is too low to continue.")
    assert is_token_exhaustion(s) is True


def test_pattern_rate_limit_exceeded():
    s = _FakeSession(error="rate limit exceeded; please wait.")
    assert is_token_exhaustion(s) is True


def test_pattern_quota_exceeded():
    s = _FakeSession(error="API quota exceeded for this period.")
    assert is_token_exhaustion(s) is True


def test_pattern_too_many_requests():
    s = _FakeSession(error="HTTP 429 — Too many requests.")
    assert is_token_exhaustion(s) is True


def test_pattern_billing():
    s = _FakeSession(error="A billing issue prevented this request.")
    assert is_token_exhaustion(s) is True


def test_pattern_exceeded_current_quota():
    s = _FakeSession(error="You exceeded your current quota; please add credit.")
    assert is_token_exhaustion(s) is True


def test_pattern_rate_limit_error_stream_json():
    """Stream-json error event: error.type='rate_limit_error' is bled into
    the [ERROR] line by terminal_service. We match on the substring."""
    s = _FakeSession(
        exit_code=1,
        output=["[ERROR] rate_limit_error: Anthropic rate limit hit"],
    )
    assert is_token_exhaustion(s) is True


def test_pattern_overloaded_error():
    s = _FakeSession(error="Anthropic returned overloaded_error (HTTP 529).")
    assert is_token_exhaustion(s) is True


def test_pattern_request_too_large():
    s = _FakeSession(error="Request too large for the context window.")
    assert is_token_exhaustion(s) is True


def test_pattern_prompt_too_long():
    s = _FakeSession(error="Prompt is too long for the model.")
    assert is_token_exhaustion(s) is True


def test_pattern_your_account_has():
    s = _FakeSession(error="Your account has run out of credits this billing cycle.")
    assert is_token_exhaustion(s) is True


def test_pattern_resets_at_phrase():
    s = _FakeSession(output=["You hit a limit. resets at 5 PM."])
    assert is_token_exhaustion(s) is True


# ---------------------------------------------------------------------------
# Negative cases — must NOT trigger
# ---------------------------------------------------------------------------


def test_clean_exit_returns_false():
    """exit_code=0 short-circuits regardless of output content."""
    s = _FakeSession(exit_code=0, error="rate limit exceeded")
    assert is_token_exhaustion(s) is False


def test_unrelated_error_returns_false():
    s = _FakeSession(error="Permission denied: cannot write /etc/foo")
    assert is_token_exhaustion(s) is False


def test_path_error_returns_false():
    s = _FakeSession(
        error="FileNotFoundError: '/repos/missing/foo'",
        output=["traceback line 1", "traceback line 2"],
    )
    assert is_token_exhaustion(s) is False


def test_empty_session_returns_false():
    s = _FakeSession(error=None, output=[])
    assert is_token_exhaustion(s) is False


# ---------------------------------------------------------------------------
# Lowercasing / position
# ---------------------------------------------------------------------------


def test_case_insensitive_uppercase():
    s = _FakeSession(error="RATE LIMIT EXCEEDED")
    assert is_token_exhaustion(s) is True


def test_case_insensitive_mixed():
    s = _FakeSession(error="Rate Limit Exceeded for project")
    assert is_token_exhaustion(s) is True


def test_pattern_in_output_tail_only():
    """Detection scans the LAST 20 output lines."""
    s = _FakeSession(
        error=None,
        output=[f"normal log line {i}" for i in range(100)] + ["finally: rate limit exceeded"],
    )
    assert is_token_exhaustion(s) is True


def test_pattern_in_output_too_far_back_returns_false():
    """If pattern is buried beyond the last 20 lines AND error is empty,
    detection should NOT trigger."""
    s = _FakeSession(
        exit_code=1,
        error=None,
        output=["rate limit exceeded"] + [f"unrelated line {i}" for i in range(50)],
    )
    assert is_token_exhaustion(s) is False


# ---------------------------------------------------------------------------
# Pattern set integrity
# ---------------------------------------------------------------------------


def test_pattern_set_has_all_documented_entries():
    """Sanity check — the constants list should have at least the new entries
    added in E3.1.2 (debugger audit)."""
    must_include = {
        "rate_limit_error",
        "overloaded_error",
        "request too large",
        "prompt is too long",
        "your account has",
        "resets at",
    }
    assert must_include.issubset(set(TOKEN_EXHAUSTION_PATTERNS))


def test_pattern_set_all_lowercase():
    """All patterns must be lowercased — detection lowercases the haystack."""
    for p in TOKEN_EXHAUSTION_PATTERNS:
        assert p == p.lower(), f"pattern not lowercase: {p!r}"


# ---------------------------------------------------------------------------
# CB-2799: Signal-buffer tests
# ---------------------------------------------------------------------------


def test_exhaustion_detected_when_marker_buried_in_long_output():
    """RC4a regression: exhaustion marker arrives early then 200 KB of tool
    output scrolls it out of the 80-line tail window.

    The ``exhaustion_signal_lines`` buffer must capture the early line so
    ``detect_exhaustion_from_session`` returns the correct category even when
    the tail-window scan finds nothing.
    """
    # One early line with the exhaustion signal — as the Claude CLI would emit
    # a JSON error object near the top of a long tool-dump.
    early_signal = '{"type":"error","error":{"type":"rate_limit_error","message":"Rate limit exceeded — resets in 5 hours"}}'

    # Generate 200 KB of garbage output that follows the error (simulating a
    # large tool-result dump after the HTTP error).
    garbage_line = "x" * 200  # 200 chars per line
    # 1000 lines × 200 chars ≈ 200 KB — well beyond the 80-line tail window.
    trailing_garbage = [garbage_line] * 1000

    session = _FakeSession(
        exit_code=1,
        error=None,
        output=[early_signal] + trailing_garbage,
        # The signal buffer would have captured the early line when it arrived.
        exhaustion_signal_lines=[early_signal],
    )

    result = detect_exhaustion_from_session(session)

    assert result is not None, (
        "detect_exhaustion_from_session returned None — exhaustion marker "
        "was not detected via the signal buffer (CB-2799 regression)"
    )
    assert result.category in (
        "rate_limit_5h", "unknown_429"
    ), f"Unexpected category: {result.category!r}"


def test_signal_buffer_used_only_as_fallback():
    """The tail-window scan is tried first; the buffer is only the fallback.

    When the tail window contains a signal directly, the result must still
    be returned (not suppressed by buffer logic).
    """
    session = _FakeSession(
        exit_code=1,
        error="rate_limit_error: Anthropic rate limit hit",
        output=[],
        exhaustion_signal_lines=[],  # buffer empty — tail/error path wins
    )
    result = detect_exhaustion_from_session(session)
    assert result is not None
    assert result.category in ("unknown_429", "rate_limit_5h", "overloaded")


def test_no_false_positive_when_buffer_empty_and_tail_clean():
    """Neither pass should fire when there are no signals anywhere."""
    session = _FakeSession(
        exit_code=1,
        error="Permission denied: /etc/foo",
        output=["normal output line"],
        exhaustion_signal_lines=[],
    )
    result = detect_exhaustion_from_session(session)
    assert result is None


def test_backwards_compat_session_without_exhaustion_signal_lines():
    """Sessions lacking ``exhaustion_signal_lines`` (pre-CB-2799 mocks) must
    not raise an AttributeError — ``getattr`` with default [] is used."""

    @dataclass
    class _LegacySession:
        exit_code: int = 1
        error: Optional[str] = None
        output: List[str] = field(default_factory=list)
        # No exhaustion_signal_lines field!

    session = _LegacySession(error="rate limit exceeded")
    result = detect_exhaustion_from_session(session)
    # Tail/error scan still works — backwards compat maintained.
    assert result is not None
