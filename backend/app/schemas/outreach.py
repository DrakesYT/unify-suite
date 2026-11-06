import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.agents.writing_checks import style_findings
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


class EmailDraft(BaseModel):
    """An email-writing agent's output. Code adds the greeting and signature."""

    subject: Subject = Field(description="Email subject line")
    body: Body = Field(
        description="Email body paragraphs only: no greeting line, no sign-off, no signature"
    )


class EmailDraftUpdate(BaseModel):
    subject: Subject | None = None
    body: Annotated[str, Field(min_length=40, max_length=3000)] | None = None


class StyleNote(BaseModel):
    rule: str
    severity: str  # "hard" = would have been rejected from an agent; "soft" = a suggestion
    text: str
    advice: str


class OutboundEmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    department: Department
    lead_id: uuid.UUID | None
    po_id: uuid.UUID | None
    order_id: uuid.UUID | None
    candidate_id: uuid.UUID | None
    job_id: uuid.UUID | None
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def style_notes(self) -> list[StyleNote]:
        """Phrasing a reviewer may want to change, found by code in the current text (also after a
        person edits the draft). Drafts with a hard finding never reach this point from an agent."""
        return [
            StyleNote(rule=f.rule, severity=f.severity, text=f.text, advice=f.advice)
            for f in style_findings(f"{self.subject}\n{self.body}")
        ]


class SupplierFollowUpInput(BaseModel):
    """What the Supplier Follow-up Writer sees about one late purchase order (facts from code)."""

    po_number: str
    vendor_name: str
    item: str | None
    quantity: int | None
    amount: str
    ordered_on: date
    expected_delivery: date
    days_late: int
    buyer_company: str


class PaymentReminderInput(BaseModel):
    """What the Payment Reminder Writer sees about one overdue customer order (facts from code)."""

    order_number: str
    customer_company: str
    amount: str
    ordered_on: date
    due_on: date
    days_overdue: int
    billing_terms: str
    seller_company: str


class InterviewInviteInput(BaseModel):
    """What the Interview Invite Writer sees: the job, verified strengths and code-picked times."""

    job_title: str
    matched_skills: list[str]
    slot_options: list[str]
    duration_minutes: int
    interview_format: str
    employer: str
