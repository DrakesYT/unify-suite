"""Interview slots offered to candidates, and which candidate/job an email is about.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_slots",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email_id", sa.Uuid(), nullable=True),
        sa.Column("released", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_interview_slots_candidate_id_candidates"),
        ),
        sa.ForeignKeyConstraint(
            ["email_id"],
            ["outbound_emails.id"],
            name=op.f("fk_interview_slots_email_id_outbound_emails"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_interview_slots_job_id_jobs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_slots")),
    )
    with op.batch_alter_table("interview_slots", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_interview_slots_candidate_id"), ["candidate_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_interview_slots_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_interview_slots_email_id"), ["email_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_interview_slots_job_id"), ["job_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_interview_slots_released"), ["released"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_interview_slots_starts_at"), ["starts_at"], unique=False
        )

    with op.batch_alter_table("outbound_emails", schema=None) as batch_op:
        batch_op.add_column(sa.Column("candidate_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("job_id", sa.Uuid(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_outbound_emails_candidate_id"), ["candidate_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_outbound_emails_job_id"), ["job_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_outbound_emails_candidate_id_candidates"),
            "candidates",
            ["candidate_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_outbound_emails_job_id_jobs"), "jobs", ["job_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("outbound_emails", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_outbound_emails_job_id_jobs"), type_="foreignkey")
        batch_op.drop_constraint(
            batch_op.f("fk_outbound_emails_candidate_id_candidates"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_outbound_emails_job_id"))
        batch_op.drop_index(batch_op.f("ix_outbound_emails_candidate_id"))
        batch_op.drop_column("job_id")
        batch_op.drop_column("candidate_id")

    with op.batch_alter_table("interview_slots", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_interview_slots_starts_at"))
        batch_op.drop_index(batch_op.f("ix_interview_slots_released"))
        batch_op.drop_index(batch_op.f("ix_interview_slots_job_id"))
        batch_op.drop_index(batch_op.f("ix_interview_slots_email_id"))
        batch_op.drop_index(batch_op.f("ix_interview_slots_created_at"))
        batch_op.drop_index(batch_op.f("ix_interview_slots_candidate_id"))

    op.drop_table("interview_slots")
