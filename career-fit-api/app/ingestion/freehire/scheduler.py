"""
Freehire Ingestion Scheduler - asyncio-based daily runner (no extra deps).

Two entry points:
- run_ingestion_cycle(): one full cycle (client -> normalizer -> upserter ->
  snapshot) in its own session scope. Callable from a future CLI script.
- run_scheduler(): infinite loop that sleeps until INGESTION_DAILY_HOUR UTC,
  runs a cycle, logs the outcome, and keeps looping. A failed cycle is logged
  and never kills the loop.

This is the one place in ingestion that owns a session and therefore the one
place allowed to commit (repositories/upserter/snapshot all flush-only).
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.database import get_session_factory
from app.ingestion.freehire.client import FreehireClient
from app.ingestion.freehire.upserter import FreehireUpserter, IngestionStats
from app.ingestion.snapshots.manager import SnapshotManager

logger = logging.getLogger(__name__)

# MVP windowing: a daily incremental pull of recently posted jobs stays well
# under the API's 10k pagination cap (a full dump of ~2M jobs is impossible).
DEFAULT_SEARCH_PARAMS: dict[str, Any] = {
    "posted_within_days": 2,
    "sort": "posted_at",
    "order": "desc",
}


def seconds_until_next_run(hour_utc: int, now: datetime | None = None) -> float:
    """Seconds from now until the next occurrence of hour_utc:00 UTC."""
    now = now or datetime.now(UTC)
    next_run = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return (next_run - now).total_seconds()


async def run_ingestion_cycle(
    search_params: dict[str, Any] | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    max_jobs: int | None = None,
) -> IngestionStats:
    """Run one full ingestion cycle and commit it as a single unit of work.

    Args:
        search_params: Freehire search filters; defaults to the daily
            incremental window (DEFAULT_SEARCH_PARAMS).
        session_factory: Override for tests/CLI; defaults to the app factory.
        max_jobs: Optional cap on jobs pulled this cycle.

    Returns:
        IngestionStats for the cycle.
    """
    params = search_params if search_params is not None else DEFAULT_SEARCH_PARAMS
    factory = session_factory or get_session_factory()

    async with FreehireClient() as client, factory() as session:
        try:
            upserter = FreehireUpserter(session)
            stats = await upserter.upsert_stream(client.iter_jobs(max_jobs=max_jobs, **params))

            snapshot = await SnapshotManager(session).create_snapshot()
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    logger.info(
        "Ingestion cycle done: inserted=%d updated=%d skipped=%d companies=%d "
        "skills=%d salaries=%d snapshot=%s",
        stats.jobs_inserted,
        stats.jobs_updated,
        stats.jobs_skipped,
        stats.companies_created,
        stats.skills_created,
        stats.salaries_upserted,
        snapshot.snapshot_date,
    )
    if stats.skip_reasons:
        logger.info("Skip reasons: %s", stats.skip_reasons)
    return stats


async def run_scheduler() -> None:
    """Loop forever: sleep until INGESTION_DAILY_HOUR UTC, run a cycle, repeat.

    Cycle errors are logged and swallowed so the scheduler survives transient
    API/DB outages; the next day's run retries naturally.
    """
    settings = get_settings()
    logger.info("Freehire scheduler started (daily at %02d:00 UTC)", settings.INGESTION_DAILY_HOUR)

    while True:
        delay = seconds_until_next_run(settings.INGESTION_DAILY_HOUR)
        logger.info("Next ingestion cycle in %.0f seconds", delay)
        await asyncio.sleep(delay)
        try:
            await run_ingestion_cycle()
        except asyncio.CancelledError:
            logger.info("Freehire scheduler cancelled; shutting down")
            raise
        except Exception:
            logger.exception("Ingestion cycle failed; scheduler keeps running")
