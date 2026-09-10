"""
Models Package - SQLAlchemy 2.0 Models.

All models inherit from app.database.Base.
Import this package to register all models with SQLAlchemy metadata.
"""

from app.models import (
    analysis,
    company,
    job,
    job_role,
    job_skill,
    market_snapshot,
    profile,
    role,
    salary_observation,
    skill,
)

__all__ = [
    "analysis",
    "company",
    "job",
    "job_role",
    "job_skill",
    "market_snapshot",
    "profile",
    "role",
    "salary_observation",
    "skill",
]