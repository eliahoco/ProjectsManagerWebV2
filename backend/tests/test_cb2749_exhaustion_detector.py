"""
CB-2749 — Categorised exhaustion detector tests.

Covers:
  - All 6 categories (rate_limit_5h, rate_limit_weekly, credit_exhaustion,
    auth_failure, overloaded, unknown_429)
  - JSON error-type extraction
  - HTTP status numeric matching
  - Reset-time extraction (header, plain text, JSON-embedded, missing)
  - Secret redaction (Bearer tokens, sk-* keys, api_key=, x-api-key:)
  - Session-based convenience wrapper (detect_exhaustion_from_session)
  - Priority ordering (auth > credit > overloaded > 5h > weekly > unknown)
  - Exit-code 0 short-circuit
  - 4 KB window enforcement
  - NO_AUTO_RESUME_CATEGORIES membership

Existing tests in test_token_exhaustion_detection.py and
test_reset_time_extraction.py must still pass — this file does NOT
replace them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

import pytest

from utils.exhaustion_detector import (
    NO_AUTO_RESUME_CATEGORIES,
    ExhaustionResult,
    detect_exhaustion,
    detect_exhaustion_from_session,
    extract_reset_time_from_text,
    redact_secrets,
)


# ---------------------------------------------------------------------------
# Fake session object (mirrors _FakeSession in test_token_exhaustion_detection)
# ---------------------------------------------------------------------------


@dataclass
class _Session:
    exit_code: int = 1
    error: Optional[str] = None
    output: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _detect(stdout: str = "", stderr: str = "", exit_code: int = 1) -> Optional[ExhaustionResult]:
    return detect_exhaustion(stdout=stdout, stderr=stderr, exit_code=exit_code)


# ===========================================================================
# Category: rate_limit_5h
# ===========================================================================


class TestRateLimit5h:
    def test_5h_pattern_explicit(self):
        r = _detect(stdout="Error: rate limit exceeded, 5 hour reset applies.")
        assert r is not None
        assert r.category == "rate_limit_5h"

    def test_5h_with_429(self):
        r = _detect(stdout="HTTP 429 — usage limit reached (5h limit). resets in 5h.")
        assert r is not None
        assert r.category == "rate_limit_5h"

    def test_5h_dash_variant(self):
        r = _detect(stderr="5-hour window exhausted. too many requests.")
        assert r is not None
        assert r.category == "rate_limit_5h"

    def test_5h_resets_in_extracted(self):
        """Reset time should be extracted when present."""
        r = _detect(stdout="rate_limit_error: 5 hour reset. resets in 4h 30m.")
        assert r is not None
        assert r.category == "rate_limit_5h"
        assert r.reset_time is not None
        delta = r.reset_time - datetime.utcnow()
        assert timedelta(hours=4, minutes=28) < delta < timedelta(hours=4, minutes=32)


# ===========================================================================
# Category: rate_limit_weekly
# ===========================================================================


class TestRateLimitWeekly:
    def test_weekly_limit(self):
        r = _detect(stdout="HTTP 429 — weekly limit reached.")
        assert r is not None
        assert r.category == "rate_limit_weekly"

    def test_per_week_phrasing(self):
        r = _detect(stderr="Too many requests. Limit is per week. retry-after: 86400")
        assert r is not None
        assert r.category == "rate_limit_weekly"
        assert r.reset_time is not None

    def test_weekly_without_429_still_detected(self):
        """Weekly signal alone (no HTTP 429 text) triggers rate_limit_weekly."""
        r = _detect(stdout="weekly usage exceeded, please wait.")
        assert r is not None
        assert r.category == "rate_limit_weekly"


# ===========================================================================
# Category: credit_exhaustion
# ===========================================================================


class TestCreditExhaustion:
    def test_credit_balance_too_low(self):
        r = _detect(stderr="Your credit balance is too low to make API calls.")
        assert r is not None
        assert r.category == "credit_exhaustion"

    def test_out_of_extra_usage(self):
        r = _detect(stdout="out of extra usage for this billing cycle.")
        assert r is not None
        assert r.category == "credit_exhaustion"

    def test_exceeded_current_quota(self):
        r = _detect(stderr="You exceeded your current quota; please add credit.")
        assert r is not None
        assert r.category == "credit_exhaustion"

    def test_no_auto_resume_for_credit(self):
        """credit_exhaustion must be in NO_AUTO_RESUME_CATEGORIES."""
        assert "credit_exhaustion" in NO_AUTO_RESUME_CATEGORIES

    def test_your_account_has(self):
        r = _detect(stdout="Process exited with code 1\nyour account has run out of credits.")
        assert r is not None
        assert r.category == "credit_exhaustion"

    def test_credit_no_reset_time(self):
        """Credit exhaustion typically has no reset hint — reset_time should be None."""
        r = _detect(stderr="credit balance is too low.")
        assert r is not None
        # reset_time may or may not be None depending on text; but if absent, None
        # (nothing in this string parses to a time)
        assert r.reset_time is None


# ===========================================================================
# Category: auth_failure
# ===========================================================================


class TestAuthFailure:
    def test_invalid_api_key(self):
        r = _detect(stderr="invalid_api_key: The provided API key is invalid.")
        assert r is not None
        assert r.category == "auth_failure"

    def test_authentication_error(self):
        r = _detect(stdout="authentication_error: please check your credentials.")
        assert r is not None
        assert r.category == "auth_failure"

    def test_http_401(self):
        r = _detect(stdout="HTTP 401 Unauthorized — check your API key.")
        assert r is not None
        assert r.category == "auth_failure"

    def test_no_auto_resume_for_auth(self):
        """auth_failure must be in NO_AUTO_RESUME_CATEGORIES."""
        assert "auth_failure" in NO_AUTO_RESUME_CATEGORIES

    def test_process_exit_code_1_with_401(self):
        """Real 5/9 incident pattern: exit code 1 + auth signal in output."""
        r = _detect(
            stdout="Claude Code v1.2.3\nProcess exited with code 1\nHTTP 401 Unauthorized",
            stderr="anthropic.APIError: 401",
            exit_code=1,
        )
        assert r is not None
        assert r.category == "auth_failure"


# ===========================================================================
# Category: overloaded
# ===========================================================================


class TestOverloaded:
    def test_overloaded_error(self):
        r = _detect(stdout="Anthropic returned overloaded_error (HTTP 529).")
        assert r is not None
        assert r.category == "overloaded"

    def test_529_numeric(self):
        r = _detect(stderr="HTTP 529 service unavailable — overloaded.")
        assert r is not None
        assert r.category == "overloaded"

    def test_overloaded_auto_resume_eligible(self):
        """overloaded is NOT in NO_AUTO_RESUME_CATEGORIES."""
        assert "overloaded" not in NO_AUTO_RESUME_CATEGORIES


# ===========================================================================
# Category: unknown_429
# ===========================================================================


class TestUnknown429:
    def test_generic_429(self):
        r = _detect(stdout="HTTP 429 Too Many Requests.")
        assert r is not None
        assert r.category == "unknown_429"

    def test_rate_limit_error_no_window_hint(self):
        """rate_limit_error without 5h or weekly text → unknown_429."""
        r = _detect(stdout="rate_limit_error: please slow down.")
        assert r is not None
        assert r.category == "unknown_429"

    def test_unknown_429_auto_resume_eligible(self):
        assert "unknown_429" not in NO_AUTO_RESUME_CATEGORIES


# ===========================================================================
# Priority ordering
# ===========================================================================


class TestCategoryPriority:
    def test_auth_beats_credit(self):
        """When both auth and credit signals appear, auth wins."""
        r = _detect(
            stdout="invalid_api_key; also credit balance is too low"
        )
        assert r is not None
        assert r.category == "auth_failure"

    def test_auth_beats_429(self):
        r = _detect(stdout="HTTP 401 rate limit exceeded too many requests")
        assert r is not None
        assert r.category == "auth_failure"

    def test_credit_beats_overloaded(self):
        r = _detect(stdout="credit balance is too low overloaded_error 529")
        assert r is not None
        assert r.category == "credit_exhaustion"

    def test_overloaded_beats_5h(self):
        r = _detect(stdout="overloaded_error 5 hour reset usage limit")
        assert r is not None
        assert r.category == "overloaded"

    def test_5h_beats_weekly(self):
        r = _detect(stdout="rate_limit_error weekly limit 5h limit")
        assert r is not None
        assert r.category == "rate_limit_5h"


# ===========================================================================
# JSON error-type detection
# ===========================================================================


class TestJsonErrorType:
    def test_json_rate_limit_error(self):
        line = '{"type":"error","error":{"type":"rate_limit_error","message":"slow down"}}'
        r = _detect(stdout=line)
        assert r is not None
        assert r.category in ("unknown_429", "rate_limit_5h", "rate_limit_weekly")

    def test_json_overloaded_error(self):
        line = '{"type":"error","error":{"type":"overloaded_error","message":"busy"}}'
        r = _detect(stdout=line)
        assert r is not None
        assert r.category == "overloaded"

    def test_json_auth_error(self):
        line = '{"type":"error","error":{"type":"authentication_error","message":"bad key"}}'
        r = _detect(stdout=line)
        assert r is not None
        assert r.category == "auth_failure"

    def test_json_invalid_api_key_type(self):
        line = '{"type":"error","error":{"type":"invalid_api_key","message":"no"}}'
        r = _detect(stdout=line)
        assert r is not None
        assert r.category == "auth_failure"


# ===========================================================================
# Reset-time extraction
# ===========================================================================


class TestResetTimeExtraction:
    def test_header_form(self):
        text = "anthropic-ratelimit-requests-reset: 2026-05-09T12:00:00Z"
        t = extract_reset_time_from_text(text)
        assert t is not None
        assert t.year == 2026 and t.month == 5 and t.hour == 12

    def test_resets_at_hhmm_pm(self):
        t = extract_reset_time_from_text("resets at 5:30 PM")
        assert t is not None
        assert t.hour == 17 and t.minute == 30

    def test_resets_in_nh(self):
        before = datetime.utcnow()
        t = extract_reset_time_from_text("resets in 3h 15m")
        assert t is not None
        assert timedelta(hours=3, minutes=14) < (t - before) < timedelta(hours=3, minutes=16)

    def test_retry_after_seconds(self):
        before = datetime.utcnow()
        t = extract_reset_time_from_text("retry-after: 300")
        assert t is not None
        assert timedelta(seconds=299) < (t - before) < timedelta(seconds=305)

    def test_try_again_after_minutes(self):
        before = datetime.utcnow()
        t = extract_reset_time_from_text("try again after 10m")
        assert t is not None
        assert timedelta(minutes=9) < (t - before) < timedelta(minutes=11)

    def test_try_again_in_hours(self):
        before = datetime.utcnow()
        t = extract_reset_time_from_text("try again in 2 hours")
        assert t is not None
        assert timedelta(hours=1, minutes=59) < (t - before) < timedelta(hours=2, minutes=1)

    def test_reset_in_x_hours(self):
        before = datetime.utcnow()
        t = extract_reset_time_from_text("reset in 1 hour")
        assert t is not None
        delta = t - before
        assert timedelta(minutes=59) < delta < timedelta(minutes=62)

    def test_json_embedded_reset(self):
        """Reset hint buried inside a JSON error.message field."""
        text = '{"type":"error","error":{"type":"rate_limit_error","message":"retry-after: 120"}}'
        t = extract_reset_time_from_text(text)
        assert t is not None

    def test_missing_returns_none(self):
        assert extract_reset_time_from_text("some random log line") is None

    def test_empty_returns_none(self):
        assert extract_reset_time_from_text("") is None
        assert extract_reset_time_from_text(None) is None  # type: ignore[arg-type]


# ===========================================================================
# Secret redaction
# ===========================================================================


class TestSecretRedaction:
    def test_bearer_token_scrubbed(self):
        text = "Authorization: Bearer sk-ant-longtoken12345678901234"
        result = redact_secrets(text)
        assert "sk-ant-" not in result
        assert "***REDACTED***" in result

    def test_sk_key_scrubbed(self):
        text = "API call with key sk-proj-abcdefghijklmnopqrstuvwxyz1234"
        result = redact_secrets(text)
        assert "sk-proj-" not in result
        assert "***REDACTED***" in result

    def test_api_key_eq_scrubbed(self):
        text = "api_key=supersecretvalue123"
        result = redact_secrets(text)
        assert "supersecretvalue123" not in result
        assert "***REDACTED***" in result

    def test_x_api_key_header_scrubbed(self):
        text = "x-api-key: my-secret-key-here"
        result = redact_secrets(text)
        assert "my-secret-key-here" not in result
        assert "***REDACTED***" in result

    def test_raw_match_is_redacted(self):
        """raw_match on returned ExhaustionResult must not contain credentials."""
        r = _detect(
            stdout="HTTP 401 invalid_api_key sk-ant-realkey1234567890abcdefghij Bearer sometoken999"
        )
        assert r is not None
        assert "sk-ant-realkey" not in r.raw_match
        assert "sometoken999" not in r.raw_match

    def test_raw_match_capped_at_500(self):
        long_line = "invalid_api_key " + ("x" * 1000)
        r = _detect(stdout=long_line)
        assert r is not None
        assert len(r.raw_match) <= 500


# ===========================================================================
# Exit code short-circuit
# ===========================================================================


class TestExitCodeZero:
    def test_exit_zero_returns_none_despite_signals(self):
        r = _detect(stdout="rate_limit_error credit balance is too low", exit_code=0)
        assert r is None

    def test_exit_zero_auth_signal_returns_none(self):
        r = _detect(stdout="invalid_api_key HTTP 401", exit_code=0)
        assert r is None


# ===========================================================================
# 4 KB window enforcement
# ===========================================================================


class TestScanWindow:
    def test_signal_at_end_of_large_output_detected(self):
        """Signal within the last 4 KB of a 10 KB output is detected."""
        padding = "A" * (10_000 - 100)
        r = _detect(stdout=padding + "\nrate_limit_error: slow down")
        assert r is not None

    def test_signal_only_in_early_output_not_detected(self):
        """Signal buried beyond last 4 KB is NOT detected (defense against noise)."""
        signal = "credit balance is too low"
        padding = "B" * 10_000
        r = _detect(stdout=signal + "\n" + padding)
        # The signal is at the start, which is outside the 4 KB tail
        assert r is None


# ===========================================================================
# Session-based wrapper
# ===========================================================================


class TestDetectExhaustionFromSession:
    def test_session_wrapper_detects_rate_limit(self):
        s = _Session(output=["rate_limit_error: API quota exceeded."])
        r = detect_exhaustion_from_session(s)
        assert r is not None
        assert r.category in ("unknown_429", "rate_limit_5h", "rate_limit_weekly")

    def test_session_wrapper_exit_zero(self):
        s = _Session(exit_code=0, error="rate_limit_error")
        r = detect_exhaustion_from_session(s)
        assert r is None

    def test_session_wrapper_auth(self):
        s = _Session(error="HTTP 401 invalid_api_key")
        r = detect_exhaustion_from_session(s)
        assert r is not None
        assert r.category == "auth_failure"

    def test_session_wrapper_credit(self):
        s = _Session(exit_code=1, output=["Process exited with code 1", "your account has run out of credits"])
        r = detect_exhaustion_from_session(s)
        assert r is not None
        assert r.category == "credit_exhaustion"

    def test_session_wrapper_overloaded(self):
        s = _Session(error="overloaded_error HTTP 529")
        r = detect_exhaustion_from_session(s)
        assert r is not None
        assert r.category == "overloaded"

    def test_session_wrapper_no_signal(self):
        s = _Session(error="FileNotFoundError: no such file /tmp/foo")
        r = detect_exhaustion_from_session(s)
        assert r is None


# ===========================================================================
# NO_AUTO_RESUME_CATEGORIES membership
# ===========================================================================


class TestNoAutoResumeSet:
    def test_contains_credit_and_auth(self):
        assert "credit_exhaustion" in NO_AUTO_RESUME_CATEGORIES
        assert "auth_failure" in NO_AUTO_RESUME_CATEGORIES

    def test_does_not_contain_rate_limit_or_overloaded(self):
        assert "rate_limit_5h" not in NO_AUTO_RESUME_CATEGORIES
        assert "rate_limit_weekly" not in NO_AUTO_RESUME_CATEGORIES
        assert "overloaded" not in NO_AUTO_RESUME_CATEGORIES
        assert "unknown_429" not in NO_AUTO_RESUME_CATEGORIES
