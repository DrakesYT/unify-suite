"""Short fit summary on each candidate score.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidate_scores", sa.Column("summary", sa.Text(), server_default="", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("candidate_scores", "summary")
