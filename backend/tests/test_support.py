"""FR-SUP-01 classify, FR-SUP-02 investigate with order IDs, FR-SUP-03 escalate with approval."""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.llm import LLMError
from app.llm.fake import FakeLLMClient
from app.models import ApprovalRequest, User
from app.models.enums import Department, OrderStatus, Role
from app.schemas.support import TicketClassification
from app.services import support

API = "/api/support"
AuthHeader = Callable[[User], dict[str, str]]
REFUND = {"category": "refund", "urgency": "high", "reason": "Customer asks for money back."}
INVESTIGATION = {
    "likely_causes": [
        {
            "cause": "Order SO-1002 was charged twice after a failed payment retry.",
            "order_numbers": ["SO-1002"],
        }
    ],
    "order_numbers_used": ["SO-1002", "SO-1001"],
    "next_step": "Confirm the duplicate charge with Finance and refund one payment.",
    "draft_reply": "Hi Hamza, thanks for flagging this. We are checking the duplicate charge now.",
}


@pytest.fixture
def customer_id(db: Session) -> str:
    customer = support.create_customer(
        db, name="Hamza Iqbal", company="Iqbal Traders", email="hamza@example.com"
    )
    for number, status, day in (
        ("SO-1001", OrderStatus.delivered, 3),
        ("SO-1002", OrderStatus.delivered, 20),
    ):
        support.add_order(
            db,
            customer.id,
            order_number=number,
            amount_minor=12500,
            currency="USD",
            status=status,
            ordered_at=datetime(2026, 10, day, tzinfo=UTC),
        )
    other = support.create_customer(db, name="Someone Else", company=None, email=None)
    support.add_order(
        db,
        other.id,
        order_number="SO-9999",
        amount_minor=100,
        currency="USD",
        status=OrderStatus.placed,
        ordered_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    return str(customer.id)


@pytest.fixture
def people(make_user: Callable[..., User], auth_header: AuthHeader) -> dict[str, dict[str, str]]:
    return {
        "agent": auth_header(make_user(Role.employee, Department.support)),
        "manager": auth_header(make_user(Role.manager, Department.support)),
        "finance_manager": auth_header(make_user(Role.manager, Department.finance)),
    }


def _ticket(
    client: TestClient, headers: dict[str, str], customer_id: str | None, **extra: Any
) -> dict[str, Any]:
    body = {
        "title": "Charged twice",
        "description": "I was billed twice for my October order, refund one.",
        "customer_id": customer_id,
    } | extra
    res = client.post(f"{API}/tickets", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_new_ticket_is_classified(
    client: TestClient, people: dict[str, dict[str, str]], fake_llm: FakeLLMClient, customer_id: str
) -> None:
    fake_llm.replies.append(REFUND)

    ticket = _ticket(client, people["agent"], customer_id)

    assert (ticket["category"], ticket["urgency"], ticket["status"]) == ("refund", "high", "open")
    assert "billed twice" in fake_llm.calls[0].user
    listed = client.get(f"{API}/tickets?category=refund", headers=people["agent"]).json()["items"]
    assert [t["id"] for t in listed] == [ticket["id"]]


@pytest.mark.parametrize("bad", [{"category": "angry"}, {"urgency": "urgent"}])
def test_classification_must_use_the_enums(bad: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        TicketClassification.model_validate(REFUND | bad)


def test_ticket_is_kept_when_the_model_is_down(
    client: TestClient, people: dict[str, dict[str, str]], fake_llm: FakeLLMClient
) -> None:
    fake_llm.replies.append(LLMError("bad key", retryable=False))

    ticket = _ticket(client, people["agent"], None)

    assert ticket["category"] is None
    fake_llm.replies.append(REFUND)
    again = client.post(f"{API}/tickets/{ticket['id']}/classify", headers=people["agent"]).json()
    assert again["category"] == "refund"


def test_investigation_lists_the_orders_used(
    client: TestClient, people: dict[str, dict[str, str]], fake_llm: FakeLLMClient, customer_id: str
) -> None:
    fake_llm.replies += [REFUND, INVESTIGATION]
    ticket = _ticket(client, people["agent"], customer_id)

    res = client.post(f"{API}/tickets/{ticket['id']}/investigate", headers=people["agent"])

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "investigating"
    assert body["investigation"]["order_numbers_used"] == ["SO-1002", "SO-1001"]
    assert body["investigation"]["likely_causes"][0]["order_numbers"] == ["SO-1002"]
    prompt = fake_llm.calls[1].user
    assert "SO-1001" in prompt and "SO-1002" in prompt and "SO-9999" not in prompt


def test_citing_another_customers_order_is_retried(
    client: TestClient, people: dict[str, dict[str, str]], fake_llm: FakeLLMClient, customer_id: str
) -> None:
    foreign = INVESTIGATION | {"order_numbers_used": ["SO-9999"]}
    fake_llm.replies += [REFUND, foreign, INVESTIGATION]
    ticket = _ticket(client, people["agent"], customer_id)

    body = client.post(f"{API}/tickets/{ticket['id']}/investigate", headers=people["agent"]).json()

    assert "SO-9999" not in body["investigation"]["order_numbers_used"]


def test_investigation_needs_a_customer(
    client: TestClient, people: dict[str, dict[str, str]], fake_llm: FakeLLMClient
) -> None:
    fake_llm.replies.append(REFUND)
    ticket = _ticket(client, people["agent"], None)

    res = client.post(f"{API}/tickets/{ticket['id']}/investigate", headers=people["agent"])

    assert res.json()["error"]["code"] == "no_customer"


def test_refund_escalation_creates_one_approval_and_manager_resolves_it(
    client: TestClient,
    people: dict[str, dict[str, str]],
    fake_llm: FakeLLMClient,
    customer_id: str,
    db: Session,
) -> None:
    fake_llm.replies.append(REFUND)
    ticket = _ticket(client, people["agent"], customer_id)

    res = client.post(
        f"{API}/tickets/{ticket['id']}/escalate",
        json={"note": "Duplicate charge"},
        headers=people["agent"],
    )

    body = res.json()
    assert body["ticket"]["status"] == "escalated"
    approval = body["approval"]
    assert (approval["action"], approval["department"], approval["required_role"]) == (
        "issue_refund",
        "support",
        "manager",
    )
    assert approval["payload"]["customer_name"] == "Hamza Iqbal"
    assert db.scalar(select(func.count()).select_from(ApprovalRequest)) == 1
    again = client.post(f"{API}/tickets/{ticket['id']}/escalate", json={}, headers=people["agent"])
    assert again.json()["error"]["code"] == "already_escalated"

    # A finance manager cannot decide a support escalation; a support manager can.
    approve = f"/api/approvals/{approval['id']}/approve"
    assert client.post(approve, json={}, headers=people["finance_manager"]).status_code == 403
    assert (
        client.post(approve, json={"comment": "OK"}, headers=people["manager"]).status_code == 200
    )
    resolved = client.get(f"{API}/tickets/{ticket['id']}", headers=people["agent"]).json()
    assert resolved["status"] == "resolved"


def test_rejected_escalation_reopens_the_ticket(
    client: TestClient, people: dict[str, dict[str, str]], fake_llm: FakeLLMClient, customer_id: str
) -> None:
    fake_llm.replies.append(REFUND | {"category": "legal"})
    ticket = _ticket(client, people["agent"], customer_id)
    approval = client.post(
        f"{API}/tickets/{ticket['id']}/escalate", json={}, headers=people["agent"]
    ).json()["approval"]
    assert approval["action"] == "legal_escalation"

    client.post(
        f"/api/approvals/{approval['id']}/reject",
        json={"comment": "Not legal, just billing"},
        headers=people["manager"],
    )

    assert (
        client.get(f"{API}/tickets/{ticket['id']}", headers=people["agent"]).json()["status"]
        == "open"
    )


def test_other_categories_escalate_without_approval(
    client: TestClient,
    people: dict[str, dict[str, str]],
    fake_llm: FakeLLMClient,
    customer_id: str,
    db: Session,
) -> None:
    fake_llm.replies.append(REFUND | {"category": "shipping"})
    ticket = _ticket(client, people["agent"], customer_id)

    body = client.post(
        f"{API}/tickets/{ticket['id']}/escalate", json={}, headers=people["agent"]
    ).json()

    assert body["approval"] is None and body["ticket"]["status"] == "escalated"
    assert db.scalar(select(func.count()).select_from(ApprovalRequest)) == 0


def test_only_support_can_use_support(
    client: TestClient, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    hr = auth_header(make_user(Role.employee, Department.hr))
    assert client.get(f"{API}/tickets", headers=hr).status_code == 403


@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1 and LIVE_LLM_API_KEY"
)
def test_live_vultr_classify_and_investigate() -> None:
    from app.agents.ticket_investigator import TicketClassifier, TicketInvestigator
    from app.config import get_settings
    from app.llm.vultr import VultrLLMClient
    from app.schemas.support import InvestigationInput, OrderFact, TicketText

    settings = get_settings()
    llm = VultrLLMClient(
        base_url=settings.llm_base_url,
        api_key=os.environ["LIVE_LLM_API_KEY"],
        model=settings.llm_model,
    )
    text = "My card was charged twice for order SO-1002 last week. Please refund one of them."

    label = TicketClassifier().run(TicketText(title="Charged twice", description=text), llm)
    found = TicketInvestigator().run(
        InvestigationInput(
            title="Charged twice",
            description=text,
            category=label.category,
            orders=[
                OrderFact(
                    order_number="SO-1001",
                    status="delivered",
                    amount="125.00 USD",
                    ordered_on="2026-10-03",
                ),
                OrderFact(
                    order_number="SO-1002",
                    status="delivered",
                    amount="125.00 USD",
                    ordered_on="2026-10-20",
                ),
            ],
        ),
        llm,
    )

    assert label.category in ("refund", "billing")
    assert "SO-1002" in found.order_numbers_used
