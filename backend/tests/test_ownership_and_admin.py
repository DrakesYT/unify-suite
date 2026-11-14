"""Ticket owners and replies, user administration, the audit log, and the controls around
purchase orders: vendor records that follow real deliveries, the PO read from the invoice,
and approvals for requests that were waiting before the Approval Center listed them."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.llm.fake import FakeLLMClient
from app.mailer.fake import FakeEmailSender
from app.models import (
    ApprovalRequest,
    AuditLog,
    Candidate,
    InterviewSlot,
    Job,
    OutboundEmail,
    PurchaseOrder,
    PurchaseRequest,
    Ticket,
    User,
    Vendor,
)
from app.models.base import utcnow
from app.models.enums import (
    Department,
    EmailStatus,
    OrderStatus,
    PurchaseOrderStatus,
    Role,
)
from app.schemas.procurement import PurchaseOrderCreate, VendorCreate
from app.services import procurement, support
from tests.conftest import TEST_PASSWORD
from tests.pdf import make_pdf
from tests.test_finance import EXTRACTED, INVOICE_LINES
from tests.test_hr import JOB, SARA_ASSESSMENT, SARA_LINES, SARA_PROFILE

MakeUser = Callable[..., User]
AuthHeader = Callable[[User], dict[str, str]]
BACKEND_DIR = Path(__file__).resolve().parents[1]
NEW_PASSWORD = "walnut-harbor-kettle-42"


# --- tickets: an owner, and a reply that goes out after approval ---------------------------------


@pytest.fixture
def desk(db: Session, make_user: MakeUser, auth_header: AuthHeader) -> dict[str, Any]:
    agent = make_user(Role.employee, Department.support)
    manager = make_user(Role.manager, Department.support)
    clerk = make_user(Role.employee, Department.finance)
    customer = support.create_customer(db, name="Hamza Iqbal", company="Iqbal", email="h@x.io")
    ticket = Ticket(title="Order is late", description="Where is it?", customer_id=customer.id)
    db.add(ticket)
    db.commit()
    return {
        "agent": auth_header(agent),
        "agent_user": agent,
        "manager": auth_header(manager),
        "clerk_user": clerk,
        "ticket": ticket,
        "url": f"/api/support/tickets/{ticket.id}",
    }


def test_a_ticket_is_assigned_to_someone_in_support(
    client: TestClient, desk: dict[str, Any]
) -> None:
    agent, url = desk["agent"], desk["url"]
    staff = client.get("/api/support/staff", headers=agent).json()
    assert [s["full_name"] for s in staff] == ["Employee Support", "Manager Support"]

    mine = client.patch(url, headers=agent, json={"assignee_id": str(desk["agent_user"].id)})
    outsider = client.patch(url, headers=agent, json={"assignee_id": str(desk["clerk_user"].id)})
    back = client.patch(url, headers=agent, json={"assignee_id": None})

    assert mine.json()["assignee_id"] == str(desk["agent_user"].id)
    assert outsider.json()["error"]["code"] == "not_support_staff"
    assert back.json()["assignee_id"] is None


def test_a_reply_is_written_approved_and_sent(
    client: TestClient, db: Session, desk: dict[str, Any], fake_mailer: FakeEmailSender
) -> None:
    agent, manager, url = desk["agent"], desk["manager"], desk["url"]

    draft = client.post(f"{url}/emails", headers=agent).json()
    assert draft["to_address"] == "h@x.io" and draft["subject"] == "Re: Order is late"
    assert draft["status"] == "draft" and draft["ticket_id"] == str(desk["ticket"].id)
    unwritten = client.post(f"/api/support/emails/{draft['id']}/request-approval", headers=agent)
    assert unwritten.json()["error"]["code"] == "reply_not_written"

    body = "Hi Hamza,\n\nYour order left our warehouse today and arrives on Friday.\n\nSupport"
    client.patch(f"/api/support/emails/{draft['id']}", headers=agent, json={"body": body})
    waiting = client.post(
        f"/api/support/emails/{draft['id']}/request-approval", headers=agent
    ).json()
    assert waiting["status"] == "pending_approval"
    assert client.post(
        f"/api/approvals/{waiting['approval_id']}/approve", headers=agent, json={}
    ).status_code == (403)

    res = client.post(f"/api/approvals/{waiting['approval_id']}/approve", headers=manager, json={})

    assert res.status_code == 200, res.text
    assert [(m.to, m.subject) for m in fake_mailer.sent] == [("h@x.io", "Re: Order is late")]
    sent = client.get(f"{url}/emails", headers=agent).json()[0]
    assert sent["status"] == "sent"


def test_a_reply_starts_from_the_investigation_and_needs_an_address(
    client: TestClient, db: Session, desk: dict[str, Any]
) -> None:
    ticket = db.get(Ticket, desk["ticket"].id)
    assert ticket is not None
    ticket.investigation = {"draft_reply": "Hi Hamza, your parcel was delayed at customs."}
    db.add(Ticket(title="No customer", description=""))
    db.commit()
    orphan = db.scalar(select(Ticket).where(Ticket.title == "No customer"))
    assert orphan is not None

    draft = client.post(f"{desk['url']}/emails", headers=desk["agent"]).json()
    refused = client.post(f"/api/support/tickets/{orphan.id}/emails", headers=desk["agent"])

    assert draft["body"].startswith("Hi Hamza, your parcel was delayed at customs.")
    assert draft["body"].endswith("Customer Support, UNIFY Demo Corp")
    assert refused.json()["error"]["code"] == "no_customer_email"


# --- requests that were already waiting get their approval ---------------------------------------


def _alembic(url: str, revision: str) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    engine = create_engine(url)
    with engine.connect() as conn:
        config.attributes["connection"] = conn
        config.attributes["configure_logger"] = False
        command.upgrade(config, revision)
        conn.commit()
    engine.dispose()


def test_waiting_requests_and_orders_get_an_approval(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'backfill.db'}"
    _alembic(url, "0016")
    engine = create_engine(url)
    with Session(engine) as db:
        buyer = User(
            email="b@x.io",
            full_name="Buyer",
            role=Role.employee,
            department=Department.procurement,
            password_hash="x",
        )
        vendor = Vendor(name="Northwind", lead_time_days=5, on_time_rate=Decimal("0.9"))
        db.add_all([buyer, vendor])
        db.flush()
        waiting = PurchaseRequest(
            item="Chairs",
            quantity=20,
            budget_minor=600000,
            currency="USD",
            requested_by_id=buyer.id,
        )
        decided = PurchaseRequest(
            item="Desks", quantity=2, budget_minor=1, currency="USD", status="approved"
        )
        order = PurchaseOrder(
            po_number="PO-1001", vendor_id=vendor.id, amount_minor=375000, currency="USD"
        )
        db.add_all([waiting, decided, order])
        db.commit()
        waiting_id, order_id, buyer_id = waiting.id, order.id, buyer.id

    _alembic(url, "head")
    _alembic(url, "head")  # running it again adds nothing

    with Session(engine) as db:
        rows = {a.action: a for a in db.scalars(select(ApprovalRequest))}
        assert sorted(rows) == ["approve_po", "approve_request"]
        request = rows["approve_request"]
        assert request.payload["request_id"] == str(waiting_id)
        assert (request.status, request.department, request.requested_by_id) == (
            "pending",
            "procurement",
            buyer_id,
        )
        assert rows["approve_po"].payload["po_id"] == str(order_id)
        assert rows["approve_po"].payload["vendor_name"] == "Northwind"
    engine.dispose()


# --- vendor records follow deliveries; the PO can come from the invoice --------------------------


def _approved_po(db: Session, actor: User, **dates: date) -> PurchaseOrder:
    vendor = procurement.create_vendor(
        db,
        VendorCreate(name="ACME Industrial Supplies Ltd.", lead_time_days=7, on_time_rate="0.95"),
        actor,
    )
    order = procurement.create_order(
        db,
        PurchaseOrderCreate(
            po_number="PO-1007", vendor_id=vendor.id, amount_minor=425000, currency="USD"
        ),
    )
    order.status = PurchaseOrderStatus.approved
    for key, value in dates.items():
        setattr(order, key, value)
    db.commit()
    return order


def test_a_late_delivery_lowers_the_vendors_on_time_rate(
    client: TestClient, db: Session, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    buyer = make_user(Role.employee, Department.procurement)
    manager = make_user(Role.manager, Department.procurement)
    today = utcnow().date()
    order = _approved_po(
        db, buyer, ordered_on=today - timedelta(days=40), expected_delivery=today - timedelta(30)
    )
    vendor_url = f"/api/procurement/vendors/{order.vendor_id}"

    res = client.post(f"/api/procurement/orders/{order.id}/delivered", headers=auth_header(buyer))
    assert res.status_code == 200, res.text
    vendor = db.get(Vendor, order.vendor_id)
    assert vendor is not None
    db.refresh(vendor)
    assert vendor.on_time_rate == Decimal("0.9048")  # (0.95 x 20 + 0) / 21

    typed = client.patch(vendor_url, headers=auth_header(buyer), json={"on_time_rate": "1.0"})
    lead = client.patch(vendor_url, headers=auth_header(buyer), json={"lead_time_days": 9})
    fixed = client.patch(vendor_url, headers=auth_header(manager), json={"on_time_rate": "0.9"})
    assert (typed.status_code, lead.status_code, fixed.status_code) == (403, 200, 200)


def _start(client: TestClient, headers: dict[str, str], po: str | None) -> dict[str, Any]:
    res = client.post(
        "/api/workflows/supplier-payment/start",
        headers=headers,
        data={} if po is None else {"po_number": po},
        files={"file": ("invoice.pdf", make_pdf(INVOICE_LINES), "application/pdf")},
    )
    assert res.status_code == 202, res.text
    return client.get(f"/api/workflows/{res.json()['id']}", headers=headers).json()


def test_the_po_is_taken_from_the_invoice_when_none_is_typed(
    client: TestClient,
    fake_llm: FakeLLMClient,
    db: Session,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    clerk = auth_header(make_user(Role.employee, Department.finance))
    _approved_po(db, make_user(Role.manager, Department.finance))
    fake_llm.replies += [EXTRACTED, EXTRACTED | {"number": "INV-2", "po_number": "PO 1 or PO 2"}]

    found = _start(client, clerk, None)
    unclear = _start(client, clerk, None)

    assert found["status"] == "waiting_approval"
    assert found["input"]["po_number"] == "PO-1007"
    payload = found["approval"]["payload"]
    assert (payload["po_number"], payload["match_status"]) == ("PO-1007", "matched")
    assert payload["warnings"] == ["The goods for PO-1007 are not marked as delivered yet."]
    p1 = next(s for s in unclear["steps"] if s["key"] == "P1")
    assert unclear["status"] == "failed" and "type the PO number" in p1["error"]


def test_no_warning_once_the_goods_arrived_and_an_admin_decision_is_marked(
    client: TestClient,
    fake_llm: FakeLLMClient,
    db: Session,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    clerk = auth_header(make_user(Role.employee, Department.finance))
    admin = make_user(Role.admin, Department.sales, email="admin@unify.example.com")
    _approved_po(db, admin, delivered_on=utcnow().date())
    fake_llm.replies.append(EXTRACTED)

    run = _start(client, clerk, "PO-1007")
    client.post(
        f"/api/approvals/{run['approval']['id']}/approve", headers=auth_header(admin), json={}
    )

    assert run["approval"]["payload"]["warnings"] == []
    decided = db.scalar(select(AuditLog).where(AuditLog.action == "approval.approved"))
    assert decided is not None and decided.detail["admin_override"] is True


# --- hiring: batches, and the time a candidate picked --------------------------------------------


def test_one_request_screens_one_batch(
    client: TestClient, fake_llm: FakeLLMClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    headers = auth_header(make_user(Role.employee, Department.hr))
    job = client.post(
        "/api/hr/jobs",
        headers=headers,
        json=JOB,
    ).json()
    for _ in range(3):
        fake_llm.replies.append(SARA_PROFILE)
        res = client.post(
            "/api/hr/candidates/upload",
            headers=headers,
            files={"file": ("resume.pdf", make_pdf(SARA_LINES), "application/pdf")},
        )
        assert res.status_code == 201, res.text
    fake_llm.replies += [SARA_ASSESSMENT] * 3
    screen = f"/api/hr/jobs/{job['id']}/screen"

    first = client.post(screen, headers=headers, json={"limit": 2}).json()
    left = client.get(f"/api/hr/jobs/{job['id']}", headers=headers).json()["unscreened"]
    second = client.post(screen, headers=headers, json={"limit": 2}).json()

    assert (len(first), left, len(second)) == (2, 1, 3)


def test_booking_keeps_the_chosen_time_and_frees_the_others(
    client: TestClient, db: Session, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    recruiter = auth_header(make_user(Role.employee, Department.hr))
    job = Job(title="Engineer", required_skills=["Python"], min_years=1)
    candidate = Candidate(name="Sara Malik", email="s@x.io")
    db.add_all([job, candidate])
    db.flush()
    email = OutboundEmail(
        kind="interview_invite",
        department=Department.hr,
        candidate_id=candidate.id,
        job_id=job.id,
        to_address="s@x.io",
        subject="Interview",
        body="x" * 50,
        status=EmailStatus.draft,
    )
    db.add(email)
    db.flush()
    start = datetime(2026, 12, 1, 5, 0, tzinfo=UTC)
    for day in range(3):
        begins = start + timedelta(days=day)
        db.add(
            InterviewSlot(
                candidate_id=candidate.id,
                job_id=job.id,
                starts_at=begins,
                ends_at=begins + timedelta(minutes=45),
                email_id=email.id,
            )
        )
    db.commit()
    url = f"/api/hr/emails/{email.id}/slots"
    offered = client.get(url, headers=recruiter).json()
    assert len(offered) == 3 and not any(s["booked"] for s in offered)
    assert offered[0]["label"] == "Tue 1 Dec 2026, 10:00-10:45 PKT"

    early = client.post(f"{url}/{offered[1]['id']}/book", headers=recruiter)
    email.status = EmailStatus.sent
    db.commit()
    booked = client.post(f"{url}/{offered[1]['id']}/book", headers=recruiter)
    again = client.post(f"{url}/{offered[1]['id']}/book", headers=recruiter)

    assert early.json()["error"]["code"] == "not_sent"
    assert [(s["id"], s["booked"]) for s in booked.json()] == [(offered[1]["id"], True)]
    assert again.json()["error"]["code"] == "already_booked"
    free = db.scalars(select(InterviewSlot).where(InterviewSlot.released.is_(True))).all()
    assert len(free) == 2


# --- users and passwords -------------------------------------------------------------------------


def test_an_admin_manages_users(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    admin_user = make_user(Role.admin, Department.finance, email="admin@unify.example.com")
    admin = auth_header(admin_user)
    manager = auth_header(make_user(Role.manager, Department.finance))
    assert client.get("/api/users", headers=manager).status_code == 403

    created = client.post(
        "/api/users",
        headers=admin,
        json={
            "email": "New.Clerk@Unify.example.com",
            "full_name": "New Clerk",
            "role": "employee",
            "department": "finance",
            "password": NEW_PASSWORD,
        },
    )
    assert created.status_code == 201, created.text
    clerk = created.json()
    assert (clerk["email"], clerk["is_active"]) == ("new.clerk@unify.example.com", True)
    login = {"email": clerk["email"], "password": NEW_PASSWORD}
    session = client.post("/api/auth/login", json=login)
    assert session.status_code == 200
    token = {"Authorization": f"Bearer {client.cookies.get('unify_session')}"}
    client.cookies.clear()

    promoted = client.patch(f"/api/users/{clerk['id']}", headers=admin, json={"role": "manager"})
    assert promoted.json()["role"] == "manager"
    assert client.get("/api/auth/me", headers=token).status_code == 401  # signs in again

    weak = client.post(
        f"/api/users/{clerk['id']}/password", headers=admin, json={"password": "password123"}
    )
    assert weak.json()["error"]["code"] == "weak_password"
    off = client.patch(f"/api/users/{clerk['id']}", headers=admin, json={"is_active": False})
    assert off.json()["is_active"] is False
    assert client.post("/api/auth/login", json=login).status_code == 403
    own = client.patch(f"/api/users/{admin_user.id}", headers=admin, json={"is_active": False})
    assert own.json()["error"]["code"] == "own_account"
    assert len(client.get("/api/users", headers=admin).json()) == 3


def test_a_user_changes_their_own_password(
    client: TestClient, db: Session, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    user = make_user(Role.employee, Department.sales)
    here, elsewhere = auth_header(user), auth_header(user)
    demo = auth_header(make_user(Role.employee, Department.hr, email="hr@demo.example.com"))

    def change(headers: dict[str, str], current: str, new: str) -> Any:
        body = {"current_password": current, "new_password": new}
        return client.post("/api/auth/password", headers=headers, json=body)

    assert change(here, "not-it", NEW_PASSWORD).json()["error"]["code"] == "wrong_password"
    assert change(here, TEST_PASSWORD, "short").json()["error"]["code"] == "weak_password"
    assert change(demo, TEST_PASSWORD, NEW_PASSWORD).json()["error"]["code"] == "demo_account"
    assert change(here, TEST_PASSWORD, NEW_PASSWORD).status_code == 204

    assert client.get("/api/auth/me", headers=here).status_code == 200
    assert client.get("/api/auth/me", headers=elsewhere).status_code == 401
    old = client.post("/api/auth/login", json={"email": user.email, "password": TEST_PASSWORD})
    new = client.post("/api/auth/login", json={"email": user.email, "password": NEW_PASSWORD})
    assert (old.status_code, new.status_code) == (401, 200)


# --- the audit log can be read -------------------------------------------------------------------


def test_the_audit_log_is_filtered_and_paged(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    manager = auth_header(make_user(Role.manager, Department.sales))
    rep = auth_header(make_user(Role.employee, Department.sales))
    for n in range(3):
        body = {"name": "A", "company": f"Co {n}", "email": f"a{n}@acme.io"}
        assert client.post("/api/sales/leads", headers=manager, json=body).status_code == 201

    everything = client.get("/api/dashboard/audit", headers=manager).json()
    leads = client.get("/api/dashboard/audit?q=lead.created&limit=2", headers=manager).json()
    older = client.get(
        "/api/dashboard/audit",
        headers=manager,
        params={"q": "lead", "before": leads[-1]["at"]},
    ).json()

    assert len(everything) >= 3
    assert [e["action"] for e in leads] == ["lead.created", "lead.created"]
    assert len(older) == 1 and older[0]["id"] not in {e["id"] for e in leads}
    assert client.get("/api/dashboard/audit", headers=rep).status_code == 403


def test_refunded_orders_are_untouched_by_ordinary_tickets(db: Session) -> None:
    customer = support.create_customer(db, name="A B", company=None, email=None)
    order = support.add_order(
        db,
        customer.id,
        order_number="SO-1",
        amount_minor=100,
        currency="USD",
        status=OrderStatus.delivered,
        ordered_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    assert order.status == OrderStatus.delivered
