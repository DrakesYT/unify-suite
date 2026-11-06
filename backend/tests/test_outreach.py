"""Sales outreach: the Outreach Writer drafts, a sales manager approves, then the email is sent."""

import os
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SELLER_COMPANY, get_settings
from app.llm.fake import FakeLLMClient
from app.mailer.fake import FakeEmailSender
from app.models import AgentTask, User
from app.models.enums import Department, Role
from tests.test_sales import HOT, LEAD

LEADS = "/api/sales/leads"
EMAILS = "/api/sales/emails"
APPROVALS = "/api/approvals"
DRAFT = {
    "subject": "A first-quarter pilot for Indus Textiles",
    "body": (
        "Your team mentioned a pilot in the first quarter with budget already approved.\n\n"
        "We help textile companies like Indus Textiles connect sales, finance and procurement "
        "with AI agents that keep a person in charge of every payment.\n\n"
        "Would a 30-minute call next week work to agree the pilot scope?"
    ),
}
Headers = dict[str, str]


@pytest.fixture
def people(
    make_user: Callable[..., User], auth_header: Callable[[User], Headers]
) -> dict[str, Headers]:
    users = {
        "rep": make_user(Role.employee, Department.sales, email="rep@unify.example.com"),
        "manager": make_user(Role.manager, Department.sales, email="boss@unify.example.com"),
        "finance_manager": make_user(Role.manager, Department.finance),
        "finance_clerk": make_user(Role.employee, Department.finance),
    }
    return {name: auth_header(user) for name, user in users.items()}


@pytest.fixture
def lead(client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient) -> str:
    lead = client.post(LEADS, json=LEAD, headers=people["rep"]).json()
    fake_llm.replies.append(HOT)
    assert client.post(f"{LEADS}/{lead['id']}/qualify", headers=people["rep"]).status_code == 200
    return str(lead["id"])


def _draft(client: TestClient, headers: Headers, lead_id: str) -> Any:
    return client.post(f"{LEADS}/{lead_id}/emails", headers=headers)


def _pending_approval(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient, lead: str
) -> tuple[str, str]:
    fake_llm.replies.append(DRAFT)
    email = _draft(client, people["rep"], lead).json()
    res = client.post(f"{EMAILS}/{email['id']}/request-approval", headers=people["rep"])
    assert res.status_code == 200, res.text
    return email["id"], res.json()["approval_id"]


def _decide(
    client: TestClient, headers: Headers, approval_id: str, verb: str, comment: str | None = None
) -> Any:
    return client.post(
        f"{APPROVALS}/{approval_id}/{verb}", headers=headers, json={"comment": comment}
    )


def _email(client: TestClient, headers: Headers, lead: str) -> dict[str, Any]:
    [email] = client.get(f"{LEADS}/{lead}/emails", headers=headers).json()
    return email


def test_agent_writes_the_middle_and_code_adds_greeting_and_signature(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient, lead: str
) -> None:
    fake_llm.replies.append(DRAFT)

    res = _draft(client, people["rep"], lead)

    assert res.status_code == 201, res.text
    email = res.json()
    assert email["status"] == "draft"
    assert email["to_address"] == LEAD["email"]
    assert email["subject"] == DRAFT["subject"]
    assert email["body"].startswith("Hi Ayesha,\n\n" + DRAFT["body"][:40])
    assert email["body"].endswith(f"Best regards,\nEmployee Sales\n{SELLER_COMPANY}")
    # The model saw business facts only: no contact name, no email address.
    prompt = fake_llm.calls[-1].user
    assert "Indus Textiles" in prompt and "Ayesha" not in prompt and "@" not in prompt


def test_a_lead_must_be_qualified_first(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient
) -> None:
    lead = client.post(LEADS, json=LEAD, headers=people["rep"]).json()

    res = _draft(client, people["rep"], lead["id"])

    assert res.status_code == 409 and res.json()["error"]["code"] == "not_qualified"
    assert fake_llm.calls == []


@pytest.mark.parametrize(
    "bad",
    [
        DRAFT | {"body": DRAFT["body"] + "\nBook here: https://cal.example.com/demo"},
        DRAFT | {"body": DRAFT["body"].replace("next week", "on [DATE]")},
        DRAFT | {"body": DRAFT["body"] + "\nReach me at sales@unify.example.com."},
        DRAFT | {"body": "Hi there,\n" + DRAFT["body"]},
        DRAFT | {"subject": "A quick question", "body": DRAFT["body"].replace("Indus", "your")},
    ],
)
def test_unsafe_drafts_are_retried(
    client: TestClient,
    people: dict[str, Headers],
    fake_llm: FakeLLMClient,
    lead: str,
    bad: dict[str, str],
) -> None:
    fake_llm.replies += [bad, DRAFT]

    res = _draft(client, people["rep"], lead)

    assert res.status_code == 201
    assert len(fake_llm.calls) == 3  # qualify + bad draft + good draft


def test_three_unsafe_drafts_fail_the_task(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient, lead: str
) -> None:
    bad = DRAFT | {"body": DRAFT["body"] + " https://x.example.com"}
    fake_llm.replies += [bad, bad, bad]

    res = _draft(client, people["rep"], lead)

    assert res.status_code == 502 and res.json()["error"]["code"] == "agent_failed"
    assert client.get(f"{LEADS}/{lead}/emails", headers=people["rep"]).json() == []


def test_rep_edits_then_asks_a_manager(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient, lead: str
) -> None:
    fake_llm.replies.append(DRAFT)
    email = _draft(client, people["rep"], lead).json()

    edited = client.patch(
        f"{EMAILS}/{email['id']}",
        json={"subject": "Pilot for Indus Textiles"},
        headers=people["rep"],
    )
    assert edited.json()["subject"] == "Pilot for Indus Textiles"

    asked = client.post(f"{EMAILS}/{email['id']}/request-approval", headers=people["rep"]).json()
    assert asked["status"] == "pending_approval"

    [approval] = client.get(APPROVALS, headers=people["manager"]).json()["items"]
    assert approval["action"] == "send_email"
    assert approval["payload"]["subject"] == "Pilot for Indus Textiles"
    assert approval["payload"]["to"] == LEAD["email"]
    assert approval["payload"]["body"] == email["body"]

    # Once a manager is looking at it, the text is frozen.
    late = client.patch(
        f"{EMAILS}/{email['id']}", json={"subject": "Changed after asking"}, headers=people["rep"]
    )
    assert late.status_code == 409


def test_approved_email_is_really_sent_and_logged(
    client: TestClient,
    people: dict[str, Headers],
    fake_llm: FakeLLMClient,
    fake_mailer: FakeEmailSender,
    lead: str,
    db: Session,
) -> None:
    _, approval_id = _pending_approval(client, people, fake_llm, lead)
    assert fake_mailer.sent == []

    assert _decide(client, people["manager"], approval_id, "approve").status_code == 200

    [message] = fake_mailer.sent
    assert message.to == LEAD["email"]
    assert message.subject == DRAFT["subject"]
    assert message.text.startswith("Hi Ayesha,")
    email = _email(client, people["rep"], lead)
    assert email["status"] == "sent" and email["delivered_to"] == LEAD["email"]
    assert email["sent_at"] is not None and email["error"] is None
    sends = db.scalars(select(AgentTask).where(AgentTask.tool == "send_email")).all()
    assert [(t.agent, t.status) for t in sends] == [("mailer", "succeeded")]


def test_demo_redirect_sends_everything_to_one_inbox(
    client: TestClient,
    people: dict[str, Headers],
    fake_llm: FakeLLMClient,
    fake_mailer: FakeEmailSender,
    lead: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "email_redirect_to", "demo-inbox@unify.example.com")
    _, approval_id = _pending_approval(client, people, fake_llm, lead)

    _decide(client, people["manager"], approval_id, "approve")

    [message] = fake_mailer.sent
    assert message.to == "demo-inbox@unify.example.com"
    assert message.text.startswith(f"[UNIFY SUITE demo: originally addressed to {LEAD['email']}]")
    assert _email(client, people["rep"], lead)["delivered_to"] == "demo-inbox@unify.example.com"


def test_rejected_email_is_never_sent(
    client: TestClient,
    people: dict[str, Headers],
    fake_llm: FakeLLMClient,
    fake_mailer: FakeEmailSender,
    lead: str,
) -> None:
    _, approval_id = _pending_approval(client, people, fake_llm, lead)

    res = _decide(client, people["manager"], approval_id, "reject", "Too pushy for a first email")

    assert res.status_code == 200
    assert fake_mailer.sent == []
    assert _email(client, people["rep"], lead)["status"] == "rejected"


def test_a_failed_send_is_recorded_and_can_be_retried(
    client: TestClient,
    people: dict[str, Headers],
    fake_llm: FakeLLMClient,
    fake_mailer: FakeEmailSender,
    lead: str,
) -> None:
    email_id, approval_id = _pending_approval(client, people, fake_llm, lead)
    fake_mailer.fail_with = "email service returned 503: try later"

    assert _decide(client, people["manager"], approval_id, "approve").status_code == 200

    failed = _email(client, people["rep"], lead)
    assert failed["status"] == "failed" and "503" in failed["error"]

    fake_mailer.fail_with = None
    retried = client.post(f"{EMAILS}/{email_id}/retry", headers=people["rep"])
    assert retried.status_code == 200 and retried.json()["status"] == "sent"
    assert len(fake_mailer.sent) == 1
    again = client.post(f"{EMAILS}/{email_id}/retry", headers=people["rep"])
    assert again.status_code == 409


def test_without_a_mail_service_the_email_fails_visibly(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient, lead: str
) -> None:
    _, approval_id = _pending_approval(client, people, fake_llm, lead)

    _decide(client, people["manager"], approval_id, "approve")

    email = _email(client, people["rep"], lead)
    assert email["status"] == "failed" and "not configured" in email["error"]


def test_only_a_sales_manager_can_approve_and_never_their_own(
    client: TestClient,
    people: dict[str, Headers],
    fake_llm: FakeLLMClient,
    fake_mailer: FakeEmailSender,
    lead: str,
) -> None:
    _, approval_id = _pending_approval(client, people, fake_llm, lead)

    assert _decide(client, people["rep"], approval_id, "approve").status_code == 403
    assert _decide(client, people["finance_manager"], approval_id, "approve").status_code == 403
    assert fake_mailer.sent == []


def test_other_departments_cannot_draft_or_read(
    client: TestClient, people: dict[str, Headers], lead: str
) -> None:
    assert _draft(client, people["finance_clerk"], lead).status_code == 403
    assert client.get(f"{LEADS}/{lead}/emails", headers=people["finance_clerk"]).status_code == 403
    # A manager of another department may read, not write.
    assert (
        client.get(f"{LEADS}/{lead}/emails", headers=people["finance_manager"]).status_code == 200
    )
    assert _draft(client, people["finance_manager"], lead).status_code == 403


@pytest.mark.skipif(not os.environ.get("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1 and LLM_API_KEY")
def test_live_vultr_writes_a_sendable_draft() -> None:
    """The real model's draft passes the same checks a sendable email must pass."""
    from app.agents.outreach_writer import OutreachWriter
    from app.llm.vultr import VultrLLMClient
    from app.schemas.outreach import OutreachInput

    settings = get_settings()
    llm = VultrLLMClient(
        base_url=settings.llm_base_url,
        api_key=os.environ["LIVE_LLM_API_KEY"],
        model=settings.llm_model,
    )
    facts = OutreachInput(
        company="Quetta Mining Co",
        status="qualified",
        priority="high",
        value="60,000.00 USD",
        notes="CFO signed the NDA; procurement is reviewing our security answers.",
        rating="hot",
        qualification_reason=HOT["reason"],
        seller_company=SELLER_COMPANY,
    )

    draft = OutreachWriter().run(facts, llm)  # raises if the draft is not sendable

    assert "quetta mining" in (draft.subject + draft.body).lower()


def test_a_bot_like_draft_is_retried(
    client: TestClient, people: dict[str, Headers], fake_llm: FakeLLMClient, lead: str
) -> None:
    slop = DRAFT | {"body": "I hope this email finds you well.\n\n" + DRAFT["body"]}
    fake_llm.replies += [slop, DRAFT]

    res = _draft(client, people["rep"], lead)

    assert res.status_code == 201, res.text
    assert "finds you well" not in res.json()["body"]
    assert res.json()["style_notes"] == []


def test_a_persons_edit_gets_suggestions_not_a_block(
    client: TestClient,
    people: dict[str, Headers],
    fake_llm: FakeLLMClient,
    lead: str,
) -> None:
    fake_llm.replies.append(DRAFT)
    email = _draft(client, people["rep"], lead).json()
    body = DRAFT["body"] + "\n\nPlease don't hesitate to reach out!"

    edited = client.patch(f"{EMAILS}/{email['id']}", json={"body": body}, headers=people["rep"])

    assert edited.status_code == 200, edited.text
    notes = {n["rule"]: n for n in edited.json()["style_notes"]}
    assert notes["don't hesitate"]["severity"] == "soft"
    assert "Reply to this email" in notes["don't hesitate"]["advice"]
