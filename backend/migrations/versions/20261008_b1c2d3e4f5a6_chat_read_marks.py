"""chat read marks

Revision ID: b1c2d3e4f5a6
Revises: c8108dcf0e8b
Create Date: 2026-10-08 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "c8108dcf0e8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("invitations", sa.Column("candidate_read_message_id", sa.Integer()))
    op.add_column("invitations", sa.Column("company_read_message_id", sa.Integer()))


def downgrade() -> None:
    op.drop_column("invitations", "company_read_message_id")
    op.drop_column("invitations", "candidate_read_message_id")
