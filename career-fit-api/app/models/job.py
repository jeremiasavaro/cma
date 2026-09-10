"""
Job Model - Raw job postings ingested from Freehire.

Represents a single job posting with all its raw data preserved.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.job_role import JobRole
    from app.models.job_skill import JobSkill
    from app.models.salary_observation import SalaryObservation


class Job(Base):
    """
    Job posting from Freehire API.

    Attributes:
        id: Internal primary key
        external_id: Unique identifier from Freehire (e.g., "freehire_12345")
        title: Job title as posted
        description: Full job description text
        location: Job location (city, state, country, or "Remote")
        work_mode: Work arrangement (remote, hybrid, onsite)
        company_id: Foreign key to Company
        posted_at: When the job was originally posted
        source_url: Original job posting URL
        raw_data: Complete original API response (JSONB) for reprocessing
        created_at: When this record was created in our DB
        updated_at: When this record was last updated
    """

    __tablename__ = "jobs"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Freehire unique identifier
    external_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique ID from Freehire API",
    )

    # Core job fields
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    work_mode: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True, comment="remote, hybrid, onsite"
    )

    # Foreign key to company
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Timestamps
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Raw data preservation for reprocessing
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
    company: Mapped["Company"] = relationship(
        "Company", back_populates="jobs", lazy="selectin"
    )
    skills: Mapped[list["JobSkill"]] = relationship(
        "JobSkill", back_populates="job", lazy="selectin", cascade="all, delete-orphan"
    )
    roles: Mapped[list["JobRole"]] = relationship(
        "JobRole", back_populates="job", lazy="selectin", cascade="all, delete-orphan"
    )
    salary_observations: Mapped[list["SalaryObservation"]] = relationship(
        "SalaryObservation", back_populates="job", lazy="selectin", cascade="all, delete-orphan"
    )

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_jobs_title_location", "title", "location"),
        Index("ix_jobs_company_posted", "company_id", "posted_at"),
        Index("ix_jobs_work_mode_posted", "work_mode", "posted_at"),
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, title='{self.title}', company_id={self.company_id})>"