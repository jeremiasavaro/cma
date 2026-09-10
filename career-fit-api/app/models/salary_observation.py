"""
Salary Observation Model - Normalized salary data points.

Each observation represents a single salary data point from a job posting,
normalized to annual USD for comparison.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.job import Job


class SalaryObservation(Base):
    """
    Normalized salary observation from a job posting.

    All salaries are converted to annual USD for consistent comparison.
    Original values are preserved in raw_data.

    Attributes:
        id: Internal primary key
        job_id: Foreign key to Job
        min_salary: Minimum annual salary in USD (normalized)
        max_salary: Maximum annual salary in USD (normalized)
        median_salary: Median/expected annual salary in USD (normalized)
        currency: Original currency code (e.g., "USD", "EUR", "GBP")
        period: Original period (e.g., "yearly", "monthly", "hourly")
        source: Source of salary data (e.g., "posted", "estimated", "glassdoor")
        confidence: Confidence score for this observation (0.0-1.0)
        raw_data: Original salary data from API (JSONB)
        created_at: When this record was created
        updated_at: When this record was last updated
    """

    __tablename__ = "salary_observations"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign key to job
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Normalized annual USD values
    min_salary: Mapped[Decimal | None] = mapped_column(
        nullable=True, comment="Minimum annual salary in USD"
    )
    max_salary: Mapped[Decimal | None] = mapped_column(
        nullable=True, comment="Maximum annual salary in USD"
    )
    median_salary: Mapped[Decimal | None] = mapped_column(
        nullable=True, comment="Median/expected annual salary in USD"
    )

    # Original values for traceability
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", index=True, comment="Original currency code"
    )
    period: Mapped[str] = mapped_column(
        String(20), nullable=False, default="yearly", index=True, comment="Original period: yearly, monthly, hourly"
    )
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default="posted", index=True, comment="posted, estimated, glassdoor, etc."
    )

    # Quality indicator
    confidence: Mapped[float] = mapped_column(
        default=1.0, nullable=False, comment="Confidence in normalization (0.0-1.0)"
    )

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
    job: Mapped["Job"] = relationship("Job", back_populates="salary_observations", lazy="selectin")

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_salary_obs_job_currency", "job_id", "currency"),
        Index("ix_salary_obs_currency_period", "currency", "period"),
        Index("ix_salary_obs_median", "median_salary"),
    )

    def __repr__(self) -> str:
        return f"<SalaryObservation(id={self.id}, job_id={self.job_id}, median={self.median_salary} USD)>"