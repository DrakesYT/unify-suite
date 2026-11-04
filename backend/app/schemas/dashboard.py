import uuid
from datetime import datetime
from typing import Any

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
