"""add last_seen_at to jobs

Revision ID: b7d3e5a19c42
Revises: 3c75f2d39e4f
Create Date: 2026-10-11 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7d3e5a19c42'
down_revision: str | Sequence[str] | None = '3c75f2d39e4f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add jobs.last_seen_at: last time ingestion saw the job in the API.

    Existing rows are backfilled to now() via a temporary server_default;
    the default is then dropped because, like created_at/updated_at, this
    column's value is always set by the application, not the database.
    """
    op.add_column(
        'jobs',
        sa.Column(
            'last_seen_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='Last time ingestion saw this job in the Freehire API',
        ),
    )
    op.alter_column('jobs', 'last_seen_at', server_default=None)
    op.create_index(op.f('ix_jobs_last_seen_at'), 'jobs', ['last_seen_at'], unique=False)


def downgrade() -> None:
    """Remove jobs.last_seen_at and its index."""
    op.drop_index(op.f('ix_jobs_last_seen_at'), table_name='jobs')
    op.drop_column('jobs', 'last_seen_at')
