"""Give every waiting purchase request and purchase order its entry in the Approval Center.

Purchase requests used to be decided only on the Procurement page, and purchase orders created
by the seed had no approval at all, so neither could be found (or decided) in the Approval
Center. Rows that already have a pending approval are left alone.

Revision ID: 0017
Revises: 0016
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
approvals = sa.table(
    "approval_requests",
    sa.column("id", sa.Uuid()),
    sa.column("action", sa.String()),
    sa.column("payload", _JSON),
    sa.column("required_role", sa.String()),
    sa.column("department", sa.String()),
    sa.column("status", sa.String()),
    sa.column("requested_by_id", sa.Uuid()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
BACKFILLED = "backfilled"  # marks the rows this migration made, so downgrade removes only those


def _waiting(bind: sa.Connection, action: str, key: str) -> set[str]:
    rows = bind.execute(
        sa.select(approvals.c.payload).where(
            approvals.c.action == action, approvals.c.status == "pending"
        )
    )
    return {str(payload.get(key)) for (payload,) in rows if payload}


def upgrade() -> None:
    bind = op.get_bind()
    new: list[dict[str, object]] = []

    have = _waiting(bind, "approve_request", "request_id")
    requests = bind.execute(
        sa.text(
            "SELECT id, item, quantity, budget_minor, currency, requested_by_id "
            "FROM purchase_requests WHERE status = 'pending'"
        )
    ).mappings()
    for row in requests:
        request_id = str(uuid.UUID(str(row["id"])))
        if request_id in have:
            continue
        payload = {
            "request_id": request_id,
            "item": row["item"],
            "quantity": row["quantity"],
            "budget_minor": row["budget_minor"],
            "amount_minor": row["budget_minor"],
            "currency": row["currency"],
            BACKFILLED: True,
        }
        requester = uuid.UUID(str(row["requested_by_id"])) if row["requested_by_id"] else None
        new.append({"action": "approve_request", "payload": payload, "requested_by_id": requester})

    have = _waiting(bind, "approve_po", "po_id")
    orders = bind.execute(
        sa.text(
            "SELECT o.id, o.po_number, o.amount_minor, o.currency, v.name AS vendor_name "
            "FROM purchase_orders o JOIN vendors v ON v.id = o.vendor_id "
            "WHERE o.status = 'pending_approval'"
        )
    ).mappings()
    for row in orders:
        po_id = str(uuid.UUID(str(row["id"])))
        if po_id in have:
            continue
        payload = {
            "po_id": po_id,
            "po_number": row["po_number"],
            "vendor_name": row["vendor_name"],
            "amount_minor": row["amount_minor"],
            "currency": row["currency"],
            "item": None,
            "quantity": None,
            "budget_minor": None,
            "over_budget": False,
            BACKFILLED: True,
        }
        new.append({"action": "approve_po", "payload": payload, "requested_by_id": None})

    now = datetime.now(UTC)
    for values in new:
        bind.execute(
            approvals.insert().values(
                id=uuid.uuid4(),
                required_role="manager",
                department="procurement",
                status="pending",
                created_at=now,
                updated_at=now,
                **values,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(approvals.c.id, approvals.c.payload).where(approvals.c.status == "pending")
    )
    for approval_id, payload in list(rows):
        if payload and payload.get(BACKFILLED):
            bind.execute(approvals.delete().where(approvals.c.id == approval_id))
