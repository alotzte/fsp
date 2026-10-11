"""profile hidden sections

Revision ID: b7c1e2d4f5a6
Revises: 53b3d4e501e4
Create Date: 2026-10-07 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c1e2d4f5a6"
down_revision: str | None = "53b3d4e501e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidate_profiles",
        sa.Column(
            "hidden_sections",
            postgresql.ARRAY(sa.String(length=16)),
            server_default="{}",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_candidate_profiles_hidden_sections_known"),
        "candidate_profiles",
        "hidden_sections <@ ARRAY['about', 'experience', 'education', 'soft_skills']::varchar[]",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_candidate_profiles_hidden_sections_known"), "candidate_profiles", type_="check"
    )
    op.drop_column("candidate_profiles", "hidden_sections")
