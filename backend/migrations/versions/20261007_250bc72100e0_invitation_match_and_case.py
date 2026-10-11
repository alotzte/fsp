"""invitation match snapshot and case

Revision ID: 250bc72100e0
Revises: 20313012d3a0
Create Date: 2026-10-07 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "250bc72100e0"
down_revision: str | None = "20313012d3a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "invitations",
        sa.Column("match_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("invitations", sa.Column("case_task", sa.Text(), nullable=True))
    op.add_column("invitations", sa.Column("case_answer", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("invitations", "case_answer")
    op.drop_column("invitations", "case_task")
    op.drop_column("invitations", "match_snapshot")
