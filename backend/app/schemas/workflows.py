import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ApprovalStatus, Department, ExecutionStatus, Role, StepStatus


class LinkSnapshot(BaseModel):
    """Verification Agent input: the rows Workflow B should have linked together."""

    po_id: uuid.UUID | None
    invoice_id: uuid.UUID | None
    invoice_po_id: uuid.UUID | None
    invoice_status: str | None
    approval_id: uuid.UUID | None
    approval_status: ApprovalStatus | None
    approval_invoice_id: uuid.UUID | None
    payment_count: int
    payment_invoice_id: uuid.UUID | None
    payment_approval_id: uuid.UUID | None
    payment_amount_minor: int | None
    invoice_amount_minor: int | None


class Check(BaseModel):
    name: str
    ok: bool


class VerificationResult(BaseModel):
    passed: bool
    checks: list[Check]


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    title: str
    department: Department | None
    status: StepStatus
    attempts: int
    output: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    payload: dict[str, Any]
    required_role: Role
    department: Department
    status: ApprovalStatus
    execution_id: uuid.UUID | None
    requested_by_id: uuid.UUID | None
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    comment: str | None
    created_at: datetime


class ExecutionSummary(BaseModel):
    id: uuid.UUID
    workflow: str
    status: ExecutionStatus
    input: dict[str, Any]
    started_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ExecutionOut(ExecutionSummary):
    steps: list[StepOut]
    approval: ApprovalOut | None
    result: dict[str, Any] | None


class DecisionIn(BaseModel):
    comment: Annotated[str, Field(max_length=1000)] | None = None


class AgentTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent: str
    tool: str | None
    execution_id: uuid.UUID | None
    step_id: uuid.UUID | None
    triggered_by_id: uuid.UUID | None
    input_hash: str
    output: Any
    status: str
    attempt: int
    duration_ms: int | None
    error: str | None
    created_at: datetime
