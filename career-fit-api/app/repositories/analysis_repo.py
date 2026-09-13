"""
Analysis Repository - Data access for Analysis records.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Analysis
from app.repositories.base import BaseRepository


class AnalysisRepository(BaseRepository[Analysis]):
    """CRUD access to the analyses table."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.model = Analysis

    async def list_by_profile(
        self, profile_id: int, limit: int = 50, offset: int = 0
    ) -> list[Analysis]:
        """
        Fetch a profile's analyses, most recent first.

        Used to show a user their analysis history, newest at the top.
        """
        result = await self.session.execute(
            select(Analysis)
            .where(Analysis.profile_id == profile_id)
            .order_by(Analysis.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
