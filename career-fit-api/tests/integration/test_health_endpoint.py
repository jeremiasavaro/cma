"""Integration tests for GET {API_PREFIX}/health."""

from httpx import AsyncClient

from app.config import get_settings


async def test_health_check_returns_healthy(client: AsyncClient) -> None:
    settings = get_settings()

    response = await client.get(f"{settings.API_PREFIX}/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected"
