"""
Shared pytest fixtures.

Tests never talk to a real Postgres instance: the `get_session` FastAPI
dependency is overridden with a fake async generator that yields a mocked
`AsyncSession`. httpx's `ASGITransport` talks to the app in-process without
triggering the lifespan (no real DB connection is attempted on startup).
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.main import app as fastapi_app


@pytest.fixture
def mock_session() -> AsyncMock:
    """A mocked AsyncSession with `.execute()` returning an AsyncMock result."""
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = AsyncMock()
    return session


@pytest.fixture
def app(mock_session: AsyncMock):
    """The FastAPI app with `get_session` overridden to avoid a real DB."""

    async def override_get_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    fastapi_app.dependency_overrides[get_session] = override_get_session
    yield fastapi_app
    fastapi_app.dependency_overrides.pop(get_session, None)


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """An async HTTP client wired directly to the app (no network, no lifespan)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
