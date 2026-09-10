"""
Skill Model - Skill taxonomy with normalized names and aliases.

Central skill dictionary enabling normalization across job postings and user profiles.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.job_skill import JobSkill
    from app.models.profile import ProfileSkill


class Skill(Base):
    """
    Normalized skill entity.

    Enables mapping of variants like "Ruby on Rails", "Rails", "RoR" to a single skill.
    Used by both market data (jobs) and user profiles for direct comparison.

    Attributes:
        id: Internal primary key
        name: Canonical skill name (e.g., "Python", "React", "AWS")
        category: Skill category (e.g., "programming", "framework", "cloud", "database", "tool", "soft")
        aliases: List of alternative names/variants (JSON array)
        description: Skill description
        is_active: Whether this skill is actively used
        raw_data: Additional metadata (JSONB)
        created_at: When this record was created
        updated_at: When this record was last updated
    """

    __tablename__ = "skills"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Canonical skill name - unique for normalization
    name: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
        index=True,
        comment="Canonical skill name",
    )

    # Skill categorization
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True, comment="programming, framework, cloud, database, tool, soft"
    )

    # Aliases for normalization (e.g., ["Rails", "RoR", "Ruby on Rails"])
    aliases: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    # Additional info
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)

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
    job_skills: Mapped[list["JobSkill"]] = relationship(
        "JobSkill", back_populates="skill", lazy="selectin"
    )
    profile_skills: Mapped[list["ProfileSkill"]] = relationship(
        "ProfileSkill", back_populates="skill", lazy="selectin"
    )

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_skills_category_active", "category", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, name='{self.name}', category='{self.category}')>"