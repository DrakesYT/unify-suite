import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Department, EmailStatus, LeadRating, LeadStatus, Priority

Subject = Annotated[str, Field(min_length=5, max_length=120)]
Body = Annotated[str, Field(min_length=40, max_length=2000)]


class OutreachInput(BaseModel):
    """What the Outreach Writer sees: business facts only (no contact name or email address)."""

    company: str
    status: LeadStatus
    priority: Priority
    value: str
    notes: str
    rating: LeadRating
    qualification_reason: str
    seller_company: str


class OutreachDraft(BaseModel):
    """Outreach Writer output. Code adds the greeting and signature."""

    subject: Subject = Field(description="Email subject line")
    body: Body = Field(
        description="Email body paragraphs only: no greeting line, no sign-off, no signature"
    )


class EmailDraftUpdate(BaseModel):
    subject: Subject | None = None
    body: Annotated[str, Field(min_length=40, max_length=3000)] | None = None


class OutboundEmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    department: Department
    lead_id: uuid.UUID | None
    to_address: str
    subject: str
    body: str
    status: EmailStatus
    approval_id: uuid.UUID | None
    drafted_by_model: str | None
    delivered_to: str | None
    sent_at: datetime | None
    error: str | None
    created_at: datetime
