"""Vendor quotes per purchase request, and the last comparison on each request.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vendor_quotes",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("unit_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
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
            "unit_price_minor >= 0", name=op.f("ck_vendor_quotes_unit_price_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["purchase_requests.id"],
            name=op.f("fk_vendor_quotes_request_id_purchase_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"], ["vendors.id"], name=op.f("fk_vendor_quotes_vendor_id_vendors")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vendor_quotes")),
        sa.UniqueConstraint(
            "request_id", "vendor_id", name=op.f("uq_vendor_quotes_request_id_vendor_id")
        ),
    )
    op.create_index(
        op.f("ix_vendor_quotes_created_at"), "vendor_quotes", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_vendor_quotes_request_id"), "vendor_quotes", ["request_id"], unique=False
    )
    op.create_index(
        op.f("ix_vendor_quotes_vendor_id"), "vendor_quotes", ["vendor_id"], unique=False
    )
    op.add_column(
        "purchase_requests",
        sa.Column(
            "comparison",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("purchase_requests", "comparison")
    op.drop_index(op.f("ix_vendor_quotes_vendor_id"), table_name="vendor_quotes")
    op.drop_index(op.f("ix_vendor_quotes_request_id"), table_name="vendor_quotes")
    op.drop_index(op.f("ix_vendor_quotes_created_at"), table_name="vendor_quotes")
    op.drop_table("vendor_quotes")
