"""
JobSkill Model - Many-to-many relationship between Jobs and Skills.

Join table enabling co-occurrence analysis, skill frequency, Jaccard similarity.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.skill import Skill


class JobSkill(Base):
    """
    Association between Job and Skill.

    Represents a skill required or mentioned in a job posting.
    Includes context about how the skill was extracted and its importance.

    Attributes:
        job_id: Foreign key to Job
        skill_id: Foreign key to Skill
        source: How this skill was identified (extracted, inferred, normalized)
        confidence: Confidence in this association (0.0-1.0)
        is_required: Whether explicitly marked as required
        context: Surrounding text/context where skill was found
        raw_data: Additional metadata (JSONB)
        created_at: When this record was created
    """

    __tablename__ = "job_skills"

    # Composite primary key
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True, index=True
    )

    # Source of the association
    source: Mapped[str] = mapped_column(
        String(30), default="extracted", nullable=False, comment="extracted, inferred, normalized, manual"
    )

    # Confidence in this association
    confidence: Mapped[float] = mapped_column(default=1.0, nullable=False)

    # Whether explicitly required
    is_required: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)

    # Context snippet
    context: Mapped[str | None] = mapped_column(nullable=True)

    # Raw data preservation
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Audit field
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="skills", lazy="selectin")
    skill: Mapped["Skill"] = relationship("Skill", back_populates="job_skills", lazy="selectin")

    # Table constraints and indexes
    __table_args__ = (
        UniqueConstraint("job_id", "skill_id", name="uq_job_skill"),
        Index("ix_job_skills_skill_required", "skill_id", "is_required"),
        Index("ix_job_skills_source", "source"),
    )

    def __repr__(self) -> str:
        return f"<JobSkill(job_id={self.job_id}, skill_id={self.skill_id}, required={self.is_required})>"