"""attempt extensions

Revision ID: 20313012d3a0
Revises: a26d94ef9ffd
Create Date: 2026-10-07 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20313012d3a0"
down_revision: str | None = "a26d94ef9ffd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessment_attempts",
        sa.Column("extensions", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("assessment_attempts", sa.Column("retest_agreement", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("assessment_attempts", "retest_agreement")
    op.drop_column("assessment_attempts", "extensions")
