"""
Market Snapshot Model - Periodic snapshots of market state.

Daily snapshots enable temporal analysis: skill demand trends, salary evolution, role emergence/decline.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MarketSnapshot(Base):
    """
    Daily market snapshot for temporal analysis.

    Captures aggregated market state at a point in time.
    Enables trend detection: skill demand, salary evolution, role emergence/decline.

    Attributes:
        id: Internal primary key
        snapshot_date: Date of the snapshot (one per day)
        total_jobs: Total jobs in snapshot
        total_companies: Total unique companies
        jobs_by_role: JSON mapping role -> job count
        jobs_by_skill: JSON mapping skill -> job count
        jobs_by_location: JSON mapping location -> job count
        jobs_by_work_mode: JSON mapping work_mode -> job count
        salary_p25: 25th percentile salary (annual USD)
        salary_p50: 50th percentile salary (annual USD)
        salary_p75: 75th percentile salary (annual USD)
        salary_by_role: JSON mapping role -> {p25, p50, p75, count}
        salary_by_skill: JSON mapping skill -> {p25, p50, p75, count}
        salary_by_location: JSON mapping location -> {p25, p50, p75, count}
        raw_data: Additional aggregated metrics (JSONB)
        created_at: When this record was created
    """

    __tablename__ = "market_snapshots"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Snapshot date (one per day)
    snapshot_date: Mapped[date] = mapped_column(
        Date, unique=True, nullable=False, index=True, comment="Date of snapshot (UTC)"
    )

    # Volume metrics
    total_jobs: Mapped[int] = mapped_column(default=0, nullable=False)
    total_companies: Mapped[int] = mapped_column(default=0, nullable=False)

    # Distribution breakdowns (JSON for flexibility)
    jobs_by_role: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    jobs_by_skill: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    jobs_by_location: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    jobs_by_work_mode: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Salary percentiles (annual USD)
    salary_p25: Mapped[Decimal | None] = mapped_column(nullable=True)
    salary_p50: Mapped[Decimal | None] = mapped_column(nullable=True)
    salary_p75: Mapped[Decimal | None] = mapped_column(nullable=True)

    # Salary breakdowns
    salary_by_role: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    salary_by_skill: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    salary_by_location: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Raw data preservation
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Audit field
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_market_snapshots_date_desc", "snapshot_date"),
    )

    def __repr__(self) -> str:
        return f"<MarketSnapshot(id={self.id}, date={self.snapshot_date}, jobs={self.total_jobs})>"