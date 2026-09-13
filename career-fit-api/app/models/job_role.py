"""
JobRole Model - Many-to-many relationship between Jobs and Roles.

Join table linking a job posting to its normalized role(s), enabling
role-based aggregation and analysis (e.g., salary by role, demand by role).
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.role import Role


class JobRole(Base):
    """
    Association between Job and Role.

    Represents the normalized role a job posting was classified into.
    Includes context about how the role was assigned and its confidence.

    Attributes:
        job_id: Foreign key to Job
        role_id: Foreign key to Role
        source: How this role was identified (extracted, inferred, normalized, manual)
        confidence: Confidence in this association (0.0-1.0)
        context: Surrounding text/context used to assign the role
        raw_data: Additional metadata (JSONB)
        created_at: When this record was created
    """

    __tablename__ = "job_roles"

    # Composite primary key
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True, index=True
    )

    # Source of the association
    source: Mapped[str] = mapped_column(
        String(30), default="extracted", nullable=False, comment="extracted, inferred, normalized, manual"
    )

    # Confidence in this association
    confidence: Mapped[float] = mapped_column(default=1.0, nullable=False)

    # Context snippet
    context: Mapped[str | None] = mapped_column(nullable=True)

    # Raw data preservation
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Audit field
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="roles", lazy="selectin")
    role: Mapped["Role"] = relationship("Role", back_populates="job_roles", lazy="selectin")

    # Table constraints and indexes
    __table_args__ = (
        UniqueConstraint("job_id", "role_id", name="uq_job_role"),
        Index("ix_job_roles_source", "source"),
    )

    def __repr__(self) -> str:
        return f"<JobRole(job_id={self.job_id}, role_id={self.role_id}, source='{self.source}')>"
