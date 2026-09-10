"""
Profile Model - Structured user profiles parsed from CVs.

Represents a user's professional profile with skills, experience, and preferences.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.profile import ProfileExperience, ProfileSkill


class Profile(Base):
    """
    Structured user profile parsed from CV.

    Attributes:
        id: Internal primary key
        user_id: External user identifier (from auth system)
        email: User email
        full_name: User full name
        headline: Professional headline
        summary: Professional summary
        location: Current location
        work_mode_preference: Preferred work mode (remote, hybrid, onsite)
        years_experience: Total years of experience
        current_role: Current role title
        current_company: Current company name
        target_roles: List of target roles (JSON array)
        target_locations: List of target locations (JSON array)
        target_work_modes: List of acceptable work modes (JSON array)
        salary_expectation_min: Minimum salary expectation (annual USD)
        salary_expectation_max: Maximum salary expectation (annual USD)
        raw_cv_text: Original CV text for reference
        raw_data: Additional parsed data (JSONB)
        created_at: When this record was created
        updated_at: When this record was last updated
    """

    __tablename__ = "profiles"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # User identification
    user_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True, comment="External user ID from auth"
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Professional info
    headline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    work_mode_preference: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="remote, hybrid, onsite"
    )
    years_experience: Mapped[float | None] = mapped_column(nullable=True)
    current_role: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_company: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Target preferences
    target_roles: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    target_locations: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    target_work_modes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    # Salary expectations
    salary_expectation_min: Mapped[Decimal | None] = mapped_column(nullable=True)
    salary_expectation_max: Mapped[Decimal | None] = mapped_column(nullable=True)

    # Original CV
    raw_cv_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Raw data preservation
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    skills: Mapped[list["ProfileSkill"]] = relationship(
        "ProfileSkill", back_populates="profile", lazy="selectin", cascade="all, delete-orphan"
    )
    experience: Mapped[list["ProfileExperience"]] = relationship(
        "ProfileExperience", back_populates="profile", lazy="selectin", cascade="all, delete-orphan"
    )
    analyses: Mapped[list["Analysis"]] = relationship(
        "Analysis", back_populates="profile", lazy="selectin"
    )

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_profiles_user_email", "user_id", "email"),
        Index("ix_profiles_location_experience", "location", "years_experience"),
    )

    def __repr__(self) -> str:
        return f"<Profile(id={self.id}, user_id='{self.user_id}', name='{self.full_name}')>"


class ProfileSkill(Base):
    """
    User's skill with proficiency level.

    Links profile to the normalized skills taxonomy.
    """

    __tablename__ = "profile_skills"

    # Composite primary key
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )

    # Proficiency level (1-5 scale)
    proficiency: Mapped[int] = mapped_column(
        default=3, nullable=False, comment="1=beginner, 2=basic, 3=intermediate, 4=advanced, 5=expert"
    )

    # Years of experience with this skill
    years_experience: Mapped[float | None] = mapped_column(nullable=True)

    # Whether this is a primary/core skill
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Source of this skill (cv, linkedin, manual, inferred)
    source: Mapped[str] = mapped_column(
        String(20), default="cv", nullable=False, comment="cv, linkedin, manual, inferred"
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    profile: Mapped["Profile"] = relationship("Profile", back_populates="skills", lazy="selectin")
    skill: Mapped["Skill"] = relationship("Skill", back_populates="profile_skills", lazy="selectin")

    # Table constraints
    __table_args__ = (
        Index("ix_profile_skills_proficiency", "proficiency"),
        Index("ix_profile_skills_primary", "is_primary"),
    )

    def __repr__(self) -> str:
        return f"<ProfileSkill(profile_id={self.profile_id}, skill_id={self.skill_id}, proficiency={self.proficiency})>"


class ProfileExperience(Base):
    """
    User's work experience record.

    Detailed experience entries linked to skills and roles.
    """

    __tablename__ = "profile_experience"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign key to profile
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Experience details
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    work_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Date range
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Duration in months (computed)
    duration_months: Mapped[int | None] = mapped_column(nullable=True)

    # Skills used in this role (linked to taxonomy)
    skill_ids: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)

    # Role normalization
    normalized_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    profile: Mapped["Profile"] = relationship("Profile", back_populates="experience", lazy="selectin")

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_profile_exp_profile_dates", "profile_id", "start_date", "end_date"),
        Index("ix_profile_exp_role_dates", "role", "start_date"),
    )

    def __repr__(self) -> str:
        return f"<ProfileExperience(id={self.id}, profile_id={self.profile_id}, role='{self.role}')>"