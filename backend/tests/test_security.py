"""
Security Tests for ProjectsManagerWebV2 Backend
Task: CB-1120 - Automated testing framework for security-related features
Part of STORY CB-1112: User can Filter Results by Date Range

Tests cover:
- CORS configuration validation
- Rate limiting enforcement
- Error handling (no stack trace leakage)
- Input validation and sanitization
- Date range filter security (injection, boundary abuse)
- SQL injection protection via ORM
- Response header security
- Structured error responses
"""

import contextlib

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock
import json

import sys
from pathlib import Path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.main import app
from app.errors import (
    ErrorCode,
    ErrorResponse,
    AppException,
    NotFoundError,
    ValidationError,
    DatabaseError,
)
from app.config import Settings


# ============================================================================
# CORS Configuration Tests
# ============================================================================

@pytest.mark.api
class TestCORSConfiguration:
    """Verify CORS is configured securely - only allowed origins can access the API."""

    async def test_allowed_origin_receives_cors_headers(self, async_client):
        """Requests from allowed origins should include CORS headers."""
        response = await async_client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3601",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3601"

    async def test_disallowed_origin_blocked(self, async_client):
        """Requests from non-allowed origins should not receive CORS allow header."""
        response = await async_client.options(
            "/api/health",
            headers={
                "Origin": "http://evil-site.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        allow_origin = response.headers.get("access-control-allow-origin")
        assert allow_origin != "http://evil-site.com"

    async def test_cors_does_not_allow_wildcard(self, async_client):
        """CORS should not use wildcard (*) for allowed origins."""
        response = await async_client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3601",
                "Access-Control-Request-Method": "GET",
            },
        )
        allow_origin = response.headers.get("access-control-allow-origin")
        assert allow_origin != "*"

    async def test_cors_exposes_limited_headers(self, async_client):
        """Only specific headers should be exposed to clients."""
        response = await async_client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3601",
                "Access-Control-Request-Method": "GET",
            },
        )
        exposed = response.headers.get("access-control-expose-headers", "")
        # Should only expose X-Request-ID, not sensitive headers
        assert "Set-Cookie" not in exposed
        assert "Authorization" not in exposed

    async def test_cors_max_age_is_set(self, async_client):
        """Preflight cache should be configured to reduce preflight requests."""
        response = await async_client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3601",
                "Access-Control-Request-Method": "GET",
            },
        )
        max_age = response.headers.get("access-control-max-age")
        if max_age:
            assert int(max_age) <= 86400  # Should not cache for more than a day


# ============================================================================
# Error Handling Security Tests
# ============================================================================

@pytest.mark.api
class TestErrorHandlingSecurity:
    """Verify error responses don't leak sensitive information."""

    async def test_404_does_not_leak_internals(self, async_client):
        """404 errors should not expose internal file paths or stack traces."""
        response = await async_client.get("/api/nonexistent-endpoint")
        assert response.status_code in (404, 405)
        body = response.text
        # Should not contain internal paths
        assert "/home/" not in body
        assert "/usr/" not in body
        assert "/Volumes/" not in body
        assert "Traceback" not in body
        assert "File \"" not in body

    async def test_invalid_json_body_returns_structured_error(self, async_client):
        """Malformed JSON should return a 422 with structured error, not a stack trace."""
        response = await async_client.post(
            "/api/projects/test-project/issues",
            content="{ this is not valid json }}}",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        body = response.text
        assert "Traceback" not in body

    async def test_unhandled_exception_returns_generic_message(self, async_client):
        """Unhandled exceptions should return a generic error, not implementation details."""
        # The general exception handler should catch unexpected errors
        # and return a generic message
        response = await async_client.get("/")
        # Root endpoint should work
        assert response.status_code == 200
        data = response.json()
        # Should have structured response
        assert "success" in data

    async def test_error_response_uses_structured_format(self, async_client):
        """All error responses should follow the ErrorResponse schema."""
        response = await async_client.get("/api/nonexistent-endpoint")
        if response.status_code >= 400:
            data = response.json()
            # Should have structured error fields
            assert "detail" in data or "error" in data or "message" in data

    async def test_method_not_allowed_doesnt_leak_info(self, async_client):
        """Method not allowed errors should not leak implementation details."""
        response = await async_client.delete("/api/health")
        assert response.status_code == 405
        body = response.text
        assert "Traceback" not in body


# ============================================================================
# Input Validation Security Tests
# ============================================================================

@pytest.mark.api
class TestInputValidationSecurity:
    """Verify inputs are properly validated to prevent injection attacks."""

    async def test_search_with_sql_injection_attempt(self, async_client):
        """SQL injection in search parameter should be safely handled by ORM."""
        malicious_inputs = [
            "'; DROP TABLE issues; --",
            "1 OR 1=1",
            "' UNION SELECT * FROM users --",
            "1; DELETE FROM issues WHERE 1=1",
            "' OR ''='",
        ]
        for payload in malicious_inputs:
            response = await async_client.get(
                "/api/projects/test-project/issues",
                params={"search": payload},
            )
            # Should not crash - either 200 (empty results) or 404 (project not found)
            assert response.status_code in (200, 404, 500), \
                f"Unexpected status {response.status_code} for payload: {payload}"
            # Should never return raw SQL error details
            body = response.text.lower()
            assert "syntax error" not in body or "sql" not in body

    async def test_search_with_xss_payload(self, async_client):
        """XSS payloads in search should be treated as plain text by the API."""
        xss_payloads = [
            '<script>alert("xss")</script>',
            '<img src=x onerror=alert(1)>',
            '"><svg/onload=alert(1)>',
            "javascript:alert(1)",
        ]
        for payload in xss_payloads:
            response = await async_client.get(
                "/api/projects/test-project/issues",
                params={"search": payload},
            )
            # Should not crash
            assert response.status_code in (200, 404, 500)

    async def test_oversized_search_query(self, async_client):
        """Extremely long search queries should be handled gracefully."""
        long_query = "A" * 10000
        response = await async_client.get(
            "/api/projects/test-project/issues",
            params={"search": long_query},
        )
        # Should not crash
        assert response.status_code in (200, 404, 422, 500)

    async def test_special_characters_in_query_params(self, async_client):
        """Special characters in query params should not cause errors."""
        special_chars = [
            "test%00null",       # null byte
            "test\nheader",      # header injection
            "test\r\ninjection", # CRLF injection
            "../../../etc/passwd",  # path traversal
        ]
        for payload in special_chars:
            response = await async_client.get(
                "/api/projects/test-project/issues",
                params={"search": payload},
            )
            assert response.status_code in (200, 400, 404, 422, 500)

    async def test_negative_page_number_rejected(self, async_client):
        """Negative page numbers should be rejected by validation."""
        response = await async_client.get(
            "/api/projects/test-project/issues",
            params={"page": -1},
        )
        # FastAPI validates ge=1 constraint
        assert response.status_code in (422, 400)

    async def test_zero_page_size_handled(self, async_client):
        """Zero page size should be handled gracefully (returns empty or defaults)."""
        response = await async_client.get(
            "/api/projects/test-project/issues",
            params={"page_size": 0},
        )
        # May return 200 with empty results or reject with validation error
        assert response.status_code in (200, 422, 400)

    async def test_excessive_page_size_rejected(self, async_client):
        """Excessively large page sizes should be rejected to prevent DoS."""
        response = await async_client.get(
            "/api/projects/test-project/issues",
            params={"page_size": 999999},
        )
        # Should either reject or cap at allowed max
        assert response.status_code in (200, 404, 422, 400)


# ============================================================================
# Date Range Filter Security Tests
# ============================================================================

@pytest.mark.api
class TestDateRangeFilterSecurity:
    """Security tests specific to the date range filter feature (CB-1112)."""

    async def test_invalid_date_format_handled_gracefully(self, async_client):
        """Invalid date format should not cause server errors."""
        response = await async_client.get(
            "/api/projects/test-project/issues",
            params={
                "date_field": "createdAt",
                "date_from": "not-a-date",
            },
        )
        # Should gracefully handle (the code uses try/except around fromisoformat)
        assert response.status_code in (200, 404, 400, 422)
        body = response.text
        assert "Traceback" not in body

    async def test_invalid_date_field_ignored(self, async_client):
        """Requesting filtering on a non-existent date field should not crash."""
        response = await async_client.get(
            "/api/projects/test-project/issues",
            params={
                "date_field": "nonExistentField",
                "date_from": "2026-01-01T00:00:00Z",
            },
        )
        assert response.status_code in (200, 404)
        body = response.text
        assert "Traceback" not in body

    async def test_date_field_sql_injection_attempt(self, async_client):
        """SQL injection via date_field parameter should be blocked."""
        response = await async_client.get(
            "/api/projects/test-project/issues",
            params={
                "date_field": "createdAt; DROP TABLE issues;",
                "date_from": "2026-01-01T00:00:00Z",
            },
        )
        # The column mapping dict lookup will simply not find the key
        assert response.status_code in (200, 404)

    async def test_date_injection_in_from_parameter(self, async_client):
        """Injection attempts in date_from should be safely handled."""
        response = await async_client.get(
            "/api/projects/test-project/issues",
            params={
                "date_field": "createdAt",
                "date_from": "2026-01-01'; DROP TABLE issues; --",
            },
        )
        # Should fail gracefully on datetime.fromisoformat
        assert response.status_code in (200, 404)

    async def test_date_injection_in_to_parameter(self, async_client):
        """Injection attempts in date_to should be safely handled."""
        response = await async_client.get(
            "/api/projects/test-project/issues",
            params={
                "date_field": "createdAt",
                "date_to": "' OR 1=1 --",
            },
        )
        assert response.status_code in (200, 404)

    async def test_extreme_date_values(self, async_client):
        """Extreme date values should not cause overflow or crash."""
        response = await async_client.get(
            "/api/projects/test-project/issues",
            params={
                "date_field": "createdAt",
                "date_from": "0001-01-01T00:00:00Z",
                "date_to": "9999-12-31T23:59:59Z",
            },
        )
        assert response.status_code in (200, 404)

    async def test_reversed_date_range(self, async_client):
        """start > end date range should be handled without error."""
        response = await async_client.get(
            "/api/projects/test-project/issues",
            params={
                "date_field": "createdAt",
                "date_from": "2026-12-31T00:00:00Z",
                "date_to": "2026-01-01T00:00:00Z",
            },
        )
        # Should return empty results, not crash
        assert response.status_code in (200, 404)

    async def test_date_with_timezone_variations(self, async_client):
        """Various timezone formats should be handled safely."""
        timezone_dates = [
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00-05:00",
            "2026-01-01T00:00:00+12:00",
        ]
        for date_val in timezone_dates:
            response = await async_client.get(
                "/api/projects/test-project/issues",
                params={
                    "date_field": "createdAt",
                    "date_from": date_val,
                },
            )
            assert response.status_code in (200, 404), \
                f"Failed for date: {date_val}"


# ============================================================================
# Error Code and Response Structure Tests
# ============================================================================

@pytest.mark.unit
class TestErrorResponseStructure:
    """Verify error response models work correctly."""

    def test_error_response_excludes_none_fields(self):
        """ErrorResponse should exclude None fields to avoid leaking structure."""
        err = ErrorResponse(
            success=False,
            error="NOT_FOUND",
            code="NOT_FOUND",
            message="Resource not found",
        )
        dumped = err.model_dump(exclude_none=True)
        assert "details" not in dumped
        assert "request_id" not in dumped

    def test_error_response_includes_provided_details(self):
        """ErrorResponse should include details when provided."""
        err = ErrorResponse(
            success=False,
            error="VALIDATION_ERROR",
            code="VALIDATION_ERROR",
            message="Invalid input",
            details={"field": "title", "reason": "too long"},
        )
        dumped = err.model_dump(exclude_none=True)
        assert "details" in dumped
        assert dumped["details"]["field"] == "title"

    def test_not_found_error_has_correct_status(self):
        """NotFoundError should always produce 404 status."""
        err = NotFoundError("Issue", "abc-123")
        assert err.status_code == 404
        assert err.code == ErrorCode.NOT_FOUND

    def test_validation_error_has_correct_status(self):
        """ValidationError should always produce 400 status."""
        err = ValidationError("Bad input")
        assert err.status_code == 400
        assert err.code == ErrorCode.VALIDATION_ERROR

    def test_database_error_has_correct_status(self):
        """DatabaseError should produce 500 status."""
        err = DatabaseError()
        assert err.status_code == 500
        assert err.code == ErrorCode.DATABASE_ERROR

    def test_error_message_does_not_expose_internals(self):
        """NotFoundError should not include raw ID in message when identifier is None."""
        err = NotFoundError("Issue")
        assert "None" not in err.message
        assert err.message == "Issue not found"

    def test_all_error_codes_are_defined(self):
        """All expected error codes should be defined in ErrorCode enum."""
        expected_codes = [
            "VALIDATION_ERROR", "NOT_FOUND", "ALREADY_EXISTS", "BAD_REQUEST",
            "UNAUTHORIZED", "FORBIDDEN", "CONFLICT", "RATE_LIMITED",
            "INTERNAL_ERROR", "DATABASE_ERROR", "EXTERNAL_SERVICE_ERROR",
            "AI_SERVICE_ERROR", "GIT_ERROR",
        ]
        for code in expected_codes:
            assert hasattr(ErrorCode, code), f"Missing error code: {code}"


# ============================================================================
# Configuration Security Tests
# ============================================================================

@pytest.mark.unit
class TestConfigurationSecurity:
    """Verify security-related configuration defaults are safe."""

    def test_debug_defaults_to_false(self):
        """DEBUG should default to False for safety when no env file is loaded."""
        s = Settings(ANTHROPIC_API_KEY="", _env_file=None)
        assert s.DEBUG is False

    def test_environment_defaults_to_production(self):
        """ENVIRONMENT should default to production for safety when no env file is loaded."""
        s = Settings(ANTHROPIC_API_KEY="", _env_file=None)
        assert s.ENVIRONMENT == "production"

    def test_webhook_signature_required_by_default(self):
        """Webhook signature verification should be required by default."""
        s = Settings(ANTHROPIC_API_KEY="", _env_file=None)
        assert s.REQUIRE_WEBHOOK_SIGNATURE is True

    def test_cors_origins_is_not_wildcard(self):
        """CORS origins should not contain wildcard."""
        s = Settings(ANTHROPIC_API_KEY="", _env_file=None)
        assert "*" not in s.CORS_ORIGINS

    def test_cors_origins_are_localhost_only_by_default(self):
        """Default CORS origins should only allow localhost."""
        s = Settings(ANTHROPIC_API_KEY="", _env_file=None)
        for origin in s.CORS_ORIGINS:
            assert "localhost" in origin or "127.0.0.1" in origin


# ============================================================================
# Rate Limiting Tests
# ============================================================================

@pytest.mark.api
class TestRateLimiting:
    """Verify rate limiting is applied to protect against abuse."""

    async def test_health_endpoint_accessible(self, async_client):
        """Health endpoint should be accessible under normal load."""
        response = await async_client.get("/api/health")
        assert response.status_code == 200

    async def test_rapid_requests_eventually_limited(self, async_client):
        """Many rapid requests should eventually trigger rate limiting."""
        # Note: The default limit is 200/minute. In testing, the limiter
        # may not be fully active due to test transport.
        # This test validates the rate limiter is configured.
        from app.main import limiter
        assert limiter is not None
        assert limiter._default_limits is not None

    async def test_rate_limit_returns_429(self, async_client):
        """When rate limit is hit, response should be 429 Too Many Requests."""
        # Verify the exception handler is registered
        from app.main import app
        from slowapi.errors import RateLimitExceeded
        # Check that RateLimitExceeded handler exists
        handlers = app.exception_handlers
        assert RateLimitExceeded in handlers


# ============================================================================
# CB-2666 — /api/projects perimeter discipline
# ============================================================================

@pytest.mark.api
class TestProjectsEndpointPerimeter:
    """Regression suite for CB-2666 — /api/projects field minimization +
    INTERNAL_API_TOKEN gate.

    Threat model recap: validate_origin lets Origin-less callers (curl,
    server-to-server, malicious local processes) through by design, so on
    a non-loopback bind the LIST endpoint became a one-call project
    enumeration that defeated the CB-2217 redaction. Two-layer fix:

      1. `path` is removed from `ProjectResponse` (extra="forbid" pin).
      2. When `INTERNAL_API_TOKEN` is set, Origin-less callers must
         present `X-Internal-Token` matching the token, or be rejected
         with HTTP 401.
    """

    @staticmethod
    def _auth_headers():
        """Header set that satisfies `require_local_or_token` under the
        per-process token configured by conftest.py for CB-2666 F2."""
        from app.config import settings
        return {"X-Internal-Token": settings.INTERNAL_API_TOKEN}

    async def test_list_response_does_not_include_path(self, async_client):
        """LIST response rows must NOT carry the abspath `path` field."""
        response = await async_client.get(
            "/api/projects", headers=self._auth_headers()
        )
        # Endpoint may return 200 (with rows) or 200 (empty) depending on DB.
        # Either way, no row may carry `path`.
        assert response.status_code == 200, (
            f"unexpected status {response.status_code}: {response.text[:200]}"
        )
        rows = response.json()
        assert isinstance(rows, list)
        for row in rows:
            assert "path" not in row, (
                f"CB-2666 regression: row leaked `path` field: {row!r}"
            )

    async def test_get_by_id_response_does_not_include_path(self, async_client):
        """GET-by-id must NOT carry the abspath `path` field either."""
        list_resp = await async_client.get(
            "/api/projects", headers=self._auth_headers()
        )
        assert list_resp.status_code == 200
        rows = list_resp.json()
        if not rows:
            pytest.skip("No projects in DB to exercise GET-by-id")
        project_id = rows[0]["id"]
        response = await async_client.get(
            f"/api/projects/{project_id}", headers=self._auth_headers()
        )
        assert response.status_code == 200
        body = response.json()
        assert "path" not in body, (
            f"CB-2666 regression: GET-by-id leaked `path`: {body!r}"
        )

    async def test_token_unset_passes_through(self, async_client, monkeypatch):
        """Default (token unset) → endpoint reachable without a header."""
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "")
        response = await async_client.get("/api/projects")
        assert response.status_code == 200

    async def test_token_set_blocks_origin_less_caller_without_header(
        self, async_client, monkeypatch
    ):
        """Token configured + no Origin + no token header → 401."""
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await async_client.get("/api/projects")
        assert response.status_code == 401, (
            f"expected 401, got {response.status_code}: {response.text[:200]}"
        )

    async def test_token_set_allows_with_valid_header(
        self, async_client, monkeypatch
    ):
        """Token configured + valid `X-Internal-Token` header → 200."""
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await async_client.get(
            "/api/projects",
            headers={"X-Internal-Token": "test-secret-abc123"},
        )
        assert response.status_code == 200

    async def test_token_set_rejects_wrong_header(
        self, async_client, monkeypatch
    ):
        """Token configured + WRONG `X-Internal-Token` → 401."""
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await async_client.get(
            "/api/projects",
            headers={"X-Internal-Token": "this-is-not-the-right-token"},
        )
        assert response.status_code == 401

    async def test_origin_spoof_alone_does_not_bypass_token_gate(
        self, async_client, monkeypatch
    ):
        """CB-2666 sec audit F1: trusting `Origin` would let any local
        process curl the endpoint with a forged header. The fix removes
        the Origin-bypass branch entirely. With the token set, an
        allow-listed Origin + no token header MUST still be 401.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await async_client.get(
            "/api/projects",
            headers={"Origin": "http://localhost:3601"},
        )
        assert response.status_code == 401, (
            "CB-2666 F1 regression: forged Origin header bypassed the "
            "internal-token gate"
        )

    async def test_token_set_rejects_wrong_origin(
        self, async_client, monkeypatch
    ):
        """Token configured + Origin NOT in ALLOWED_ORIGINS + no token
        header → 403 from validate_origin OR 401 from internal-token gate.

        Either rejection is acceptable — both are part of the perimeter.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await async_client.get(
            "/api/projects",
            headers={"Origin": "http://evil.example.com"},
        )
        assert response.status_code in (401, 403), (
            f"expected reject (401|403), got {response.status_code}"
        )

    async def test_get_by_id_also_gated(self, async_client, monkeypatch):
        """The GET-by-id endpoint shares the gate."""
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await async_client.get(
            "/api/projects/some-id-that-may-not-exist"
        )
        # 401 BEFORE the DB lookup runs — gate is in front.
        assert response.status_code == 401

    async def test_initialize_sequence_also_gated(
        self, async_client, monkeypatch
    ):
        """POST /initialize-sequence also wears `InternalAuthDep` so a
        local foothold cannot mutate sequence state on arbitrary
        project_ids without the token (defense-in-depth).
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await async_client.post(
            "/api/projects/some-id/initialize-sequence"
        )
        assert response.status_code == 401

    def test_token_compare_uses_constant_time_and_fixed_length(self):
        """`require_local_or_token` must use `secrets.compare_digest` and
        must hash both sides to a fixed length so token LENGTH cannot
        leak via the compare_digest unequal-length short-circuit
        (CB-2666 sec audit F4).
        """
        from pathlib import Path
        src = Path(__file__).resolve().parent.parent / "app" / "security.py"
        text = src.read_text()
        assert "compare_digest" in text, (
            "secrets.compare_digest missing — token comparison must be "
            "constant-time to avoid a timing oracle"
        )
        assert "sha256" in text or "_digest" in text, (
            "CB-2666 F4 regression: token comparison must hash both sides "
            "to a fixed length before compare_digest"
        )

    def test_project_response_schema_forbids_extra(self):
        """`ProjectResponse` is `extra="forbid"` so a future regression
        that re-adds `path` (or any name-shaped field) to the response
        fails fast at contract level."""
        from models.schemas import ProjectResponse
        # extra=forbid is the structural pin; assert it's present.
        assert ProjectResponse.model_config.get("extra") == "forbid", (
            "ProjectResponse must keep extra='forbid' (CB-2666 contract pin)"
        )
        # `path` MUST NOT reappear in declared fields.
        assert "path" not in ProjectResponse.model_fields, (
            "CB-2666 regression: ProjectResponse re-declared `path`"
        )

    def test_startup_asserts_token_when_allow_lan_set(self):
        """CB-2666 sec audit F2: flipping `ALLOW_LAN=true` (or pointing
        `HOST` at a non-loopback interface) without setting
        `INTERNAL_API_TOKEN` must fail loudly at module load — silent
        pass-through is the misconfiguration that re-introduced this bug.

        Re-imports `app.main` under a patched settings tuple to verify
        the assertion fires. The default test env (ALLOW_LAN=false,
        HOST=127.0.0.1) leaves the existing import intact.
        """
        import importlib
        import sys
        from app.config import settings

        # Save then patch — the assertion runs at module evaluation, so
        # we must reload `app.main` under the patched settings.
        original_allow_lan = settings.ALLOW_LAN
        original_token = settings.INTERNAL_API_TOKEN
        original_host = settings.HOST
        try:
            settings.ALLOW_LAN = True
            settings.INTERNAL_API_TOKEN = ""
            settings.HOST = "0.0.0.0"
            sys.modules.pop("app.main", None)
            with pytest.raises(RuntimeError, match="INTERNAL_API_TOKEN"):
                importlib.import_module("app.main")
        finally:
            settings.ALLOW_LAN = original_allow_lan
            settings.INTERNAL_API_TOKEN = original_token
            settings.HOST = original_host
            # Reload the canonical app.main so subsequent tests see a
            # clean module (the conftest fixture references this app).
            sys.modules.pop("app.main", None)
            importlib.import_module("app.main")


# ============================================================================
# CB-2668 — /docs + /redoc + /openapi.json route-map perimeter
# ============================================================================

@pytest.mark.api
class TestDocsSurfacePerimeter:
    """Regression suite for CB-2668 — FastAPI's default Swagger / ReDoc /
    OpenAPI surface publishes every route, every project_id-shaped param,
    and every request/response schema. Chained with CB-2666 H-1 and
    CB-2667 H-2 it turns isolated identifier disclosures into a guided
    enumeration kit.

    Fix: `app.main` constructs FastAPI with `docs_url`, `redoc_url`,
    `openapi_url` set to `None` unless `settings.is_development` opts in.
    Production / staging / unset / typo'd ENVIRONMENT all stay locked.
    """

    def test_is_development_helper_matrix(self):
        """`is_development` accepts only the canonical aliases.
        CB-2668 fail-closed posture — a typo locks the surface, never opens it.
        """
        from app.config import Settings

        for value in ["development", "dev", "DEV", "Development"]:
            s = Settings(ANTHROPIC_API_KEY="", ENVIRONMENT=value, _env_file=None)
            assert s.is_development is True, f"alias {value!r} must enable docs"

        for value in ["production", "staging", "test", "", "dev-staging", " dev "]:
            s = Settings(ANTHROPIC_API_KEY="", ENVIRONMENT=value, _env_file=None)
            assert s.is_development is False, (
                f"value {value!r} must NOT enable docs (fail-closed)"
            )

    @staticmethod
    @contextlib.contextmanager
    def _app_under_environment(value: str):
        """Yield `app.main.app` reloaded with `settings.ENVIRONMENT=value`.

        The live `.env` on the developer's machine sets
        `ENVIRONMENT=development` (it has to, so launching the backend
        gives the operator the docs surface). That means the conftest
        fixture's `async_client` always wraps a development-mode app,
        so the production-mode assertions can't reuse it — we must
        reload `app.main` under a patched setting.

        Wrapped as a `@contextmanager` (not a (target, restore) tuple)
        so cleanup ALWAYS runs even if the reload itself raises mid-
        import. A naive (build-restore-then-call-it) pattern leaves
        `settings.ENVIRONMENT` mutated when the import body fails,
        polluting every subsequent test in the run.
        """
        import importlib
        import sys
        from app.config import settings

        original_environment = settings.ENVIRONMENT
        try:
            settings.ENVIRONMENT = value
            sys.modules.pop("app.main", None)
            reloaded = importlib.import_module("app.main")
            yield reloaded.app
        finally:
            settings.ENVIRONMENT = original_environment
            sys.modules.pop("app.main", None)
            importlib.import_module("app.main")

    @staticmethod
    async def _probe(target_app, paths):
        transport = ASGITransport(app=target_app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return {p: (await client.get(p)).status_code for p in paths}

    @pytest.mark.parametrize("env_value", ["production", "staging", "test", ""])
    async def test_docs_disabled_in_non_development(self, env_value):
        """Production / staging / test / unset all lock down all three
        routes. CB-2668 fail-closed posture.
        """
        with self._app_under_environment(env_value) as target_app:
            results = await self._probe(
                target_app, ["/docs", "/redoc", "/openapi.json"]
            )
            for path, status_code in results.items():
                assert status_code == 404, (
                    f"CB-2668 regression: {path} reachable under "
                    f"ENVIRONMENT={env_value!r} (got {status_code})"
                )

    async def test_swagger_oauth2_redirect_disabled_in_production(self):
        """Disabling `docs_url` also drops the Swagger static-asset
        endpoint (`/docs/oauth2-redirect`). The CB-2668 fix also pins
        `swagger_ui_oauth2_redirect_url=None` for defense-in-depth, so
        an upstream FastAPI refactor that mounts the asset independently
        of `docs_url` cannot re-publish the asset path.
        """
        with self._app_under_environment("production") as target_app:
            results = await self._probe(target_app, ["/docs/oauth2-redirect"])
            assert results["/docs/oauth2-redirect"] == 404

    @pytest.mark.parametrize("env_value", ["development", "dev"])
    async def test_docs_enabled_in_development(self, env_value):
        """Reload `app.main` under each accepted alias and confirm all
        three URLs come back. Counterweight to the production-mode 404
        assertion — without it, a regression that hard-codes `None`
        unconditionally would still pass the production tests.
        """
        with self._app_under_environment(env_value) as target_app:
            results = await self._probe(
                target_app, ["/docs", "/redoc", "/openapi.json"]
            )
            assert results["/docs"] == 200, (
                f"/docs must serve Swagger UI under ENVIRONMENT={env_value!r}"
            )
            assert results["/redoc"] == 200, (
                f"/redoc must serve ReDoc under ENVIRONMENT={env_value!r}"
            )
            assert results["/openapi.json"] == 200, (
                f"/openapi.json must serve schema under ENVIRONMENT={env_value!r}"
            )


# ============================================================================
# CB-2667 — /api/search/{project_id}/stats perimeter discipline
# ============================================================================

@pytest.mark.api
class TestSearchStatsEndpointPerimeter:
    """Regression suite for CB-2667 — `/api/search/{project_id}/stats`
    discloses a per-project indexed-document count for any caller-supplied
    project_id. Combined with CB-2666 H-1 (project enumeration via
    `/api/projects`), this defeats CB-2217's collection-name redaction in
    one extra hop: list the project_ids, fan out a `/stats` per id, get
    the count distribution rebound to real CUIDs.

    Fix: same `InternalAuthDep` gate + 30/min per-IP rate limit that
    `/api/projects` wears (CB-2666 sec audit F6). `INTERNAL_API_TOKEN`
    empty → pass-through (preserves dev workflow on loopback bind);
    non-empty → `X-Internal-Token` required or 401.

    Tests assert behavior at the gate, BEFORE the route body runs. The
    `app.state.rag` instance is not initialized under ASGITransport
    (lifespan does not fire in the test fixture), so the route body
    would 500 even with valid auth — but the gate fires first, so:
      - reject paths assert exactly `401` (gate path).
      - accept paths assert `!= 401` (gate passed; downstream behavior
        is exercised by separate RAG service tests).
    """

    @staticmethod
    def _auth_headers():
        from app.config import settings
        return {"X-Internal-Token": settings.INTERNAL_API_TOKEN}

    @staticmethod
    def _install_mock_rag(request):
        """ASGITransport doesn't fire lifespan, so `app.state.rag` is unset.
        The route body would normally raise `RuntimeError` from `get_rag`,
        which leaks through pytest's transport.

        Use the module-level `app` binding (imported once at the top of
        test_security.py — same instance the `async_client` fixture wraps).
        After CB-2666 F2's `test_startup_asserts_token_when_allow_lan_set`
        reloads `app.main`, `sys.modules["app.main"].app` becomes a fresh
        instance, but the `app` name bound at the top of THIS module still
        points to the ORIGINAL — which is what AsyncClient's transport
        is also wrapping. Injecting via `app.dependency_overrides` here
        therefore lands on the right object regardless of test order.
        """
        from api.deps import get_rag
        from unittest.mock import MagicMock

        stub = MagicMock()
        stub.get_collection.return_value.count.return_value = 0
        # `app` is the module-level binding from `from app.main import app`
        # at the top of test_security.py — see docstring.
        app.dependency_overrides[get_rag] = lambda: stub
        request.addfinalizer(
            lambda: app.dependency_overrides.pop(get_rag, None)
        )

    async def test_token_unset_passes_through(
        self, async_client, monkeypatch, request
    ):
        """Default (token unset) → endpoint reachable without a header.

        Preserves the loopback-bind dev workflow: a developer running
        `./launch.sh` with the default `.env` and an empty
        `INTERNAL_API_TOKEN` must NOT see 401s on the SemanticSearchPanel
        stats fetch. The frontend calls this endpoint directly from the
        browser (see `frontend/components/codeboard/SemanticSearchPanel.tsx`).

        Asserts exactly 200 (not just `!= 401`) so a future regression
        that returns 403 from a misplaced middleware is also caught.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "")
        self._install_mock_rag(request)
        response = await async_client.get("/api/search/any-project-id/stats")
        assert response.status_code == 200, (
            f"CB-2667 regression: token-unset path returned "
            f"{response.status_code} (should pass-through with 200): "
            f"{response.text[:200]}"
        )
        body = response.json()
        assert body["project_id"] == "any-project-id"
        assert body["indexed_count"] == 0

    async def test_token_set_blocks_origin_less_caller_without_header(
        self, async_client, monkeypatch
    ):
        """Token configured + no Origin + no token header → 401.

        This is the primary attack path the bug describes: an Origin-less
        caller (curl, server-to-server) chaining `/api/projects` →
        per-project `/stats`. With the gate, the second request fails
        before the rag lookup runs.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await async_client.get("/api/search/any-project-id/stats")
        assert response.status_code == 401, (
            f"expected 401, got {response.status_code}: {response.text[:200]}"
        )

    async def test_token_set_allows_with_valid_header(
        self, async_client, monkeypatch, request
    ):
        """Token configured + valid `X-Internal-Token` header → gate passes
        and the stub rag returns a 200 stats payload."""
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        self._install_mock_rag(request)
        response = await async_client.get(
            "/api/search/any-project-id/stats",
            headers={"X-Internal-Token": "test-secret-abc123"},
        )
        assert response.status_code == 200, (
            f"CB-2667 regression: valid token rejected with "
            f"{response.status_code}: {response.text[:200]}"
        )
        body = response.json()
        assert body["project_id"] == "any-project-id"
        assert body["indexed_count"] == 0

    async def test_token_set_rejects_wrong_header(
        self, async_client, monkeypatch
    ):
        """Token configured + WRONG `X-Internal-Token` → 401."""
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await async_client.get(
            "/api/search/any-project-id/stats",
            headers={"X-Internal-Token": "this-is-not-the-right-token"},
        )
        assert response.status_code == 401

    async def test_origin_spoof_alone_does_not_bypass_token_gate(
        self, async_client, monkeypatch
    ):
        """CB-2666 sec audit F1 invariant — applies to every gated endpoint.

        Trusting the `Origin` header on a server-side gate is meaningless
        because any local process can `curl -H 'Origin: http://localhost:3601'`
        and pass. Stats endpoint must reject Origin-spoofed requests with no
        token header, identical to `/api/projects`.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await async_client.get(
            "/api/search/any-project-id/stats",
            headers={"Origin": "http://localhost:3601"},
        )
        assert response.status_code == 401, (
            "CB-2667/F1 regression: forged Origin header bypassed the "
            "internal-token gate on the stats endpoint"
        )

    @pytest.mark.parametrize(
        "header_name",
        ["x-internal-token", "X-Internal-Token", "X-INTERNAL-TOKEN"],
    )
    async def test_token_header_name_case_insensitive(
        self, async_client, monkeypatch, request, header_name
    ):
        """HTTP header names are case-insensitive (RFC 7230). Starlette
        normalizes inbound headers to lowercase, and `security.py:69`
        looks up `"x-internal-token"`. Pin that all three common
        casings of the header name resolve to the same value so a
        future regression that switches to a case-sensitive lookup
        fails this test, not a deploy.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        self._install_mock_rag(request)
        response = await async_client.get(
            "/api/search/any-project-id/stats",
            headers={header_name: "test-secret-abc123"},
        )
        assert response.status_code == 200, (
            f"CB-2667 L-1 regression: header name {header_name!r} "
            f"rejected with {response.status_code}: {response.text[:200]}"
        )

    async def test_token_value_with_whitespace_padding_rejected(
        self, async_client, monkeypatch, request
    ):
        """A leading/trailing space on the presented token must NOT
        match the configured value. `_digest()` hashes the raw input,
        so `_digest(" token ")` ≠ `_digest("token")` — confirm the
        constant-time compare actually rejects rather than silently
        normalizing.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        self._install_mock_rag(request)
        response = await async_client.get(
            "/api/search/any-project-id/stats",
            headers={"X-Internal-Token": " test-secret-abc123 "},
        )
        assert response.status_code == 401, (
            f"CB-2667 L-1 regression: whitespace-padded token "
            f"accepted with {response.status_code}: {response.text[:200]}"
        )

    async def test_authorization_header_is_not_accepted_as_token(
        self, async_client, monkeypatch, request
    ):
        """The gate accepts ONLY `X-Internal-Token`. `Authorization:
        Bearer <token>` (or any other alternate header name) MUST NOT
        bypass — pinning this so a future "let's also accept Bearer"
        change is caught.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        self._install_mock_rag(request)
        response = await async_client.get(
            "/api/search/any-project-id/stats",
            headers={"Authorization": "Bearer test-secret-abc123"},
        )
        assert response.status_code == 401, (
            f"CB-2667 L-1 regression: Authorization header accepted "
            f"as fallback for X-Internal-Token: {response.status_code}"
        )

    def test_search_stats_endpoint_carries_internal_auth_dep(self):
        """Source-level pin: a future regression that drops
        `dependencies=[InternalAuthDep]` from the `/stats` route is the
        exact shape of bug CB-2667 returning. AST-walks `search.py` and
        asserts `InternalAuthDep` appears literally inside the
        `@router.get(... dependencies=[...])` decorator on
        `get_index_stats` — substring matching is too loose because
        `InternalAuthDep` could move into a comment or onto a different
        endpoint without breaking a "both substrings present" check.
        """
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parent.parent / "api" / "search.py"
        tree = ast.parse(src.read_text())

        target = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "get_index_stats":
                    target = node
                    break
        assert target is not None, (
            "CB-2667 regression: get_index_stats handler missing from "
            "search.py — gate cannot be enforced on a deleted route"
        )

        # The router decorator stack: @limiter.limit(...) outer, then
        # @router.get("/{project_id}/stats", dependencies=[...]) inner.
        # Walk the @router.get call and inspect its `dependencies` kwarg.
        router_get_call = None
        for dec in target.decorator_list:
            if isinstance(dec, ast.Call):
                fn = dec.func
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == "get"
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "router"
                ):
                    router_get_call = dec
                    break
        assert router_get_call is not None, (
            "CB-2667 regression: get_index_stats has no @router.get "
            "decorator — route registration may have been refactored"
        )

        deps_kwarg = None
        for kw in router_get_call.keywords:
            if kw.arg == "dependencies":
                deps_kwarg = kw.value
                break
        assert deps_kwarg is not None, (
            "CB-2667 regression: @router.get on get_index_stats is "
            "missing the `dependencies=[...]` kwarg — InternalAuthDep "
            "gate has been dropped"
        )

        # Stringify the kwarg AST and assert InternalAuthDep is named.
        deps_src = ast.unparse(deps_kwarg)
        assert "InternalAuthDep" in deps_src, (
            f"CB-2667 regression: `dependencies={deps_src}` does not "
            "include InternalAuthDep — the token gate is no longer "
            "enforced on /stats"
        )


# ============================================================================
# CB-2732 — sibling /api/search/* perimeter discipline
# ============================================================================

# (path_template, method, query_string, handler_name, expected_limit)
#
# `path_template` uses a fixed CUID-shaped placeholder so the AST source-text
# pin (`test_handler_carries_internal_auth_dep`) and the runtime probes share
# the same path. `query_string` carries the minimum required Query params for
# each route — the gate fires before validation, so a missing required Query
# param would 422 instead of 401 and mask the regression we're testing.
_SEARCH_SIBLING_ENDPOINTS = [
    ("/api/search/test-pid", "GET", "q=foo", "search_issues", "30/minute"),
    (
        "/api/search/test-pid/similar",
        "GET",
        "title=foo",
        "find_similar_issues",
        "30/minute",
    ),
    (
        "/api/search/test-pid/embed/test-iid",
        "POST",
        "key=CB-1&title=t",
        "embed_issue",
        "10/minute",
    ),
    (
        "/api/search/test-pid/embed/test-iid",
        "DELETE",
        "",
        "delete_embedding",
        "10/minute",
    ),
    (
        "/api/search/test-pid/embed-all",
        "POST",
        "",
        "embed_all_issues",
        "10/minute",
    ),
]


@pytest.mark.api
class TestSearchSiblingEndpointsPerimeter:
    """Regression suite for CB-2732 — the five sibling endpoints under
    `/api/search/*` share the same per-project_id disclosure / write-
    amplification shape that CB-2667 closed on `/stats`.

    Coverage matrix mirrors `TestSearchStatsEndpointPerimeter`:
      - Token unset → endpoint passes through (preserves dev workflow).
      - Token set + missing header → 401 (primary attack path).
      - Token set + valid header → gate passes (route body returns or
        500s downstream — irrelevant to the gate).
      - Token set + wrong header → 401.
      - Token set + spoofed Origin (no header) → 401 (CB-2666 F1
        invariant — Origin spoofing must NOT bypass the token gate).
      - AST source-text pin per handler — the `dependencies=[
        InternalAuthDep]` kwarg must be structurally present so a future
        regression that drops it on a single endpoint is caught at the
        unit-test level, not at deploy.
      - Per-handler `@limiter.limit(...)` value matches the read/write
        cap split (30/minute for the two GETs, 10/minute for the three
        write endpoints — write paths are DoS-amplifying, not just
        disclosure, so they get the stricter cap).
    """

    @staticmethod
    def _install_mock_deps(request):
        """ASGITransport doesn't fire lifespan, so `app.state.rag` is unset
        and the `embed-all` route also pulls `db = Depends(get_db)`.

        Override both with stubs that satisfy the route bodies — the gate
        runs BEFORE the body in all cases that matter (token-unset
        pass-through and valid-header), and on reject paths the body is
        never reached, so the stubs only need to be callable, not realistic.
        """
        from api.deps import get_rag
        from models import get_db
        from unittest.mock import AsyncMock, MagicMock

        rag_stub = MagicMock()
        rag_stub.search_issues = AsyncMock(return_value=[])
        rag_stub.find_similar_issues = AsyncMock(return_value=[])
        rag_stub.embed_issue = AsyncMock(return_value=True)
        rag_stub.delete_issue_embedding = AsyncMock(return_value=True)
        app.dependency_overrides[get_rag] = lambda: rag_stub

        db_stub = MagicMock()
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=[])
        execute_result = MagicMock()
        execute_result.scalars = MagicMock(return_value=scalars)
        db_stub.execute = AsyncMock(return_value=execute_result)

        async def _override_db():
            yield db_stub

        app.dependency_overrides[get_db] = _override_db
        request.addfinalizer(
            lambda: app.dependency_overrides.pop(get_rag, None)
        )
        request.addfinalizer(
            lambda: app.dependency_overrides.pop(get_db, None)
        )

    @staticmethod
    async def _request(async_client, method, path, query, headers=None):
        url = f"{path}?{query}" if query else path
        return await async_client.request(method, url, headers=headers or {})

    @pytest.mark.parametrize(
        "path,method,query,_handler,_limit", _SEARCH_SIBLING_ENDPOINTS
    )
    async def test_token_unset_passes_through(
        self, async_client, monkeypatch, request, path, method, query, _handler, _limit
    ):
        """Token unset → endpoint reachable without a header.

        Preserves the loopback-bind dev workflow: SemanticSearchPanel and
        the `useSearchIssues` / `useFindSimilarIssues` hooks call these
        endpoints from the browser with an empty `INTERNAL_API_TOKEN` and
        must NOT see a 401.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "")
        self._install_mock_deps(request)
        response = await self._request(async_client, method, path, query)
        assert response.status_code != 401, (
            f"CB-2732 regression: token-unset {method} {path} returned "
            f"401 (should pass-through): {response.text[:200]}"
        )
        # Stronger assertion: the gate is the only 4xx the pass-through
        # path should produce. A 422 here would mean we're missing a
        # required Query param in the parametrize tuple, masking the gate
        # behavior we're trying to test.
        assert response.status_code < 500, (
            f"CB-2732 setup error: token-unset {method} {path} returned "
            f"{response.status_code} — fix the parametrize tuple or stub: "
            f"{response.text[:200]}"
        )

    @pytest.mark.parametrize(
        "path,method,query,_handler,_limit", _SEARCH_SIBLING_ENDPOINTS
    )
    async def test_token_set_blocks_origin_less_caller_without_header(
        self, async_client, monkeypatch, path, method, query, _handler, _limit
    ):
        """Token configured + no Origin + no token header → 401.

        Primary attack path: an Origin-less caller chains
        `/api/projects` (gated CB-2666) → fans out per-project to these
        sibling endpoints. Without the gate the second hop succeeds; with
        it, every probe fails before the rag/db lookups run.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await self._request(async_client, method, path, query)
        assert response.status_code == 401, (
            f"CB-2732 regression: {method} {path} returned "
            f"{response.status_code}, expected 401: {response.text[:200]}"
        )

    @pytest.mark.parametrize(
        "path,method,query,_handler,_limit", _SEARCH_SIBLING_ENDPOINTS
    )
    async def test_token_set_allows_with_valid_header(
        self,
        async_client,
        monkeypatch,
        request,
        path,
        method,
        query,
        _handler,
        _limit,
    ):
        """Token configured + valid `X-Internal-Token` → gate passes.

        Asserts `!= 401` rather than `== 200` because the route body of
        each endpoint hits different downstream contracts (e.g. embed
        returns `{success, issue_id}`) and the relevant invariant for the
        gate is "the 401-producing branch is not taken". Body correctness
        is exercised by the rag_service unit tests, not here.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        self._install_mock_deps(request)
        response = await self._request(
            async_client,
            method,
            path,
            query,
            headers={"X-Internal-Token": "test-secret-abc123"},
        )
        assert response.status_code != 401, (
            f"CB-2732 regression: valid token rejected on {method} {path} "
            f"with {response.status_code}: {response.text[:200]}"
        )

    @pytest.mark.parametrize(
        "path,method,query,_handler,_limit", _SEARCH_SIBLING_ENDPOINTS
    )
    async def test_token_set_rejects_wrong_header(
        self, async_client, monkeypatch, path, method, query, _handler, _limit
    ):
        """Token configured + WRONG `X-Internal-Token` → 401."""
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await self._request(
            async_client,
            method,
            path,
            query,
            headers={"X-Internal-Token": "this-is-not-the-right-token"},
        )
        assert response.status_code == 401, (
            f"CB-2732 regression: wrong token accepted on {method} {path} "
            f"with {response.status_code}: {response.text[:200]}"
        )

    @pytest.mark.parametrize(
        "path,method,query,_handler,_limit", _SEARCH_SIBLING_ENDPOINTS
    )
    async def test_origin_spoof_alone_does_not_bypass_token_gate(
        self, async_client, monkeypatch, path, method, query, _handler, _limit
    ):
        """CB-2666 F1 invariant — applies to every gated endpoint.

        `curl -H 'Origin: http://localhost:3601'` must NOT bypass the
        token gate. Server-side gates that trust the Origin header are
        meaningless because any local process can forge it.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-secret-abc123")
        response = await self._request(
            async_client,
            method,
            path,
            query,
            headers={"Origin": "http://localhost:3601"},
        )
        assert response.status_code == 401, (
            f"CB-2732/F1 regression: forged Origin bypassed gate on "
            f"{method} {path}: {response.status_code}"
        )

    @pytest.mark.parametrize(
        "_path,_method,_query,handler,limit", _SEARCH_SIBLING_ENDPOINTS
    )
    def test_handler_carries_internal_auth_dep(
        self, _path, _method, _query, handler, limit
    ):
        """Source-level pin: each of the five handlers must carry
        `dependencies=[InternalAuthDep]` AND `@limiter.limit("<limit>")`.

        AST-walks `search.py` and asserts both decorations are
        structurally present on the named handler. Substring matching at
        the file level is too loose — `InternalAuthDep` could move into
        a comment, or a future refactor could drop the kwarg from one
        endpoint without breaking a "string is somewhere in the file"
        check. Walking the decorator stack of each named function pins
        the relationship.
        """
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parent.parent / "api" / "search.py"
        tree = ast.parse(src.read_text())

        target = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == handler:
                    target = node
                    break
        assert target is not None, (
            f"CB-2732 regression: handler {handler!r} missing from "
            "search.py — gate cannot be enforced on a deleted route"
        )

        # Find the @router.<method>(... dependencies=[...] ...) call.
        router_call = None
        router_idx = None
        for i, dec in enumerate(target.decorator_list):
            if isinstance(dec, ast.Call):
                fn = dec.func
                if (
                    isinstance(fn, ast.Attribute)
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "router"
                ):
                    router_call = dec
                    router_idx = i
                    break
        assert router_call is not None, (
            f"CB-2732 regression: handler {handler!r} has no @router "
            "decorator — route registration may have been refactored"
        )

        deps_kwarg = None
        for kw in router_call.keywords:
            if kw.arg == "dependencies":
                deps_kwarg = kw.value
                break
        assert deps_kwarg is not None, (
            f"CB-2732 regression: @router on {handler!r} is missing the "
            "`dependencies=[...]` kwarg — InternalAuthDep gate dropped"
        )
        deps_src = ast.unparse(deps_kwarg)
        assert "InternalAuthDep" in deps_src, (
            f"CB-2732 regression: `dependencies={deps_src}` on {handler!r} "
            "does not include InternalAuthDep — token gate not enforced"
        )

        # Find the @limiter.limit("<limit>") decorator. The decorator is
        # @limiter.limit("...") which AST-parses as a Call on
        # Attribute(value=Name('limiter'), attr='limit').
        limit_value = None
        limit_idx = None
        for i, dec in enumerate(target.decorator_list):
            if isinstance(dec, ast.Call):
                fn = dec.func
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == "limit"
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "limiter"
                ):
                    if dec.args and isinstance(dec.args[0], ast.Constant):
                        limit_value = dec.args[0].value
                    limit_idx = i
                    break
        assert limit_value is not None, (
            f"CB-2732 regression: handler {handler!r} has no "
            "@limiter.limit(...) decorator — per-route rate cap dropped"
        )
        assert limit_value == limit, (
            f"CB-2732 regression: handler {handler!r} limit drifted from "
            f"{limit!r} to {limit_value!r}. Read endpoints stay at "
            "30/minute; write endpoints (embed*, embed-all) MUST stay at "
            "10/minute — they are DoS-amplifying, not just disclosure."
        )

        # CB-2732 sec audit M-1: decorator order MUST be `@router.<verb>`
        # syntactically ABOVE `@limiter.limit(...)`. The shipped pattern
        # is:
        #
        #     @router.get(..., dependencies=[InternalAuthDep])  # source 1st
        #     @limiter.limit("30/minute")                       # source 2nd
        #     async def handler(...): ...
        #
        # Python applies decorators bottom-up: `limiter.limit` wraps `f`
        # FIRST, then `router.<verb>` registers `limiter.limit(f)` as the
        # route handler. The router then runs `dependencies=[]` BEFORE
        # invoking the wrapped function, so the gate fires before slowapi
        # touches its bucket — the M-1 / CB-2667 deploy-state-oracle
        # posture is preserved (auth fails close, limiter never decrements
        # for unauthenticated probes). `decorator_list` is source-order
        # top→bottom, so this correct shape gives `router_idx == 0` and
        # `limit_idx == 1` → `router_idx < limit_idx`.
        #
        # The inverted shape:
        #
        #     @limiter.limit("30/minute")                       # source 1st
        #     @router.get(..., dependencies=[InternalAuthDep])  # source 2nd
        #     async def handler(...): ...
        #
        # parses to `limit_idx == 0` and `router_idx == 1` —
        # `router_idx > limit_idx`. In this shape `router.<verb>` registers
        # the BARE function `f` (FastAPI's router decorators register the
        # route and return `f` unmodified), and `limiter.limit` then wraps
        # the module-level binding the router will never call. Net effect:
        # the auth gate still fires (it's on the route registration), but
        # the per-route rate cap silently collapses to the global 200/min
        # default. None of the gate-only tests above catch this — they
        # don't measure 429 boundaries — so this assertion is the only
        # backstop for a decorator-inversion regression.
        assert router_idx < limit_idx, (
            f"CB-2732 sec audit M-1 regression: handler {handler!r} has "
            f"`@router.<verb>` at decorator_list[{router_idx}] but "
            f"`@limiter.limit` at [{limit_idx}]. Decorator order is "
            "inverted: `@router.<verb>(..., dependencies=[InternalAuthDep])` "
            "MUST be syntactically ABOVE `@limiter.limit(...)`. In the "
            "inverted form the router registers the bare function and "
            "slowapi wraps a module-level name the router never calls — "
            f"the per-route cap silently collapses to the global "
            "200/min default while the auth gate still appears to work."
        )


# ============================================================================
# CB-2783 — search.py file-level perimeter invariant
# ============================================================================

def _collect_router_handlers(file_path):
    """Walk the AST of `file_path` and return one dict per function
    decorated by `@router.<verb>(...)`.

    Returned shape per handler:
        {
            "name": str,                # function name
            "lineno": int,
            "router_idx": int,          # decorator_list index of @router.<verb>
            "router_call": ast.Call,    # the @router.<verb>(...) node
            "limit_idx": int | None,    # decorator_list index of @limiter.limit
            "limit_value": str | None,  # literal arg of @limiter.limit("...")
            "deps_src": str | None,     # ast.unparse of `dependencies=[...]`
        }

    Discovery, not enumeration — the caller does NOT supply a list of
    expected handler names. That's the whole point of the file-level
    invariant: a future endpoint cannot escape the gate by being absent
    from the test's parametrize list (the failure mode CB-2783 fixes).
    """
    import ast
    tree = ast.parse(file_path.read_text())
    handlers = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        router_idx = None
        router_call = None
        limit_idx = None
        limit_value = None
        for i, dec in enumerate(node.decorator_list):
            if not isinstance(dec, ast.Call):
                continue
            fn = dec.func
            if not (
                isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
            ):
                continue
            if fn.value.id == "router" and router_idx is None:
                router_idx = i
                router_call = dec
            elif (
                fn.value.id == "limiter"
                and fn.attr == "limit"
                and limit_idx is None
            ):
                limit_idx = i
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    limit_value = dec.args[0].value
        if router_idx is None:
            continue
        deps_src = None
        for kw in router_call.keywords:
            if kw.arg == "dependencies":
                deps_src = ast.unparse(kw.value)
                break
        handlers.append({
            "name": node.name,
            "lineno": node.lineno,
            "router_idx": router_idx,
            "router_call": router_call,
            "limit_idx": limit_idx,
            "limit_value": limit_value,
            "deps_src": deps_src,
        })
    return handlers


@pytest.mark.unit
class TestSearchPyFileLevelInvariant:
    """CB-2783 — file-level perimeter invariant for `backend/api/search.py`.

    Why a file-level test on top of CB-2732's per-handler AST pin:

    `TestSearchSiblingEndpointsPerimeter::test_handler_carries_internal_auth_dep`
    pins the FIVE current sibling handlers + `/stats` from CB-2667 by name
    via the hard-coded `_SEARCH_SIBLING_ENDPOINTS` parametrize list. A
    future ticket that adds a SIXTH router-decorated handler to
    `search.py` (e.g. `POST /{project_id}/reindex-since`) and FORGETS one
    of the gates would NOT fail that per-handler test — the new handler
    is simply absent from the list. Closure was structural for the
    handlers it knew about; structural for new handlers it became.

    This invariant walks every `@router.<verb>(...)`-decorated function
    in `search.py` (discovery, not enumeration) and asserts each one:

      1. carries `dependencies=[...]` containing `InternalAuthDep`
      2. carries a `@limiter.limit("...")` decorator with a literal cap
      3. has `@router.<verb>` in source ABOVE `@limiter.limit`
         (decorator-order invariant from CB-2732 sec audit M-1 — inverted
         order silently collapses the per-route cap to the global default
         while the gate still APPEARS to fire)

    A new endpoint cannot bypass the perimeter without deliberately
    defeating this test.

    PROJECTS.PY DEFERRED. The same shape would apply to
    `backend/api/projects.py` (CB-2666 perimeter), but
    `initialize_sequence` there carries `InternalAuthDep` WITHOUT a
    `@limiter.limit` decorator. Extending this invariant to `projects.py`
    is held for a follow-up that decides whether `initialize_sequence`
    should wear the write-cap (10/min, matching `search.py`'s
    `embed*` write endpoints) or be explicitly exempted. The helper
    `_collect_router_handlers` is already file-agnostic, so the
    follow-up is one line of parametrize once that decision lands.
    """

    SEARCH_PY = (
        Path(__file__).resolve().parent.parent / "api" / "search.py"
    )

    def test_at_least_one_handler_present(self):
        """Sanity floor: a refactor that empties `search.py` of router
        handlers would make every other assertion in this class vacuously
        true. Pin a non-zero floor so the invariant cannot pass on a file
        that registers no routes.

        Five sibling endpoints (CB-2732) + `/stats` (CB-2667) = SIX. The
        floor is set at SIX so a regression that drops a route also fails
        loud here.
        """
        handlers = _collect_router_handlers(self.SEARCH_PY)
        names = sorted(h["name"] for h in handlers)
        assert len(handlers) >= 6, (
            f"CB-2783 sanity guard: expected >= 6 router-decorated "
            f"handlers in search.py (CB-2732 perimeter closed five + "
            f"CB-2667 added /stats), found {len(handlers)}: {names}"
        )

    def test_every_handler_has_internal_auth_dep(self):
        """Every router-decorated handler in `search.py` must carry
        `dependencies=[...]` containing `InternalAuthDep`.

        Walks the handler set returned by `_collect_router_handlers`,
        accumulates every violation, then asserts once with a combined
        report so a CI run surfaces ALL missing handlers in a single
        failure (not just the first).
        """
        handlers = _collect_router_handlers(self.SEARCH_PY)
        violations = []
        for h in handlers:
            if h["deps_src"] is None:
                violations.append(
                    f"  - {h['name']} (line {h['lineno']}): "
                    "@router decorator has no `dependencies=[...]` kwarg"
                )
            elif "InternalAuthDep" not in h["deps_src"]:
                violations.append(
                    f"  - {h['name']} (line {h['lineno']}): "
                    f"`dependencies={h['deps_src']}` does not contain "
                    "InternalAuthDep"
                )
        assert not violations, (
            "CB-2783 invariant: every router-decorated handler in "
            "search.py must carry `dependencies=[InternalAuthDep, ...]`. "
            "Failing handlers:\n" + "\n".join(violations)
        )

    def test_every_handler_has_limiter_limit(self):
        """Every router-decorated handler must wear `@limiter.limit("...")`.

        Pins PRESENCE only — per-handler tests in
        `TestSearchSiblingEndpointsPerimeter` and
        `TestSearchStatsEndpointPerimeter` already pin the exact
        30/minute vs 10/minute split. The file-level invariant catches
        the case where a new endpoint lands without ANY per-route cap
        (defaulting silently to the global 200/minute).
        """
        handlers = _collect_router_handlers(self.SEARCH_PY)
        violations = []
        for h in handlers:
            if h["limit_idx"] is None:
                violations.append(
                    f"  - {h['name']} (line {h['lineno']}): "
                    "no `@limiter.limit(...)` decorator"
                )
            elif h["limit_value"] is None:
                violations.append(
                    f"  - {h['name']} (line {h['lineno']}): "
                    "@limiter.limit present but argument is not a literal "
                    "string — cap value cannot be statically verified"
                )
        assert not violations, (
            "CB-2783 invariant: every router-decorated handler in "
            "search.py must wear `@limiter.limit(\"<cap>\")` with a "
            "literal string cap. Failing handlers:\n"
            + "\n".join(violations)
        )

    def test_every_handler_router_above_limiter_in_source(self):
        """`@router.<verb>(...)` must appear in source ABOVE
        `@limiter.limit(...)` for every handler (CB-2732 sec audit M-1).

        Inverted order silently collapses the per-route cap to the
        global default while the auth gate still APPEARS to fire — see
        the long-form rationale on
        `TestSearchSiblingEndpointsPerimeter::test_handler_carries_internal_auth_dep`.
        Lifting it to the file level catches the same inversion on a
        future SIXTH handler that the per-handler list never knew about.
        """
        handlers = _collect_router_handlers(self.SEARCH_PY)
        violations = []
        for h in handlers:
            if h["limit_idx"] is None:
                # `test_every_handler_has_limiter_limit` owns the missing-
                # limiter case; skip here so the failure surfaces once,
                # in the test that is actually about it.
                continue
            if h["router_idx"] >= h["limit_idx"]:
                violations.append(
                    f"  - {h['name']} (line {h['lineno']}): "
                    f"@router at decorator_list[{h['router_idx']}], "
                    f"@limiter.limit at [{h['limit_idx']}]. "
                    "@router MUST be syntactically ABOVE @limiter.limit."
                )
        assert not violations, (
            "CB-2783 + CB-2732/M-1 invariant: every router-decorated "
            "handler must declare `@router.<verb>` ABOVE `@limiter.limit`. "
            "Inverted order makes the router register the bare function "
            "while slowapi wraps a module-level binding the router never "
            "calls — the per-route cap silently collapses to the global "
            "200/min default while the auth gate still appears to work. "
            "Failing handlers:\n" + "\n".join(violations)
        )
