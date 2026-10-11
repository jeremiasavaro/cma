"""Unit tests for app.ingestion.freehire.scheduler timing math.

seconds_until_next_run decides how long the daily loop sleeps; an off-by-one
here either skips a day of ingestion or runs it twice, so the boundary cases
are pinned down exactly.
"""

from datetime import UTC, datetime

import pytest

from app.ingestion.freehire.scheduler import seconds_until_next_run


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
