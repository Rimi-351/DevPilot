"""Integration tests for health and root endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient) -> None:
    """Test root application status endpoint."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "DevPilot"
    assert data["status"] == "online"


@pytest.mark.asyncio
async def test_health_check_endpoint(client: AsyncClient) -> None:
    """Test health check and database connectivity probe."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["service"] == "DevPilot"


@pytest.mark.asyncio
async def test_ui_dashboard_endpoint(client: AsyncClient) -> None:
    """Test web dashboard UI endpoint and HTML response."""
    response = await client.get("/ui")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "DevPilot" in response.text
