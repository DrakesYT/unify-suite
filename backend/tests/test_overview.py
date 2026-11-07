"""Dashboard overview panels and the top-bar search: real rows in, exact numbers out."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    ApprovalRequest,
    Candidate,
    CandidateScore,
    Customer,
    Invoice,
    Job,
    Lead,
    Order,
    OutboundEmail,
    PurchaseOrder,
    Ticket,
    User,
    Vendor,
)
from app.models.base import utcnow
from app.models.enums import (
    Department,
    EmailStatus,
    InvoiceStatus,
    LeadRating,
    LeadStatus,
    OrderStatus,
    PurchaseOrderStatus,
    Role,
    TicketCategory,
    TicketStatus,
    Urgency,
)
from app.services import interviews
from app.services.company_settings import quarter_of

AuthHeader = Callable[[User], dict[str, str]]


@pytest.fixture
def org(db: Session) -> None:
    today = utcnow().date()
    job = Job(title="Backend Engineer", required_skills=["python"])
    vendor = Vendor(name="Northwind", lead_time_days=5, on_time_rate=Decimal("0.9"))
    customer = Customer(name="Sara", company="Karachi Logistics", billing_terms="net_30")
    db.add_all([job, vendor, customer])
    db.flush()

    applied = Candidate(name="Ali Applied")
    screened = Candidate(name="Sana Screened")
    pending = Candidate(name="Omar Pending")
    sent = Candidate(name="Hina Sent")
    bounced = Candidate(name="Zara Rejected")  # invite rejected → back to screened
    db.add_all([applied, screened, pending, sent, bounced])
    db.flush()
    for cand, score in ((screened, 81), (pending, 74), (sent, 90), (bounced, 60)):
        db.add(CandidateScore(candidate_id=cand.id, job_id=job.id, score=score))

    def invite(cand: Candidate, status: EmailStatus) -> OutboundEmail:
        return OutboundEmail(
            kind=interviews.KIND,
            department=Department.hr,
            candidate_id=cand.id,
            job_id=job.id,
            to_address="x@example.com",
            subject="Interview",
            body="b",
            status=status,
        )

    db.add_all(
        [
            invite(pending, EmailStatus.pending_approval),
            invite(sent, EmailStatus.sent),
            invite(bounced, EmailStatus.rejected),
        ]
    )

    def lead(company: str, status: LeadStatus, value: int, rating: LeadRating | None = None):  # type: ignore[no-untyped-def]
        return Lead(
            name="n",
            company=company,
            email=f"{company}@example.com",
            status=status,
            value_minor=value,
            rating=rating,
        )

    db.add_all(
        [
            lead("Indus", LeadStatus.contacted, 4_800_000, LeadRating.hot),
            lead("Lahore", LeadStatus.new, 1_200_000),
            lead("Won Co", LeadStatus.won, 3_000_000),
            lead("Lost Co", LeadStatus.lost, 900_000),
            lead("Lost Too", LeadStatus.lost, 100_000),
        ]
    )

    db.add_all(
        [
            Ticket(title="Refund now", status=TicketStatus.open, urgency=Urgency.normal),
            Ticket(
                title="Site down",
                status=TicketStatus.escalated,
                urgency=Urgency.critical,
                category=TicketCategory.technical,
            ),
            Ticket(title="Old", status=TicketStatus.resolved, urgency=Urgency.critical),
        ]
    )

    db.add_all(
        [
            Invoice(
                number="INV-1",
                vendor_id=vendor.id,
                invoice_date=today,
                amount_minor=50_000,
                currency="USD",
                status=InvoiceStatus.needs_review,
            ),
            Invoice(
                number="INV-2",
                vendor_id=vendor.id,
                invoice_date=today,
                amount_minor=20_000,
                currency="USD",
                status=InvoiceStatus.approved,
            ),
            Invoice(
                number="INV-3",
                vendor_id=vendor.id,
                invoice_date=today,
                amount_minor=99_000,
                currency="USD",
                status=InvoiceStatus.payment_submitted,
            ),
            PurchaseOrder(
                po_number="PO-LATE",
                vendor_id=vendor.id,
                amount_minor=1,
                currency="USD",
                status=PurchaseOrderStatus.approved,
                ordered_on=today - timedelta(days=20),
                expected_delivery=today - timedelta(days=13),
            ),
            PurchaseOrder(
                po_number="PO-ONTIME",
                vendor_id=vendor.id,
                amount_minor=1,
                currency="USD",
                status=PurchaseOrderStatus.approved,
                ordered_on=today,
                expected_delivery=today + timedelta(days=5),
            ),
            Order(
                order_number="SO-OLD",
                customer_id=customer.id,
                amount_minor=70_000,
                currency="USD",
                status=OrderStatus.delivered,
                ordered_at=datetime.now(UTC) - timedelta(days=45),
            ),
            ApprovalRequest(
                action="pay_invoice",
                payload={},
                required_role=Role.manager,
                department=Department.finance,
            ),
        ]
    )
    db.commit()


def _overview(client: TestClient, user: User, auth_header: AuthHeader) -> dict:  # type: ignore[type-arg]
    res = client.get("/api/dashboard/overview", headers=auth_header(user))
    assert res.status_code == 200, res.text
    return res.json()


def test_hiring_board_puts_each_candidate_in_the_furthest_proven_stage(
    client: TestClient, org: None, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    body = _overview(client, make_user(Role.executive), auth_header)["hiring"]

    names = {s["stage"]: [c["name"] for c in s["cards"]] for s in body["stages"]}
    assert names == {
        "applied": ["Ali Applied"],
        "screened": ["Sana Screened", "Zara Rejected"],  # best score first
        "invite_pending": ["Omar Pending"],
        "invite_sent": ["Hina Sent"],
    }
    assert body["open_jobs"] == 1
    assert len(body["applications_by_day"]) == 14
    assert body["applications_by_day"][-1]["value"] == 5  # all five applied today


def test_deal_board_counts_pipeline_win_rate_and_target(
    client: TestClient, org: None, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    crm = _overview(client, make_user(Role.manager), auth_header)["crm"]

    stages = {s["stage"]: s["count"] for s in crm["stages"]}
    assert stages == {"new": 1, "contacted": 1, "qualified": 0, "won": 1, "lost": 2}
    assert crm["pipeline"] == [{"amount_minor": 6_000_000, "currency": "USD"}]
    assert crm["win_rate"] == 33  # 1 won of 3 closed
    assert crm["target"]["won_minor"] == 3_000_000
    assert crm["target"]["target_minor"] == 250_000 * 100  # the default setting, in cents
    assert crm["target"]["quarter"] == quarter_of(utcnow().date())[0]
    assert [d["company"] for d in crm["top_deals"]] == ["Indus", "Lahore"]


def test_support_and_money_panels(
    client: TestClient, org: None, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    body = _overview(client, make_user(Role.admin), auth_header)

    support = body["support"]
    assert support["open"] == 2
    assert support["tickets"][0]["title"] == "Site down"  # critical first
    assert support["by_urgency"] == [
        {"label": "critical", "value": 1},
        {"label": "normal", "value": 1},
    ]

    money = body["money"]
    assert money["unpaid_invoices"] == [{"amount_minor": 70_000, "currency": "USD"}]
    assert (money["invoices_to_review"], money["invoices_to_pay"]) == (1, 1)
    assert money["receivables_overdue"] == 1
    assert money["overdue"][0]["order_number"] == "SO-OLD"
    assert money["deliveries_open"] == 2
    assert money["late_deliveries"] == [
        {"po_number": "PO-LATE", "vendor_name": "Northwind", "days_late": 13}
    ]


def test_insights_are_facts_with_links(
    client: TestClient, org: None, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    insights = _overview(client, make_user(Role.executive), auth_header)["insights"]

    texts = [i["text"] for i in insights]
    assert texts[0] == "1 decision waiting for a manager"
    assert "PO-LATE from Northwind is 13 days late" in texts
    assert "1 customer payment overdue (700.00 USD)" in texts
    assert "1 urgent ticket open" in texts
    assert "1 hot lead in the pipeline (Indus)" in texts
    assert all(i["link"].startswith("/") for i in insights)


def test_empty_database_is_all_clear(
    client: TestClient, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    body = _overview(client, make_user(Role.executive), auth_header)

    assert body["insights"] == [
        {"tone": "good", "text": "All clear: nothing is waiting on anyone", "link": "/activity"}
    ]
    assert body["crm"]["win_rate"] is None


def test_employees_do_not_get_the_overview(
    client: TestClient, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    res = client.get("/api/dashboard/overview", headers=auth_header(make_user(Role.employee)))
    assert res.status_code == 403


def test_search_finds_across_departments_for_leaders(
    client: TestClient, org: None, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    res = client.get("/api/search?q=karachi", headers=auth_header(make_user(Role.executive)))

    assert res.status_code == 200, res.text
    assert [(h["kind"], h["title"]) for h in res.json()] == [("order", "SO-OLD")]

    hits = client.get("/api/search?q=north", headers=auth_header(make_user(Role.manager))).json()
    assert [h["kind"] for h in hits] == ["vendor"]


def test_search_only_shows_an_employee_their_own_department(
    client: TestClient, org: None, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    sales_rep = make_user(Role.employee, Department.sales)

    hits = client.get("/api/search?q=o", headers=auth_header(sales_rep))
    assert hits.status_code == 422  # too short

    found = client.get("/api/search?q=co", headers=auth_header(sales_rep)).json()
    assert {h["kind"] for h in found} == {"lead"}
    assert all(h["link"].startswith("/sales#lead-") for h in found)


def test_search_treats_wildcards_as_text(
    client: TestClient, org: None, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    hits = client.get("/api/search?q=%25%25", headers=auth_header(make_user(Role.admin))).json()
    assert hits == []
