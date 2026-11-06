"""Company settings people change in the app (first: the quarterly sales target).

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column(
            "value",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
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
            ["updated_by_id"], ["users.id"], name=op.f("fk_app_settings_updated_by_id_users")
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_settings")),
    )
    with op.batch_alter_table("app_settings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_app_settings_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_app_settings_updated_by_id"), ["updated_by_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("app_settings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_app_settings_updated_by_id"))
        batch_op.drop_index(batch_op.f("ix_app_settings_created_at"))
    op.drop_table("app_settings")
