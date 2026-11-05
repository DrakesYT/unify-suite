"""Outbound emails: drafted by an agent, sent only after a manager approves.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXED = ["approval_id", "created_at", "created_by_id", "department", "lead_id", "status"]


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    op.create_table(
        "outbound_emails",
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column(
            "department",
            _enum("department", "sales", "finance", "hr", "support", "procurement"),
            nullable=False,
        ),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("to_address", sa.String(length=254), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status",
            _enum("email_status", "draft", "pending_approval", "sent", "failed", "rejected"),
            nullable=False,
        ),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("drafted_by_model", sa.String(length=80), nullable=True),
        sa.Column("delivered_to", sa.String(length=254), nullable=True),
        sa.Column("provider_message_id", sa.String(length=120), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=True),
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
            ["approval_id"],
            ["approval_requests.id"],
            name=op.f("fk_outbound_emails_approval_id_approval_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_outbound_emails_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], name=op.f("fk_outbound_emails_lead_id_leads")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_emails")),
    )
    for column in INDEXED:
        op.create_index(
            op.f(f"ix_outbound_emails_{column}"), "outbound_emails", [column], unique=False
        )


def downgrade() -> None:
    for column in INDEXED:
        op.drop_index(op.f(f"ix_outbound_emails_{column}"), table_name="outbound_emails")
    op.drop_table("outbound_emails")
