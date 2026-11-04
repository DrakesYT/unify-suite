"""FR-AURA-01: chat messages route to the right department agent, which then really runs."""

import os
from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.fake import FakeLLMClient
from app.models import AgentTask, Lead, PurchaseRequest, User, Vendor, VendorQuote
from app.models.enums import Department, Role

AuthHeader = Callable[[User], dict[str, str]]
HOT = {
    "rating": "hot",
    "reason": "The head of operations has budget approved this quarter and wants a demo on Friday, "
    "so need, authority and timing are all present for a near-term deal.",
    "cited_fields": ["notes"],
}


def _route(route: str, target: str | None = None) -> dict[str, str | None]:
    return {"route": route, "target": target, "reply": "On it."}


def _chat(client: TestClient, headers: dict[str, str], message: str):  # type: ignore[no-untyped-def]
    res = client.post("/api/ai/chat", json={"message": message}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_qualify_lead_by_company_name(
    client: TestClient,
    db: Session,
    fake_llm: FakeLLMClient,
    make_user: Callable[..., User],
    auth_header: AuthHeader,
) -> None:
    rep = make_user(Role.employee, Department.sales)
    db.add_all(
        [
            Lead(
                name="A",
                company="Karachi Logistics Group",
                email="a@klg.example.com",
                notes="budget approved",
            ),
            Lead(name="B", company="Other Co", email="b@other.example.com"),
        ]
    )
    db.commit()
    fake_llm.replies += [_route("sales.qualify_lead", "Karachi Logistics"), HOT]

    body = _chat(client, auth_header(rep), "Can you rate the Karachi Logistics lead?")

    assert (body["outcome"], body["agent"], body["link"]) == ("done", "lead_qualifier", "/sales")
    assert body["summary"] == "Karachi Logistics Group is rated hot."
    assert db.scalar(select(Lead.rating).where(Lead.company == "Karachi Logistics Group")) == "hot"
    agents = {t.agent for t in db.scalars(select(AgentTask))}
    assert {"aura_router", "lead_qualifier"} <= agents


def test_compare_vendors_from_chat(
    client: TestClient,
    db: Session,
    fake_llm: FakeLLMClient,
    make_user: Callable[..., User],
    auth_header: AuthHeader,
) -> None:
    buyer = make_user(Role.employee, Department.procurement)
    request = PurchaseRequest(
        item="Laptops for new hires", quantity=2, budget_minor=500000, currency="USD"
    )
    a = Vendor(name="Fast IT", lead_time_days=2, on_time_rate=Decimal("0.99"))
    b = Vendor(name="Slow IT", lead_time_days=20, on_time_rate=Decimal("0.7"))
    db.add_all([request, a, b])
    db.flush()
    db.add_all(
        [
            VendorQuote(
                request_id=request.id, vendor_id=a.id, unit_price_minor=100000, currency="USD"
            ),
            VendorQuote(
                request_id=request.id, vendor_id=b.id, unit_price_minor=100000, currency="USD"
            ),
        ]
    )
    db.commit()
    fake_llm.replies += [
        _route("procurement.compare_vendors", "laptops"),
        {"reason": "Fast IT wins with the same price, a 2 day lead time and a 99% on-time record."},
    ]

    body = _chat(client, auth_header(buyer), "compare vendors for the laptops request")

    assert body["outcome"] == "done"
    assert body["summary"].startswith("Fast IT ranks first")


def test_aura_cannot_do_more_than_the_user_can(
    client: TestClient,
    db: Session,
    fake_llm: FakeLLMClient,
    make_user: Callable[..., User],
    auth_header: AuthHeader,
) -> None:
    db.add(Lead(name="A", company="Acme", email="a@acme.example.com"))
    db.commit()
    hr_person = make_user(Role.employee, Department.hr)
    fake_llm.replies.append(_route("sales.qualify_lead", "Acme"))

    body = _chat(client, auth_header(hr_person), "rate the Acme lead")

    assert body["outcome"] == "not_allowed"
    assert db.scalar(select(Lead.rating)) is None


def test_unknown_record_and_no_route(
    client: TestClient,
    fake_llm: FakeLLMClient,
    make_user: Callable[..., User],
    auth_header: AuthHeader,
) -> None:
    headers = auth_header(make_user(Role.employee, Department.sales))
    fake_llm.replies += [_route("sales.qualify_lead", "Nonexistent Ltd"), _route("none")]

    assert _chat(client, headers, "rate Nonexistent Ltd")["outcome"] == "not_found"
    assert _chat(client, headers, "what's the weather?")["outcome"] == "no_route"


def test_invoice_verification_asks_for_the_file(
    client: TestClient,
    fake_llm: FakeLLMClient,
    make_user: Callable[..., User],
    auth_header: AuthHeader,
) -> None:
    fake_llm.replies.append(_route("finance.verify_invoice"))

    body = _chat(
        client, auth_header(make_user(Role.employee, Department.finance)), "check invoice INV-9"
    )

    assert (body["outcome"], body["link"]) == ("needs_input", "/payments")


def test_route_must_be_one_of_the_list(
    client: TestClient,
    fake_llm: FakeLLMClient,
    make_user: Callable[..., User],
    auth_header: AuthHeader,
) -> None:
    fake_llm.replies += [_route("finance.delete_everything"), _route("none")]

    body = _chat(client, auth_header(make_user()), "do something drastic")

    assert body["route"] == "none"  # the invalid route was rejected and retried


@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1 and LIVE_LLM_API_KEY"
)
@pytest.mark.parametrize(
    ("message", "route"),
    [
        ("Is the Karachi Logistics lead worth chasing?", "sales.qualify_lead"),
        ("Rank the applicants for the Senior Backend Engineer role", "hr.screen_candidates"),
        ("Look into the ticket about being charged twice", "support.investigate_ticket"),
        ("Which supplier should we buy the laptops from?", "procurement.compare_vendors"),
        ("I have an invoice from Northwind to check before we pay it", "finance.verify_invoice"),
    ],
)
def test_live_five_sample_commands_route_correctly(message: str, route: str) -> None:
    from app.agents.aura_router import AuraRouter
    from app.config import get_settings
    from app.llm.vultr import VultrLLMClient
    from app.schemas.aura import AuraRequest

    settings = get_settings()
    llm = VultrLLMClient(
        base_url=settings.llm_base_url,
        api_key=os.environ["LIVE_LLM_API_KEY"],
        model=settings.llm_model,
    )

    assert AuraRouter(Department.sales).run(AuraRequest(message=message), llm).route == route


def test_read_only_users_get_the_current_state(
    client: TestClient,
    db: Session,
    fake_llm: FakeLLMClient,
    make_user: Callable[..., User],
    auth_header: AuthHeader,
) -> None:
    db.add(Lead(name="A", company="Acme Corp", email="a@acme.example.com", rating="warm"))
    db.commit()
    executive = make_user(Role.executive, Department.finance)
    fake_llm.replies.append(_route("sales.qualify_lead", "Acme"))

    body = _chat(client, auth_header(executive), "how hot is the Acme lead?")

    assert body["outcome"] == "not_allowed"
    assert body["summary"] == "Your role can view but not run this. Acme Corp is rated warm."
    assert len(fake_llm.calls) == 1  # no agent was run
