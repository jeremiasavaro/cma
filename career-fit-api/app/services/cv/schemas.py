"""
CV Schemas - Structured profile extracted from a raw CV.

These are internal service-layer models (not API request/response schemas).
CVExtractor.extract() returns a UserProfile built from these pieces.
"""

from pydantic import BaseModel, Field


class Skill(BaseModel):
    """A single normalized skill on a user's profile."""

    name: str = Field(..., description="Canonical skill name from the skills taxonomy")
    years_experience: float | None = Field(
        None, description="Years of experience with this skill, if inferable from the CV"
    )
    # TODO: confirm whether we need a raw/original name field to keep the
    # unnormalized text the LLM extracted, for debugging normalization quality.


class ExperienceRecord(BaseModel):
    """A single work experience entry."""

    company: str
    role: str
    start_date: str | None = Field(None, description="ISO date or free text, e.g. '2021-03'")
    end_date: str | None = Field(None, description="ISO date, free text, or None if current")
    description: str | None = None
    skills_used: list[str] = Field(default_factory=list)
    # TODO: confirm date format/parsing strategy (free text vs. strict ISO) once
    # the extraction prompt is implemented.


class Education(BaseModel):
    """A single education entry."""

    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    end_date: str | None = Field(None, description="Graduation date, ISO date or free text")


class UserProfile(BaseModel):
    """Structured profile extracted from a CV.

    Produced by CVExtractor.extract() and consumed by downstream services
    (MatchingScorer, SalaryEstimator, RecommendationEngine).
    """

    skills: list[Skill] = Field(default_factory=list)
    experience: list[ExperienceRecord] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    seniority: str = Field(..., description="One of: 'junior', 'mid', 'senior', 'lead'")
    industries: list[str] = Field(default_factory=list)
    management_experience: bool = False
