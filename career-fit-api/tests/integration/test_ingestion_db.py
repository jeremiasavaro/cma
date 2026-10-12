"""Integration tests for the ingestion persistence layer (upserter + snapshots).

These tests run against a real PostgreSQL server but NEVER against the app's
`career_fit` database: a dedicated `career_fit_test` database is (re)created
for the session and dropped afterwards, and every test starts from truncated
tables. When no Postgres is reachable the whole module skips cleanly, so the
suite still passes on machines without Docker.

Connection target defaults to the dockerized dev server
(postgres:postgres@localhost:5432) and can be overridden with
TEST_POSTGRES_HOST / TEST_POSTGRES_PORT (used to verify the skip path).
"""

import asyncio
import os
import socket
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.database import Base
from app.ingestion.freehire.upserter import FreehireUpserter
from app.ingestion.snapshots.manager import SnapshotManager
from app.models.company import Company
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.models.market_snapshot import MarketSnapshot
from app.models.salary_observation import SalaryObservation
from app.models.skill import Skill

_DB_HOST = os.environ.get("TEST_POSTGRES_HOST", "localhost")
_DB_PORT = int(os.environ.get("TEST_POSTGRES_PORT", "5432"))
_TEST_DB_NAME = "career_fit_test"
_ADMIN_URL = f"postgresql+asyncpg://postgres:postgres@{_DB_HOST}:{_DB_PORT}/postgres"
_TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@{_DB_HOST}:{_DB_PORT}/{_TEST_DB_NAME}"

_ALL_TABLES = "job_skills, salary_observations, jobs, companies, skills, market_snapshots"


def _postgres_reachable() -> bool:
    """Short-timeout TCP probe so the module can skip without Docker running."""
    try:
        with socket.create_connection((_DB_HOST, _DB_PORT), timeout=1.5):
            return True
    except OSError:
        return False


if not _postgres_reachable():
    pytest.skip(
        f"No PostgreSQL reachable at {_DB_HOST}:{_DB_PORT} — these tests require "
        "the dockerized Postgres (docker compose up -d db)",
        allow_module_level=True,
    )


async def _create_test_database() -> None:
    """(Re)create career_fit_test and build the schema from the ORM metadata."""
    admin = create_async_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB_NAME} WITH (FORCE)"))
            await conn.execute(text(f"CREATE DATABASE {_TEST_DB_NAME}"))
    finally:
        await admin.dispose()

    engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            import app.models  # noqa: F401  (registers every model on Base.metadata)

            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


async def _drop_test_database() -> None:
    admin = create_async_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB_NAME} WITH (FORCE)"))
    finally:
        await admin.dispose()


@pytest.fixture(scope="session")
def ingestion_test_db() -> Any:
    """Session-scoped, sync fixture: own event loops via asyncio.run.

    Keeping DB create/drop in dedicated loops avoids pytest-asyncio
    cross-loop issues between session- and function-scoped async fixtures.
    """
    asyncio.run(_create_test_database())
    yield _TEST_DB_URL
    asyncio.run(_drop_test_database())


@pytest_asyncio.fixture
async def db_session(ingestion_test_db: str) -> Any:
    """A per-test AsyncSession on truncated tables (NullPool: loop-safe)."""
    engine = create_async_engine(ingestion_test_db, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {_ALL_TABLES} RESTART IDENTITY CASCADE"))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# Raw payload factory
# ---------------------------------------------------------------------------


def make_raw_job(
    external_id: str,
    *,
    title: str = "Backend Engineer",
    company: str | None = "Acme Corp",
    company_slug: str | None = "acme-corp",
    skills: list[str] | None = None,
    location: str = "Remote - Americas",
    salary: tuple[int, int] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """A compact but realistic raw Freehire job dict (live-verified shape)."""
    raw: dict[str, Any] = {
        "external_id": external_id,
        "public_slug": f"{external_id}-slug",
        "title": title,
        "company": company,
        "company_slug": company_slug,
        "location": location,
        "skills": skills if skills is not None else ["python", "postgresql"],
        "description": f"Description for {external_id}.",
        "posted_at": "2026-10-08T12:00:00Z",
        "enriched_at": None,
        "enrichment": None,
    }
    if salary is not None:
        raw["enriched_at"] = "2026-10-09T01:00:00Z"
        raw["enrichment"] = {
            "salary_min": salary[0],
            "salary_max": salary[1],
            "salary_currency": "USD",
            "salary_period": "yearly",
        }
    raw.update(overrides)
    return raw


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


# ---------------------------------------------------------------------------
# Upserter
# ---------------------------------------------------------------------------


async def test_upsert_batch_inserts_new_records(db_session: AsyncSession) -> None:
    """A batch of fresh jobs lands in jobs/companies/skills/job_skills.

    Protects the end-to-end persistence path, including that the salary
    observation is only created for the enriched record.
    """
    batch = [
        make_raw_job("freehire_1", skills=["python"]),
        make_raw_job("freehire_2", skills=["python", "go"]),
        make_raw_job(
            "freehire_3",
            company="Globex",
            company_slug="globex",
            skills=["go"],
            salary=(100_000, 140_000),
        ),
    ]

    stats = await FreehireUpserter(db_session).upsert_batch(batch)
    await db_session.commit()

    assert stats.jobs_inserted == 3
    assert stats.jobs_updated == 0
    assert stats.jobs_skipped == 0
    assert stats.companies_created == 2
    assert stats.skills_created == 2  # python, go
    assert stats.salaries_upserted == 1

    assert await _count(db_session, Job) == 3
    assert await _count(db_session, Company) == 2
    assert await _count(db_session, Skill) == 2
    assert await _count(db_session, JobSkill) == 4
    observations = (await db_session.execute(select(SalaryObservation))).scalars().all()
    assert len(observations) == 1
    assert observations[0].min_salary == Decimal(100_000)
    assert observations[0].max_salary == Decimal(140_000)
    assert observations[0].median_salary == Decimal(120_000)
    assert observations[0].source == "posted"


async def test_upsert_batch_is_idempotent(db_session: AsyncSession) -> None:
    """Running the same batch twice updates in place — no duplicate rows.

    This is the core ingestion guarantee: the daily window overlaps (48h),
    so most records are re-seen and must not inflate any table.
    """
    batch = [
        make_raw_job("freehire_1", skills=["python"]),
        make_raw_job("freehire_2", skills=["python", "go"]),
        make_raw_job("freehire_3", skills=["go"], salary=(100_000, 140_000)),
    ]
    await FreehireUpserter(db_session).upsert_batch(batch)
    await db_session.commit()

    # Fresh upserter = fresh caches: idempotency must come from the DB.
    stats = await FreehireUpserter(db_session).upsert_batch(batch)
    await db_session.commit()

    assert stats.jobs_inserted == 0
    assert stats.jobs_updated == 3
    assert stats.companies_created == 0
    assert stats.skills_created == 0

    assert await _count(db_session, Job) == 3
    assert await _count(db_session, Company) == 1
    assert await _count(db_session, Skill) == 2
    assert await _count(db_session, JobSkill) == 4
    # The salary observation was updated in place, not duplicated.
    assert await _count(db_session, SalaryObservation) == 1


async def test_poison_record_does_not_poison_batch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One record failing at flush rolls back only its SAVEPOINT.

    The normalizer now NUL-strips every text field (including description), so
    no raw payload can make the flush fail on its own. To keep this test
    exercising a REAL Postgres flush failure, normalize_job — as imported by
    the upserter module — is wrapped: for the one marker record it returns a
    NormalizedRecord poisoned post-normalization (a NUL byte injected directly
    into the dataclass title, which Postgres rejects at flush), while every
    other input goes through the real function. The two good records must
    persist and the session must remain fully usable afterwards.
    """
    from app.ingestion.freehire import upserter as upserter_module
    from app.ingestion.freehire.normalizer import NormalizedRecord
    from app.ingestion.freehire.normalizer import normalize_job as real_normalize_job

    def poisoning_normalize_job(raw: Any) -> tuple[NormalizedRecord | None, str | None]:
        record, reason = real_normalize_job(raw)
        if record is not None and record.job.external_id == "freehire_poison":
            record.job.title = "poisoned \x00 title postgres rejects"
        return record, reason

    monkeypatch.setattr(upserter_module, "normalize_job", poisoning_normalize_job)

    batch = [
        make_raw_job("freehire_good_1", skills=["python"]),
        make_raw_job("freehire_poison", company="Evil Corp", company_slug="evil-corp"),
        make_raw_job("freehire_good_2", skills=["go"]),
    ]

    upserter = FreehireUpserter(db_session)
    stats = await upserter.upsert_batch(batch)
    await db_session.commit()

    assert stats.jobs_inserted == 2
    assert stats.jobs_skipped == 1
    assert stats.skip_reasons == {"upsert_error": 1}

    external_ids = set((await db_session.execute(select(Job.external_id))).scalars().all())
    assert external_ids == {"freehire_good_1", "freehire_good_2"}
    # The poison record's company was created inside the rolled-back SAVEPOINT.
    company_slugs = set((await db_session.execute(select(Company.external_id))).scalars().all())
    assert "evil-corp" not in company_slugs

    # The session is not poisoned: a follow-up upsert on it still works.
    stats_after = await upserter.upsert_batch([make_raw_job("freehire_good_3")])
    await db_session.commit()
    assert stats_after.jobs_inserted == 1
    assert await _count(db_session, Job) == 3


async def test_shared_company_and_skills_are_deduped(db_session: AsyncSession) -> None:
    """Two jobs sharing a company and overlapping skills reuse the same rows."""
    batch = [
        make_raw_job("freehire_1", skills=["python", "postgresql"]),
        make_raw_job("freehire_2", skills=["python", "go"]),
    ]

    stats = await FreehireUpserter(db_session).upsert_batch(batch)
    await db_session.commit()

    assert stats.companies_created == 1
    assert await _count(db_session, Company) == 1
    skill_names = sorted((await db_session.execute(select(Skill.name))).scalars().all())
    assert skill_names == ["go", "postgresql", "python"]
    # Both jobs point at the single company row.
    company_ids = set((await db_session.execute(select(Job.company_id))).scalars().all())
    assert len(company_ids) == 1


# ---------------------------------------------------------------------------
# SnapshotManager
# ---------------------------------------------------------------------------


async def test_snapshot_aggregates_and_is_idempotent_per_day(db_session: AsyncSession) -> None:
    """create_snapshot aggregates totals, skill counts and exact percentiles.

    Percentiles are hand-computed for 4 known annual medians
    [100k, 120k, 140k, 160k]: percentile_cont interpolates linearly at rank
    p*(n-1), giving p25=115k (0.75 between 100k and 120k), p50=130k and
    p75=145k (2.25 -> 0.25 between 140k and 160k). Re-running on the same
    date refreshes the single existing row instead of inserting a second one.
    """
    batch = [
        make_raw_job("freehire_1", skills=["python"], salary=(100_000, 100_000)),
        make_raw_job("freehire_2", skills=["python", "go"], salary=(120_000, 120_000)),
        make_raw_job(
            "freehire_3",
            company="Globex",
            company_slug="globex",
            skills=["python"],
            salary=(140_000, 140_000),
        ),
        make_raw_job(
            "freehire_4",
            company="Globex",
            company_slug="globex",
            skills=["go"],
            salary=(160_000, 160_000),
        ),
    ]
    await FreehireUpserter(db_session).upsert_batch(batch)
    manager = SnapshotManager(db_session)
    snapshot_day = date(2026, 10, 10)

    snapshot = await manager.create_snapshot(snapshot_day)
    await db_session.commit()

    assert snapshot.snapshot_date == snapshot_day
    assert snapshot.total_jobs == 4
    assert snapshot.total_companies == 2
    assert snapshot.jobs_by_skill == {"python": 3, "go": 2}
    assert snapshot.jobs_by_work_mode == {"remote": 4}  # "Remote - ..." location
    assert snapshot.salary_p25 == Decimal(115_000)
    assert snapshot.salary_p50 == Decimal(130_000)
    assert snapshot.salary_p75 == Decimal(145_000)
    assert snapshot.salary_by_skill["python"]["count"] == 3
    assert snapshot.salary_by_skill["python"]["p50"] == 120_000.0
    assert snapshot.salary_by_skill["go"]["count"] == 2

    # Add one more (unenriched) job, snapshot the same date again.
    await FreehireUpserter(db_session).upsert_batch([make_raw_job("freehire_5")])
    refreshed = await manager.create_snapshot(snapshot_day)
    await db_session.commit()

    assert await _count(db_session, MarketSnapshot) == 1  # Still exactly one row.
    assert refreshed.id == snapshot.id
    assert refreshed.total_jobs == 5
    # Salary percentiles are unchanged: the new job has no observation.
    assert refreshed.salary_p50 == Decimal(130_000)


async def _seed_recent_and_stale_jobs(db_session: AsyncSession) -> date:
    """Upsert one fresh job and one job last seen 60 days ago; returns today.

    The recent job: Acme, python+postgresql, remote, salary median 100k.
    The stale job: Globex, cobol, Berlin, salary median 200k — everything about
    it is distinct so each snapshot breakdown can prove it was excluded.
    """
    batch = [
        make_raw_job("freehire_recent", skills=["python"], salary=(100_000, 100_000)),
        make_raw_job(
            "freehire_stale",
            company="Globex",
            company_slug="globex",
            skills=["cobol"],
            location="Berlin, Germany",
            salary=(200_000, 200_000),
        ),
    ]
    await FreehireUpserter(db_session).upsert_batch(batch)
    # Age the stale job directly in the DB: ingestion "saw" it 60 days ago.
    await db_session.execute(
        update(Job)
        .where(Job.external_id == "freehire_stale")
        .values(last_seen_at=datetime.now(UTC) - timedelta(days=60))
    )
    return datetime.now(UTC).date()


async def test_snapshot_recency_window_excludes_stale_jobs(db_session: AsyncSession) -> None:
    """A job last seen 60 days ago is excluded from EVERY snapshot aggregate.

    With the default 30-day window only the fresh job counts: totals,
    skill/location breakdowns and all salary percentiles must reflect the
    fresh job alone, with no trace of the stale job's skill (cobol),
    location (Berlin) or salary (200k).
    """
    snapshot_day = await _seed_recent_and_stale_jobs(db_session)

    snapshot = await SnapshotManager(db_session).create_snapshot(snapshot_day)
    await db_session.commit()

    assert snapshot.total_jobs == 1
    assert snapshot.total_companies == 1
    assert snapshot.jobs_by_skill == {"python": 1}
    assert "Berlin, Germany" not in snapshot.jobs_by_location
    # Only the fresh job's 100k median feeds the percentiles.
    assert snapshot.salary_p25 == Decimal(100_000)
    assert snapshot.salary_p50 == Decimal(100_000)
    assert snapshot.salary_p75 == Decimal(100_000)
    assert "cobol" not in snapshot.salary_by_skill
    assert "Berlin, Germany" not in snapshot.salary_by_location
    assert snapshot.salary_by_skill["python"]["count"] == 1


async def test_snapshot_recency_days_parameter_widens_window(db_session: AsyncSession) -> None:
    """recency_days=90 brings the 60-day-old job back into the snapshot."""
    snapshot_day = await _seed_recent_and_stale_jobs(db_session)

    snapshot = await SnapshotManager(db_session).create_snapshot(snapshot_day, recency_days=90)
    await db_session.commit()

    assert snapshot.total_jobs == 2
    assert snapshot.total_companies == 2
    assert snapshot.jobs_by_skill == {"python": 1, "cobol": 1}
    assert snapshot.jobs_by_location["Berlin, Germany"] == 1
    # Both medians [100k, 200k] feed the percentiles: p50 interpolates to 150k.
    assert snapshot.salary_p50 == Decimal(150_000)
    assert snapshot.salary_by_skill["cobol"]["count"] == 1
    assert snapshot.salary_by_location["Berlin, Germany"]["count"] == 1


async def test_reupsert_refreshes_last_seen_at(db_session: AsyncSession) -> None:
    """Re-seeing an existing job bumps last_seen_at even if nothing changed.

    This is what keeps live jobs inside the recency window: the upserter must
    refresh the timestamp on EVERY sighting, not only when a field differs.
    """
    raw = make_raw_job("freehire_1")
    await FreehireUpserter(db_session).upsert_batch([raw])
    await db_session.commit()

    # Pretend the job was last seen 45 days ago (outside the 30-day window).
    await db_session.execute(
        update(Job).values(last_seen_at=datetime.now(UTC) - timedelta(days=45))
    )
    await db_session.commit()

    # Same identical payload re-ingested: the sighting alone must refresh it.
    stats = await FreehireUpserter(db_session).upsert_batch([raw])
    await db_session.commit()
    assert stats.jobs_updated == 1

    last_seen = await db_session.scalar(select(Job.last_seen_at))
    assert last_seen is not None
    assert last_seen >= datetime.now(UTC) - timedelta(minutes=5)

    # And the job counts again in a fresh snapshot.
    snapshot = await SnapshotManager(db_session).create_snapshot()
    await db_session.commit()
    assert snapshot.total_jobs == 1


async def test_snapshot_temporal_helpers(db_session: AsyncSession) -> None:
    """get_by_date / get_latest / list_range return the right rows in order."""
    manager = SnapshotManager(db_session)
    d1, d2, d3 = date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)
    # Created out of order on purpose: ordering must come from queries.
    for day in (d3, d1, d2):
        await manager.create_snapshot(day)
    await db_session.commit()

    by_date = await manager.get_by_date(d2)
    assert by_date is not None
    assert by_date.snapshot_date == d2
    assert await manager.get_by_date(date(2025, 1, 1)) is None

    latest = await manager.get_latest()
    assert latest is not None
    assert latest.snapshot_date == d3

    in_range = await manager.list_range(d1, d2)
    assert [snap.snapshot_date for snap in in_range] == [d1, d2]
    full_range = await manager.list_range(d1, d3)
    assert [snap.snapshot_date for snap in full_range] == [d1, d2, d3]
