"""Record the job a candidate applied for (screening then covers that job's applicants only).

Candidates already screened for exactly one job are linked to it; the rest stay unlinked, which
counts as applying for every job, as before.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("candidates", schema=None) as batch_op:
        batch_op.add_column(sa.Column("job_id", sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f("ix_candidates_job_id"), ["job_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_candidates_job_id_jobs"), "jobs", ["job_id"], ["id"]
        )
    op.execute(
        sa.text(
            """
            UPDATE candidates SET job_id = (
                SELECT s.job_id FROM candidate_scores s WHERE s.candidate_id = candidates.id
                LIMIT 1
            )
            WHERE job_id IS NULL AND (
                SELECT COUNT(*) FROM candidate_scores s WHERE s.candidate_id = candidates.id
            ) = 1
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("candidates", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_candidates_job_id_jobs"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_candidates_job_id"))
        batch_op.drop_column("job_id")
