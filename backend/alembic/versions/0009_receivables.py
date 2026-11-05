"""Receivables: when a customer order was paid, and which order a payment reminder is about.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("paid_on", sa.Date(), nullable=True))

    with op.batch_alter_table("outbound_emails", schema=None) as batch_op:
        batch_op.add_column(sa.Column("order_id", sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f("ix_outbound_emails_order_id"), ["order_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_outbound_emails_order_id_orders"), "orders", ["order_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("outbound_emails", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_outbound_emails_order_id_orders"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_outbound_emails_order_id"))
        batch_op.drop_column("order_id")

    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_column("paid_on")
