"""fsp data consent

Revision ID: c3d9a1f0e8b2
Revises: b7c1e2d4f5a6
Create Date: 2026-10-07 11:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3d9a1f0e8b2"
down_revision: str | None = "b7c1e2d4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "ck_consents_consentkind"


def _replace_check(kinds: list[str]) -> None:
    op.drop_constraint(op.f(_NAME), "consents", type_="check")
    values = ", ".join(f"'{kind}'" for kind in kinds)
    op.create_check_constraint(op.f(_NAME), "consents", f"kind IN ({values})")


def upgrade() -> None:
    _replace_check(["data_processing", "profile_publication", "fsp_data"])


def downgrade() -> None:
    op.execute("DELETE FROM consents WHERE kind = 'fsp_data'")
    _replace_check(["data_processing", "profile_publication"])
