"""
Company Repository - Data access for Company records.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    """CRUD access to the companies table."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.model = Company

    async def get_by_external_id(self, external_id: str) -> Company | None:
        """
        Fetch a company by its Freehire external_id (the company slug).

        external_id is unique, so this is how ingestion checks whether a
        company already exists before deciding to insert vs. update it.
        """
        result = await self.session.execute(
            select(Company).where(Company.external_id == external_id)
        )
        return result.scalar_one_or_none()
