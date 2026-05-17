"""
Exhaustion detector — CB-2749 (EPIC E3, Bulletproof AutoPilot CB-2746).

Replaces the flat ``TOKEN_EXHAUSTION_PATTERNS`` substring scan with a
categorised, defence-in-depth detector that distinguishes:

  - rate_limit_5h       → auto-resume eligible (timer)
  - rate_limit_weekly   → auto-resume eligible if reset within 24 h
  - credit_exhaustion   → NO auto-resume; user must top up
  - auth_failure        → NO auto-resume; user must fix key
  - overloaded          → auto-resume after 60 s
  - unknown_429         → auto-resume after 5 min, max 3 attempts

The ``detect_exhaustion`` function is the primary public API.  It is
designed to be called from the run_queue loop immediately after a task
subprocess exits non-zero, and replaces the ``is_token_exhaustion`` +
``extract_reset_time`` pairing used before.

Secret redaction
----------------
``raw_match`` is scrubbed of known credential patterns (Bearer tokens,
sk-* keys, api[_-]?key=, x-api-key: headers) before being stored or
emitted in events.  The payload is capped at 500 chars per field and
8 KB overall before event persistence (consistent with the existing audit
log policy in ``autopilot_queue_service._redact_for_audit``).

Reset-time extraction
---------------------
``extract_reset_time_from_text`` is an extended version of the original
``_parse_reset_time_from_text`` (which remains in
``autopilot_queue_service`` for backward compat with existing callers and
tests).  The extended version additionally handles:

  - ``anthropic-ratelimit-requests-reset: <ISO>`` header echoed to output
  - "try again after Nm" / "reset in X hours" plain-text variants
  - JSON ``error.message`` containing reset hints

Usage
-----
::

    from utils.exhaustion_detector import detect_exhaustion

    result = detect_exhaustion(stdout=session_output, stderr=session_error,
                               exit_code=session.exit_code)
    if result:
        # route queue → PAUSED or WAITING_RESET based on result.category
        ...
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

ExhaustionCategory = Literal[
    "rate_limit_5h",
    "rate_limit_weekly",
    "credit_exhaustion",
    "auth_failure",
    "overloaded",
    "unknown_429",
]

# Categories where auto-resume is NOT appropriate — user must act.
NO_AUTO_RESUME_CATEGORIES: frozenset[ExhaustionCategory] = frozenset(
    ["credit_exhaustion", "auth_failure"]
)


@dataclass
class ExhaustionResult:
    """Structured result returned by ``detect_exhaustion``.

    Attributes:
        category: Exhaustion kind — drives queue state transition + UI banner.
        reset_time: UTC datetime when the limit should lift, or ``None`` if
            unknown.  Callers should apply a default (e.g. now + 5 min) when
            ``None`` and the category is auto-resume eligible.
        raw_match: The matching snippet that triggered detection, capped at
            500 chars, with credentials redacted.
    """

    category: ExhaustionCategory
    reset_time: Optional[datetime]
    raw_match: str


# ---------------------------------------------------------------------------
# Secret redaction (mirrors autopilot_queue_service._redact_for_audit)
# ---------------------------------------------------------------------------

_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE), "Bearer ***REDACTED***"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "sk-***REDACTED***"),
    (re.compile(r"api[_-]?key\s*[:=]\s*\S+", re.IGNORECASE), "api_key=***REDACTED***"),
    (re.compile(r"x-api-key\s*:\s*\S+", re.IGNORECASE), "x-api-key: ***REDACTED***"),
]

_RAW_MATCH_MAX_CHARS = 500
_EVENT_PAYLOAD_MAX_BYTES = 8 * 1024  # 8 KB


def redact_secrets(text: str) -> str:
    """Remove credential-shaped substrings from *text*.

    Scrubs Bearer tokens, sk-* API keys, api_key=... and x-api-key: headers.
    Returns the sanitised string.

    Args:
        text: Raw text that may contain credentials.

    Returns:
        Text with credential patterns replaced by ``***REDACTED***`` markers.
    """
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _cap_raw_match(snippet: str) -> str:
    """Redact and cap a matching snippet to ``_RAW_MATCH_MAX_CHARS``."""
    return redact_secrets(snippet)[:_RAW_MATCH_MAX_CHARS]


# ---------------------------------------------------------------------------
# Detection signal sets (each is a frozenset of lowercase substrings)
# ---------------------------------------------------------------------------

# Auth / identity failures — HTTP 401 / key invalid / account suspended.
# These will NOT auto-resume regardless of any timer hint.
# CB-2759: removed bare "x-api-key" substring — it fires on any header dump
# and causes false-positive auth_failure classification. Rely on http_status==401
# + json error.type (both already checked below) for the common case.
_AUTH_SIGNALS: frozenset[str] = frozenset([
    "invalid_api_key",
    "authentication_error",
    "invalid x-api-key",
    "invalid api key",
    "unauthorized",
    "not authenticated",
    "permission_error",
])

# Credit / billing failures — distinct from rate-limit; won't clear on timer.
# CB-2760: tightened to multi-word billing-specific patterns only; bare words
# like "credits", "billing", "your account has" caused false positives on
# normal log text.
_CREDIT_SIGNALS: frozenset[str] = frozenset([
    "out of credits",
    "out of extra usage",
    "billing issue",
    "credit balance is too low",
    "insufficient_quota",
    "your account has insufficient",
    "exceeded your current quota",
    "payment required",
])

# 5-hour rate-limit window phrasing (Anthropic free-tier / Pro).
_5H_SIGNALS: frozenset[str] = frozenset([
    "5 hour",
    "5-hour",
    "five hour",
    "5h limit",
    "5h reset",
    "usage limit",          # generic but common in the 5 h window message
    "usage_limit",
])

# Weekly rate-limit window phrasing.
_WEEKLY_SIGNALS: frozenset[str] = frozenset([
    "weekly limit",
    "weekly usage",
    "per week",
    "week limit",
])

# Server-overload phrasing (HTTP 529 / overloaded_error).
_OVERLOADED_SIGNALS: frozenset[str] = frozenset([
    "overloaded_error",
    "overloaded",
    "529",
])

# Generic rate-limit (HTTP 429) phrasing that does NOT fit 5 h / weekly buckets.
_GENERIC_429_SIGNALS: frozenset[str] = frozenset([
    "rate_limit_error",
    "rate limit exceeded",
    "rate limit",
    "too many requests",
    "429",
    "quota exceeded",
    "resets at",
    "resets in",
    "retry after",
    "retry-after",
])

# HTTP status pattern used for fallback numeric matching.
_HTTP_STATUS_RE = re.compile(r"\bHTTP[/ ](\d{3})\b", re.IGNORECASE)

# JSON error object pattern — last ``{"type":"error",...}`` line.
_JSON_ERROR_RE = re.compile(r'\{[^{}]*"type"\s*:\s*"error"[^{}]*\}')


# ---------------------------------------------------------------------------
# Reset-time extraction (extended)
# ---------------------------------------------------------------------------

def extract_reset_time_from_text(text: str) -> Optional[datetime]:
    """Extract a UTC reset datetime from *text* using multiple heuristics.

    This is the extended version of the original ``_parse_reset_time_from_text``
    in ``autopilot_queue_service``.  It adds:

      - ``anthropic-ratelimit-requests-reset:`` header value (ISO 8601)
      - "try again after Nm" / "try again in X hours" plain-text
      - JSON ``error.message`` recursive search for time hints

    Returns ``None`` when no reset time can be determined.

    Args:
        text: Combined stdout + stderr or any output text from the subprocess.

    Returns:
        A tz-naive UTC ``datetime`` or ``None``.
    """
    if not text:
        return None
    now = datetime.utcnow()

    # ---- 0. Anthropic rate-limit header echoed to output ----
    m = re.search(
        r"anthropic-ratelimit-requests-reset\s*[:=]\s*(\S+)",
        text,
        re.IGNORECASE,
    )
    if m:
        val = m.group(1).strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue

    # ---- 1. resets at HH:MM am/pm ----
    m = re.search(
        r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)",
        text,
        re.IGNORECASE,
    )
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        meridian = m.group(3).lower()
        if meridian == "pm" and hour < 12:
            hour += 12
        elif meridian == "am" and hour == 12:
            hour = 0
        if 0 <= hour < 24 and 0 <= minute < 60:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target

    # ---- 2. resets in Nh [Mm] ----
    m = re.search(
        r"resets?\s+in\s+(\d+)\s*h(?:ours?)?(?:\s+(\d+)\s*m(?:in(?:ute)?s?)?)?",
        text,
        re.IGNORECASE,
    )
    if m:
        hours = int(m.group(1))
        minutes = int(m.group(2) or 0)
        return now + timedelta(hours=hours, minutes=minutes)

    # ---- 3. ISO datetime ----
    m = re.search(
        r"resets?\s+(?:at\s+)?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?)",
        text,
        re.IGNORECASE,
    )
    if m:
        ts = m.group(1).replace(" ", "T")
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                return datetime.strptime(ts, fmt)
            except ValueError:
                continue

    # ---- 4. retry-after: <seconds> ----
    m = re.search(r"retry[-_]?after[:\s]+(\d+)", text, re.IGNORECASE)
    if m:
        return now + timedelta(seconds=int(m.group(1)))

    # ---- 5. "try again after Nm" / "try again in N hours" ----
    m = re.search(
        r"try\s+again\s+(?:after|in)\s+(\d+)\s*(s(?:ec(?:ond)?s?)?|m(?:in(?:ute)?s?)?|h(?:ours?)?)",
        text,
        re.IGNORECASE,
    )
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("h"):
            return now + timedelta(hours=amount)
        elif unit.startswith("m"):
            return now + timedelta(minutes=amount)
        else:
            return now + timedelta(seconds=amount)

    # ---- 6. "reset in X hours" (without "resets") ----
    m = re.search(
        r"reset\s+in\s+(\d+)\s*h(?:ours?)?",
        text,
        re.IGNORECASE,
    )
    if m:
        return now + timedelta(hours=int(m.group(1)))

    # ---- 7. JSON error.message containing hints ----
    for json_match in _JSON_ERROR_RE.finditer(text):
        try:
            obj = json.loads(json_match.group(0))
            msg = ""
            if isinstance(obj, dict):
                err = obj.get("error", obj)
                if isinstance(err, dict):
                    msg = err.get("message", "") or ""
            if msg:
                parsed = extract_reset_time_from_text(msg)
                if parsed:
                    return parsed
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    return None


# ---------------------------------------------------------------------------
# JSON error-type extraction
# ---------------------------------------------------------------------------

def _extract_json_error_type(text: str) -> Optional[str]:
    """Try to parse the last JSON error object in *text* and return error.type.

    Anthropic's stream-json output contains lines like::

        {"type":"error","error":{"type":"rate_limit_error","message":"..."},...}

    Returns the ``error.type`` string value, or ``None`` if not found.

    Args:
        text: Combined subprocess output to scan.

    Returns:
        The ``error.type`` string or ``None``.
    """
    for match in reversed(list(_JSON_ERROR_RE.finditer(text))):
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                err = obj.get("error", {})
                if isinstance(err, dict):
                    etype = err.get("type")
                    if isinstance(etype, str):
                        return etype.lower()
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def _extract_http_status(text: str) -> Optional[int]:
    """Return the last HTTP status code found in *text*, or ``None``.

    Args:
        text: Combined subprocess output to scan.

    Returns:
        Integer HTTP status code or ``None``.
    """
    statuses = [int(m.group(1)) for m in _HTTP_STATUS_RE.finditer(text)]
    return statuses[-1] if statuses else None


# ---------------------------------------------------------------------------
# Primary detector
# ---------------------------------------------------------------------------

def detect_exhaustion(
    stdout: str,
    stderr: str,
    exit_code: int,
) -> Optional[ExhaustionResult]:
    """Detect and categorise API exhaustion / auth failures from subprocess output.

    Scans the last 4 KB of *stdout* + *stderr* combined for exhaustion signals.
    Returns ``None`` if no exhaustion pattern matches (i.e. the failure is a
    genuine task error, not a quota/auth issue).

    Detection strategy (defence-in-depth):
      1. JSON-shaped Anthropic error — ``error.type`` field (most reliable).
      2. HTTP status numeric match in output.
      3. Substring scan against categorised signal sets.

    Categorisation priority (highest-priority wins):
      auth_failure > credit_exhaustion > overloaded > rate_limit_5h >
      rate_limit_weekly > unknown_429

    Args:
        stdout: Last portion of subprocess stdout (caller may pre-slice; this
            function additionally caps to last 4 KB internally).
        stderr: Last portion of subprocess stderr.
        exit_code: The subprocess exit code.  Exit code 0 always returns ``None``.

    Returns:
        An :class:`ExhaustionResult` if exhaustion is detected, else ``None``.
    """
    if exit_code == 0:
        return None

    # Combine and cap to last 4 KB for the scan window
    combined_raw = (stdout or "") + "\n" + (stderr or "")
    scan_window = combined_raw[-4096:]
    scan_lower = scan_window.lower()

    # ---- Signal collection ----
    has_auth = any(s in scan_lower for s in _AUTH_SIGNALS)
    has_credit = any(s in scan_lower for s in _CREDIT_SIGNALS)
    has_5h = any(s in scan_lower for s in _5H_SIGNALS)
    has_weekly = any(s in scan_lower for s in _WEEKLY_SIGNALS)
    has_overloaded = any(s in scan_lower for s in _OVERLOADED_SIGNALS)
    has_generic_429 = any(s in scan_lower for s in _GENERIC_429_SIGNALS)

    # JSON error.type lookup
    json_error_type = _extract_json_error_type(scan_window)
    if json_error_type:
        if "auth" in json_error_type or "invalid_api" in json_error_type:
            has_auth = True
        if "rate_limit" in json_error_type:
            has_generic_429 = True
        if "overloaded" in json_error_type:
            has_overloaded = True
        if "permission" in json_error_type:
            has_auth = True

    # HTTP status lookup
    http_status = _extract_http_status(scan_window)
    if http_status == 401:
        has_auth = True
    elif http_status == 429:
        has_generic_429 = True
    elif http_status == 529:
        has_overloaded = True

    # ---- Gate: any exhaustion signal present? ----
    any_signal = (
        has_auth or has_credit or has_5h or has_weekly
        or has_overloaded or has_generic_429
    )
    if not any_signal:
        return None

    # ---- Categorise (priority order: auth > credit > overloaded > 5h > weekly > unknown_429) ----
    if has_auth:
        category: ExhaustionCategory = "auth_failure"
    elif has_credit:
        category = "credit_exhaustion"
    elif has_overloaded:
        category = "overloaded"
    elif has_5h and has_generic_429:
        category = "rate_limit_5h"
    elif has_weekly and has_generic_429:
        category = "rate_limit_weekly"
    elif has_generic_429:
        category = "unknown_429"
    elif has_5h:
        # 5h signal without explicit 429 marker still indicates rate-limit
        category = "rate_limit_5h"
    elif has_weekly:
        category = "rate_limit_weekly"
    else:
        # Fallback — some credit/auth signal triggered but nothing else matched
        category = "credit_exhaustion"

    # ---- Extract reset time ----
    reset_time = extract_reset_time_from_text(scan_window)

    # ---- Build raw_match snippet ----
    # Find the first non-empty line in the scan window that contains a signal.
    raw_match = _find_best_match_line(scan_window, scan_lower)

    return ExhaustionResult(
        category=category,
        reset_time=reset_time,
        raw_match=_cap_raw_match(raw_match),
    )


def _find_best_match_line(window: str, window_lower: str) -> str:
    """Return the best single-line snippet that triggered detection.

    Preference order: auth signals, then credit, then 429/overloaded.
    Falls back to last non-empty line if nothing specific is found.

    Args:
        window: The raw 4 KB scan window.
        window_lower: Lowercased version of *window*.

    Returns:
        A single representative line from *window*.
    """
    all_signals: list[frozenset[str]] = [
        _AUTH_SIGNALS,
        _CREDIT_SIGNALS,
        _OVERLOADED_SIGNALS,
        _5H_SIGNALS,
        _WEEKLY_SIGNALS,
        _GENERIC_429_SIGNALS,
    ]
    lines = window.splitlines()
    lines_lower = window_lower.splitlines()

    for signal_set in all_signals:
        for line, line_lower in zip(lines, lines_lower):
            if any(sig in line_lower for sig in signal_set):
                return line.strip()

    # Fallback: last non-empty line
    for line in reversed(lines):
        if line.strip():
            return line.strip()
    return ""


# ---------------------------------------------------------------------------
# Backward-compat shim: session-based API (mirrors original is_token_exhaustion)
# ---------------------------------------------------------------------------

def detect_exhaustion_from_session(session) -> Optional[ExhaustionResult]:
    """Convenience wrapper that accepts a ``TerminalSession``-like object.

    CB-2799 two-pass strategy:

    1. **Tail-window scan** (existing behaviour, kept as backstop):
       assembles the last 80 output lines + stderr and calls
       :func:`detect_exhaustion`.

    2. **Signal-buffer scan** (new):
       if the tail-window returns ``None``, read
       ``session.exhaustion_signal_lines`` — the rolling buffer of lines that
       contained exhaustion/error patterns when they were originally appended.
       This fixes the "marker buried in long output" failure mode (RC4a) where
       the Claude CLI dumps 40-200 KB of tool output *after* the HTTP-429
       error object, scrolling it out of the 80-line window.

    Uses ``getattr(session, 'exhaustion_signal_lines', [])`` for backwards
    compatibility with existing test fixtures and mock sessions that pre-date
    CB-2799.

    This replaces ``is_token_exhaustion(session)`` + ``extract_reset_time(session)``
    in a single call.

    Args:
        session: Any object with ``exit_code: int``, ``output: list[str]``,
            and ``error: Optional[str]`` attributes.  Optionally has
            ``exhaustion_signal_lines: list[str]`` (CB-2799).

    Returns:
        An :class:`ExhaustionResult` or ``None``.
    """
    # --- Pass 1: tail-window scan (original behaviour) ---
    stdout = "\n".join((session.output or [])[-80:])
    stderr = session.error or ""
    result = detect_exhaustion(
        stdout=stdout,
        stderr=stderr,
        exit_code=session.exit_code,
    )
    if result is not None:
        return result

    # --- Pass 2: signal-buffer scan (CB-2799) ---
    signal_lines: list = getattr(session, "exhaustion_signal_lines", [])
    if not signal_lines:
        return None
    signal_text = "\n".join(signal_lines)
    return detect_exhaustion(
        stdout=signal_text,
        stderr=stderr,
        exit_code=session.exit_code,
    )
