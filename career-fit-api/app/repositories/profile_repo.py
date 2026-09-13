"""
Profile Repository - Data access for Profile records.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import Profile
from app.repositories.base import BaseRepository


class ProfileRepository(BaseRepository[Profile]):
    """CRUD access to the profiles table."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.model = Profile

    async def get_by_user_id(self, user_id: str) -> Profile | None:
        """
        Fetch a profile by its external user_id (from the auth system).

        user_id is unique, so this is the standard lookup used to resolve
        "who is this request for" once a user is authenticated.
        """
        result = await self.session.execute(select(Profile).where(Profile.user_id == user_id))
        return result.scalar_one_or_none()
