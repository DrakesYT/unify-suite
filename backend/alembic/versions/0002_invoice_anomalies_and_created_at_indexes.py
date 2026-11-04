"""Invoice anomalies table and created_at indexes for pagination.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invoice_anomalies",
        sa.Column(
            "kind",
            sa.Enum(
                "duplicate",
                "number_conflict",
                "unknown_vendor",
                "po_mismatch",
                "no_po",
                name="anomaly_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("existing_invoice_id", sa.Uuid(), nullable=True),
        sa.Column("upload_id", sa.Uuid(), nullable=True),
        sa.Column(
            "detail",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
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
        sa.ForeignKeyConstraint(
            ["existing_invoice_id"],
            ["invoices.id"],
            name=op.f("fk_invoice_anomalies_existing_invoice_id_invoices"),
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["invoices.id"], name=op.f("fk_invoice_anomalies_invoice_id_invoices")
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"], ["uploads.id"], name=op.f("fk_invoice_anomalies_upload_id_uploads")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_anomalies")),
    )
    op.create_index(
        op.f("ix_invoice_anomalies_created_at"), "invoice_anomalies", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_invoice_anomalies_existing_invoice_id"),
        "invoice_anomalies",
        ["existing_invoice_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_invoice_anomalies_invoice_id"), "invoice_anomalies", ["invoice_id"], unique=False
    )
    op.create_index(op.f("ix_invoice_anomalies_kind"), "invoice_anomalies", ["kind"], unique=False)
    op.create_index(
        op.f("ix_invoice_anomalies_upload_id"), "invoice_anomalies", ["upload_id"], unique=False
    )
    op.create_index(op.f("ix_agent_tasks_created_at"), "agent_tasks", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_approval_requests_created_at"), "approval_requests", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_candidate_scores_created_at"), "candidate_scores", ["created_at"], unique=False
    )
    op.create_index(op.f("ix_candidates_created_at"), "candidates", ["created_at"], unique=False)
    op.create_index(op.f("ix_customers_created_at"), "customers", ["created_at"], unique=False)
    op.create_index(op.f("ix_invoices_created_at"), "invoices", ["created_at"], unique=False)
    op.create_index(op.f("ix_jobs_created_at"), "jobs", ["created_at"], unique=False)
    op.create_index(op.f("ix_leads_created_at"), "leads", ["created_at"], unique=False)
    op.create_index(op.f("ix_orders_created_at"), "orders", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_purchase_orders_created_at"), "purchase_orders", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_purchase_requests_created_at"), "purchase_requests", ["created_at"], unique=False
    )
    op.create_index(op.f("ix_tickets_created_at"), "tickets", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_transactions_created_at"), "transactions", ["created_at"], unique=False
    )
    op.create_index(op.f("ix_uploads_created_at"), "uploads", ["created_at"], unique=False)
    op.create_index(op.f("ix_users_created_at"), "users", ["created_at"], unique=False)
    op.create_index(op.f("ix_vendors_created_at"), "vendors", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_workflow_definitions_created_at"),
        "workflow_definitions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_executions_created_at"),
        "workflow_executions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_steps_created_at"), "workflow_steps", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_workflow_steps_created_at"), table_name="workflow_steps")
    op.drop_index(op.f("ix_workflow_executions_created_at"), table_name="workflow_executions")
    op.drop_index(op.f("ix_workflow_definitions_created_at"), table_name="workflow_definitions")
    op.drop_index(op.f("ix_vendors_created_at"), table_name="vendors")
    op.drop_index(op.f("ix_users_created_at"), table_name="users")
    op.drop_index(op.f("ix_uploads_created_at"), table_name="uploads")
    op.drop_index(op.f("ix_transactions_created_at"), table_name="transactions")
    op.drop_index(op.f("ix_tickets_created_at"), table_name="tickets")
    op.drop_index(op.f("ix_purchase_requests_created_at"), table_name="purchase_requests")
    op.drop_index(op.f("ix_purchase_orders_created_at"), table_name="purchase_orders")
    op.drop_index(op.f("ix_orders_created_at"), table_name="orders")
    op.drop_index(op.f("ix_leads_created_at"), table_name="leads")
    op.drop_index(op.f("ix_jobs_created_at"), table_name="jobs")
    op.drop_index(op.f("ix_invoices_created_at"), table_name="invoices")
    op.drop_index(op.f("ix_customers_created_at"), table_name="customers")
    op.drop_index(op.f("ix_candidates_created_at"), table_name="candidates")
    op.drop_index(op.f("ix_candidate_scores_created_at"), table_name="candidate_scores")
    op.drop_index(op.f("ix_approval_requests_created_at"), table_name="approval_requests")
    op.drop_index(op.f("ix_agent_tasks_created_at"), table_name="agent_tasks")
    op.drop_index(op.f("ix_invoice_anomalies_upload_id"), table_name="invoice_anomalies")
    op.drop_index(op.f("ix_invoice_anomalies_kind"), table_name="invoice_anomalies")
    op.drop_index(op.f("ix_invoice_anomalies_invoice_id"), table_name="invoice_anomalies")
    op.drop_index(op.f("ix_invoice_anomalies_existing_invoice_id"), table_name="invoice_anomalies")
    op.drop_index(op.f("ix_invoice_anomalies_created_at"), table_name="invoice_anomalies")
    op.drop_table("invoice_anomalies")
