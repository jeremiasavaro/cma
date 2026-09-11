"""
Request Schemas - Input validation for API endpoints.

Uses Pydantic for automatic validation and serialization.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from enum import Enum


class WorkMode(str, Enum):
    """Work arrangement options."""
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class Seniority(str, Enum):
    """Seniority levels."""
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"


class AnalysisLevel(str, Enum):
    """Analysis depth levels."""
    BASIC = "basic"
    STANDARD = "standard"
    FULL = "full"


class TargetRole(BaseModel):
    """Target role specification from user."""
    role: str = Field(..., description="Target role title, e.g., 'Senior Backend Engineer'")
    location: Optional[str] = Field(None, description="Country or city")
    work_mode: Optional[WorkMode] = None
    seniority: Optional[Seniority] = None
    skills: List[str] = Field(default_factory=list, description="Required skills for this role")


class AnalysisConfig(BaseModel):
    """Configuration for analysis depth."""
    level: AnalysisLevel = AnalysisLevel.FULL
    include_salary: bool = True
    include_skill_gaps: bool = True
    include_unlocked_opportunities: bool = True
    include_career_paths: bool = False
    include_salary_premiums: bool = True


class AnalyzeRequest(BaseModel):
    """Main analysis request."""
    cv: str = Field(..., min_length=100, description="Full CV text")
    target: TargetRole
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)