"""
Skill Repository - Data access for Skill records.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill
from app.repositories.base import BaseRepository


class SkillRepository(BaseRepository[Skill]):
    """CRUD access to the skills table."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.model = Skill

    async def get_by_name(self, name: str) -> Skill | None:
        """Fetch a skill by its canonical, unique name."""
        result = await self.session.execute(select(Skill).where(Skill.name == name))
        return result.scalar_one_or_none()

    async def list_active(self, limit: int = 50, offset: int = 0) -> list[Skill]:
        """Fetch a page of skills that are currently active (is_active == True)."""
        result = await self.session.execute(
            select(Skill).where(Skill.is_active.is_(True)).limit(limit).offset(offset)
        )
        return list(result.scalars().all())
