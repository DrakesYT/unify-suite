"""Tickets get an owner, and an email can be a reply to a ticket.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tickets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("assignee_id", sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f("ix_tickets_assignee_id"), ["assignee_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_tickets_assignee_id_users"), "users", ["assignee_id"], ["id"]
        )
    with op.batch_alter_table("outbound_emails", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ticket_id", sa.Uuid(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_outbound_emails_ticket_id"), ["ticket_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_outbound_emails_ticket_id_tickets"), "tickets", ["ticket_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("outbound_emails", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_outbound_emails_ticket_id_tickets"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_outbound_emails_ticket_id"))
        batch_op.drop_column("ticket_id")
    with op.batch_alter_table("tickets", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_tickets_assignee_id_users"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_tickets_assignee_id"))
        batch_op.drop_column("assignee_id")
