"""vacancies and applications

Revision ID: d4e5f6a7b8c9
Revises: c3d9a1f0e8b2
Create Date: 2026-10-07 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d9a1f0e8b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hiring_needs", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "invitations",
        sa.Column(
            "direction",
            sa.Enum(
                "employer",
                "candidate",
                name="invitationdirection",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="employer",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.execute("DELETE FROM invitations WHERE direction = 'candidate'")
    op.drop_column("invitations", "direction")
    op.drop_column("hiring_needs", "published_at")
