"""
Unit tests for the AI-response JSON parser in documentation_generator (CB-1583).

Exercises `DocumentationGenerator._parse_ai_response` and the supporting
coercion helpers. Mirrors the `_extract_json_object` pattern from
`ai_service.py` while adding defensive defaults, oversized-input refusal,
and unknown-key normalization.
"""

from __future__ import annotations

import json

import pytest

from services.documentation_generator import (
    DocumentationGenerator,
    _coerce_int,
    _coerce_str_list,
    _normalize_ai_fields,
    _safe_json_loads,
    _truncate,
    _MAX_AI_RESPONSE_CHARS,
    _EXPECTED_KEYS,
)


# ---------------------------------------------------------------------------
# _parse_ai_response — happy paths
# ---------------------------------------------------------------------------

def test_parse_raw_json_object():
    payload = {
        "summary": "Implemented feature X",
        "componentsModified": ["backend"],
        "filesTouched": ["a.py"],
        "linesAdded": 10,
        "linesRemoved": 2,
        "architectureNotes": "",
        "technicalNotes": "",
        "challengesFaced": "",
        "lessonsLearned": "",
    }
    result = DocumentationGenerator._parse_ai_response(json.dumps(payload))
    assert result["summary"] == "Implemented feature X"
    assert result["componentsModified"] == ["backend"]
    assert result["linesAdded"] == 10


def test_parse_json_inside_fenced_code_block():
    text = """```json
{"summary": "x", "filesTouched": ["a.py"]}
```"""
    result = DocumentationGenerator._parse_ai_response(text)
    assert result == {"summary": "x", "filesTouched": ["a.py"]}


def test_parse_json_inside_unlabelled_fence():
    text = """Here you go:

```
{"summary": "y"}
```
"""
    result = DocumentationGenerator._parse_ai_response(text)
    assert result["summary"] == "y"


def test_parse_json_embedded_in_prose():
    text = (
        "Sure, here is the summary:\n"
        '{"summary": "embedded", "filesTouched": []}\n'
        "Hope that helps!"
    )
    result = DocumentationGenerator._parse_ai_response(text)
    assert result["summary"] == "embedded"
    assert result["filesTouched"] == []


# ---------------------------------------------------------------------------
# _parse_ai_response — defensive paths
# ---------------------------------------------------------------------------

def test_parse_none_returns_empty_dict():
    assert DocumentationGenerator._parse_ai_response(None) == {}


def test_parse_empty_string_returns_empty_dict():
    assert DocumentationGenerator._parse_ai_response("") == {}


def test_parse_pure_prose_returns_empty_dict():
    assert DocumentationGenerator._parse_ai_response(
        "I am sorry, I cannot help with that."
    ) == {}


def test_parse_invalid_json_returns_empty_dict():
    # Unbalanced braces, no recoverable inner span
    assert DocumentationGenerator._parse_ai_response("{ this is not json") == {}


def test_parse_json_array_returns_empty_dict():
    # Top-level array — parser only accepts objects
    assert DocumentationGenerator._parse_ai_response('[{"a": 1}]') == {}


def test_parse_oversized_response_refused():
    huge = "{" + ("a" * (_MAX_AI_RESPONSE_CHARS + 10)) + "}"
    assert DocumentationGenerator._parse_ai_response(huge) == {}


def test_parse_drops_unknown_keys():
    payload = '{"summary": "ok", "evilKey": "drop me", "filesTouched": ["a"]}'
    result = DocumentationGenerator._parse_ai_response(payload)
    assert "evilKey" not in result
    assert result["summary"] == "ok"
    assert result["filesTouched"] == ["a"]


def test_parse_handles_trailing_text_after_json_block():
    # Common AI failure mode: valid JSON followed by an apology
    text = '{"summary": "ok"}\n\nLet me know if you need anything else.'
    result = DocumentationGenerator._parse_ai_response(text)
    assert result == {"summary": "ok"}


def test_parse_recovers_from_leading_garbage():
    # Closing fence missing — the inner-span fallback should still find it
    text = '```json\n{"summary": "recovered"}'
    result = DocumentationGenerator._parse_ai_response(text)
    assert result == {"summary": "recovered"}


def test_parse_unicode_payload():
    payload = {
        "summary": "Implemented 日本語 + emoji 🚀 + RTL עברית",
        "filesTouched": ["docs/中文.md"],
    }
    out = DocumentationGenerator._parse_ai_response(json.dumps(payload, ensure_ascii=False))
    assert out["summary"] == payload["summary"]
    assert out["filesTouched"] == payload["filesTouched"]


def test_parse_whitespace_only_returns_empty_dict():
    assert DocumentationGenerator._parse_ai_response("   \n\t  ") == {}


def test_parse_multiple_fenced_blocks_picks_first_match():
    # Some models emit a thinking block and then the answer. The non-greedy
    # regex picks the first fence pair; the inner-span fallback (find first
    # '{' / rfind last '}') then covers spillover.
    text = (
        "```\nfirst block — not JSON\n```\n\n"
        '```json\n{"summary": "from second"}\n```'
    )
    result = DocumentationGenerator._parse_ai_response(text)
    # First fence captures non-JSON; outer-span fallback recovers the object.
    assert result == {"summary": "from second"}


def test_parse_duplicate_keys_keeps_last_value():
    # json.loads behavior: duplicate keys → last wins. Confirm the parser
    # does not introduce surprises here.
    text = '{"summary": "first", "summary": "last"}'
    assert DocumentationGenerator._parse_ai_response(text) == {"summary": "last"}


def test_parse_recursion_error_is_caught():
    # Deeply nested object — exceeds Python's recursion limit. Parser must
    # return {} rather than propagating RecursionError.
    depth = 5000
    deep = "{\"a\":" * depth + "1" + "}" * depth
    # Fits within _MAX_AI_RESPONSE_CHARS so we exercise the json.loads path.
    assert len(deep) < 1_000_000
    assert DocumentationGenerator._parse_ai_response(deep) == {}


# ---------------------------------------------------------------------------
# _normalize_ai_fields — schema fence
# ---------------------------------------------------------------------------

def test_normalize_only_keeps_expected_keys():
    obj = {key: "v" for key in _EXPECTED_KEYS}
    obj["bogus"] = "drop"
    out = _normalize_ai_fields(obj)
    assert set(out.keys()) == _EXPECTED_KEYS
    assert "bogus" not in out


def test_normalize_missing_keys_remain_missing():
    out = _normalize_ai_fields({"summary": "x"})
    assert out == {"summary": "x"}


# ---------------------------------------------------------------------------
# _coerce_str_list — list coercion for componentsModified / filesTouched
# ---------------------------------------------------------------------------

def test_coerce_str_list_from_list():
    assert _coerce_str_list(["a", "b", ""]) == ["a", "b"]


def test_coerce_str_list_from_mixed_types():
    assert _coerce_str_list(["a", 42, None, " "]) == ["a", "42"]


def test_coerce_str_list_from_string():
    assert _coerce_str_list("solo") == ["solo"]


def test_coerce_str_list_from_none():
    assert _coerce_str_list(None) == []


def test_coerce_str_list_from_empty_list():
    assert _coerce_str_list([]) == []


def test_coerce_str_list_from_empty_string():
    assert _coerce_str_list("") == []


# ---------------------------------------------------------------------------
# _coerce_int — int coercion for linesAdded/linesRemoved
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,fallback,expected", [
    (10, 0, 10),
    (None, 7, 7),
    ("42", 0, 42),
    ("+5 lines", 0, 5),
    ("-3", 0, -3),
    ("none", 99, 99),
    (True, 5, 5),     # bool excluded — fallback wins
    (False, 5, 5),
    (3.7, 5, 5),      # floats not accepted — fallback wins
])
def test_coerce_int_variants(value, fallback, expected):
    assert _coerce_int(value, fallback) == expected


# ---------------------------------------------------------------------------
# _truncate — defensive cap on free-text fields
# ---------------------------------------------------------------------------

def test_truncate_under_limit_passthrough():
    assert _truncate("hello", 100) == "hello"


def test_truncate_over_limit_appends_marker_within_budget():
    out = _truncate("x" * 50, 30)
    # Final length stays inside the budget AND ends with the marker
    assert len(out) == 30
    assert out.endswith("[truncated]")


def test_truncate_limit_smaller_than_marker_returns_hard_cut():
    # When the limit is smaller than the marker, we cannot fit the marker —
    # fall back to a plain hard cut at the limit.
    out = _truncate("x" * 50, 5)
    assert out == "xxxxx"


def test_truncate_none_returns_none():
    assert _truncate(None, 10) is None


def test_truncate_non_string_coerced():
    assert _truncate(12345, 100) == "12345"


# ---------------------------------------------------------------------------
# _safe_json_loads — used by RAG indexing path
# ---------------------------------------------------------------------------

def test_safe_json_loads_valid():
    assert _safe_json_loads('["a", "b"]', []) == ["a", "b"]


def test_safe_json_loads_invalid_returns_default():
    assert _safe_json_loads("not json", ["fallback"]) == ["fallback"]


def test_safe_json_loads_empty_returns_default():
    assert _safe_json_loads("", []) == []
    assert _safe_json_loads(None, {"k": 1}) == {"k": 1}
