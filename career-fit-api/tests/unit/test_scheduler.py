"""Unit tests for app.ingestion.freehire.scheduler.

Two areas:
- seconds_until_next_run timing math: an off-by-one here either skips a day of
  ingestion or runs it twice, so the boundary cases are pinned down exactly.
- run_ingestion_cycle wiring: with client/upserter/snapshot faked out (no DB,
  no network), the cycle must forward search params and max_jobs, honor the
  create_snapshot flag (default True), and always commit on success.
"""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.ingestion.freehire import scheduler
from app.ingestion.freehire.scheduler import run_ingestion_cycle, seconds_until_next_run
from app.ingestion.freehire.upserter import IngestionStats


def test_same_day_future_hour() -> None:
    """Before today's run hour, the delay targets today's occurrence."""
    now = datetime(2026, 10, 11, 1, 30, 0, tzinfo=UTC)

    assert seconds_until_next_run(3, now=now) == 5400.0  # 1.5h to 03:00


def test_rollover_to_next_day() -> None:
    """Past today's run hour, the delay rolls over to tomorrow's occurrence."""
    now = datetime(2026, 10, 11, 4, 0, 0, tzinfo=UTC)

    assert seconds_until_next_run(3, now=now) == 82800.0  # 23h to 03:00 tomorrow


def test_exactly_at_run_hour_waits_a_full_day() -> None:
    """At exactly hour:00:00 the next run is tomorrow, never 0 (no double run)."""
    now = datetime(2026, 10, 11, 3, 0, 0, 0, tzinfo=UTC)

    assert seconds_until_next_run(3, now=now) == 86400.0


@pytest.mark.parametrize("hour_utc", range(24))
def test_result_always_within_one_day(hour_utc: int) -> None:
    """For any target hour the delay is in (0, 86400] — the loop never spins."""
    now = datetime(2026, 10, 11, 13, 47, 23, 500000, tzinfo=UTC)

    delay = seconds_until_next_run(hour_utc, now=now)

    assert 0 < delay <= 86400


# --- run_ingestion_cycle wiring (all internals faked; no DB, no network) -----


class FakeSession:
    """Async-context-manager session that only records commit/rollback calls."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@pytest.fixture
def cycle_fakes(monkeypatch):
    """Patch client/upserter/snapshot in the scheduler module; return a recorder.

    The recorder exposes what iter_jobs was called with, whether a snapshot was
    created, and the FakeSession so tests can assert on commit behavior.
    """
    recorder = SimpleNamespace(iter_kwargs=None, snapshot_calls=0, session=FakeSession())

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def iter_jobs(self, *, max_jobs=None, **filters):
            recorder.iter_kwargs = {"max_jobs": max_jobs, **filters}
            return
            yield  # makes this an async generator that yields nothing

    class FakeUpserter:
        def __init__(self, session):
            pass

        async def upsert_stream(self, stream):
            async for _ in stream:
                pass
            return IngestionStats(jobs_inserted=2)

    class FakeSnapshotManager:
        def __init__(self, session):
            pass

        async def create_snapshot(self):
            recorder.snapshot_calls += 1
            return SimpleNamespace(snapshot_date=date(2026, 10, 11))

    monkeypatch.setattr(scheduler, "FreehireClient", FakeClient)
    monkeypatch.setattr(scheduler, "FreehireUpserter", FakeUpserter)
    monkeypatch.setattr(scheduler, "SnapshotManager", FakeSnapshotManager)
    recorder.session_factory = lambda: recorder.session
    return recorder


async def test_cycle_defaults_create_snapshot_and_commit(cycle_fakes) -> None:
    """Without new args the cycle behaves exactly as before: snapshot + commit."""
    stats = await run_ingestion_cycle(session_factory=cycle_fakes.session_factory)

    assert stats.jobs_inserted == 2
    assert cycle_fakes.snapshot_calls == 1
    assert cycle_fakes.session.committed is True
    # Default query window is the scheduler's incremental pull.
    assert cycle_fakes.iter_kwargs == {"max_jobs": None, **scheduler.DEFAULT_SEARCH_PARAMS}


async def test_cycle_create_snapshot_false_skips_snapshot_but_commits(cycle_fakes) -> None:
    """create_snapshot=False skips the aggregation but still commits the jobs."""
    stats = await run_ingestion_cycle(
        session_factory=cycle_fakes.session_factory, create_snapshot=False
    )

    assert stats.jobs_inserted == 2
    assert cycle_fakes.snapshot_calls == 0
    assert cycle_fakes.session.committed is True
    assert cycle_fakes.session.rolled_back is False


async def test_cycle_forwards_custom_params_and_max_jobs(cycle_fakes) -> None:
    """Custom search_params and max_jobs reach the client's iter_jobs untouched."""
    params = {"skills": ["python"], "posted_within_days": 7}

    await run_ingestion_cycle(
        search_params=params, max_jobs=50, session_factory=cycle_fakes.session_factory
    )

    assert cycle_fakes.iter_kwargs == {"max_jobs": 50, **params}
