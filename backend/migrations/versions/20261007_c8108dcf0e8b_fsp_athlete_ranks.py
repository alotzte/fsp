"""fsp athlete ranks

Revision ID: c8108dcf0e8b
Revises: a7b8c9d0e1f2
Create Date: 2026-10-07 23:49:35.275867

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8108dcf0e8b"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fsp_athlete_ranks",
        sa.Column("fsp_id", sa.String(length=64), nullable=False),
        sa.Column(
            "rank",
            sa.Enum(
                "third",
                "second",
                "first",
                "cms",
                "ms",
                name="fspsportrank",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("assigned_on", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("fsp_id", name=op.f("pk_fsp_athlete_ranks")),
    )


def downgrade() -> None:
    op.drop_table("fsp_athlete_ranks")
