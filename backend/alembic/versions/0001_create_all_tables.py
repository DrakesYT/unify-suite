"""Create all tables.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# audit_logs is append-only: PostgreSQL rejects any UPDATE or DELETE on it.
AUDIT_GUARD_FUNCTION = """
CREATE FUNCTION audit_logs_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only';
END;
$$ LANGUAGE plpgsql;
"""
AUDIT_GUARD_TRIGGER = """
CREATE TRIGGER audit_logs_append_only
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only();
"""


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("company", sa.String(length=160), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("billing_terms", sa.String(length=40), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
    )
    op.create_index(op.f("ix_customers_email"), "customers", ["email"], unique=False)
    op.create_table(
        "jobs",
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column(
            "required_skills",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("min_years", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "closed",
                name="job_status",
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
        sa.CheckConstraint("min_years >= 0", name=op.f("ck_jobs_min_years_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=100), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "admin",
                "manager",
                "employee",
                "executive",
                name="user_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "department",
            sa.Enum(
                "sales",
                "finance",
                "hr",
                "support",
                "procurement",
                name="user_department",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_department"), "users", ["department"], unique=False)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.create_table(
        "vendors",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("contact", sa.String(length=254), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column("on_time_rate", sa.Numeric(precision=5, scale=4), nullable=False),
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
        sa.CheckConstraint("lead_time_days >= 0", name=op.f("ck_vendors_lead_time_non_negative")),
        sa.CheckConstraint(
            "on_time_rate >= 0 AND on_time_rate <= 1", name=op.f("ck_vendors_on_time_rate_range")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vendors")),
        sa.UniqueConstraint("name", name=op.f("uq_vendors_name")),
    )
    op.create_table(
        "workflow_definitions",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "steps",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_definitions")),
        sa.UniqueConstraint("name", name=op.f("uq_workflow_definitions_name")),
    )
    op.create_table(
        "audit_logs",
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column(
            "detail",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_audit_logs_actor_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_at"), "audit_logs", ["at"], unique=False)
    op.create_index(op.f("ix_audit_logs_entity"), "audit_logs", ["entity"], unique=False)
    op.create_table(
        "leads",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("company", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "contacted",
                "qualified",
                "won",
                "lost",
                name="lead_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum(
                "low",
                "medium",
                "high",
                name="lead_priority",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("value_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "rating",
            sa.Enum(
                "hot",
                "warm",
                "cold",
                name="lead_rating",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "qualification",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("value_minor >= 0", name=op.f("ck_leads_value_non_negative")),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_leads_owner_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leads")),
    )
    op.create_index(op.f("ix_leads_owner_id"), "leads", ["owner_id"], unique=False)
    op.create_index(op.f("ix_leads_priority"), "leads", ["priority"], unique=False)
    op.create_index(op.f("ix_leads_rating"), "leads", ["rating"], unique=False)
    op.create_index(op.f("ix_leads_status"), "leads", ["status"], unique=False)
    op.create_table(
        "orders",
        sa.Column("order_number", sa.String(length=40), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "placed",
                "shipped",
                "delivered",
                "cancelled",
                "refunded",
                name="order_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint("amount_minor >= 0", name=op.f("ck_orders_amount_non_negative")),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_orders_customer_id_customers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("order_number", name=op.f("uq_orders_order_number")),
    )
    op.create_index(op.f("ix_orders_customer_id"), "orders", ["customer_id"], unique=False)
    op.create_index(op.f("ix_orders_status"), "orders", ["status"], unique=False)
    op.create_table(
        "purchase_requests",
        sa.Column("item", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("budget_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "rejected",
                "ordered",
                name="purchase_request_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("chosen_vendor_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by_id", sa.Uuid(), nullable=True),
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
            "budget_minor >= 0", name=op.f("ck_purchase_requests_budget_non_negative")
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_purchase_requests_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["chosen_vendor_id"],
            ["vendors.id"],
            name=op.f("fk_purchase_requests_chosen_vendor_id_vendors"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_purchase_requests_requested_by_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_requests")),
    )
    op.create_index(
        op.f("ix_purchase_requests_chosen_vendor_id"),
        "purchase_requests",
        ["chosen_vendor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purchase_requests_requested_by_id"),
        "purchase_requests",
        ["requested_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purchase_requests_status"), "purchase_requests", ["status"], unique=False
    )
    op.create_table(
        "tickets",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "billing",
                "technical",
                "shipping",
                "refund",
                "legal",
                "account",
                "other",
                name="ticket_category",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "urgency",
            sa.Enum(
                "low",
                "normal",
                "high",
                "critical",
                name="ticket_urgency",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "investigating",
                "escalated",
                "resolved",
                "closed",
                name="ticket_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column(
            "investigation",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
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
            ["customer_id"], ["customers.id"], name=op.f("fk_tickets_customer_id_customers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
    )
    op.create_index(op.f("ix_tickets_category"), "tickets", ["category"], unique=False)
    op.create_index(op.f("ix_tickets_customer_id"), "tickets", ["customer_id"], unique=False)
    op.create_index(op.f("ix_tickets_status"), "tickets", ["status"], unique=False)
    op.create_index(op.f("ix_tickets_urgency"), "tickets", ["urgency"], unique=False)
    op.create_table(
        "uploads",
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column(
            "department",
            sa.Enum(
                "sales",
                "finance",
                "hr",
                "support",
                "procurement",
                name="upload_department",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
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
            ["uploaded_by_id"], ["users.id"], name=op.f("fk_uploads_uploaded_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploads")),
    )
    op.create_index(op.f("ix_uploads_department"), "uploads", ["department"], unique=False)
    op.create_index(op.f("ix_uploads_sha256"), "uploads", ["sha256"], unique=False)
    op.create_index(op.f("ix_uploads_uploaded_by_id"), "uploads", ["uploaded_by_id"], unique=False)
    op.create_table(
        "workflow_executions",
        sa.Column("definition_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "waiting_approval",
                "approved",
                "rejected",
                "failed",
                "completed",
                name="execution_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("started_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "input",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "result",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
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
            ["definition_id"],
            ["workflow_definitions.id"],
            name=op.f("fk_workflow_executions_definition_id_workflow_definitions"),
        ),
        sa.ForeignKeyConstraint(
            ["started_by_id"], ["users.id"], name=op.f("fk_workflow_executions_started_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_executions")),
    )
    op.create_index(
        op.f("ix_workflow_executions_definition_id"),
        "workflow_executions",
        ["definition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_executions_started_by_id"),
        "workflow_executions",
        ["started_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_executions_status"), "workflow_executions", ["status"], unique=False
    )
    op.create_table(
        "candidates",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column(
            "skills",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column(
            "education",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("file_id", sa.Uuid(), nullable=True),
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
            ["file_id"], ["uploads.id"], name=op.f("fk_candidates_file_id_uploads")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidates")),
    )
    op.create_index(op.f("ix_candidates_email"), "candidates", ["email"], unique=False)
    op.create_index(op.f("ix_candidates_file_id"), "candidates", ["file_id"], unique=False)
    op.create_table(
        "purchase_orders",
        sa.Column("po_number", sa.String(length=40), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending_approval",
                "approved",
                "rejected",
                name="purchase_order_status",
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
        sa.CheckConstraint(
            "amount_minor >= 0", name=op.f("ck_purchase_orders_amount_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["purchase_requests.id"],
            name=op.f("fk_purchase_orders_request_id_purchase_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"], ["vendors.id"], name=op.f("fk_purchase_orders_vendor_id_vendors")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_orders")),
        sa.UniqueConstraint("po_number", name=op.f("uq_purchase_orders_po_number")),
    )
    op.create_index(
        op.f("ix_purchase_orders_request_id"), "purchase_orders", ["request_id"], unique=False
    )
    op.create_index(op.f("ix_purchase_orders_status"), "purchase_orders", ["status"], unique=False)
    op.create_index(
        op.f("ix_purchase_orders_vendor_id"), "purchase_orders", ["vendor_id"], unique=False
    )
    op.create_table(
        "workflow_steps",
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("step_key", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "succeeded",
                "failed",
                "waiting_approval",
                "rejected",
                "skipped",
                name="step_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "input",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "output",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
            ["execution_id"],
            ["workflow_executions.id"],
            name=op.f("fk_workflow_steps_execution_id_workflow_executions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_steps")),
        sa.UniqueConstraint(
            "execution_id", "step_key", name=op.f("uq_workflow_steps_execution_id_step_key")
        ),
    )
    op.create_index(
        op.f("ix_workflow_steps_execution_id"), "workflow_steps", ["execution_id"], unique=False
    )
    op.create_index(op.f("ix_workflow_steps_status"), "workflow_steps", ["status"], unique=False)
    op.create_table(
        "agent_tasks",
        sa.Column("agent", sa.String(length=60), nullable=False),
        sa.Column("tool", sa.String(length=60), nullable=True),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("triggered_by_id", sa.Uuid(), nullable=True),
        sa.Column("input_hash", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "output",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "succeeded",
                "failed",
                name="task_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
            ["execution_id"],
            ["workflow_executions.id"],
            name=op.f("fk_agent_tasks_execution_id_workflow_executions"),
        ),
        sa.ForeignKeyConstraint(
            ["step_id"], ["workflow_steps.id"], name=op.f("fk_agent_tasks_step_id_workflow_steps")
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_id"], ["users.id"], name=op.f("fk_agent_tasks_triggered_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_tasks")),
    )
    op.create_index(op.f("ix_agent_tasks_agent"), "agent_tasks", ["agent"], unique=False)
    op.create_index(
        op.f("ix_agent_tasks_execution_id"), "agent_tasks", ["execution_id"], unique=False
    )
    op.create_index(op.f("ix_agent_tasks_status"), "agent_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_agent_tasks_step_id"), "agent_tasks", ["step_id"], unique=False)
    op.create_index(
        op.f("ix_agent_tasks_triggered_by_id"), "agent_tasks", ["triggered_by_id"], unique=False
    )
    op.create_table(
        "approval_requests",
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "required_role",
            sa.Enum(
                "admin",
                "manager",
                "employee",
                "executive",
                name="approval_required_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "department",
            sa.Enum(
                "sales",
                "finance",
                "hr",
                "support",
                "procurement",
                name="approval_department",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "rejected",
                "cancelled",
                name="approval_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
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
            ["decided_by_id"], ["users.id"], name=op.f("fk_approval_requests_decided_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["workflow_executions.id"],
            name=op.f("fk_approval_requests_execution_id_workflow_executions"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_approval_requests_requested_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["workflow_steps.id"],
            name=op.f("fk_approval_requests_step_id_workflow_steps"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_requests")),
    )
    op.create_index(
        op.f("ix_approval_requests_action"), "approval_requests", ["action"], unique=False
    )
    op.create_index(
        op.f("ix_approval_requests_decided_by_id"),
        "approval_requests",
        ["decided_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_department"), "approval_requests", ["department"], unique=False
    )
    op.create_index(
        op.f("ix_approval_requests_execution_id"),
        "approval_requests",
        ["execution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_requested_by_id"),
        "approval_requests",
        ["requested_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_status"), "approval_requests", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_approval_requests_step_id"), "approval_requests", ["step_id"], unique=False
    )
    op.create_table(
        "candidate_scores",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column(
            "evidence",
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
        sa.CheckConstraint(
            "score >= 0 AND score <= 100", name=op.f("ck_candidate_scores_score_range")
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_candidate_scores_candidate_id_candidates"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_candidate_scores_job_id_jobs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_scores")),
        sa.UniqueConstraint(
            "candidate_id", "job_id", name=op.f("uq_candidate_scores_candidate_id_job_id")
        ),
    )
    op.create_index(
        op.f("ix_candidate_scores_candidate_id"), "candidate_scores", ["candidate_id"], unique=False
    )
    op.create_index(
        op.f("ix_candidate_scores_job_id"), "candidate_scores", ["job_id"], unique=False
    )
    op.create_table(
        "invoices",
        sa.Column("number", sa.String(length=60), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=True),
        sa.Column("po_number", sa.String(length=40), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "received",
                "needs_review",
                "approved",
                "rejected",
                "payment_submitted",
                name="invoice_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "match_status",
            sa.Enum(
                "matched",
                "mismatch",
                "no_po",
                name="invoice_match_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("file_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("amount_minor >= 0", name=op.f("ck_invoices_amount_non_negative")),
        sa.ForeignKeyConstraint(
            ["file_id"], ["uploads.id"], name=op.f("fk_invoices_file_id_uploads")
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            ["purchase_orders.id"],
            name=op.f("fk_invoices_purchase_order_id_purchase_orders"),
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"], ["vendors.id"], name=op.f("fk_invoices_vendor_id_vendors")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoices")),
        sa.UniqueConstraint("vendor_id", "number", name=op.f("uq_invoices_vendor_id_number")),
    )
    op.create_index(op.f("ix_invoices_file_id"), "invoices", ["file_id"], unique=False)
    op.create_index(op.f("ix_invoices_match_status"), "invoices", ["match_status"], unique=False)
    op.create_index(
        op.f("ix_invoices_purchase_order_id"), "invoices", ["purchase_order_id"], unique=False
    )
    op.create_index(op.f("ix_invoices_status"), "invoices", ["status"], unique=False)
    op.create_index(op.f("ix_invoices_vendor_id"), "invoices", ["vendor_id"], unique=False)
    op.create_table(
        "transactions",
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("counterparty", sa.String(length=160), nullable=False),
        sa.Column("matched_invoice_id", sa.Uuid(), nullable=True),
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
            ["matched_invoice_id"],
            ["invoices.id"],
            name=op.f("fk_transactions_matched_invoice_id_invoices"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
    )
    op.create_index(
        op.f("ix_transactions_matched_invoice_id"),
        "transactions",
        ["matched_invoice_id"],
        unique=False,
    )
    op.create_index(op.f("ix_transactions_txn_date"), "transactions", ["txn_date"], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute(AUDIT_GUARD_FUNCTION)
        op.execute(AUDIT_GUARD_TRIGGER)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER audit_logs_append_only ON audit_logs")
        op.execute("DROP FUNCTION audit_logs_append_only()")
    op.drop_index(op.f("ix_transactions_txn_date"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_matched_invoice_id"), table_name="transactions")
    op.drop_table("transactions")
    op.drop_index(op.f("ix_invoices_vendor_id"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_status"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_purchase_order_id"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_match_status"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_file_id"), table_name="invoices")
    op.drop_table("invoices")
    op.drop_index(op.f("ix_candidate_scores_job_id"), table_name="candidate_scores")
    op.drop_index(op.f("ix_candidate_scores_candidate_id"), table_name="candidate_scores")
    op.drop_table("candidate_scores")
    op.drop_index(op.f("ix_approval_requests_step_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_status"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_requested_by_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_execution_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_department"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_decided_by_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_action"), table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index(op.f("ix_agent_tasks_triggered_by_id"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_step_id"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_status"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_execution_id"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_agent"), table_name="agent_tasks")
    op.drop_table("agent_tasks")
    op.drop_index(op.f("ix_workflow_steps_status"), table_name="workflow_steps")
    op.drop_index(op.f("ix_workflow_steps_execution_id"), table_name="workflow_steps")
    op.drop_table("workflow_steps")
    op.drop_index(op.f("ix_purchase_orders_vendor_id"), table_name="purchase_orders")
    op.drop_index(op.f("ix_purchase_orders_status"), table_name="purchase_orders")
    op.drop_index(op.f("ix_purchase_orders_request_id"), table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_index(op.f("ix_candidates_file_id"), table_name="candidates")
    op.drop_index(op.f("ix_candidates_email"), table_name="candidates")
    op.drop_table("candidates")
    op.drop_index(op.f("ix_workflow_executions_status"), table_name="workflow_executions")
    op.drop_index(op.f("ix_workflow_executions_started_by_id"), table_name="workflow_executions")
    op.drop_index(op.f("ix_workflow_executions_definition_id"), table_name="workflow_executions")
    op.drop_table("workflow_executions")
    op.drop_index(op.f("ix_uploads_uploaded_by_id"), table_name="uploads")
    op.drop_index(op.f("ix_uploads_sha256"), table_name="uploads")
    op.drop_index(op.f("ix_uploads_department"), table_name="uploads")
    op.drop_table("uploads")
    op.drop_index(op.f("ix_tickets_urgency"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_status"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_customer_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_category"), table_name="tickets")
    op.drop_table("tickets")
    op.drop_index(op.f("ix_purchase_requests_status"), table_name="purchase_requests")
    op.drop_index(op.f("ix_purchase_requests_requested_by_id"), table_name="purchase_requests")
    op.drop_index(op.f("ix_purchase_requests_chosen_vendor_id"), table_name="purchase_requests")
    op.drop_table("purchase_requests")
    op.drop_index(op.f("ix_orders_status"), table_name="orders")
    op.drop_index(op.f("ix_orders_customer_id"), table_name="orders")
    op.drop_table("orders")
    op.drop_index(op.f("ix_leads_status"), table_name="leads")
    op.drop_index(op.f("ix_leads_rating"), table_name="leads")
    op.drop_index(op.f("ix_leads_priority"), table_name="leads")
    op.drop_index(op.f("ix_leads_owner_id"), table_name="leads")
    op.drop_table("leads")
    op.drop_index(op.f("ix_audit_logs_entity"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("workflow_definitions")
    op.drop_table("vendors")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_index(op.f("ix_users_department"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_customers_email"), table_name="customers")
    op.drop_table("customers")
