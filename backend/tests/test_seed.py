"""The demo seed: complete, repeatable, and good enough to run Workflow B end to end."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import SESSION_COOKIE
from app.llm.fake import FakeLLMClient
from app.models import Candidate, Lead, Payment, PurchaseOrder, User
from app.seed import DEMO_DOMAIN, USERS, demo_invoice_lines, seed
from tests.pdf import make_pdf

PASSWORD = "demo-password-for-tests"


def _login(client: TestClient, handle: str) -> dict[str, str]:
    res = client.post(
        "/api/auth/login", json={"email": f"{handle}@{DEMO_DOMAIN}", "password": PASSWORD}
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.cookies[SESSION_COOKIE]}"}


def test_seed_is_complete_and_repeatable(db: Session) -> None:
    first = seed(db, PASSWORD)

    assert first == {
        "users": len(USERS),
        "vendors": 5,
        "purchase_orders": 3,
        "invoices": 3,
        "leads": 8,
        "jobs": 3,
        "candidates": 4,
        "customers": 3,
        "orders": 7,
        "tickets": 3,
        "purchase_requests": 3,
        "quotes": 7,
        "delivery_dates": 3,
        "payments_received": 1,
    }
    assert all(n == 0 for n in seed(db, PASSWORD).values())  # second run adds nothing
    assert db.scalar(select(func.count()).select_from(User)) == len(USERS)
    assert db.scalar(select(func.count()).select_from(Lead).where(Lead.rating.is_not(None))) == 0
    assert all(c.file_id for c in db.scalars(select(Candidate)))
    statuses = {o.po_number: o.delivery_status for o in db.scalars(select(PurchaseOrder))}
    assert statuses == {"PO-1007": "on_track", "PO-2001": "late", "PO-2002": "delivered"}


def test_every_demo_user_can_sign_in(client: TestClient, db: Session) -> None:
    seed(db, PASSWORD)

    for handle, *_ in USERS:
        _login(client, handle)


def test_dashboard_shows_the_seeded_totals(client: TestClient, db: Session) -> None:
    seed(db, PASSWORD)

    kpis = client.get("/api/dashboard/kpis", headers=_login(client, "ceo")).json()

    # open leads: 48,000 + 36,000 + 12,000 + 25,000 + 0 + 60,000 (won and lost excluded)
    assert kpis["sales_pipeline"] == [{"amount_minor": 18_100_000, "currency": "USD"}]
    # unpaid: ACME-5521 980.00 + TH-30019 2,545.00 (NW-87110 is already paid)
    assert kpis["unpaid_invoices"] == [{"amount_minor": 352_500, "currency": "USD"}]
    assert (kpis["open_vacancies"], kpis["open_tickets"], kpis["pending_purchase_requests"]) == (
        2,
        3,
        2,
    )


def test_workflow_b_end_to_end_on_seeded_data(
    client: TestClient, db: Session, fake_llm: FakeLLMClient
) -> None:
    seed(db, PASSWORD)
    clerk, manager = _login(client, "finance.clerk"), _login(client, "finance.manager")
    fake_llm.replies.append(
        {
            "number": "INV-DEMO-042",
            "invoice_date": "2026-11-04",
            "vendor_name": "ACME Industrial Supplies Ltd.",
            "total_amount": "4250.00",
            "currency": "USD",
            "po_number": "PO-1007",
        }
    )

    started = client.post(
        "/api/workflows/supplier-payment/start",
        headers=clerk,
        data={"po_number": "PO-1007"},
        files={"file": ("acme.pdf", make_pdf(demo_invoice_lines()), "application/pdf")},
    ).json()
    run = client.get(f"/api/workflows/{started['id']}", headers=clerk).json()
    assert run["status"] == "waiting_approval"

    client.post(f"/api/approvals/{run['approval']['id']}/approve", json={}, headers=manager)

    run = client.get(f"/api/workflows/{started['id']}", headers=clerk).json()
    assert run["status"] == "completed" and run["result"]["passed"] is True
    assert db.scalar(select(Payment.amount_minor)) == 425_000
    assert "PO-1007" in fake_llm.calls[0].user
