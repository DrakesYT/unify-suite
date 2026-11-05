"""Aura's morning brief (model wording, checked by code) and quick actions (real records)."""

import os
from collections.abc import Callable, Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.brief_writer import check_brief, numbers_in
from app.llm import LLMOutputError, get_optional_llm
from app.llm.fake import FakeLLMClient
from app.main import app
from app.models import (
    AgentTask,
    ApprovalRequest,
    Candidate,
    Job,
    Lead,
    PurchaseRequest,
    Ticket,
    User,
)
from app.models.enums import (
    Department,
    LeadRating,
    LeadStatus,
    Role,
    TaskStatus,
    TicketStatus,
    Urgency,
)
from app.schemas.brief import BriefDraft, BriefFact, BriefInput

AuthHeader = Callable[[User], dict[str, str]]
MakeUser = Callable[..., User]


@pytest.fixture
def model(client: TestClient) -> Iterator[FakeLLMClient]:
    fake = FakeLLMClient(model="test-model")
    app.dependency_overrides[get_optional_llm] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_optional_llm, None)


@pytest.fixture
def no_model(client: TestClient) -> Iterator[None]:
    app.dependency_overrides[get_optional_llm] = lambda: None
    yield
    app.dependency_overrides.pop(get_optional_llm, None)


@pytest.fixture
def org(db: Session) -> None:
    db.add_all(
        [
            Lead(
                name="Ayesha",
                company="Indus Textiles",
                email="a@indus.example.com",
                status=LeadStatus.contacted,
                value_minor=4_800_000,
                rating=LeadRating.hot,
            ),
            Lead(
                name="Bilal",
                company="Karachi Logistics",
                email="b@khi.example.com",
                status=LeadStatus.new,
                value_minor=3_600_000,
            ),
            Job(title="Senior Backend Engineer", required_skills=["python"]),
            Candidate(name="Sara Malik"),
            PurchaseRequest(item="laptops", quantity=10, budget_minor=1, currency="USD"),
            Ticket(title="Site down", status=TicketStatus.open, urgency=Urgency.critical),
            ApprovalRequest(
                action="pay_invoice",
                payload={},
                required_role=Role.manager,
                department=Department.finance,
            ),
        ]
    )
    db.commit()


def _facts(*texts: str) -> BriefInput:
    return BriefInput(
        first_name="Zara",
        role="executive",
        department="finance",
        weekday="Friday",
        focus="Oversees the whole company: lead with the risks.",
        facts=[BriefFact(id=i + 1, text=t, link="/x", tone="info") for i, t in enumerate(texts)],
    )


def test_numbers_are_compared_by_value_not_by_spelling() -> None:
    assert numbers_in("1,250.00 USD, 13 days late, two tickets") == {
        Decimal(1250),
        Decimal(13),
        Decimal(2),
    }


def test_check_accepts_numbers_from_the_facts_and_drops_unknown_ids() -> None:
    data = _facts("1 customer payment overdue (450.00 USD)", "PO-2001 is 13 days late")
    draft = BriefDraft(
        headline="PO-2001 is 13 days late",
        summary="You have 1 overdue payment of $450 to chase.",
        top=[2, 9, 1],
    )
    assert check_brief(draft, data).top == [2, 1]


def test_check_rejects_a_number_no_fact_contains() -> None:
    data = _facts("PO-2001 is 13 days late")
    draft = BriefDraft(headline="Late order", summary="PO-2001 is 14 days late now.", top=[1])
    with pytest.raises(LLMOutputError, match="14"):
        check_brief(draft, data)


def test_brief_uses_the_checked_model_draft(
    client: TestClient,
    db: Session,
    org: None,
    model: FakeLLMClient,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    manager = make_user(Role.manager, Department.finance)
    model.replies.append(
        {
            "headline": "A payment waits for your approval",
            "summary": "1 decision is waiting for you. 1 urgent ticket is open.",
            "top": [1],
        }
    )

    res = client.get("/api/ai/brief", headers=auth_header(manager))

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["written_by"] == "model"
    assert body["model"] == "test-model"
    assert body["headline"] == "A payment waits for your approval"
    assert body["items"][0]["text"] == "1 decision is waiting for your approval"
    assert "<document>" in model.calls[0].user  # facts are fenced like any untrusted text
    task = db.scalar(select(AgentTask).where(AgentTask.agent == "brief_writer"))
    assert task is not None and task.status == TaskStatus.succeeded


def test_brief_falls_back_to_code_when_the_model_keeps_inventing_numbers(
    client: TestClient,
    db: Session,
    org: None,
    model: FakeLLMClient,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    invented = {"headline": "Busy day", "summary": "You have 99 approvals waiting.", "top": [1]}
    model.replies.extend([invented, invented, invented])

    body = client.get(
        "/api/ai/brief", headers=auth_header(make_user(Role.executive, Department.finance))
    ).json()

    assert body["written_by"] == "code"
    assert body["model"] is None
    assert body["headline"] == "1 urgent ticket open"  # the executive approves nothing: risks lead
    assert "99" not in body["summary"]
    failed = db.scalars(select(AgentTask).where(AgentTask.status == TaskStatus.failed)).all()
    assert len(failed) == 3  # every attempt is on record in the Command Center


def test_brief_without_a_model_is_written_by_code(
    client: TestClient, org: None, no_model: None, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    body = client.get(
        "/api/ai/brief", headers=auth_header(make_user(Role.executive, Department.finance))
    ).json()

    assert body["written_by"] == "code"
    assert body["summary"].startswith("Also: ")
    assert len(body["items"]) == 4


def test_empty_company_gets_an_all_clear_brief(
    client: TestClient, no_model: None, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    body = client.get(
        "/api/ai/brief", headers=auth_header(make_user(Role.executive, Department.finance))
    ).json()
    assert body["headline"] == "All clear: nothing is waiting on anyone"


def test_quick_actions_point_at_real_records(
    client: TestClient, org: None, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    manager = make_user(Role.manager, Department.finance)

    actions = client.get("/api/ai/quick-actions", headers=auth_header(manager)).json()

    assert [(a["icon"], a["detail"]) for a in actions] == [
        ("approvals", "1 waiting for you"),
        ("lead", "Karachi Logistics"),  # not rated yet comes first
        ("hiring", "Senior Backend Engineer"),
        ("supplier", "laptops"),
    ]
    assert actions[1]["prompt"] == "Is the Karachi Logistics lead worth chasing?"
    assert actions[0]["link"] == "/approvals"


def test_employees_do_not_get_the_brief(
    client: TestClient, no_model: None, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    clerk = make_user(Role.employee, Department.finance)
    assert client.get("/api/ai/brief", headers=auth_header(clerk)).status_code == 403
    assert client.get("/api/ai/quick-actions", headers=auth_header(clerk)).status_code == 403


LIVE_FACTS = (
    "2 decisions are waiting for another manager (not yours to approve)",
    "PO-2001 from Northwind Metals Ltd. is 13 days late",
    "1 customer payment overdue (450.00 USD)",
    "1 invoice needs a human check",
    "2 urgent tickets open",
    "2 hot leads in the pipeline (Quetta Mining Co, Indus Textiles)",
    "Open sales pipeline: 181,000.00 USD in 5 deals",
)


@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1 and LIVE_LLM_API_KEY"
)
@pytest.mark.parametrize(("role", "department"), [("executive", "finance"), ("manager", "sales")])
def test_live_model_writes_a_brief_that_passes_the_checks(role: str, department: str) -> None:
    from app.agents.brief_writer import BriefWriter
    from app.config import get_settings
    from app.llm.vultr import VultrLLMClient

    settings = get_settings()
    llm = VultrLLMClient(
        base_url=settings.llm_base_url,
        api_key=os.environ["LIVE_LLM_API_KEY"],
        model=settings.llm_model,
    )
    from app.services.brief import focus

    reader = User(
        email="x@example.com", full_name="Zara Khan", role=Role(role), department=department
    )
    data = _facts(*LIVE_FACTS).model_copy(
        update={"role": role, "department": department, "focus": focus(reader)}
    )

    draft = BriefWriter(Department(department)).run(data, llm)  # raises if a check fails

    assert draft.top and set(draft.top) <= set(range(1, len(LIVE_FACTS) + 1))
    print(f"\n[{role}] {draft.headline}\n{draft.summary}\ntop={draft.top}")


def test_code_writer_skips_the_model(
    client: TestClient,
    org: None,
    model: FakeLLMClient,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    body = client.get(
        "/api/ai/brief?writer=code",
        headers=auth_header(make_user(Role.executive, Department.finance)),
    ).json()

    assert body["written_by"] == "code"
    assert model.calls == []


def test_code_brief_keeps_codes_and_names_capitalised() -> None:
    from app.services.brief import _sentence_case

    assert _sentence_case("PO-2001 is 13 days late") == "PO-2001 is 13 days late"
    assert _sentence_case("Open sales pipeline: 5 deals") == "open sales pipeline: 5 deals"
    assert _sentence_case("2 urgent tickets open") == "2 urgent tickets open"


def test_a_decision_for_another_department_is_never_called_yours(
    client: TestClient, org: None, no_model: None, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    sales_manager = make_user(Role.manager, Department.sales)

    body = client.get("/api/ai/brief", headers=auth_header(sales_manager)).json()

    texts = [i["text"] for i in body["items"]]
    assert not any("your approval" in t for t in texts)
    actions = client.get("/api/ai/quick-actions", headers=auth_header(sales_manager)).json()
    assert actions[0]["detail"] == "nothing waiting for you"
