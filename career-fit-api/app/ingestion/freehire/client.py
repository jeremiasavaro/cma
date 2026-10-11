"""
Freehire API Client - Async HTTP access to the Freehire jobs API.

API contract (live-verified 2026-10-09):
- Base URL: settings.FREEHIRE_BASE_URL (keyless GET endpoints).
- Collections envelope: {"data": [...], "meta": {"limit", "offset", "total"}}.
- Errors: {"error": "message"} (often with a 4xx/5xx status).
- Ingestion uses GET /jobs/search: the plain /jobs endpoint silently ignores
  all filters except limit/offset.
- Hard pagination cap: offset + limit must not exceed 10_000 or the API
  returns 400 "pagination too deep". The full dataset is ~2M+ jobs, so the
  expected usage is narrow, filtered queries (e.g. posted_within_days windows
  or per-target-role skill filters) that stay under the cap — never a full dump.

Transient failures (429 rate limit, 503 "search temporarily unavailable",
network errors) are retried with exponential backoff via tenacity.
"""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

# API hard limits (live-verified).
API_MAX_LIMIT = 100
MAX_PAGINATION_DEPTH = 10_000

# Byte budget per response body (compromised-upstream OOM guard).
MAX_RESPONSE_BYTES = 10 * 1024 * 1024

_ALLOWED_SORTS = {"created_at", "posted_at", "view_count", "salary_min", "salary_max"}
_ALLOWED_ORDERS = {"asc", "desc"}


class FreehireAPIError(Exception):
    """The API returned an {"error": ...} payload or an unusable response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FreehireTransientError(FreehireAPIError):
    """Retryable failure: 429 rate limit or 503 search unavailable."""


@dataclass
class FreehirePage:
    """One parsed page of a Freehire collection response."""

    data: list[dict[str, Any]]
    limit: int
    offset: int
    total: int
    ignored_params: list[str] = field(default_factory=list)


def _reject_json_constant(token: str) -> Any:
    """json.loads parse_constant hook: refuse Infinity/-Infinity/NaN tokens."""
    raise ValueError(f"Rejected non-finite JSON constant: {token}")


def _parse_json_strict(text: str) -> Any:
    """Parse JSON refusing the non-standard non-finite float tokens."""
    return json.loads(text, parse_constant=_reject_json_constant)


def _join_facet(value: str | list[str] | None) -> str | None:
    """Comma-join facet filters (comma-separated values mean OR on the API side)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return ",".join(str(v) for v in value)


class FreehireClient:
    """Async client for the Freehire jobs API (async context manager)."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        page_size: int | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.FREEHIRE_BASE_URL).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.FREEHIRE_TIMEOUT
        # The API caps limit at 100 regardless of what config asks for.
        self._page_size = min(page_size or settings.FREEHIRE_PAGE_SIZE, API_MAX_LIMIT)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "FreehireClient":
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "FreehireClient is not open — use 'async with FreehireClient() as client'"
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((FreehireTransientError, httpx.TransportError)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """GET with retry on 429/503/network errors; returns the parsed JSON body."""
        async with self._require_client().stream("GET", path, params=params) as response:
            if response.status_code in (429, 503):
                raise FreehireTransientError(
                    f"Freehire transient failure on {path} (HTTP {response.status_code})",
                    status_code=response.status_code,
                )
            text = await self._read_body_capped(response, path)

        # The payload is untrusted external input: parse and shape-check before
        # use, refusing Infinity/-Infinity/NaN tokens.
        try:
            body = _parse_json_strict(text)
        except ValueError as exc:
            raise FreehireAPIError(
                f"Non-JSON response from {path} (HTTP {response.status_code})",
                status_code=response.status_code,
            ) from exc

        if isinstance(body, dict) and "error" in body:
            raise FreehireAPIError(str(body["error"]), status_code=response.status_code)
        if response.status_code >= 400:
            raise FreehireAPIError(
                f"HTTP {response.status_code} from {path}", status_code=response.status_code
            )
        if not isinstance(body, dict):
            raise FreehireAPIError(f"Unexpected response shape from {path}: {type(body).__name__}")
        return body

    @staticmethod
    async def _read_body_capped(response: httpx.Response, path: str) -> str:
        """Read a streamed body enforcing the MAX_RESPONSE_BYTES budget."""
        declared = response.headers.get("Content-Length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
            raise FreehireAPIError(
                f"Response from {path} declares {declared} bytes, "
                f"over the {MAX_RESPONSE_BYTES}-byte cap",
                status_code=response.status_code,
            )
        received = 0
        chunks: list[bytes] = []
        async for chunk in response.aiter_bytes():
            received += len(chunk)
            if received > MAX_RESPONSE_BYTES:
                raise FreehireAPIError(
                    f"Response from {path} exceeds the {MAX_RESPONSE_BYTES}-byte cap",
                    status_code=response.status_code,
                )
            chunks.append(chunk)
        return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")

    @staticmethod
    def _parse_collection(body: dict[str, Any]) -> FreehirePage:
        """Validate the {"data": [...], "meta": {...}} envelope and build a page."""
        data = body.get("data")
        meta = body.get("meta")
        if not isinstance(data, list) or not isinstance(meta, dict):
            raise FreehireAPIError("Malformed collection envelope: missing data/meta")

        records = [item for item in data if isinstance(item, dict)]
        dropped = len(data) - len(records)
        if dropped:
            logger.warning("Dropped %d non-dict records from Freehire page", dropped)

        # Unknown query params are echoed back as [{"param": name}, ...].
        ignored_raw = meta.get("ignored_params") or []
        ignored = [
            str(item.get("param"))
            for item in ignored_raw
            if isinstance(item, dict) and item.get("param")
        ]
        if ignored:
            logger.warning("Freehire ignored query params: %s", ignored)

        def _int(value: Any, default: int = 0) -> int:
            try:
                return int(value)
            except (TypeError, ValueError, OverflowError):
                return default

        return FreehirePage(
            data=records,
            limit=_int(meta.get("limit"), len(records)),
            offset=_int(meta.get("offset")),
            total=_int(meta.get("total"), len(records)),
            ignored_params=ignored,
        )

    async def search_jobs(
        self,
        *,
        q: str | None = None,
        sort: str | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        skills: str | list[str] | None = None,
        countries: str | list[str] | None = None,
        regions: str | list[str] | None = None,
        cities: str | list[str] | None = None,
        skills_mode_and: bool = False,
        salary_min: int | None = None,
        salary_max: int | None = None,
        experience_years_min: int | None = None,
        experience_years_max: int | None = None,
        posted_within_days: int | None = None,
        open_within_days: int | None = None,
        visa_sponsorship: bool | None = None,
        requires_clearance: bool | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> FreehirePage:
        """Fetch one page from GET /jobs/search with validated filter params.

        Raises ValueError on invalid sort/order/limit or when offset + limit
        would cross the 10_000 pagination cap.
        """
        limit = self._page_size if limit is None else limit
        if not 1 <= limit <= API_MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {API_MAX_LIMIT}, got {limit}")
        if offset < 0:
            raise ValueError(f"offset must be >= 0, got {offset}")
        if offset + limit > MAX_PAGINATION_DEPTH:
            raise ValueError(
                f"offset + limit ({offset + limit}) exceeds the API pagination cap "
                f"of {MAX_PAGINATION_DEPTH}; narrow the query (e.g. posted_within_days)"
            )
        if sort is not None and sort not in _ALLOWED_SORTS:
            raise ValueError(f"sort must be one of {sorted(_ALLOWED_SORTS)}, got {sort!r}")
        if order is not None and order not in _ALLOWED_ORDERS:
            raise ValueError(f"order must be one of {sorted(_ALLOWED_ORDERS)}, got {order!r}")

        params: dict[str, Any] = {"limit": limit, "offset": offset}
        scalar_filters = {
            "q": q,
            "sort": sort,
            "order": order,
            "skills": _join_facet(skills),
            "countries": _join_facet(countries),
            "regions": _join_facet(regions),
            "cities": _join_facet(cities),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "experience_years_min": experience_years_min,
            "experience_years_max": experience_years_max,
            "posted_within_days": posted_within_days,
            "open_within_days": open_within_days,
        }
        params.update({k: v for k, v in scalar_filters.items() if v is not None})
        if skills_mode_and:
            params["skills_mode"] = "and"
        # Booleans are serialized explicitly to avoid httpx sending "True"/"False".
        if visa_sponsorship is not None:
            params["visa_sponsorship"] = "true" if visa_sponsorship else "false"
        if requires_clearance is not None:
            params["requires_clearance"] = "true" if requires_clearance else "false"
        if extra_params:
            params.update(extra_params)

        body = await self._get("/jobs/search", params)
        return self._parse_collection(body)

    ## Itera en muchas paginas con un maximo de trabajos, para no sobrepasar el limite de 10k
    ## Llama a search_jobs() para obtener cada pagina y yield cada trabajo individualmente
    async def iter_jobs(
        self,
        *,
        max_jobs: int | None = None,
        **filters: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate raw job dicts, paginating transparently.

        Stops cleanly at end of results or at the 10_000 pagination cap.
        Windowing strategy: because the cap caps any single query at 10k rows
        (dataset is ~2M+), callers must narrow queries — e.g. filter by
        posted_within_days for daily increments, or per-target-role skill
        filters — rather than attempt a full dump.

        Args:
            max_jobs: Optional hard stop after yielding this many jobs.
            **filters: Any search_jobs() filter (q, skills, posted_within_days, ...).
        """
        offset = 0
        yielded = 0
        page_size = self._page_size

        while True:
            # Shrink the final page instead of crossing the 10k boundary.
            if offset + page_size > MAX_PAGINATION_DEPTH:
                page_size = MAX_PAGINATION_DEPTH - offset
                if page_size <= 0:
                    logger.info(
                        "Stopping pagination at the %d-row API cap (narrow filters to go deeper)",
                        MAX_PAGINATION_DEPTH,
                    )
                    return

            page = await self.search_jobs(limit=page_size, offset=offset, **filters)
            for job in page.data:
                yield job
                yielded += 1
                if max_jobs is not None and yielded >= max_jobs:
                    return

            # End of results = empty or short page. meta.total can under-report,
            # so it is never used as an exit condition — logging only.
            if len(page.data) < page_size:
                logger.debug(
                    "Freehire pagination done at offset=%d (meta.total=%d)",
                    offset + len(page.data),
                    page.total,
                )
                return
            offset += len(page.data)
