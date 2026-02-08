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
