"""
Company Model - Company profiles extracted from job postings.

Represents a company with its metadata and aggregated information.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.job import Job


class Company(Base):
    """
    Company profile aggregated from job postings.

    Attributes:
        id: Internal primary key
        external_id: Unique identifier from Freehire
        name: Company name
        description: Company description
        website: Company website URL
        logo_url: Company logo URL
        size: Company size range (e.g., "1-10", "11-50", "51-200", "201-500", "501-1000", "1000+")
        industry: Industry sector
        headquarters: Headquarters location
        raw_data: Complete original API response (JSONB) for reprocessing
        created_at: When this record was created in our DB
        updated_at: When this record was last updated
    """

    __tablename__ = "companies"

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

    # Core company fields
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    headquarters: Mapped[str | None] = mapped_column(String(200), nullable=True)

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
    jobs: Mapped[list["Job"]] = relationship(
        "Job", back_populates="company", lazy="selectin"
    )

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_companies_name_industry", "name", "industry"),
        Index("ix_companies_size_industry", "size", "industry"),
    )

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name='{self.name}', size='{self.size}')>"