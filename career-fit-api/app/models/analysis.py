"""
Analysis Model - Analysis request records and results.

Stores analysis requests linking profile to target with computed results.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.profile import Profile


class AnalysisLevel(str, PyEnum):
    """Analysis depth level."""

    BASIC = "basic"
    STANDARD = "standard"
    FULL = "full"


class AnalysisStatus(str, PyEnum):
    """Analysis processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Analysis(Base):
    """
    Analysis request record.

    Links a profile to a target role/location and stores the computed results.

    Attributes:
        id: Internal primary key
        profile_id: Foreign key to Profile
        target_role: Target role name
        target_location: Target location
        target_work_mode: Target work mode
        analysis_level: Depth of analysis (basic, standard, full)
        status: Processing status
        market_fit_score: Overall market fit score (0-100)
        market_fit_details: Detailed breakdown (JSON)
        skill_match_score: Skill match score (0-100)
        experience_match_score: Experience match score (0-100)
        location_match_score: Location match score (0-100)
        total_matching_jobs: Number of matching jobs found
        analyzed_jobs_count: Number of jobs actually analyzed
        salary_p25: 25th percentile salary (annual USD)
        salary_p50: 50th percentile salary (annual USD)
        salary_p75: 75th percentile salary (annual USD)
        salary_confidence: Confidence in salary estimate (0.0-1.0)
        salary_sample_size: Number of salary observations used
        skill_gaps: Missing skills with priority (JSON)
        recommendations: Learning recommendations (JSON)
        unlocked_opportunities: New roles unlocked by learning skills (JSON)
        career_paths: Suggested career paths (JSON)
        confidence_overall: Overall confidence in analysis (0.0-1.0)
        confidence_factors: Factors affecting confidence (JSON)
        error_message: Error message if failed
        processing_time_ms: Processing time in milliseconds
        raw_data: Full raw results (JSONB)
        created_at: When this record was created
        updated_at: When this record was last updated
        completed_at: When analysis completed
    """

    __tablename__ = "analyses"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign key to profile
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Target criteria
    target_role: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    target_location: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    target_work_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Analysis configuration
    analysis_level: Mapped[AnalysisLevel] = mapped_column(
        Enum(AnalysisLevel), default=AnalysisLevel.FULL, nullable=False
    )
    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(AnalysisStatus), default=AnalysisStatus.PENDING, nullable=False, index=True
    )

    # Market fit scores (0-100)
    market_fit_score: Mapped[float | None] = mapped_column(nullable=True)
    market_fit_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    skill_match_score: Mapped[float | None] = mapped_column(nullable=True)
    experience_match_score: Mapped[float | None] = mapped_column(nullable=True)
    location_match_score: Mapped[float | None] = mapped_column(nullable=True)

    # Job matching stats
    total_matching_jobs: Mapped[int] = mapped_column(default=0, nullable=False)
    analyzed_jobs_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Salary estimates (annual USD)
    salary_p25: Mapped[Decimal | None] = mapped_column(nullable=True)
    salary_p50: Mapped[Decimal | None] = mapped_column(nullable=True)
    salary_p75: Mapped[Decimal | None] = mapped_column(nullable=True)
    salary_confidence: Mapped[float | None] = mapped_column(nullable=True)
    salary_sample_size: Mapped[int] = mapped_column(default=0, nullable=False)

    # Results (JSON for flexibility)
    skill_gaps: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    recommendations: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    unlocked_opportunities: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    career_paths: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    # Confidence
    confidence_overall: Mapped[float | None] = mapped_column(nullable=True)
    confidence_factors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Error handling
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Performance
    processing_time_ms: Mapped[int | None] = mapped_column(nullable=True)

    # Raw data preservation
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    profile: Mapped["Profile"] = relationship("Profile", back_populates="analyses", lazy="selectin")
    skill_gaps_detail: Mapped[list["AnalysisSkillGap"]] = relationship(
        "AnalysisSkillGap", back_populates="analysis", lazy="selectin", cascade="all, delete-orphan"
    )
    salary_detail: Mapped[list["AnalysisSalary"]] = relationship(
        "AnalysisSalary", back_populates="analysis", lazy="selectin", cascade="all, delete-orphan"
    )
    recommendations_detail: Mapped[list["AnalysisRecommendation"]] = relationship(
        "AnalysisRecommendation", back_populates="analysis", lazy="selectin", cascade="all, delete-orphan"
    )

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_analyses_profile_created", "profile_id", "created_at"),
        Index("ix_analyses_target_status", "target_role", "target_location", "status"),
        Index("ix_analyses_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Analysis(id={self.id}, profile_id={self.profile_id}, target='{self.target_role}', status='{self.status}')>"


class AnalysisSkillGap(Base):
    """
    Detailed skill gap analysis result.

    Each missing skill with its priority and impact metrics.
    """

    __tablename__ = "analysis_skill_gaps"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign key to analysis
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Skill reference
    skill_id: Mapped[int | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL"), nullable=True, index=True
    )
    skill_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Gap metrics
    priority_score: Mapped[float] = mapped_column(
        nullable=False, comment="Composite priority: demand × match_impact × salary_impact"
    )
    market_demand: Mapped[float] = mapped_column(
        nullable=False, comment="Frequency in target role postings (0-1)"
    )
    match_impact: Mapped[float] = mapped_column(
        nullable=False, comment="How much this skill improves fit score (0-1)"
    )
    salary_impact: Mapped[float] = mapped_column(
        nullable=False, comment="Salary premium associated with this skill (0-1)"
    )
    accessibility: Mapped[float | None] = mapped_column(
        nullable=True, comment="Learning accessibility estimate (0-1)"
    )

    # Context
    jobs_requiring: Mapped[int] = mapped_column(default=0, nullable=False)
    jobs_matching_with: Mapped[int] = mapped_column(default=0, nullable=False)
    unlocked_jobs_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Recommendation
    recommended_action: Mapped[str | None] = mapped_column(String(500), nullable=True)
    learning_resources: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    analysis: Mapped["Analysis"] = relationship("Analysis", back_populates="skill_gaps_detail", lazy="selectin")

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_analysis_gaps_analysis_priority", "analysis_id", "priority_score"),
        Index("ix_analysis_gaps_skill", "skill_id"),
    )

    def __repr__(self) -> str:
        return f"<AnalysisSkillGap(id={self.id}, analysis_id={self.analysis_id}, skill='{self.skill_name}', priority={self.priority_score})>"


class AnalysisSalary(Base):
    """
    Detailed salary analysis result.

    Multiple salary estimates for different scenarios.
    """

    __tablename__ = "analysis_salary"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign key to analysis
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Scenario (current, with_skill_X, target_role, etc.)
    scenario: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    scenario_description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Salary percentiles (annual USD)
    p25: Mapped[Decimal | None] = mapped_column(nullable=True)
    p50: Mapped[Decimal | None] = mapped_column(nullable=True)
    p75: Mapped[Decimal | None] = mapped_column(nullable=True)

    # Confidence metrics
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    sample_size: Mapped[int] = mapped_column(default=0, nullable=False)
    date_range_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_range_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Method used
    method: Mapped[str] = mapped_column(
        String(50), default="percentile", nullable=False, comment="percentile, model, hybrid"
    )

    # Raw data
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    analysis: Mapped["Analysis"] = relationship("Analysis", back_populates="salary_detail", lazy="selectin")

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_analysis_salary_analysis_scenario", "analysis_id", "scenario"),
    )

    def __repr__(self) -> str:
        return f"<AnalysisSalary(id={self.id}, analysis_id={self.analysis_id}, scenario='{self.scenario}', p50={self.p50})>"


class AnalysisRecommendation(Base):
    """
    Detailed recommendation result.

    Actionable recommendations with projected impact.
    """

    __tablename__ = "analysis_recommendations"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign key to analysis
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Recommendation type
    type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="skill, role, location, certification, project"
    )

    # Target
    target_name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_id: Mapped[int | None] = mapped_column(nullable=True, comment="skill_id, role_id, etc.")

    # Impact projections
    fit_score_delta: Mapped[float | None] = mapped_column(nullable=True, comment="Projected fit score change")
    salary_delta_p50: Mapped[Decimal | None] = mapped_column(nullable=True, comment="Projected median salary change")
    unlocked_jobs_delta: Mapped[int] = mapped_column(default=0, nullable=False)

    # Priority and effort
    priority: Mapped[float] = mapped_column(nullable=False, comment="Overall priority score")
    effort_estimate: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="low, medium, high, very_high"
    )
    time_to_acquire: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="e.g., '2-3 months', '6 months'"
    )

    # Details
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    resources: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    analysis: Mapped["Analysis"] = relationship("Analysis", back_populates="recommendations_detail", lazy="selectin")

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_analysis_rec_analysis_priority", "analysis_id", "priority"),
        Index("ix_analysis_rec_type", "type"),
    )

    def __repr__(self) -> str:
        return f"<AnalysisRecommendation(id={self.id}, analysis_id={self.analysis_id}, type='{self.type}', target='{self.target_name}')>"