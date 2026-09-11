"""
Response Schemas - Output validation for API endpoints.

Defines the exact structure of API responses.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime


class SkillGap(BaseModel):
    """Missing skill with priority information."""
    skill: str
    market_frequency: float = Field(ge=0, le=1, description="How often this skill appears in target market")
    importance: Literal["high", "medium", "low"]
    priority: float = Field(ge=0, le=1, description="Combined priority score")
    estimated_learning_weeks: Optional[int] = None


class SalaryEstimate(BaseModel):
    """Salary estimation with confidence."""
    currency: str = "USD"
    p25: int = Field(description="25th percentile (annual)")
    median: int = Field(description="50th percentile (annual)")
    p75: int = Field(description="75th percentile (annual)")
    confidence: Literal["high", "medium", "low"]
    sample_size: int = Field(description="Number of job postings used")


class MarketFit(BaseModel):
    """Market fit scores."""
    current: float = Field(ge=0, le=1, description="Current fit score")
    potential: float = Field(ge=0, le=1, description="Potential fit if gaps filled")
    breakdown: Dict[str, float] = Field(description="Component scores: skills, experience, seniority, etc.")


class UnlockedOpportunity(BaseModel):
    """Additional jobs unlocked by learning a skill."""
    skill: str
    additional_compatible_jobs: int
    relative_increase: float


class SalaryPremium(BaseModel):
    """Salary premium associated with a skill."""
    skill: str
    premium_pct: float
    confidence: Literal["high", "medium", "low"]
    sample_size: int


class CareerPath(BaseModel):
    """Potential career progression."""
    role: str
    market_fit: float
    missing_skills: List[str]
    salary_median: int


class AnalyzeResponse(BaseModel):
    """Complete analysis response."""
    profile_id: str
    target_role: str
    market_fit: MarketFit
    skill_gaps: List[SkillGap]
    salary: SalaryEstimate
    salary_premiums: List[SalaryPremium]
    unlocked_opportunities: List[UnlockedOpportunity]
    career_paths: List[CareerPath] = []
    confidence: Dict[str, str]
    metadata: Dict[str, Any]
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)