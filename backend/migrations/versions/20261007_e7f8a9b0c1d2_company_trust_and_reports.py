"""company trust and reports

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-10-07 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("trust_level", sa.SmallInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "companies",
        sa.Column("verified_domain", sa.String(length=253), server_default="", nullable=False),
    )
    op.add_column("companies", sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "company_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_user_id", sa.Uuid(), nullable=False),
        sa.Column("invitation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "reason",
            sa.Enum(
                "fake_vacancy",
                "asked_money",
                "terms_differ",
                name="reportreason",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_user_id"],
            ["users.id"],
            name=op.f("fk_company_reports_candidate_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_reports_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invitation_id"],
            ["invitations.id"],
            name=op.f("fk_company_reports_invitation_id_invitations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_reports")),
        sa.UniqueConstraint(
            "company_id",
            "candidate_user_id",
            name=op.f("uq_company_reports_company_id"),
        ),
    )
    op.create_index(
        op.f("ix_company_reports_company_id"), "company_reports", ["company_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_company_reports_company_id"), table_name="company_reports")
    op.drop_table("company_reports")
    op.drop_column("companies", "frozen_at")
    op.drop_column("companies", "verified_domain")
    op.drop_column("companies", "trust_level")
