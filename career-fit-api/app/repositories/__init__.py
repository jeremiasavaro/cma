"""
Repositories Package - Async CRUD data access for SQLAlchemy models.

Each concrete repository wraps a single model with basic create/read/update/
delete plus a few lookups by unique or foreign-key fields. Import this
package to access all repository classes from one place.
"""

from app.repositories.analysis_repo import AnalysisRepository
from app.repositories.base import BaseRepository
from app.repositories.job_repo import JobRepository
from app.repositories.profile_repo import ProfileRepository
from app.repositories.skill_repo import SkillRepository

__all__ = [
    "AnalysisRepository",
    "BaseRepository",
    "JobRepository",
    "ProfileRepository",
    "SkillRepository",
]
