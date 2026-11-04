"""Payments table (one per invoice, only after approval).

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "submitted",
                name="payment_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
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
        sa.CheckConstraint("amount_minor >= 0", name=op.f("ck_payments_amount_non_negative")),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approval_requests.id"],
            name=op.f("fk_payments_approval_id_approval_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["workflow_executions.id"],
            name=op.f("fk_payments_execution_id_workflow_executions"),
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["invoices.id"], name=op.f("fk_payments_invoice_id_invoices")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("invoice_id", name=op.f("uq_payments_invoice_id")),
    )
    op.create_index(op.f("ix_payments_approval_id"), "payments", ["approval_id"], unique=False)
    op.create_index(op.f("ix_payments_created_at"), "payments", ["created_at"], unique=False)
    op.create_index(op.f("ix_payments_execution_id"), "payments", ["execution_id"], unique=False)
    op.create_index(op.f("ix_payments_status"), "payments", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_status"), table_name="payments")
    op.drop_index(op.f("ix_payments_execution_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_created_at"), table_name="payments")
    op.drop_index(op.f("ix_payments_approval_id"), table_name="payments")
    op.drop_table("payments")
