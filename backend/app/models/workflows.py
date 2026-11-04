import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, JsonType, TimestampMixin, str_enum
from app.models.enums import (
    ApprovalStatus,
    Department,
    ExecutionStatus,
    Role,
    StepStatus,
    TaskStatus,
)


class WorkflowDefinition(IdMixin, TimestampMixin, Base):
    __tablename__ = "workflow_definitions"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JsonType)


class WorkflowExecution(IdMixin, TimestampMixin, Base):
    __tablename__ = "workflow_executions"

    definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_definitions.id"), index=True
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        str_enum(ExecutionStatus, "execution_status"), default=ExecutionStatus.running, index=True
    )
    started_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    input: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonType)


class WorkflowStep(IdMixin, TimestampMixin, Base):
    """State of one step in one execution. `input` is kept so a retry reuses it."""

    __tablename__ = "workflow_steps"
    __table_args__ = (UniqueConstraint("execution_id", "step_key"),)

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_executions.id"), index=True
    )
    step_key: Mapped[str] = mapped_column(String(20))
    status: Mapped[StepStatus] = mapped_column(
        str_enum(StepStatus, "step_status"), default=StepStatus.pending, index=True
    )
    attempts: Mapped[int] = mapped_column(default=0)
    input: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    output: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentTask(IdMixin, TimestampMixin, Base):
    """One agent call or tool call (`tool` set) — the Command Center reads this table."""

    __tablename__ = "agent_tasks"

    agent: Mapped[str] = mapped_column(String(60), index=True)
    tool: Mapped[str | None] = mapped_column(String(60))
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_executions.id"), index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_steps.id"), index=True)
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    input_hash: Mapped[str] = mapped_column(CHAR(64))
    output: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    status: Mapped[TaskStatus] = mapped_column(
        str_enum(TaskStatus, "task_status"), default=TaskStatus.running, index=True
    )
    attempt: Mapped[int] = mapped_column(default=1)
    duration_ms: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)


class ApprovalRequest(IdMixin, TimestampMixin, Base):
    __tablename__ = "approval_requests"

    action: Mapped[str] = mapped_column(String(60), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    required_role: Mapped[Role] = mapped_column(str_enum(Role, "approval_required_role"))
    department: Mapped[Department] = mapped_column(
        str_enum(Department, "approval_department"), index=True
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        str_enum(ApprovalStatus, "approval_status"), default=ApprovalStatus.pending, index=True
    )
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_executions.id"), index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_steps.id"), index=True)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
