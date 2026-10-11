"""Unit tests for app.ingestion.freehire.client — all HTTP is faked.

Every test uses httpx.MockTransport: no request ever leaves the process.
FreehireClient builds its AsyncClient internally in __aenter__ with no
transport injection point, so the helper replaces the private `_client`
attribute directly (documented workaround; app code is not modified).
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from app.ingestion.freehire.client import (
    MAX_PAGINATION_DEPTH,
    MAX_RESPONSE_BYTES,
    FreehireAPIError,
    FreehireClient,
)

BASE_URL = "https://freehire.test/api/v1"


@asynccontextmanager
async def fake_client(
    handler: Callable[[httpx.Request], httpx.Response],
    page_size: int | None = None,
) -> AsyncIterator[FreehireClient]:
    """A FreehireClient whose internal AsyncClient talks to a MockTransport."""
    client = FreehireClient(base_url=BASE_URL, page_size=page_size)
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=BASE_URL
    )
    try:
        yield client
    finally:
        await client.close()


def page_response(
    jobs: list[dict[str, Any]], *, limit: int, offset: int, total: int
) -> httpx.Response:
    """A well-formed {"data": [...], "meta": {...}} collection response."""
    return httpx.Response(
        200, json={"data": jobs, "meta": {"limit": limit, "offset": offset, "total": total}}
    )


class _ChunkStream(httpx.AsyncByteStream):
    """Response body served as raw chunks, without a Content-Length header."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


def _refuse_http(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"No HTTP request expected, got {request.url}")


# ---------------------------------------------------------------------------
# Envelope parsing and error payloads
# ---------------------------------------------------------------------------


async def test_search_jobs_parses_collection_envelope() -> None:
    """A valid data/meta envelope becomes a FreehirePage; non-dicts are dropped.

    Protects the contract every downstream consumer (iter_jobs, upserter)
    relies on: page.data only ever contains dict records.
    """
    job = {"external_id": "freehire_1", "title": "Engineer"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/jobs/search"
        assert request.url.params["limit"] == "10"
        return page_response([job, "junk-string", 42], limit=10, offset=0, total=3)

    async with fake_client(handler) as client:
        page = await client.search_jobs(limit=10)

    assert page.data == [job]
    assert page.limit == 10
    assert page.offset == 0
    assert page.total == 3


async def test_error_body_raises_api_error() -> None:
    """An {"error": ...} payload surfaces as FreehireAPIError with its message."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid filter combination"})

    async with fake_client(handler) as client:
        with pytest.raises(FreehireAPIError, match="invalid filter combination") as excinfo:
            await client.search_jobs(limit=10)

    assert excinfo.value.status_code == 400


async def test_malformed_envelope_raises_api_error() -> None:
    """A 200 body without the data/meta envelope must not be trusted."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})  # meta missing

    async with fake_client(handler) as client:
        with pytest.raises(FreehireAPIError, match="Malformed collection envelope"):
            await client.search_jobs(limit=10)


# ---------------------------------------------------------------------------
# Filter validation happens before any HTTP
# ---------------------------------------------------------------------------


async def test_limit_over_api_max_rejected_before_http() -> None:
    """limit > 100 is a caller bug: fail fast locally, never hit the API."""
    async with fake_client(_refuse_http) as client:
        with pytest.raises(ValueError, match="limit must be between"):
            await client.search_jobs(limit=101)


async def test_pagination_cap_rejected_before_http() -> None:
    """offset + limit > 10_000 would get a 400 upstream: refuse it locally."""
    async with fake_client(_refuse_http) as client:
        with pytest.raises(ValueError, match="pagination cap"):
            await client.search_jobs(limit=100, offset=9_901)


# ---------------------------------------------------------------------------
# Hostile / oversized payload defenses
# ---------------------------------------------------------------------------


async def test_infinity_token_in_body_rejected() -> None:
    """Non-standard Infinity/NaN JSON tokens are refused by the strict parser.

    Python's json.loads would happily parse them into non-finite floats that
    poison aggregates; the client must treat such a body as non-JSON.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'{"data": [{"salary": Infinity}], "meta": {}}',
            headers={"Content-Type": "application/json"},
        )

    async with fake_client(handler) as client:
        with pytest.raises(FreehireAPIError, match="Non-JSON response"):
            await client.search_jobs(limit=10)


async def test_oversized_declared_content_length_rejected() -> None:
    """A Content-Length over the 10 MB cap is refused before reading the body."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)},
            stream=_ChunkStream([b"{}"]),
        )

    async with fake_client(handler) as client:
        with pytest.raises(FreehireAPIError, match="declares"):
            await client.search_jobs(limit=10)


async def test_oversized_chunked_body_rejected() -> None:
    """A chunked body (no Content-Length) is cut off once it crosses the cap."""
    chunk = b"x" * (1024 * 1024)  # 1 MiB chunks, 11 MiB total.

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_ChunkStream([chunk] * 11))

    async with fake_client(handler) as client:
        with pytest.raises(FreehireAPIError, match="exceeds"):
            await client.search_jobs(limit=10)


# ---------------------------------------------------------------------------
# iter_jobs pagination
# ---------------------------------------------------------------------------


def _dataset_handler(
    dataset: list[dict[str, Any]], *, reported_total: int, requests: list[tuple[int, int]]
) -> Callable[[httpx.Request], httpx.Response]:
    """Serve slices of a finite dataset, reporting a fixed (possibly wrong) total."""

    def handler(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        requests.append((limit, offset))
        return page_response(
            dataset[offset : offset + limit], limit=limit, offset=offset, total=reported_total
        )

    return handler


async def test_iter_jobs_ignores_underreported_total() -> None:
    """meta.total under-reporting must not stop pagination early.

    The live API's total is unreliable: the only valid exit condition is a
    short (or empty) page. Here total=1 but 5 jobs exist — all must arrive.
    """
    dataset = [{"external_id": f"freehire_{i}", "title": f"Job {i}"} for i in range(5)]
    requests: list[tuple[int, int]] = []
    handler = _dataset_handler(dataset, reported_total=1, requests=requests)

    async with fake_client(handler, page_size=2) as client:
        jobs = [job async for job in client.iter_jobs()]

    assert len(jobs) == 5
    # Full pages at 0 and 2, then the short page at 4 stops the loop.
    assert requests == [(2, 0), (2, 2), (2, 4)]


async def test_iter_jobs_stops_on_empty_first_page() -> None:
    """An empty first page ends iteration after exactly one request."""
    requests: list[tuple[int, int]] = []
    handler = _dataset_handler([], reported_total=0, requests=requests)

    async with fake_client(handler, page_size=2) as client:
        jobs = [job async for job in client.iter_jobs()]

    assert jobs == []
    assert requests == [(2, 0)]


async def test_iter_jobs_shrinks_final_page_at_pagination_cap() -> None:
    """At the 10k boundary the last page shrinks instead of crossing the cap.

    With page_size=97 the client must issue 103 full pages (ending at offset
    9991), then one shrunk page of limit 4+5=9, then stop at exactly 10_000
    jobs without ever requesting offset + limit > 10_000.
    """
    requests: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        requests.append((limit, offset))
        jobs = [{"external_id": f"freehire_{offset + i}", "title": "J"} for i in range(limit)]
        return page_response(jobs, limit=limit, offset=offset, total=2_000_000)

    async with fake_client(handler, page_size=97) as client:
        jobs = [job async for job in client.iter_jobs()]

    assert len(jobs) == 10_000
    assert len(jobs) == len({job["external_id"] for job in jobs})  # No duplicates.
    assert requests[-1] == (9, 9991)  # Shrunk final page.
    assert all(limit + offset <= MAX_PAGINATION_DEPTH for limit, offset in requests)


async def test_iter_jobs_honors_max_jobs() -> None:
    """max_jobs stops iteration mid-page without fetching further pages."""
    dataset = [{"external_id": f"freehire_{i}", "title": f"Job {i}"} for i in range(10)]
    requests: list[tuple[int, int]] = []
    handler = _dataset_handler(dataset, reported_total=10, requests=requests)

    async with fake_client(handler, page_size=4) as client:
        jobs = [job async for job in client.iter_jobs(max_jobs=3)]

    assert len(jobs) == 3
    assert requests == [(4, 0)]
