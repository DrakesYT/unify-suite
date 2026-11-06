import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class Money(BaseModel):
    amount_minor: int
    currency: str


class Kpis(BaseModel):
    """FR-DASH-01: the five headline numbers, plus what waits for a human."""

    sales_pipeline: list[Money]  # open leads (not won or lost), per currency
    unpaid_invoices: list[Money]  # received, needs review or approved, not yet paid
    open_vacancies: int
    open_tickets: int
    pending_purchase_requests: int
    pending_approvals: int


class Count(BaseModel):
    label: str
    value: int


class DayCount(BaseModel):
    day: str
    succeeded: int
    failed: int


class Charts(BaseModel):
    leads_by_rating: list[Count]
    tickets_by_category: list[Count]
    invoices_by_match: list[Count]
    agent_calls_by_day: list[DayCount]


class ActivityItem(BaseModel):
    id: uuid.UUID
    at: datetime
    actor_name: str | None
    action: str
    entity: str
    entity_id: str | None
    detail: dict[str, Any]


# --- Dashboard overview: one payload for every panel. All numbers are counted by code. ---


class Insight(BaseModel):
    """One fact worth a look, worded by code from live data (no model involved)."""

    tone: Literal["alert", "warn", "good", "info"]
    text: str
    link: str


class HiringCard(BaseModel):
    candidate_id: uuid.UUID
    name: str
    job_title: str | None
    score: int | None


class HiringStage(BaseModel):
    stage: Literal["applied", "screened", "invite_pending", "invite_sent"]
    count: int
    cards: list[HiringCard]  # the first few; `count` is the full number


class Hiring(BaseModel):
    open_jobs: int
    stages: list[HiringStage]
    applications_by_day: list[Count]  # label = ISO date


class DealStage(BaseModel):
    stage: str  # a lead status
    count: int
    value: list[Money]


class Deal(BaseModel):
    lead_id: uuid.UUID
    company: str
    contact: str
    status: str
    rating: str | None
    amount_minor: int
    currency: str


class SalesTarget(BaseModel):
    """Won deals this quarter against the quarterly target (a company setting)."""

    quarter: str  # e.g. "Q4 2026"
    target_minor: int
    won_minor: int
    currency: str
    set_by: str | None = None  # who set the target in the app; None = deployment default
    set_at: datetime | None = None


class Crm(BaseModel):
    stages: list[DealStage]
    pipeline: list[Money]
    win_rate: int | None  # percent of closed deals that were won; None until one closes
    won: int
    lost: int
    target: SalesTarget
    top_deals: list[Deal]


class TicketRow(BaseModel):
    ticket_id: uuid.UUID
    title: str
    customer_name: str | None
    category: str | None
    urgency: str | None
    status: str
    created_at: datetime


class SupportPanel(BaseModel):
    open: int
    by_urgency: list[Count]
    by_category: list[Count]
    tickets: list[TicketRow]


class InvoiceRow(BaseModel):
    invoice_id: uuid.UUID
    number: str
    vendor_name: str
    amount_minor: int
    currency: str
    status: str
    match_status: str | None


class ReceivableRow(BaseModel):
    order_number: str
    customer_name: str
    amount_minor: int
    currency: str
    days_overdue: int
    status: str


class LateDelivery(BaseModel):
    po_number: str
    vendor_name: str
    days_late: int


class MoneyPanel(BaseModel):
    unpaid_invoices: list[Money]
    invoices_to_review: int
    invoices_to_pay: int  # approved, payment not yet submitted
    recent_invoices: list[InvoiceRow]
    receivables_open: int
    receivables_overdue: int
    overdue_amount: list[Money]
    receivables_on_hold: int
    overdue: list[ReceivableRow]
    deliveries_open: int
    late_deliveries: list[LateDelivery]


class AgentHealth(BaseModel):
    """Agent and tool calls in the last 24 hours."""

    calls: int
    succeeded: int
    failed: int


class Overview(BaseModel):
    insights: list[Insight]
    hiring: Hiring
    crm: Crm
    support: SupportPanel
    money: MoneyPanel
    agents: AgentHealth


class SearchHit(BaseModel):
    kind: str
    title: str
    subtitle: str
    link: str  # a page in the app
