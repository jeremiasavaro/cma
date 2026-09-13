"""Integration tests for POST {API_PREFIX}/analyze."""

from httpx import AsyncClient

from app.config import get_settings
from tests.fixtures import SAMPLE_CV_TEXT


def _valid_payload() -> dict:
    return {
        "cv": SAMPLE_CV_TEXT,
        "target": {"role": "Senior Backend Engineer"},
    }


async def test_analyze_returns_501_not_implemented(client: AsyncClient) -> None:
    settings = get_settings()

    response = await client.post(f"{settings.API_PREFIX}/analyze", json=_valid_payload())

    assert response.status_code == 501
    assert (
        response.json()["detail"]
        == "Analysis pipeline not implemented yet. TODO: implement in services layer."
    )


async def test_analyze_returns_422_on_invalid_cv(client: AsyncClient) -> None:
    settings = get_settings()
    payload = _valid_payload()
    payload["cv"] = "too short"

    response = await client.post(f"{settings.API_PREFIX}/analyze", json=payload)

    assert response.status_code == 422
