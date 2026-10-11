"""
Snapshot Manager - Builds daily MarketSnapshot rows from ingested data.

Runs after each ingestion cycle: aggregates the current state of jobs,
companies, skills and salaries into one MarketSnapshot per day (idempotent —
re-running on the same date updates that day's row).

Transaction convention (Paso 11): flush() only, NEVER commit(); the session
owner controls the transaction boundary.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.job_skill import JobSkill
from app.models.market_snapshot import MarketSnapshot
from app.models.salary_observation import SalaryObservation
from app.models.skill import Skill

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

    async def create_snapshot(self, snapshot_date: date | None = None) -> MarketSnapshot:
        """Aggregate current DB state into the snapshot row for the given date.

        Idempotent per day: snapshot_date is unique, so an existing row for the
        date is updated in place instead of violating the constraint.
        """
        snapshot_date = snapshot_date or datetime.now(UTC).date()

        total_jobs = await self.session.scalar(select(func.count(Job.id))) or 0
        total_companies = (
            await self.session.scalar(select(func.count(func.distinct(Job.company_id))))
        ) or 0
        jobs_by_skill = await self._jobs_by_skill()
        jobs_by_location = await self._jobs_by_column(Job.location, _TOP_LOCATIONS)
        jobs_by_work_mode = await self._jobs_by_column(Job.work_mode, limit=None)
        p25, p50, p75 = await self._overall_salary_percentiles()
        salary_by_skill = await self._salary_by_skill()
        salary_by_location = await self._salary_by_location()

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

    async def _jobs_by_skill(self) -> dict[str, int]:
        """Top skills by number of linked jobs."""
        count = func.count(JobSkill.job_id)
        result = await self.session.execute(
            select(Skill.name, count)
            .join(JobSkill, JobSkill.skill_id == Skill.id)
            .group_by(Skill.name)
            .order_by(count.desc())
            .limit(_TOP_SKILLS)
        )
        return {name: int(n) for name, n in result.all()}

    async def _jobs_by_column(self, column: Any, limit: int | None) -> dict[str, int]:
        """Job counts grouped by a nullable Job column (location, work_mode)."""
        count = func.count(Job.id)
        stmt = (
            select(column, count)
            .where(column.is_not(None))
            .group_by(column)
            .order_by(count.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return {value: int(n) for value, n in result.all()}

    async def _overall_salary_percentiles(
        self,
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
        """p25/p50/p75 of normalized median salaries (Postgres percentile_cont)."""
        result = await self.session.execute(
            select(
                func.percentile_cont(0.25).within_group(SalaryObservation.median_salary),
                func.percentile_cont(0.5).within_group(SalaryObservation.median_salary),
                func.percentile_cont(0.75).within_group(SalaryObservation.median_salary),
            ).where(SalaryObservation.median_salary.is_not(None))
        )
        row = result.one_or_none()
        if row is None:
            return None, None, None
        return tuple(Decimal(str(v)) if v is not None else None for v in row)  # type: ignore[return-value]

    async def _salary_by_skill(self) -> dict[str, dict[str, float | int | None]]:
        """Salary percentiles per skill for the skills with most observations."""
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
            .where(SalaryObservation.median_salary.is_not(None))
            .group_by(Skill.name)
            .order_by(count.desc())
            .limit(_TOP_SALARY_GROUPS)
        )
        return {
            name: _percentile_entry(p25, p50, p75, n)
            for name, p25, p50, p75, n in result.all()
        }

    async def _salary_by_location(self) -> dict[str, dict[str, float | int | None]]:
        """Salary percentiles per job location string."""
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
            .where(SalaryObservation.median_salary.is_not(None), Job.location.is_not(None))
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
