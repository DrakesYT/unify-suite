"""Controls that keep a workflow correct end to end: one payment per purchase order, decisions
that never depend on the model, runs that survive a restart, tickets and invoices that can be
finished, and one place for every decision."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import ratelimit
from app.llm import get_optional_llm
from app.llm.fake import FakeLLMClient
from app.main import app
from app.models import (
    ApprovalRequest,
    Candidate,
    CandidateScore,
    Invoice,
    Job,
    Order,
    Payment,
    PurchaseOrder,
    User,
    WorkflowExecution,
    WorkflowStep,
)
from app.models.base import utcnow
from app.models.enums import Department, OrderStatus, PurchaseOrderStatus, Role, StepStatus
from app.orchestrator import engine as workflow
from app.orchestrator.templates import TEMPLATES
from app.schemas.procurement import PurchaseOrderCreate, VendorCreate
from app.services import brief, hr, procurement, support
from tests.pdf import make_pdf
from tests.test_finance import EXTRACTED, INVOICE_LINES

MakeUser = Callable[..., User]
AuthHeader = Callable[[User], dict[str, str]]


@pytest.fixture(autouse=True)
def _fresh_brief_cache() -> None:
    brief.clear_cache()


def _acme_po(db: Session, actor: User) -> PurchaseOrder:
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
    db.commit()
    return order


def _start_run(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    res = client.post(
        "/api/workflows/supplier-payment/start",
        headers=headers,
        data={"po_number": "PO-1007"},
        files={"file": ("invoice.pdf", make_pdf(INVOICE_LINES), "application/pdf")},
    )
    assert res.status_code == 202, res.text
    return client.get(f"/api/workflows/{res.json()['id']}", headers=headers).json()


# --- one payment per purchase order ------------------------------------------------------------


def test_second_invoice_for_a_paid_purchase_order_is_a_mismatch(
    client: TestClient,
    fake_llm: FakeLLMClient,
    db: Session,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    clerk = auth_header(make_user(Role.employee, Department.finance))
    manager_user = make_user(Role.manager, Department.finance)
    manager = auth_header(manager_user)
    _acme_po(db, manager_user)
    fake_llm.replies.append(EXTRACTED)
    first = _start_run(client, clerk)
    assert first["approval"]["payload"]["match_status"] == "matched"
    client.post(f"/api/approvals/{first['approval']['id']}/approve", headers=manager, json={})

    fake_llm.replies.append(EXTRACTED | {"number": "INV-2026-0099"})
    second = _start_run(client, clerk)

    payload = second["approval"]["payload"]
    assert payload["match_status"] == "mismatch"
    assert payload["discrepancies"] == [
        "this purchase order (4,250.00 USD) was already invoiced: INV-2026-0042 (4,250.00 USD); "
        "paying this one too would pay more than the order"
    ]
    assert [p.amount_minor for p in db.scalars(select(Payment))] == [425000]


def test_a_rejected_invoice_does_not_use_up_the_purchase_order(
    client: TestClient,
    fake_llm: FakeLLMClient,
    db: Session,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    clerk = auth_header(make_user(Role.employee, Department.finance))
    manager_user = make_user(Role.manager, Department.finance)
    manager = auth_header(manager_user)
    _acme_po(db, manager_user)
    fake_llm.replies.append(EXTRACTED)
    first = _start_run(client, clerk)
    client.post(
        f"/api/approvals/{first['approval']['id']}/reject",
        headers=manager,
        json={"comment": "Sent twice by the supplier"},
    )

    fake_llm.replies.append(EXTRACTED | {"number": "INV-2026-0099"})
    second = _start_run(client, clerk)

    assert second["approval"]["payload"]["match_status"] == "matched"


def test_part_invoices_within_the_order_amount_still_match(
    db: Session, make_user: MakeUser
) -> None:
    from app.schemas.finance import InvoiceFields, MatchResult, PoSnapshot
    from app.services.finance import _with_earlier_invoices

    order = _acme_po(db, make_user(Role.manager, Department.finance))
    db.add(
        Invoice(
            number="PART-1",
            vendor_id=order.vendor_id,
            purchase_order_id=order.id,
            invoice_date=datetime(2026, 10, 1, tzinfo=UTC).date(),
            amount_minor=200000,
            currency="USD",
        )
    )
    db.commit()
    po = PoSnapshot(
        id=order.id,
        po_number="PO-1007",
        vendor_id=order.vendor_id,
        vendor_name="ACME",
        amount_minor=425000,
        currency="USD",
    )
    matched = MatchResult(status="matched")
    part = InvoiceFields.model_validate(EXTRACTED | {"total_amount": "2250.00"})
    over = InvoiceFields.model_validate(EXTRACTED | {"total_amount": "2250.01"})

    assert _with_earlier_invoices(db, matched, part, po).status == "matched"
    assert _with_earlier_invoices(db, matched, over, po).status == "mismatch"


# --- decisions never depend on the model -------------------------------------------------------


def _po_approval(
    client: TestClient, db: Session, make_user: MakeUser, auth_header: AuthHeader
) -> tuple[str, dict[str, str], User]:
    buyer = auth_header(make_user(Role.employee, Department.procurement))
    manager_user = make_user(Role.manager, Department.procurement)
    vendor = procurement.create_vendor(
        db, VendorCreate(name="Northwind", lead_time_days=5, on_time_rate="0.9"), manager_user
    )
    res = client.post(
        "/api/procurement/orders",
        headers=buyer,
        json={
            "po_number": "PO-5001",
            "vendor_id": str(vendor.id),
            "amount_minor": 100000,
            "currency": "USD",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["approval_id"], auth_header(manager_user), manager_user


def test_a_decision_works_without_a_model_and_with_the_ai_budget_spent(
    client: TestClient, db: Session, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    approval_id, manager, manager_user = _po_approval(client, db, make_user, auth_header)
    for _ in range(ratelimit.ai_runs_by_user.limit):
        ratelimit.ai_runs_by_user.hit(str(manager_user.id))

    res = client.post(f"/api/approvals/{approval_id}/approve", headers=manager, json={})

    assert res.status_code == 200, res.text
    assert db.scalar(select(PurchaseOrder.status)) == PurchaseOrderStatus.approved


def test_an_approved_payment_is_made_without_a_model(
    client: TestClient,
    fake_llm: FakeLLMClient,
    db: Session,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    clerk = auth_header(make_user(Role.employee, Department.finance))
    manager_user = make_user(Role.manager, Department.finance)
    _acme_po(db, manager_user)
    fake_llm.replies.append(EXTRACTED)
    run = _start_run(client, clerk)
    app.dependency_overrides[get_optional_llm] = lambda: None  # the model goes away

    res = client.post(
        f"/api/approvals/{run['approval']['id']}/approve",
        headers=auth_header(manager_user),
        json={},
    )

    assert res.status_code == 200, res.text
    done = client.get(f"/api/workflows/{run['id']}", headers=clerk).json()
    assert done["status"] == "completed" and done["result"]["passed"] is True


# --- runs survive a restart --------------------------------------------------------------------


def _cut_off_run(db: Session, actor: User, minutes_ago: int) -> WorkflowExecution:
    """What a restart leaves behind: a run marked running, one step caught mid-flight."""
    execution = workflow.start(
        db,
        TEMPLATES["supplier-payment"],
        {"upload_id": "00000000-0000-0000-0000-000000000000", "file_name": "x", "po_number": "P"},
        actor,
    )
    then = utcnow() - timedelta(minutes=minutes_ago)
    execution.created_at = execution.updated_at = then
    step = db.scalar(
        select(WorkflowStep).where(
            WorkflowStep.execution_id == execution.id, WorkflowStep.step_key == "F1"
        )
    )
    assert step is not None
    step.status, step.started_at = StepStatus.running, then
    db.commit()
    return execution


def test_an_interrupted_run_can_be_resumed_by_hand(
    client: TestClient,
    fake_llm: FakeLLMClient,
    db: Session,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    clerk = make_user(Role.employee, Department.finance)
    stale = _cut_off_run(db, clerk, minutes_ago=10)
    fresh = _cut_off_run(db, clerk, minutes_ago=0)

    resumed = client.post(f"/api/workflows/{stale.id}/retry", headers=auth_header(clerk))
    refused = client.post(f"/api/workflows/{fresh.id}/retry", headers=auth_header(clerk))

    assert resumed.status_code == 202, resumed.text
    after = client.get(f"/api/workflows/{stale.id}", headers=auth_header(clerk)).json()
    assert after["status"] == "failed"  # it ran again and stopped for a real reason
    assert {s["key"]: s["status"] for s in after["steps"]}["F1"] == "failed"
    assert refused.status_code == 409  # a run that is still working is left alone


def test_start_up_picks_up_runs_the_last_process_left_behind(
    engine: Engine, db: Session, make_user: MakeUser
) -> None:
    execution = _cut_off_run(db, make_user(Role.employee, Department.finance), minutes_ago=0)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    left_behind = workflow.interrupted_runs(db)
    workflow.recover_interrupted(factory, left_behind, None)

    assert left_behind == [execution.id]
    db.expire_all()
    steps = {s.step_key: s for s in workflow.steps_of(db, execution).values()}
    # The step that was cut off ran again and stopped with a clear reason, not a crash.
    assert steps["F1"].status == StepStatus.failed and steps["F1"].attempts == 1
    assert db.get(WorkflowExecution, execution.id).status == "failed"
    assert workflow.interrupted_runs(db) == []


# --- tickets can be finished -------------------------------------------------------------------


@pytest.fixture
def support_people(make_user: MakeUser, auth_header: AuthHeader) -> dict[str, dict[str, str]]:
    return {
        "agent": auth_header(make_user(Role.employee, Department.support)),
        "manager": auth_header(make_user(Role.manager, Department.support)),
        "finance": auth_header(make_user(Role.employee, Department.finance)),
    }


def _ticket(
    client: TestClient,
    fake_llm: FakeLLMClient,
    headers: dict[str, str],
    category: str,
    customer_id: str | None = None,
) -> dict[str, Any]:
    fake_llm.replies.append({"category": category, "urgency": "normal", "reason": "Says so."})
    res = client.post(
        "/api/support/tickets",
        headers=headers,
        json={"title": "Order is late", "description": "Where is it?", "customer_id": customer_id},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_a_ticket_can_be_resolved_closed_and_reopened(
    client: TestClient, fake_llm: FakeLLMClient, support_people: dict[str, dict[str, str]]
) -> None:
    agent = support_people["agent"]
    url = f"/api/support/tickets/{_ticket(client, fake_llm, agent, 'shipping')['id']}"

    def move(verb: str) -> Any:
        return client.post(f"{url}/{verb}", headers=agent, json={"note": "Delivered today"})

    assert move("reopen").json()["error"]["code"] == "invalid_status_change"
    assert move("resolve").json()["status"] == "resolved"
    assert move("resolve").status_code == 409
    assert move("close").json()["status"] == "closed"
    edit = client.patch(url, headers=agent, json={"title": "Changed"})
    assert edit.json()["error"]["code"] == "ticket_closed"
    assert move("reopen").json()["status"] == "open"
    assert client.patch(url, headers=agent, json={"title": "Order SO-1 is late"}).json()[
        "title"
    ] == ("Order SO-1 is late")


def test_resolving_a_dispute_lifts_the_hold_on_payment_reminders(
    client: TestClient,
    fake_llm: FakeLLMClient,
    db: Session,
    support_people: dict[str, dict[str, str]],
) -> None:
    customer = support.create_customer(db, name="Hamza Iqbal", company="Iqbal", email="h@x.io")
    support.add_order(
        db,
        customer.id,
        order_number="SO-1002",
        amount_minor=12500,
        currency="USD",
        status=OrderStatus.delivered,
        ordered_at=utcnow() - timedelta(days=60),
    )
    agent, finance = support_people["agent"], support_people["finance"]
    ticket = _ticket(client, fake_llm, agent, "billing", str(customer.id))

    def receivable() -> str:
        return client.get("/api/finance/receivables", headers=finance).json()[0]["status"]

    assert receivable() == "on_hold"
    client.post(f"/api/support/tickets/{ticket['id']}/resolve", headers=agent, json={})
    assert receivable() == "overdue"


def test_an_approved_refund_is_recorded_on_the_order(
    client: TestClient,
    fake_llm: FakeLLMClient,
    db: Session,
    support_people: dict[str, dict[str, str]],
) -> None:
    customer = support.create_customer(db, name="Hamza Iqbal", company="Iqbal", email="h@x.io")
    other = support.create_customer(db, name="Someone Else", company=None, email=None)
    for owner, number in ((customer, "SO-1002"), (other, "SO-9999")):
        support.add_order(
            db,
            owner.id,
            order_number=number,
            amount_minor=12500,
            currency="USD",
            status=OrderStatus.delivered,
            ordered_at=datetime(2026, 10, 20, tzinfo=UTC),
        )
    agent, manager = support_people["agent"], support_people["manager"]
    ticket = _ticket(client, fake_llm, agent, "refund", str(customer.id))
    escalate = f"/api/support/tickets/{ticket['id']}/escalate"

    wrong = client.post(escalate, headers=agent, json={"note": "n", "order_number": "SO-9999"})
    assert wrong.json()["error"]["code"] == "not_customers_order"
    approval = client.post(
        escalate, headers=agent, json={"note": "Damaged", "order_number": "SO-1002"}
    ).json()["approval"]
    assert (approval["payload"]["order_number"], approval["payload"]["refund_amount_minor"]) == (
        "SO-1002",
        12500,
    )
    blocked = client.post(f"/api/support/tickets/{ticket['id']}/resolve", headers=agent, json={})
    assert blocked.json()["error"]["code"] == "waiting_approval"

    client.post(f"/api/approvals/{approval['id']}/approve", headers=manager, json={})

    order = db.scalar(select(Order).where(Order.order_number == "SO-1002"))
    assert order is not None
    db.refresh(order)
    assert order.status == OrderStatus.refunded
    assert client.get(f"/api/support/tickets/{ticket['id']}", headers=agent).json()["status"] == (
        "resolved"
    )


# --- an invoice that needs review can be settled -------------------------------------------------


def test_a_manager_can_reject_an_invoice_that_needs_review(
    client: TestClient,
    fake_llm: FakeLLMClient,
    db: Session,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    clerk = auth_header(make_user(Role.employee, Department.finance))
    manager_user = make_user(Role.manager, Department.finance)
    manager = auth_header(manager_user)
    _acme_po(db, manager_user)
    fake_llm.replies.append(EXTRACTED | {"po_number": None})  # no PO: saved as needs_review
    uploaded = client.post(
        "/api/finance/invoices/upload",
        headers=clerk,
        files={"file": ("invoice.pdf", make_pdf(INVOICE_LINES), "application/pdf")},
    ).json()
    url = f"/api/finance/invoices/{uploaded['invoice']['id']}/reject"
    assert uploaded["invoice"]["status"] == "needs_review"

    assert client.post(url, headers=clerk, json={"reason": "No order"}).status_code == 403
    assert client.post(url, headers=manager, json={"reason": ""}).status_code == 422
    done = client.post(url, headers=manager, json={"reason": "Never ordered"})
    again = client.post(url, headers=manager, json={"reason": "Never ordered"})

    assert done.status_code == 200 and done.json()["status"] == "rejected"
    assert again.json()["error"]["code"] == "not_reviewable"
    kpis = client.get("/api/dashboard/kpis", headers=manager).json()
    assert kpis["unpaid_invoices"] == []


def test_an_invoice_waiting_for_approval_is_decided_in_the_approval_center(
    client: TestClient,
    fake_llm: FakeLLMClient,
    db: Session,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    clerk = auth_header(make_user(Role.employee, Department.finance))
    manager_user = make_user(Role.manager, Department.finance)
    _acme_po(db, manager_user)
    fake_llm.replies.append(EXTRACTED)
    run = _start_run(client, clerk)
    invoice_id = run["approval"]["payload"]["invoice_id"]

    res = client.post(
        f"/api/finance/invoices/{invoice_id}/reject",
        headers=auth_header(manager_user),
        json={"reason": "Wrong"},
    )

    assert res.json()["error"]["code"] == "waiting_approval"


# --- the brief asks the model once per set of facts ----------------------------------------------


def test_the_brief_is_reused_until_the_facts_change(
    client: TestClient, fake_llm: FakeLLMClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    app.dependency_overrides[get_optional_llm] = lambda: fake_llm
    manager_user = make_user(Role.manager, Department.sales)
    headers = auth_header(manager_user)

    def lead(email: str) -> None:
        body = {"name": "A", "company": "Acme", "email": email, "value_minor": 100000}
        assert client.post("/api/sales/leads", headers=headers, json=body).status_code == 201

    draft = {"headline": "Pipeline is open", "summary": "Deals are in the pipeline.", "top": [1]}
    fake_llm.replies.extend([draft, draft])
    lead("a@acme.io")

    first = client.get("/api/ai/brief", headers=headers).json()
    second = client.get("/api/ai/brief", headers=headers).json()
    assert first == second and first["written_by"] == "model"  # served from the first one
    assert len(fake_llm.calls) == 1
    assert ratelimit.ai_runs_by_user.retry_after(str(manager_user.id)) == 0

    lead("b@acme.io")  # the pipeline fact changes
    client.get("/api/ai/brief", headers=headers)
    assert len(fake_llm.calls) == 2


# --- every decision is in the Approval Center ----------------------------------------------------


def _request(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    res = client.post(
        "/api/procurement/requests",
        headers=headers,
        json={"item": "Chairs", "quantity": 20, "budget_minor": 600000, "currency": "USD"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_a_purchase_request_is_decided_in_the_approval_center(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    buyer = auth_header(make_user(Role.employee, Department.procurement))
    manager = auth_header(make_user(Role.manager, Department.procurement))
    request = _request(client, buyer)
    client.patch(f"/api/procurement/requests/{request['id']}", headers=buyer, json={"quantity": 25})

    pending = client.get("/api/approvals", headers=manager).json()["items"]
    assert [(a["action"], a["payload"]["quantity"]) for a in pending] == [("approve_request", 25)]
    assert (
        client.post(
            f"/api/approvals/{pending[0]['id']}/approve", headers=buyer, json={}
        ).status_code
        == 403
    )
    res = client.post(f"/api/approvals/{pending[0]['id']}/approve", headers=manager, json={})

    assert res.status_code == 200, res.text
    after = client.get(f"/api/procurement/requests/{request['id']}", headers=buyer).json()
    assert after["status"] == "approved"


def test_deciding_on_the_procurement_page_closes_the_approval_too(
    client: TestClient, db: Session, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    buyer = auth_header(make_user(Role.employee, Department.procurement))
    manager_user = make_user(Role.manager, Department.procurement)
    request = _request(client, buyer)

    res = client.post(
        f"/api/procurement/requests/{request['id']}/reject", headers=auth_header(manager_user)
    )

    assert res.json()["status"] == "rejected"
    approval = db.scalar(select(ApprovalRequest))
    assert approval is not None
    assert (approval.status, approval.decided_by_id) == ("rejected", manager_user.id)


# --- small rules ---------------------------------------------------------------------------------


def test_years_beyond_the_minimum_raise_the_score() -> None:
    from app.schemas.hr import EvidenceItem

    job = Job(title="Data Analyst", required_skills=["Python", "SQL"], min_years=3)
    evidence = [
        EvidenceItem(requirement="Python", quote="Python"),
        EvidenceItem(requirement="SQL", quote="SQL queries"),
    ]

    def score(years: int | None) -> int:
        return hr.compute_score(job, Candidate(name="X", years_experience=years), evidence)

    assert [score(y) for y in (None, 1, 3, 4, 6, 9)] == [70, 77, 90, 93, 100, 100]


def test_equal_scores_rank_by_experience_then_name(db: Session) -> None:
    job = Job(title="Data Analyst", required_skills=["SQL"], min_years=3)
    db.add(job)
    db.flush()
    for name, years in (("Abe", 3), ("Zed", 9), ("Bea", None), ("Cal", 9)):
        candidate = Candidate(name=name, years_experience=years)
        db.add(candidate)
        db.flush()
        db.add(CandidateScore(candidate_id=candidate.id, job_id=job.id, score=100))
    db.commit()

    assert [s.candidate.name for s in hr.ranked_scores(db, job.id)] == ["Cal", "Zed", "Abe", "Bea"]


def test_an_open_lead_is_not_added_twice_but_a_lost_one_can_return(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    rep = auth_header(make_user(Role.employee, Department.sales))
    body = {"name": "A", "company": "Acme", "email": "a@acme.io"}
    first = client.post("/api/sales/leads", headers=rep, json=body).json()

    again = client.post("/api/sales/leads", headers=rep, json=body | {"email": "A@Acme.io"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "duplicate_lead"

    client.patch(f"/api/sales/leads/{first['id']}", headers=rep, json={"status": "lost"})
    assert client.post("/api/sales/leads", headers=rep, json=body).status_code == 201


def test_a_manager_can_delete_a_lead_entered_by_mistake(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    rep = auth_header(make_user(Role.employee, Department.sales))
    manager = auth_header(make_user(Role.manager, Department.sales))
    lead = client.post(
        "/api/sales/leads", headers=rep, json={"name": "T", "company": "Test", "email": "t@t.io"}
    ).json()
    url = f"/api/sales/leads/{lead['id']}"

    assert client.delete(url, headers=rep).status_code == 403
    assert client.delete(url, headers=manager).status_code == 204
    assert client.get(url, headers=rep).status_code == 404


def test_the_verification_stop_is_shown_as_rules_and_the_docs_page_is_off(
    client: TestClient,
    fake_llm: FakeLLMClient,
    db: Session,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    manager_user = make_user(Role.manager, Department.finance)
    _acme_po(db, manager_user)
    fake_llm.replies.append(EXTRACTED)
    _start_run(client, auth_header(manager_user))

    nodes = client.get("/api/agents/handoff", headers=auth_header(manager_user)).json()["run"][
        "nodes"
    ]

    assert {n["key"]: n["kind"] for n in nodes}["V1"] == "rules"
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 200
