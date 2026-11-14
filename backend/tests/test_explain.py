"""The "Why?" drawer: real flows run with the fake model, then explained from stored records."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.llm.fake import FakeLLMClient
from app.models import OutboundEmail, Ticket, User
from app.models.enums import (
    Department,
    EmailStatus,
    PurchaseOrderStatus,
    Role,
    TicketCategory,
    Urgency,
)
from app.schemas.procurement import PurchaseOrderCreate, VendorCreate
from app.services import procurement
from tests.pdf import make_pdf
from tests.test_finance import EXTRACTED, INVOICE_LINES
from tests.test_hr import SARA_ASSESSMENT, SARA_PROFILE, _job, _upload
from tests.test_sales import HOT, LEAD
from tests.test_support import INVESTIGATION, REFUND, _ticket, customer_id  # noqa: F401

AuthHeader = Callable[[User], dict[str, str]]
MakeUser = Callable[..., User]


def _why(client: TestClient, headers: dict[str, str], path: str) -> dict[str, Any]:
    res = client.get(f"/api/explain/{path}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_lead_rating_shows_the_exact_input_and_who_ran_it(
    client: TestClient, fake_llm: FakeLLMClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    rep = make_user(Role.employee, Department.sales)
    h = auth_header(rep)
    lead = client.post("/api/sales/leads", json=LEAD, headers=h).json()
    fake_llm.replies.append(HOT)
    client.post(f"/api/sales/leads/{lead['id']}/qualify", headers=h)

    why = _why(client, h, f"lead/{lead['id']}")

    assert why["title"] == "Why is Indus Textiles rated hot?"
    assert why["model"] == "fake"
    assert why["input_verified"] is True  # the logged call's input hash equals what is shown
    read = {f["label"]: f["value"] for f in why["ai_read"]}
    assert read["email domain"] == "industextiles.example.com"
    assert "Ayesha" not in str(why["ai_read"])  # the contact's name never went to the model
    assert [c["status"] for c in why["calls"]] == ["succeeded"]
    assert [(p["who"], p["did"]) for p in why["people"]] == [
        (rep.full_name, "added the lead"),
        (rep.full_name, "ran the Lead Qualifier"),
    ]


def test_editing_the_lead_after_rating_is_admitted_not_hidden(
    client: TestClient, fake_llm: FakeLLMClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    h = auth_header(make_user(Role.employee, Department.sales))
    lead = client.post("/api/sales/leads", json=LEAD, headers=h).json()
    fake_llm.replies.append(HOT)
    client.post(f"/api/sales/leads/{lead['id']}/qualify", headers=h)
    client.patch(f"/api/sales/leads/{lead['id']}", json={"notes": "Budget frozen."}, headers=h)

    why = _why(client, h, f"lead/{lead['id']}")

    assert why["input_verified"] is False
    assert why["calls"] == []


def test_unrated_lead_has_nothing_to_explain(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    h = auth_header(make_user(Role.employee, Department.sales))
    lead = client.post("/api/sales/leads", json=LEAD, headers=h).json()
    assert client.get(f"/api/explain/lead/{lead['id']}", headers=h).status_code == 409


def test_other_departments_cannot_read_the_explanation(
    client: TestClient, fake_llm: FakeLLMClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    h = auth_header(make_user(Role.employee, Department.sales))
    lead = client.post("/api/sales/leads", json=LEAD, headers=h).json()
    fake_llm.replies.append(HOT)
    client.post(f"/api/sales/leads/{lead['id']}/qualify", headers=h)
    outsider = auth_header(make_user(Role.employee, Department.hr))

    assert client.get(f"/api/explain/lead/{lead['id']}", headers=outsider).status_code == 403


def test_vendor_comparison_shows_code_ranking_and_the_ai_reason(
    client: TestClient, fake_llm: FakeLLMClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    h = auth_header(make_user(Role.employee, Department.procurement))
    api = "/api/procurement"
    rid = client.post(
        f"{api}/requests",
        json={"item": "laptops", "quantity": 10, "budget_minor": 1_500_000, "currency": "USD"},
        headers=h,
    ).json()["id"]
    for name, price, lead, rate in (("Alpha", 140_000, 10, "0.90"), ("Beta", 120_000, 7, "0.95")):
        vid = client.post(
            f"{api}/vendors",
            json={"name": name, "lead_time_days": lead, "on_time_rate": rate},
            headers=h,
        ).json()["id"]
        client.post(
            f"{api}/requests/{rid}/quotes",
            json={"vendor_id": vid, "unit_price_minor": price},
            headers=h,
        )
    reason = "Beta wins: it is the cheapest, the fastest and the most reliable of the two vendors."
    fake_llm.replies.append({"reason": reason})
    assert client.post(f"{api}/compare-vendors", json={"request_id": rid}, headers=h).is_success

    why = _why(client, h, f"purchase-request/{rid}")

    assert why["title"] == "Why Beta for 10 x laptops?"
    assert why["input_verified"] is True
    assert why["ai_said"] == [{"label": "reason", "value": reason}]
    assert why["code_decided"][0].startswith("Ranked the vendors: 50% price")
    assert any(line.startswith("#1 Beta: price") for line in why["code_decided"])


def test_invoice_run_explains_extraction_match_and_the_approver(
    client: TestClient,
    db: Session,
    fake_llm: FakeLLMClient,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    clerk = make_user(Role.employee, Department.finance)
    manager = make_user(Role.manager, Department.finance)
    vendor = procurement.create_vendor(
        db,
        VendorCreate(name="ACME Industrial Supplies Ltd.", lead_time_days=7, on_time_rate="0.95"),
        manager,
    )
    order = procurement.create_order(
        db,
        PurchaseOrderCreate(
            po_number="PO-1007", vendor_id=vendor.id, amount_minor=425000, currency="USD"
        ),
    )
    order.status = PurchaseOrderStatus.approved
    db.commit()
    fake_llm.replies.append(EXTRACTED)
    started = client.post(
        "/api/workflows/supplier-payment/start",
        headers=auth_header(clerk),
        data={"po_number": "PO-1007"},
        files={"file": ("invoice.pdf", make_pdf(INVOICE_LINES), "application/pdf")},
    ).json()
    run = client.get(f"/api/workflows/{started['id']}", headers=auth_header(clerk)).json()
    client.post(
        f"/api/approvals/{run['approval']['id']}/approve",
        headers=auth_header(manager),
        json={"comment": "Matches the PO"},
    )

    why = _why(client, auth_header(manager), f"run/{run['id']}")

    assert why["agent"] == "Invoice Processor"
    assert why["input_verified"] is True
    assert {f["label"] for f in why["ai_said"]} >= {"number", "vendor name", "total amount"}
    assert any("matched" in line for line in why["code_decided"])
    assert any(line.startswith("Verification:") for line in why["code_decided"])
    did = [(p["who"], p["did"]) for p in why["people"]]
    assert (clerk.full_name, "uploaded the invoice and started the check") in did
    assert (manager.full_name, 'approved: "Matches the PO"') in did


def test_ticket_investigation_shows_the_orders_it_read(
    client: TestClient,
    fake_llm: FakeLLMClient,
    request: pytest.FixtureRequest,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    customer = request.getfixturevalue("customer_id")  # the support tests' customer and orders
    h = auth_header(make_user(Role.employee, Department.support))
    fake_llm.replies += [REFUND, INVESTIGATION]
    ticket = _ticket(client, h, customer)
    client.post(f"/api/support/tickets/{ticket['id']}/investigate", headers=h)

    why = _why(client, h, f"ticket/{ticket['id']}")

    assert why["agent"] == "Ticket Investigator"
    assert why["input_verified"] is True
    orders = next(f["value"] for f in why["ai_read"] if f["label"].startswith("the customer's"))
    assert "SO-1001" in orders and "SO-9999" not in orders  # only this customer's orders
    assert why["ai_said"][0]["value"].endswith("(orders SO-1002)")


def test_candidate_score_shows_quotes_and_the_formula(
    client: TestClient, fake_llm: FakeLLMClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    h = auth_header(make_user(Role.employee, Department.hr))
    job = _job(client, h)
    fake_llm.replies += [SARA_PROFILE, SARA_ASSESSMENT]
    candidate = _upload(client, h).json()
    client.post(f"/api/hr/jobs/{job['id']}/screen", json={}, headers=h)

    why = _why(client, h, f"candidate/{job['id']}/{candidate['id']}")

    assert why["title"] == "Why does Sara Malik score 73 for Senior Backend Engineer?"
    assert why["input_verified"] is True
    assert why["ai_said"][0] == {
        "label": 'evidence for "Python"',
        "value": '"Built payment APIs in Python and FastAPI"',
    }
    assert "skills with evidence (2 of 3)" in why["code_decided"][1]
    assert why["code_decided"][2] == "Missing: Docker."


def test_email_explains_the_checks_and_why_it_was_not_sent(
    client: TestClient, db: Session, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    email = OutboundEmail(
        kind="supplier_followup",
        department=Department.procurement,
        to_address="orders@northwind.example.com",
        subject="PO-2001 is late",
        body="Please confirm a new delivery date for PO-2001.",
        status=EmailStatus.pending_approval,
        drafted_by_model="fake",
    )
    db.add(email)
    db.commit()

    why = _why(
        client, auth_header(make_user(Role.employee, Department.procurement)), f"email/{email.id}"
    )

    assert why["agent"] == "Supplier Follow-up Writer"
    assert why["model"] == "fake"
    assert why["code_decided"][-1] == "Not sent: waiting for a manager's approval."
    sales = auth_header(make_user(Role.employee, Department.sales))
    assert client.get(f"/api/explain/email/{email.id}", headers=sales).status_code == 403


def test_a_category_set_by_a_person_is_not_passed_off_as_ai(
    client: TestClient, db: Session, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    triaged = Ticket(title="Parcel lost", category=TicketCategory.shipping, urgency=Urgency.normal)
    db.add(triaged)
    db.commit()
    h = auth_header(make_user(Role.employee, Department.support))

    res = client.get(f"/api/explain/ticket/{triaged.id}", headers=h)

    assert res.status_code == 409
    assert "A person set" in res.json()["error"]["message"]
