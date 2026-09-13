"""
Job Repository - Data access for Job records.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    """CRUD access to the jobs table."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.model = Job

    async def get_by_external_id(self, external_id: str) -> Job | None:
        """
        Fetch a job by its Freehire external_id.

        external_id is unique, so this is how ingestion checks whether a job
        posting already exists before deciding to insert vs. update it.
        """
        result = await self.session.execute(select(Job).where(Job.external_id == external_id))
        return result.scalar_one_or_none()
