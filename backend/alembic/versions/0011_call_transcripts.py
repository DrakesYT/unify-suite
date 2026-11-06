"""Call transcripts linked to a lead or a ticket, with the Call Analyzer's checked analysis.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "call_transcripts",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "department",
            sa.Enum(
                "sales",
                "finance",
                "hr",
                "support",
                "procurement",
                name="call_department",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "analysis",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("analyzed_by_model", sa.String(length=80), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analysis_error", sa.String(length=300), nullable=True),
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
        sa.CheckConstraint(
            "(lead_id IS NULL) <> (ticket_id IS NULL)",
            name=op.f("ck_call_transcripts_exactly_one_lead_or_ticket"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_call_transcripts_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], name=op.f("fk_call_transcripts_lead_id_leads")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name=op.f("fk_call_transcripts_ticket_id_tickets")
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"], ["uploads.id"], name=op.f("fk_call_transcripts_upload_id_uploads")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_call_transcripts")),
    )
    with op.batch_alter_table("call_transcripts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_call_transcripts_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_call_transcripts_created_by_id"), ["created_by_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_call_transcripts_department"), ["department"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_call_transcripts_lead_id"), ["lead_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_call_transcripts_ticket_id"), ["ticket_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_call_transcripts_upload_id"), ["upload_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("call_transcripts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_call_transcripts_upload_id"))
        batch_op.drop_index(batch_op.f("ix_call_transcripts_ticket_id"))
        batch_op.drop_index(batch_op.f("ix_call_transcripts_lead_id"))
        batch_op.drop_index(batch_op.f("ix_call_transcripts_department"))
        batch_op.drop_index(batch_op.f("ix_call_transcripts_created_by_id"))
        batch_op.drop_index(batch_op.f("ix_call_transcripts_created_at"))

    op.drop_table("call_transcripts")
