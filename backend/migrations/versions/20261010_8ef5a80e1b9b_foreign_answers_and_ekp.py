"""foreign answers in attempts, EKP number of FSP events

Revision ID: 8ef5a80e1b9b
Revises: b1c2d3e4f5a6
Create Date: 2026-10-10 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8ef5a80e1b9b"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessment_attempts",
        sa.Column("foreign_answers", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("fsp_events", sa.Column("ekp_number", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("fsp_events", "ekp_number")
    op.drop_column("assessment_attempts", "foreign_answers")
