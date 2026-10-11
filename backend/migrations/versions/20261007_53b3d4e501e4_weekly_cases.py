"""weekly cases

Revision ID: 53b3d4e501e4
Revises: 250bc72100e0
Create Date: 2026-10-07 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "53b3d4e501e4"
down_revision: str | None = "250bc72100e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weekly_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("week", sa.Date(), nullable=False),
        sa.Column("specialization_id", sa.Integer(), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column("competency_title", sa.String(length=128), nullable=False),
        sa.Column("a", sa.Float(), nullable=False),
        sa.Column("b", sa.Float(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "choice",
                "text",
                name="itemkind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("options", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["specialization_id"],
            ["specializations.id"],
            name=op.f("fk_weekly_cases_specialization_id_specializations"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_weekly_cases_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weekly_cases")),
        sa.UniqueConstraint("user_id", "week", name=op.f("uq_weekly_cases_user_id")),
    )
    op.create_index(op.f("ix_weekly_cases_user_id"), "weekly_cases", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_weekly_cases_user_id"), table_name="weekly_cases")
    op.drop_table("weekly_cases")
