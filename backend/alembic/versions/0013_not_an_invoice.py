"""Allow the anomaly kind `not_an_invoice` (a credit note, quotation or reminder: nothing to pay).

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = ["duplicate", "number_conflict", "unknown_vendor", "po_mismatch", "no_po"]
NEW = [*OLD, "not_an_invoice"]
TABLE = "invoice_anomalies"
CHECK = "anomaly_kind"  # becomes ck_invoice_anomalies_anomaly_kind by the naming convention


def _replace_check(kinds: list[str]) -> None:
    allowed = sa.column("kind").in_(kinds)
    if op.get_bind().dialect.name == "sqlite":
        # SQLite can't alter a constraint: batch mode rebuilds the table with the new check.
        with op.batch_alter_table(TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(op.f(f"ck_{TABLE}_{CHECK}"), type_="check")
            batch_op.create_check_constraint(CHECK, allowed)
    else:
        op.drop_constraint(op.f(f"ck_{TABLE}_{CHECK}"), TABLE, type_="check")
        op.create_check_constraint(CHECK, TABLE, allowed)


def upgrade() -> None:
    _replace_check(NEW)


def downgrade() -> None:
    op.execute(sa.text(f"DELETE FROM {TABLE} WHERE kind = 'not_an_invoice'"))
    _replace_check(OLD)
