"""
Reset-time extraction tests (CB-1951 E3.2.3).

Drives the pure ``_parse_reset_time_from_text`` helper directly (no need to
build a ``TerminalSession``) and covers all formats supported in E3.2.2.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from services.autopilot_queue_service import _parse_reset_time_from_text


# ---------------------------------------------------------------------------
# Format 1: resets at HH:MM am/pm (today UTC; rolls to tomorrow if past)
# ---------------------------------------------------------------------------


def test_resets_at_hhmm_pm():
    out = _parse_reset_time_from_text("Usage resets at 5:30 PM today.")
    assert out is not None
    assert out.hour == 17 and out.minute == 30


def test_resets_at_hh_am():
    out = _parse_reset_time_from_text("Quota resets at 9 AM Pacific.")
    assert out is not None
    assert out.hour == 9 and out.minute == 0


def test_resets_at_12am_normalizes_to_midnight():
    out = _parse_reset_time_from_text("resets at 12:00 AM tomorrow")
    assert out is not None
    assert out.hour == 0 and out.minute == 0


def test_resets_at_12pm_stays_noon():
    out = _parse_reset_time_from_text("resets at 12:00 PM")
    assert out is not None
    assert out.hour == 12 and out.minute == 0


def test_resets_at_already_past_rolls_to_tomorrow():
    """If the parsed time is already past, target should be on a future day."""
    out = _parse_reset_time_from_text("resets at 12:01 AM")
    assert out is not None
    # Either today's later 12:01 AM (if before midnight) or tomorrow.
    # In practice for a clock that's not exactly at midnight, this is
    # always >= now (the implementation rolls forward when target <= now).
    assert out >= datetime.utcnow() - timedelta(seconds=2)


# ---------------------------------------------------------------------------
# Format 2: resets in Nh [Mm]
# ---------------------------------------------------------------------------


def test_resets_in_4h():
    before = datetime.utcnow()
    out = _parse_reset_time_from_text("Quota resets in 4h.")
    after = datetime.utcnow()
    assert out is not None
    delta = out - before
    assert timedelta(hours=4) - timedelta(seconds=2) <= delta <= timedelta(hours=4) + (after - before)


def test_resets_in_4h_30m():
    before = datetime.utcnow()
    out = _parse_reset_time_from_text("Quota resets in 4h 30m.")
    assert out is not None
    delta = out - before
    assert timedelta(hours=4, minutes=29) <= delta <= timedelta(hours=4, minutes=31)


# ---------------------------------------------------------------------------
# Format 3: ISO datetime
# ---------------------------------------------------------------------------


def test_iso_datetime_T_separator():
    out = _parse_reset_time_from_text("resets at 2026-05-04T03:15:00 UTC")
    assert out is not None
    assert out.year == 2026 and out.month == 5 and out.day == 4
    assert out.hour == 3 and out.minute == 15


def test_iso_datetime_no_seconds():
    out = _parse_reset_time_from_text("reset 2026-12-31T23:59")
    assert out is not None
    assert out.year == 2026 and out.month == 12 and out.day == 31
    assert out.hour == 23 and out.minute == 59


def test_iso_datetime_space_separator():
    out = _parse_reset_time_from_text("resets at 2026-05-04 06:00:00")
    assert out is not None
    assert out.year == 2026 and out.day == 4 and out.hour == 6


# ---------------------------------------------------------------------------
# Format 4: retry-after seconds
# ---------------------------------------------------------------------------


def test_retry_after_seconds():
    before = datetime.utcnow()
    out = _parse_reset_time_from_text("HTTP 429 retry-after: 120")
    assert out is not None
    delta = out - before
    assert timedelta(seconds=119) <= delta <= timedelta(seconds=125)


def test_retry_after_underscore_form():
    before = datetime.utcnow()
    out = _parse_reset_time_from_text("retry_after: 60")
    assert out is not None
    delta = out - before
    assert timedelta(seconds=59) <= delta <= timedelta(seconds=65)


# ---------------------------------------------------------------------------
# Negative + malformed
# ---------------------------------------------------------------------------


def test_empty_returns_none():
    assert _parse_reset_time_from_text("") is None
    assert _parse_reset_time_from_text(None) is None  # type: ignore[arg-type]


def test_no_match_returns_none():
    assert _parse_reset_time_from_text("just a normal log line") is None


def test_malformed_hour_returns_none():
    """Hour > 12 with am/pm is rejected (the AM/PM regex requires 1-2 digits
    but the implementation also bounds hour < 24 after PM adjustment)."""
    out = _parse_reset_time_from_text("resets at 25 PM")
    # 25 PM is 25+12=37, > 24, rejected
    assert out is None


def test_invalid_iso_returns_none_falls_through():
    """Bad ISO format should not raise — falls through silently."""
    out = _parse_reset_time_from_text("resets at 2026-13-99T99:99:99")
    # The format pattern matches but datetime.strptime fails; we return None
    assert out is None


def test_first_match_wins_priority_order():
    """When multiple formats match, the FIRST format (HH:MM am/pm) wins."""
    text = "resets at 5 PM ... retry-after: 600"
    out = _parse_reset_time_from_text(text)
    assert out is not None
    # 5 PM = 17:00 — verify hour, not retry-after's now+10min
    assert out.hour == 17
