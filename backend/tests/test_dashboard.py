"""FR-DASH-01 KPIs match the seeded totals exactly; FR-DASH-02 feed shows the last 20 events."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    ApprovalRequest,
    AuditLog,
    Invoice,
    Job,
    Lead,
    PurchaseRequest,
    Ticket,
    User,
    Vendor,
)
from app.models.enums import (
    ApprovalStatus,
    Department,
    InvoiceStatus,
    JobStatus,
    LeadRating,
    LeadStatus,
    PurchaseRequestStatus,
    Role,
    TicketCategory,
    TicketStatus,
)

AuthHeader = Callable[[User], dict[str, str]]


@pytest.fixture
def seeded(db: Session) -> None:
    def lead(status: LeadStatus, value: int, rating: LeadRating | None = None) -> Lead:
        return Lead(
            name="x",
            company="c",
            email="x@example.com",
            status=status,
            value_minor=value,
            rating=rating,
        )

    vendor = Vendor(name="V", lead_time_days=1, on_time_rate=Decimal("0.9"))
    db.add(vendor)
    db.flush()

    def invoice(number: str, status: InvoiceStatus, amount: int) -> Invoice:
        return Invoice(
            number=number,
            vendor_id=vendor.id,
            invoice_date=date(2026, 11, 1),
            amount_minor=amount,
            currency="USD",
            status=status,
        )

    db.add_all(
        [
            lead(LeadStatus.new, 100_000, LeadRating.hot),
            lead(LeadStatus.contacted, 250_000, LeadRating.warm),
            lead(LeadStatus.qualified, 50_000),
            lead(LeadStatus.won, 999_999),  # closed, not pipeline
            lead(LeadStatus.lost, 888_888),
            invoice("I-1", InvoiceStatus.received, 10_000),
            invoice("I-2", InvoiceStatus.needs_review, 20_000),
            invoice("I-3", InvoiceStatus.approved, 30_000),
            invoice("I-4", InvoiceStatus.payment_submitted, 40_000),  # paid
            invoice("I-5", InvoiceStatus.rejected, 50_000),  # will not be paid
            Job(title="A", required_skills=["x"], status=JobStatus.open),
            Job(title="B", required_skills=["x"], status=JobStatus.open),
            Job(title="C", required_skills=["x"], status=JobStatus.closed),
            Ticket(title="t1", status=TicketStatus.open, category=TicketCategory.refund),
            Ticket(title="t2", status=TicketStatus.investigating, category=TicketCategory.refund),
            Ticket(title="t3", status=TicketStatus.escalated, category=TicketCategory.legal),
            Ticket(title="t4", status=TicketStatus.resolved),
            PurchaseRequest(
                item="p1",
                quantity=1,
                budget_minor=1,
                currency="USD",
                status=PurchaseRequestStatus.pending,
            ),
            PurchaseRequest(
                item="p2",
                quantity=1,
                budget_minor=1,
                currency="USD",
                status=PurchaseRequestStatus.approved,
            ),
            ApprovalRequest(
                action="pay_invoice",
                payload={},
                required_role=Role.manager,
                department=Department.finance,
            ),
            ApprovalRequest(
                action="pay_invoice",
                payload={},
                required_role=Role.manager,
                department=Department.finance,
                status=ApprovalStatus.approved,
            ),
        ]
    )
    db.commit()


def test_kpis_match_the_seeded_totals(
    client: TestClient, seeded: None, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    res = client.get(
        "/api/dashboard/kpis", headers=auth_header(make_user(Role.executive, Department.finance))
    )

    assert res.status_code == 200, res.text
    assert res.json() == {
        "sales_pipeline": [{"amount_minor": 400_000, "currency": "USD"}],
        "unpaid_invoices": [{"amount_minor": 60_000, "currency": "USD"}],
        "open_vacancies": 2,
        "open_tickets": 3,
        "pending_purchase_requests": 1,
        "pending_approvals": 1,
    }


def test_charts_break_down_the_data(
    client: TestClient, seeded: None, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    body = client.get("/api/dashboard/charts", headers=auth_header(make_user(Role.manager))).json()

    assert {c["label"]: c["value"] for c in body["leads_by_rating"]} == {
        "unrated": 3,
        "hot": 1,
        "warm": 1,
    }
    assert body["tickets_by_category"][0] == {"label": "refund", "value": 2}
    assert len(body["agent_calls_by_day"]) == 7


def test_feed_shows_the_latest_20_of_25_events(
    client: TestClient, db: Session, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    viewer = make_user(Role.executive, Department.finance)
    start = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    for i in range(25):  # one second apart, so "newest" is unambiguous on any clock
        db.add(
            AuditLog(
                at=start + timedelta(seconds=i),
                action=f"test.event_{i:02d}",
                entity="test",
                actor_id=viewer.id,
            )
        )
    db.commit()

    feed = client.get("/api/dashboard/activity", headers=auth_header(viewer)).json()

    assert len(feed) == 20
    assert feed[0]["action"] == "test.event_24"  # newest first
    assert feed[0]["actor_name"] == viewer.full_name


def test_employees_do_not_get_the_cross_department_dashboard(
    client: TestClient, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    assert (
        client.get("/api/dashboard/kpis", headers=auth_header(make_user(Role.employee))).status_code
        == 403
    )
