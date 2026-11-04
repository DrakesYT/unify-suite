import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OrderStatus, TicketCategory, TicketStatus, Urgency
from app.schemas.workflows import ApprovalOut


class TicketCreate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=5000)] = ""
    customer_id: uuid.UUID | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    category: TicketCategory | None
    urgency: Urgency | None
    status: TicketStatus
    customer_id: uuid.UUID | None
    investigation: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class EscalateIn(BaseModel):
    note: Annotated[str, Field(max_length=1000)] = ""


class EscalationOut(BaseModel):
    ticket: TicketOut
    approval: ApprovalOut | None = Field(
        description="Set when the category needs a manager's approval"
    )


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_number: str
    amount_minor: int
    currency: str
    status: OrderStatus
    ordered_at: datetime


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    company: str | None
    email: str | None


# --- agent inputs / outputs ----------------------------------------------------------------


class TicketText(BaseModel):
    title: str
    description: str


class TicketClassification(BaseModel):
    category: TicketCategory = Field(
        description="billing, technical, shipping, refund, legal, account or other"
    )
    urgency: Urgency = Field(description="low, normal, high or critical")
    reason: Annotated[str, Field(min_length=1, max_length=300)] = Field(
        description="One sentence why"
    )


class OrderFact(BaseModel):
    order_number: str
    status: OrderStatus
    amount: str
    ordered_on: str


class InvestigationInput(BaseModel):
    title: str
    description: str
    category: TicketCategory | None
    orders: list[OrderFact]


class LikelyCause(BaseModel):
    cause: Annotated[str, Field(min_length=1, max_length=300)]
    order_numbers: Annotated[list[str], Field(max_length=10)] = Field(
        description="Order numbers from the history that support this cause"
    )


class Investigation(BaseModel):
    likely_causes: Annotated[list[LikelyCause], Field(min_length=1, max_length=5)]
    order_numbers_used: Annotated[list[str], Field(max_length=20)] = Field(
        description="Every order number you relied on"
    )
    next_step: Annotated[str, Field(min_length=1, max_length=400)] = Field(
        description="What support should do next"
    )
    draft_reply: Annotated[str, Field(max_length=1500)] = Field(
        description="A short, polite reply to the customer (a draft; never sent automatically)"
    )
