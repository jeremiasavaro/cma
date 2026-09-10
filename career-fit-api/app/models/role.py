"""
Role Model - Role families and normalized titles.

Represents normalized role categories (e.g., "Backend Engineer", "Data Scientist")
that group similar job titles together.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.job_role import JobRole


class Role(Base):
    """
    Normalized role family / title.

    Groups similar job titles into canonical roles for analysis.
    E.g., "Backend Engineer", "Backend Developer", "Server-Side Engineer" → "Backend Engineer"

    Attributes:
        id: Internal primary key
        name: Canonical role name (e.g., "Backend Engineer", "Data Scientist")
        category: Role category (e.g., "engineering", "data", "design", "product", "management")
        level: Seniority level (e.g., "junior", "mid", "senior", "lead", "principal", "staff")
        aliases: List of alternative titles (JSON array)
        description: Role description
        is_active: Whether this role is actively used
        raw_data: Additional metadata (JSONB)
        created_at: When this record was created
        updated_at: When this record was last updated
    """

    __tablename__ = "roles"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Canonical role name
    name: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
        index=True,
        comment="Canonical role name",
    )

    # Role categorization
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True, comment="engineering, data, design, product, management"
    )
    level: Mapped[str | None] = mapped_column(
        String(30), nullable=True, index=True, comment="junior, mid, senior, lead, principal, staff"
    )

    # Aliases for normalization
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
    job_roles: Mapped[list["JobRole"]] = relationship(
        "JobRole", back_populates="role", lazy="selectin"
    )

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_roles_category_level", "category", "level"),
        Index("ix_roles_category_active", "category", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name='{self.name}', category='{self.category}', level='{self.level}')>"