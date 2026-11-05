"""Receivables on the demo seed: what is overdue, who is on hold, and payment reminders."""

import os
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SELLER_COMPANY
from app.llm.fake import FakeLLMClient
from app.mailer.fake import FakeEmailSender
from app.models import Ticket
from app.models.base import utcnow
from app.models.enums import TicketStatus
from app.seed import seed
from tests.test_seed import PASSWORD, _login

API = "/api/finance/receivables"
REMINDER = {
    "subject": "Friendly reminder: order SO-1101 is 10 days overdue",
    "body": (
        "Our records show that order SO-1101 for 450.00 USD was due on its payment date and is "
        "now 10 days overdue.\n\nIf payment is already on its way, please ignore this note. "
        "Otherwise we would be grateful if you could arrange it, or let us know if anything is "
        "wrong with the order."
    ),
}


@pytest.fixture
def demo(client: TestClient, db: Session) -> dict[str, dict[str, str]]:
    seed(db, PASSWORD)
    handles = ("finance.clerk", "finance.manager", "sales.rep")
    return {h: _login(client, h) for h in handles}


def _by_number(client: TestClient, headers: dict[str, str]) -> dict[str, dict[str, Any]]:
    return {r["order_number"]: r for r in client.get(API, headers=headers).json()}


def test_overdue_on_hold_and_not_due_are_decided_by_code(
    client: TestClient, demo: dict[str, dict[str, str]]
) -> None:
    rows = client.get(API, headers=demo["finance.clerk"]).json()
    items = {r["order_number"]: r for r in rows}

    assert rows[0]["order_number"] == "SO-1101"  # most overdue first
    assert (items["SO-1101"]["status"], items["SO-1101"]["days_overdue"]) == ("overdue", 10)
    assert items["SO-1001"]["status"] == "on_hold"
    assert "refund" in items["SO-1001"]["hold_reason"]
    assert {items[n]["status"] for n in ("SO-1002", "SO-1003", "SO-1102")} == {"not_due"}
    assert "SO-1201" not in items  # paid
    assert "SO-1202" not in items  # refunded
    ordered = utcnow().date() - timedelta(days=40)
    assert items["SO-1101"]["due_on"] == (ordered + timedelta(days=30)).isoformat()


def _draft(client: TestClient, headers: dict[str, str], order_id: str) -> Any:
    return client.post(f"{API}/{order_id}/emails", headers=headers)


def test_reminder_quotes_the_facts_and_is_signed_by_code(
    client: TestClient, demo: dict[str, dict[str, str]], fake_llm: FakeLLMClient
) -> None:
    order = _by_number(client, demo["finance.clerk"])["SO-1101"]
    fake_llm.replies.append(REMINDER)

    res = _draft(client, demo["finance.clerk"], order["order_id"])

    assert res.status_code == 201, res.text
    email = res.json()
    assert email["to_address"] == "fatima@zahraboutique.example.com"
    assert email["order_id"] == order["order_id"]
    assert email["body"].startswith("Hello Fatima,\n\n")
    assert email["body"].endswith(f"Accounts Receivable, {SELLER_COMPANY}")
    prompt = fake_llm.calls[-1].user
    assert '"order_number": "SO-1101"' in prompt and '"days_overdue": 10' in prompt
    assert "@" not in prompt  # the model never sees the customer's address


@pytest.mark.parametrize(("number", "code"), [("SO-1001", "on_hold"), ("SO-1002", "not_overdue")])
def test_no_reminder_when_on_hold_or_not_due(
    client: TestClient,
    demo: dict[str, dict[str, str]],
    fake_llm: FakeLLMClient,
    number: str,
    code: str,
) -> None:
    order = _by_number(client, demo["finance.clerk"])[number]

    res = _draft(client, demo["finance.clerk"], order["order_id"])

    assert res.status_code == 409 and res.json()["error"]["code"] == code
    assert fake_llm.calls == []


def test_finance_manager_approves_and_the_customer_is_emailed(
    client: TestClient,
    demo: dict[str, dict[str, str]],
    fake_llm: FakeLLMClient,
    fake_mailer: FakeEmailSender,
) -> None:
    order = _by_number(client, demo["finance.clerk"])["SO-1101"]
    fake_llm.replies.append(REMINDER)
    email = _draft(client, demo["finance.clerk"], order["order_id"]).json()
    approval_id = client.post(
        f"/api/finance/emails/{email['id']}/request-approval", headers=demo["finance.clerk"]
    ).json()["approval_id"]

    [approval] = [
        a
        for a in client.get("/api/approvals", headers=demo["finance.manager"]).json()["items"]
        if a["id"] == approval_id
    ]
    assert approval["payload"]["company"] == "Zahra Boutique"
    assert approval["payload"]["order_number"] == "SO-1101"
    client.post(
        f"/api/approvals/{approval_id}/approve",
        headers=demo["finance.manager"],
        json={"comment": None},
    )

    [message] = fake_mailer.sent
    assert message.to == "fatima@zahraboutique.example.com"
    assert "SO-1101" in message.subject


def test_marking_paid_closes_the_receivable(
    client: TestClient, demo: dict[str, dict[str, str]]
) -> None:
    order = _by_number(client, demo["finance.clerk"])["SO-1101"]

    res = client.post(f"{API}/{order['order_id']}/paid", headers=demo["finance.clerk"])

    assert res.status_code == 200
    assert "SO-1101" not in _by_number(client, demo["finance.clerk"])
    again = client.post(f"{API}/{order['order_id']}/paid", headers=demo["finance.clerk"])
    assert again.status_code == 409


def test_resolving_the_dispute_lifts_the_hold(
    client: TestClient, demo: dict[str, dict[str, str]], db: Session
) -> None:
    ticket = db.scalar(select(Ticket).where(Ticket.title.like("Charged twice%")))
    assert ticket is not None
    ticket.status = TicketStatus.resolved
    db.commit()

    assert _by_number(client, demo["finance.clerk"])["SO-1001"]["status"] == "overdue"


def test_other_departments_cannot_see_receivables(
    client: TestClient, demo: dict[str, dict[str, str]]
) -> None:
    assert client.get(API, headers=demo["sales.rep"]).status_code == 403


@pytest.mark.skipif(not os.environ.get("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1 and LLM_API_KEY")
def test_live_vultr_writes_a_sendable_reminder() -> None:
    """The real model's reminder passes the same checks a sendable email must pass."""
    from app.agents.payment_reminder import PaymentReminderWriter
    from app.config import get_settings
    from app.llm.vultr import VultrLLMClient
    from app.schemas.outreach import PaymentReminderInput

    settings = get_settings()
    llm = VultrLLMClient(
        base_url=settings.llm_base_url,
        api_key=os.environ["LIVE_LLM_API_KEY"],
        model=settings.llm_model,
    )
    today = utcnow().date()
    facts = PaymentReminderInput(
        order_number="SO-1101",
        customer_company="Zahra Boutique",
        amount="450.00 USD",
        ordered_on=today - timedelta(days=40),
        due_on=today - timedelta(days=10),
        days_overdue=10,
        billing_terms="net_30",
        seller_company=SELLER_COMPANY,
    )

    draft = PaymentReminderWriter().run(facts, llm)  # raises if not sendable

    assert "SO-1101" in draft.subject + draft.body
