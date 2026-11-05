"""Purchase order delivery dates, and which PO a supplier follow-up email is about.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("outbound_emails", schema=None) as batch_op:
        batch_op.add_column(sa.Column("po_id", sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f("ix_outbound_emails_po_id"), ["po_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_outbound_emails_po_id_purchase_orders"),
            "purchase_orders",
            ["po_id"],
            ["id"],
        )

    with op.batch_alter_table("purchase_orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ordered_on", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("expected_delivery", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("delivered_on", sa.Date(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_purchase_orders_expected_delivery"), ["expected_delivery"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("purchase_orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_purchase_orders_expected_delivery"))
        batch_op.drop_column("delivered_on")
        batch_op.drop_column("expected_delivery")
        batch_op.drop_column("ordered_on")

    with op.batch_alter_table("outbound_emails", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_outbound_emails_po_id_purchase_orders"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_outbound_emails_po_id"))
        batch_op.drop_column("po_id")
