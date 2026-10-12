"""
Snapshot Manager - Builds daily MarketSnapshot rows from ingested data.

Runs after each ingestion cycle: aggregates the current state of jobs,
companies, skills and salaries into one MarketSnapshot per day (idempotent —
re-running on the same date updates that day's row).

Recency window: a snapshot is a photo of the market "as of" its date, so it
only counts jobs ingestion saw recently (Job.last_seen_at within the last
DEFAULT_RECENCY_DAYS days before the snapshot date). Without this, dead
postings would inflate every snapshot forever.

Transaction convention (Paso 11): flush() only, NEVER commit(); the session
owner controls the transaction boundary.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.job_skill import JobSkill
from app.models.market_snapshot import MarketSnapshot
from app.models.salary_observation import SalaryObservation
from app.models.skill import Skill

# A job counts toward a snapshot only if ingestion saw it within this many
# days before the snapshot date (sliding window over Job.last_seen_at).
DEFAULT_RECENCY_DAYS = 30

# Keep JSONB breakdowns bounded.
_TOP_SKILLS = 50
_TOP_LOCATIONS = 50
_TOP_SALARY_GROUPS = 20


def _to_float(value: Decimal | float | None) -> float | None:
    """Decimals are not JSON-serializable; JSONB breakdowns store floats."""
    return float(value) if value is not None else None


def _percentile_entry(p25: Any, p50: Any, p75: Any, n: Any) -> dict[str, float | int | None]:
    """One {p25, p50, p75, count} JSONB entry with JSON-safe numeric types."""
    return {"p25": _to_float(p25), "p50": _to_float(p50), "p75": _to_float(p75), "count": int(n)}


class SnapshotManager:
    """Creates and queries MarketSnapshot rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_snapshot(
        self,
        snapshot_date: date | None = None,
        recency_days: int = DEFAULT_RECENCY_DAYS,
    ) -> MarketSnapshot:
        """Aggregate recently-seen jobs into the snapshot row for the given date.

        The snapshot is a photo of the market "as of" snapshot_date: every
        aggregate (totals, breakdowns, salary percentiles) counts only jobs
        whose last_seen_at falls within the last `recency_days` days before
        that date, so postings that vanished from the API age out instead of
        inflating the numbers forever. Older snapshots are never touched.

        Idempotent per day: snapshot_date is unique, so an existing row for the
        date is updated in place instead of violating the constraint.
        """
        snapshot_date = snapshot_date or datetime.now(UTC).date()
        # Jobs count only if ingestion saw them on/after this moment (UTC).
        cutoff = datetime.combine(snapshot_date, time.min, tzinfo=UTC) - timedelta(
            days=recency_days
        )

        total_jobs = (
            await self.session.scalar(
                select(func.count(Job.id)).where(Job.last_seen_at >= cutoff)
            )
        ) or 0
        total_companies = (
            await self.session.scalar(
                select(func.count(func.distinct(Job.company_id))).where(
                    Job.last_seen_at >= cutoff
                )
            )
        ) or 0
        jobs_by_skill = await self._jobs_by_skill(cutoff)
        jobs_by_location = await self._jobs_by_column(Job.location, _TOP_LOCATIONS, cutoff)
        jobs_by_work_mode = await self._jobs_by_column(Job.work_mode, None, cutoff)
        p25, p50, p75 = await self._overall_salary_percentiles(cutoff)
        salary_by_skill = await self._salary_by_skill(cutoff)
        salary_by_location = await self._salary_by_location(cutoff)

        fields: dict[str, Any] = {
            "total_jobs": total_jobs,
            "total_companies": total_companies,
            # jobs_by_role / salary_by_role stay None: role tagging is not
            # part of ingestion yet (JobRole rows are produced downstream).
            "jobs_by_role": None,
            "jobs_by_skill": jobs_by_skill,
            "jobs_by_location": jobs_by_location,
            "jobs_by_work_mode": jobs_by_work_mode,
            "salary_p25": p25,
            "salary_p50": p50,
            "salary_p75": p75,
            "salary_by_role": None,
            "salary_by_skill": salary_by_skill,
            "salary_by_location": salary_by_location,
        }

        snapshot = await self.get_by_date(snapshot_date)
        if snapshot is None:
            snapshot = MarketSnapshot(snapshot_date=snapshot_date, **fields)
            self.session.add(snapshot)
        else:
            for key, value in fields.items():
                setattr(snapshot, key, value)
        await self.session.flush()
        await self.session.refresh(snapshot)
        return snapshot

    # ------------------------------------------------------------------
    # Aggregation queries
    # ------------------------------------------------------------------

    async def _jobs_by_skill(self, cutoff: datetime) -> dict[str, int]:
        """Top skills by number of linked jobs seen since the cutoff."""
        count = func.count(JobSkill.job_id)
        result = await self.session.execute(
            select(Skill.name, count)
            .join(JobSkill, JobSkill.skill_id == Skill.id)
            .join(Job, Job.id == JobSkill.job_id)
            .where(Job.last_seen_at >= cutoff)
            .group_by(Skill.name)
            .order_by(count.desc())
            .limit(_TOP_SKILLS)
        )
        return {name: int(n) for name, n in result.all()}

    async def _jobs_by_column(
        self, column: Any, limit: int | None, cutoff: datetime
    ) -> dict[str, int]:
        """Recent-job counts grouped by a nullable Job column (location, work_mode)."""
        count = func.count(Job.id)
        stmt = (
            select(column, count)
            .where(column.is_not(None), Job.last_seen_at >= cutoff)
            .group_by(column)
            .order_by(count.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return {value: int(n) for value, n in result.all()}

    async def _overall_salary_percentiles(
        self, cutoff: datetime
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
        """p25/p50/p75 of median salaries of recent jobs (percentile_cont)."""
        result = await self.session.execute(
            select(
                func.percentile_cont(0.25).within_group(SalaryObservation.median_salary),
                func.percentile_cont(0.5).within_group(SalaryObservation.median_salary),
                func.percentile_cont(0.75).within_group(SalaryObservation.median_salary),
            )
            .select_from(SalaryObservation)
            .join(Job, Job.id == SalaryObservation.job_id)
            .where(
                SalaryObservation.median_salary.is_not(None),
                Job.last_seen_at >= cutoff,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None, None, None
        return tuple(Decimal(str(v)) if v is not None else None for v in row)  # type: ignore[return-value]

    async def _salary_by_skill(
        self, cutoff: datetime
    ) -> dict[str, dict[str, float | int | None]]:
        """Salary percentiles per skill, over recent jobs' observations only."""
        count = func.count(SalaryObservation.id)
        result = await self.session.execute(
            select(
                Skill.name,
                func.percentile_cont(0.25).within_group(SalaryObservation.median_salary),
                func.percentile_cont(0.5).within_group(SalaryObservation.median_salary),
                func.percentile_cont(0.75).within_group(SalaryObservation.median_salary),
                count,
            )
            .join(JobSkill, JobSkill.skill_id == Skill.id)
            .join(SalaryObservation, SalaryObservation.job_id == JobSkill.job_id)
            .join(Job, Job.id == SalaryObservation.job_id)
            .where(
                SalaryObservation.median_salary.is_not(None),
                Job.last_seen_at >= cutoff,
            )
            .group_by(Skill.name)
            .order_by(count.desc())
            .limit(_TOP_SALARY_GROUPS)
        )
        return {
            name: _percentile_entry(p25, p50, p75, n)
            for name, p25, p50, p75, n in result.all()
        }

    async def _salary_by_location(
        self, cutoff: datetime
    ) -> dict[str, dict[str, float | int | None]]:
        """Salary percentiles per location, over recent jobs only."""
        count = func.count(SalaryObservation.id)
        result = await self.session.execute(
            select(
                Job.location,
                func.percentile_cont(0.25).within_group(SalaryObservation.median_salary),
                func.percentile_cont(0.5).within_group(SalaryObservation.median_salary),
                func.percentile_cont(0.75).within_group(SalaryObservation.median_salary),
                count,
            )
            .join(SalaryObservation, SalaryObservation.job_id == Job.id)
            .where(
                SalaryObservation.median_salary.is_not(None),
                Job.location.is_not(None),
                Job.last_seen_at >= cutoff,
            )
            .group_by(Job.location)
            .order_by(count.desc())
            .limit(_TOP_SALARY_GROUPS)
        )
        return {
            loc: _percentile_entry(p25, p50, p75, n)
            for loc, p25, p50, p75, n in result.all()
        }

    # ------------------------------------------------------------------
    # Temporal query helpers
    # ------------------------------------------------------------------

    async def get_by_date(self, snapshot_date: date) -> MarketSnapshot | None:
        """Fetch the snapshot for a specific date, or None."""
        result = await self.session.execute(
            select(MarketSnapshot).where(MarketSnapshot.snapshot_date == snapshot_date)
        )
        return result.scalar_one_or_none()

    async def get_latest(self) -> MarketSnapshot | None:
        """Fetch the most recent snapshot, or None if none exist."""
        result = await self.session.execute(
            select(MarketSnapshot).order_by(MarketSnapshot.snapshot_date.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def list_range(self, start: date, end: date) -> list[MarketSnapshot]:
        """Fetch snapshots with start <= snapshot_date <= end, oldest first."""
        result = await self.session.execute(
            select(MarketSnapshot)
            .where(MarketSnapshot.snapshot_date >= start, MarketSnapshot.snapshot_date <= end)
            .order_by(MarketSnapshot.snapshot_date.asc())
        )
        return list(result.scalars().all())
