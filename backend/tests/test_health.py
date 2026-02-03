"""
Health endpoint tests for ProjectsManagerWebV2 Backend.

These tests verify the basic health check endpoints are working correctly.
"""

import pytest


@pytest.mark.api
class TestHealthEndpoints:
    """Tests for health check endpoints."""

    async def test_root_endpoint(self, async_client):
        """Test the root endpoint returns service info."""
        response = await async_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "ok"
        assert data["service"] == "ProjectsManagerWebV2 API"
        assert "version" in data

    async def test_health_endpoint(self, async_client):
        """Test the health check endpoint."""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "healthy"
        assert data["service"] == "ProjectsManagerWebV2 API"

    async def test_api_health_endpoint(self, async_client):
        """Test the API-specific health check endpoint."""
        response = await async_client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["api"] == "v1"


@pytest.mark.unit
class TestHealthResponseFormat:
    """Tests for health response format validation."""

    async def test_root_response_keys(self, async_client):
        """Verify root endpoint response contains expected keys."""
        response = await async_client.get("/")
        data = response.json()

        expected_keys = {"success", "status", "service", "version"}
        assert expected_keys.issubset(data.keys())

    async def test_health_response_keys(self, async_client):
        """Verify health endpoint response contains expected keys."""
        response = await async_client.get("/health")
        data = response.json()

        expected_keys = {"success", "status", "service"}
        assert expected_keys.issubset(data.keys())
