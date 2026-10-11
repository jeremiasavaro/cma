"""
Freehire Upserter - Idempotent persistence of normalized Freehire records.

Order per record: company -> job -> skills -> job_skills -> salary_observation.
Idempotency keys: Job.external_id, Company.external_id (slug), Skill.name,
(job_id, skill_id) for JobSkill, (job_id, source="posted") for salaries.

Transaction convention (Paso 11): everything here uses flush() only, NEVER
commit() — the commit/rollback boundary belongs to whoever owns the session
(the scheduler cycle or a FastAPI request).
"""

import logging
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.ingestion.freehire.normalizer import (
    NormalizedRecord,
    NormalizedSalaryObservation,
    normalize_job,
)
from app.models.company import Company
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.models.salary_observation import SalaryObservation
from app.models.skill import Skill
from app.repositories import CompanyRepository, JobRepository, SkillRepository

logger = logging.getLogger(__name__)


@dataclass
class IngestionStats:
    """Counters summarizing one ingestion run."""

    jobs_inserted: int = 0
    jobs_updated: int = 0
    jobs_skipped: int = 0
    companies_created: int = 0
    skills_created: int = 0
    salaries_upserted: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)

    def record_skip(self, reason: str) -> None:
        self.jobs_skipped += 1
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1

    def merge(self, other: "IngestionStats") -> None:
        self.jobs_inserted += other.jobs_inserted
        self.jobs_updated += other.jobs_updated
        self.jobs_skipped += other.jobs_skipped
        self.companies_created += other.companies_created
        self.skills_created += other.skills_created
        self.salaries_upserted += other.salaries_upserted
        for reason, count in other.skip_reasons.items():
            self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + count


class FreehireUpserter:
    """Upserts raw Freehire job payloads through the repositories layer."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.jobs = JobRepository(session)
        self.companies = CompanyRepository(session)
        self.skills = SkillRepository(session)
        # Per-run caches so a batch doesn't re-query the same company/skill.
        self._company_cache: dict[str, Company] = {}
        self._skill_cache: dict[str, Skill] = {}

    async def upsert_batch(self, raw_jobs: Iterable[dict[str, Any]]) -> IngestionStats:
        """Normalize and upsert a batch of raw job dicts; returns batch stats."""
        stats = IngestionStats()
        for raw in raw_jobs:
            record, skip_reason = normalize_job(raw)
            if record is None:
                stats.record_skip(skip_reason or "unknown")
                continue
            try:
                # SAVEPOINT per record: a failed flush rolls back only this
                # record instead of poisoning the session for the whole cycle.
                # Commit still belongs exclusively to the session owner.
                async with self.session.begin_nested():
                    await self._upsert_record(record, stats)
            except Exception:
                # One bad record must not poison the batch; log and count it.
                logger.exception(
                    "Failed to upsert job external_id=%s", record.job.external_id
                )
                stats.record_skip("upsert_error")
                # Entities inserted inside the rolled-back SAVEPOINT no longer
                # exist; evict them so later records re-query/re-create them.
                if record.company is not None:
                    self._company_cache.pop(record.company.external_id, None)
                for name in record.skills:
                    self._skill_cache.pop(name, None)
        return stats

    async def upsert_stream(self, raw_jobs: AsyncIterator[dict[str, Any]]) -> IngestionStats:
        """Consume an async iterator of raw jobs in INGESTION_BATCH_SIZE batches."""
        batch_size = get_settings().INGESTION_BATCH_SIZE
        stats = IngestionStats()
        batch: list[dict[str, Any]] = []
        async for raw in raw_jobs:
            batch.append(raw)
            if len(batch) >= batch_size:
                stats.merge(await self.upsert_batch(batch))
                batch.clear()
        if batch:
            stats.merge(await self.upsert_batch(batch))
        return stats

    async def _upsert_record(self, record: NormalizedRecord, stats: IngestionStats) -> None:
        company = await self._get_or_create_company(record, stats)

        job_fields = {
            "title": record.job.title,
            "description": record.job.description,
            "location": record.job.location,
            "work_mode": record.job.work_mode,
            "company_id": company.id if company is not None else None,
            "posted_at": record.job.posted_at,
            "source_url": record.job.source_url,
            "raw_data": record.job.raw_data,
        }

        job = await self.jobs.get_by_external_id(record.job.external_id)
        if job is None:
            job = await self.jobs.create(external_id=record.job.external_id, **job_fields)
            stats.jobs_inserted += 1
        else:
            job = await self.jobs.update(job, **job_fields)
            stats.jobs_updated += 1

        await self._sync_job_skills(job, record.skills, stats)

        if record.salary is not None:
            await self._upsert_salary(job, record.salary, stats)

    async def _get_or_create_company(
        self, record: NormalizedRecord, stats: IngestionStats
    ) -> Company | None:
        if record.company is None:
            return None
        cached = self._company_cache.get(record.company.external_id)
        if cached is not None:
            return cached

        company = await self.companies.get_by_external_id(record.company.external_id)
        if company is None:
            company = await self.companies.create(
                external_id=record.company.external_id,
                name=record.company.name,
                raw_data=record.company.raw_data,
            )
            stats.companies_created += 1
        self._company_cache[record.company.external_id] = company
        return company

    async def _get_or_create_skill(self, name: str, stats: IngestionStats) -> Skill:
        cached = self._skill_cache.get(name)
        if cached is not None:
            return cached

        skill = await self.skills.get_by_name(name)
        if skill is None:
            skill = await self.skills.create(name=name)
            stats.skills_created += 1
        self._skill_cache[name] = skill
        return skill

    async def _sync_job_skills(
        self, job: Job, skill_names: list[str], stats: IngestionStats
    ) -> None:
        """Attach any skills not yet linked to the job (additive, idempotent)."""
        if not skill_names:
            return
        result = await self.session.execute(
            select(JobSkill.skill_id).where(JobSkill.job_id == job.id)
        )
        existing_ids = set(result.scalars().all())

        added = False
        for name in skill_names:
            skill = await self._get_or_create_skill(name, stats)
            if skill.id in existing_ids:
                continue
            self.session.add(JobSkill(job_id=job.id, skill_id=skill.id, source="extracted"))
            existing_ids.add(skill.id)
            added = True
        if added:
            await self.session.flush()

    async def _upsert_salary(
        self, job: Job, salary: NormalizedSalaryObservation, stats: IngestionStats
    ) -> None:
        """One 'posted' observation per job: update it in place if it exists."""
        result = await self.session.execute(
            select(SalaryObservation).where(
                SalaryObservation.job_id == job.id,
                SalaryObservation.source == salary.source,
            )
        )
        observation = result.scalar_one_or_none()
        if observation is None:
            observation = SalaryObservation(job_id=job.id)
            self.session.add(observation)

        observation.min_salary = salary.min_salary
        observation.max_salary = salary.max_salary
        observation.median_salary = salary.median_salary
        observation.currency = salary.currency
        observation.period = salary.period
        observation.source = salary.source
        observation.confidence = salary.confidence
        observation.raw_data = salary.raw_data
        await self.session.flush()
        stats.salaries_upserted += 1
