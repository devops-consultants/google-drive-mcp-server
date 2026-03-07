"""Tests for the health endpoint."""

import pytest
from httpx import AsyncClient, ASGITransport
from google_drive_mcp_server.server import create_app


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok():
    """Health endpoint returns 200 with {"status": "ok"}."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
