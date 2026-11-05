"""Purchase order delivery tracking and supplier follow-ups for late orders."""

import os
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import SELLER_COMPANY
from app.llm.fake import FakeLLMClient
from app.mailer.fake import FakeEmailSender
from app.models import PurchaseOrder, User
from app.models.base import utcnow
from app.models.enums import Department, PurchaseOrderStatus, Role
from app.schemas.procurement import PurchaseOrderCreate, VendorCreate
from app.services import procurement

API = "/api/procurement"
APPROVALS = "/api/approvals"
Headers = dict[str, str]
FOLLOW_UP = {
    "subject": "PO-2001 is 13 days late: please confirm a new delivery date",
    "body": (
        "Purchase order PO-2001 was expected on the agreed date and is now 13 days late.\n\n"
        "Please confirm a new delivery date and the reason for the delay within two business "
        "days so we can plan our warehouse work."
    ),
}


@pytest.fixture
def people(
    make_user: Callable[..., User], auth_header: Callable[[User], Headers]
) -> dict[str, Headers]:
    users = {
        "buyer": make_user(Role.employee, Department.procurement, email="buyer@unify.example.com"),
        "manager": make_user(Role.manager, Department.procurement, email="pm@unify.example.com"),
        "sales_manager": make_user(Role.manager, Department.sales),
        "sales_rep": make_user(Role.employee, Department.sales),
    }
    return {name: auth_header(user) for name, user in users.items()}


def _order(
    db: Session,
    *,
    days_ago: int,
    contact: str | None = "billing@northwind.example.com",
    status: PurchaseOrderStatus = PurchaseOrderStatus.approved,
) -> PurchaseOrder:
    admin = User(
        email=f"admin-{days_ago}@unify.example.com",
        full_name="Admin",
        password_hash="x",
        role=Role.admin,
        department=Department.procurement,
    )
    db.add(admin)
    db.flush()
    vendor = procurement.create_vendor(
        db,
        VendorCreate(
            name=f"Northwind Metals Ltd. {days_ago}" if days_ago != 18 else "Northwind Metals Ltd.",
            contact=contact,
            lead_time_days=5,
            on_time_rate="0.97",
        ),
        admin,
    )
    order = procurement.create_order(
        db,
        PurchaseOrderCreate(
            po_number=f"PO-{2000 + days_ago - 17}",
            vendor_id=vendor.id,
            amount_minor=1_280_050,
            currency="USD",
        ),
    )
    order.status = status
    order.ordered_on = utcnow().date() - timedelta(days=days_ago)
    order.expected_delivery = order.ordered_on + timedelta(days=5)
    db.commit()
    return order


def _draft(client: TestClient, headers: Headers, order: PurchaseOrder) -> Any:
    return client.post(f"{API}/orders/{order.id}/emails", headers=headers)


def test_approving_a_po_starts_tracking_from_the_vendor_lead_time(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient, db: Session
) -> None:
    vendor = client.post(
        f"{API}/vendors",
        headers=people["buyer"],
        json={
            "name": "QuickShip IT",
            "contact": "sales@quickship.example.com",
            "lead_time_days": 3,
            "on_time_rate": "0.97",
        },
    ).json()
    created = client.post(
        f"{API}/orders",
        headers=people["buyer"],
        json={
            "po_number": "PO-3001",
            "vendor_id": vendor["id"],
            "amount_minor": 1000,
            "currency": "USD",
        },
    ).json()
    assert created["order"]["delivery_status"] == "not_ordered"

    approved = client.post(
        f"{APPROVALS}/{created['approval_id']}/approve",
        headers=people["manager"],
        json={"comment": None},
    )
    assert approved.status_code == 200, approved.text

    order = client.get(f"{API}/orders/PO-3001", headers=people["buyer"]).json()
    today = utcnow().date()
    assert order["ordered_on"] == today.isoformat()
    assert order["expected_delivery"] == (today + timedelta(days=3)).isoformat()
    assert (order["delivery_status"], order["days_late"]) == ("on_track", 0)


def test_late_on_track_and_delivered_are_computed_from_dates(db: Session) -> None:
    late = _order(db, days_ago=18)
    on_track = _order(db, days_ago=2)
    pending = _order(db, days_ago=30, status=PurchaseOrderStatus.pending_approval)

    assert (late.delivery_status, late.days_late) == ("late", 13)
    assert (on_track.delivery_status, on_track.days_late) == ("on_track", 0)
    assert (pending.delivery_status, pending.days_late) == ("not_ordered", 0)
    late.delivered_on = utcnow().date()
    assert (late.delivery_status, late.days_late) == ("delivered", 0)


def test_buyer_marks_delivered_once(
    client: TestClient, people: dict[str, Headers], db: Session
) -> None:
    order = _order(db, days_ago=18)

    res = client.post(f"{API}/orders/{order.id}/delivered", headers=people["buyer"])

    assert res.status_code == 200 and res.json()["delivery_status"] == "delivered"
    again = client.post(f"{API}/orders/{order.id}/delivered", headers=people["buyer"])
    assert again.status_code == 409


def test_a_confirmed_new_date_clears_the_late_flag(
    client: TestClient, people: dict[str, Headers], db: Session
) -> None:
    order = _order(db, days_ago=18)
    new_date = (utcnow().date() + timedelta(days=4)).isoformat()

    res = client.patch(
        f"{API}/orders/{order.id}/delivery",
        headers=people["buyer"],
        json={"expected_delivery": new_date},
    )

    assert res.json()["expected_delivery"] == new_date
    assert res.json()["delivery_status"] == "on_track"


def test_follow_up_is_drafted_only_for_late_orders(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient, db: Session
) -> None:
    on_track = _order(db, days_ago=2)

    res = _draft(client, people["buyer"], on_track)

    assert res.status_code == 409 and res.json()["error"]["code"] == "not_late"
    assert fake_llm.calls == []


def test_follow_up_quotes_the_facts_and_is_signed_by_code(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient, db: Session
) -> None:
    order = _order(db, days_ago=18)
    fake_llm.replies.append(FOLLOW_UP)

    res = _draft(client, people["buyer"], order)

    assert res.status_code == 201, res.text
    email = res.json()
    assert email["to_address"] == "billing@northwind.example.com"
    assert email["po_id"] == str(order.id)
    assert email["body"].startswith("Hello Northwind Metals Ltd. team,\n\n")
    assert email["body"].endswith(f"Procurement, {SELLER_COMPANY}")
    prompt = fake_llm.calls[-1].user
    assert '"po_number": "PO-2001"' in prompt and '"days_late": 13' in prompt


def test_a_draft_that_omits_the_po_number_is_retried(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient, db: Session
) -> None:
    order = _order(db, days_ago=18)
    vague = {
        "subject": "Your late order",
        "body": FOLLOW_UP["body"].replace("PO-2001", "the order"),
    }
    fake_llm.replies += [vague, FOLLOW_UP]

    assert _draft(client, people["buyer"], order).status_code == 201
    assert len(fake_llm.calls) == 2


def test_vendor_without_an_email_cannot_be_chased(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient, db: Session
) -> None:
    order = _order(db, days_ago=18, contact="Call Ahmed on the landline")

    res = _draft(client, people["buyer"], order)

    assert res.status_code == 409 and res.json()["error"]["code"] == "no_vendor_email"


def test_procurement_manager_approves_and_the_supplier_is_emailed(
    client: TestClient,
    people: dict[str, Headers],
    fake_llm: FakeLLMClient,
    fake_mailer: FakeEmailSender,
    db: Session,
) -> None:
    order = _order(db, days_ago=18)
    fake_llm.replies.append(FOLLOW_UP)
    email = _draft(client, people["buyer"], order).json()
    asked = client.post(f"{API}/emails/{email['id']}/request-approval", headers=people["buyer"])
    approval_id = asked.json()["approval_id"]

    [approval] = client.get(APPROVALS, headers=people["manager"]).json()["items"]
    assert approval["department"] == "procurement"
    assert approval["payload"]["company"] == "Northwind Metals Ltd."
    assert approval["payload"]["po_number"] == "PO-2001"
    # A sales manager cannot send procurement's email.
    denied = client.post(
        f"{APPROVALS}/{approval_id}/approve",
        headers=people["sales_manager"],
        json={"comment": None},
    )
    assert denied.status_code == 403

    client.post(
        f"{APPROVALS}/{approval_id}/approve", headers=people["manager"], json={"comment": None}
    )

    [message] = fake_mailer.sent
    assert message.to == "billing@northwind.example.com"
    assert "PO-2001" in message.subject
    [sent] = client.get(f"{API}/orders/{order.id}/emails", headers=people["buyer"]).json()
    assert sent["status"] == "sent"


def test_departments_cannot_touch_each_others_emails(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient, db: Session
) -> None:
    order = _order(db, days_ago=18)
    fake_llm.replies.append(FOLLOW_UP)
    email = _draft(client, people["buyer"], order).json()

    via_sales = client.patch(
        f"/api/sales/emails/{email['id']}",
        headers=people["sales_rep"],
        json={"subject": "Hijacked subject"},
    )

    assert via_sales.status_code == 404
    assert _draft(client, people["sales_rep"], order).status_code == 403


@pytest.mark.skipif(not os.environ.get("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1 and LLM_API_KEY")
def test_live_vultr_writes_a_sendable_follow_up() -> None:
    """The real model's chase email passes the same checks a sendable email must pass."""
    from app.agents.supplier_followup import SupplierFollowUpWriter
    from app.config import get_settings
    from app.llm.vultr import VultrLLMClient
    from app.schemas.outreach import SupplierFollowUpInput

    settings = get_settings()
    llm = VultrLLMClient(
        base_url=settings.llm_base_url,
        api_key=os.environ["LIVE_LLM_API_KEY"],
        model=settings.llm_model,
    )
    today = utcnow().date()
    facts = SupplierFollowUpInput(
        po_number="PO-2001",
        vendor_name="Northwind Metals Ltd.",
        item="Steel brackets for warehouse racks",
        quantity=400,
        amount="12,800.50 USD",
        ordered_on=today - timedelta(days=18),
        expected_delivery=today - timedelta(days=13),
        days_late=13,
        buyer_company=SELLER_COMPANY,
    )

    draft = SupplierFollowUpWriter().run(facts, llm)  # raises if not sendable

    assert "PO-2001" in draft.subject + draft.body
