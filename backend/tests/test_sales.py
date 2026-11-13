"""FR-SAL-01 leads CRUD and FR-SAL-02 Lead Qualifier."""

import os
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.fake import FakeLLMClient
from app.models import AgentTask, User
from app.models.enums import Department, Role
from app.schemas.sales import QualificationResult

API = "/api/sales/leads"
LEAD = {
    "name": "Ayesha Khan",
    "company": "Indus Textiles",
    "email": "ayesha@industextiles.example.com",
    "status": "contacted",
    "priority": "high",
    "value_minor": 4800000,
    "currency": "USD",
    "notes": "COO asked for a pilot in Q1, budget approved, wants a demo next week.",
}
REASON = (
    "The COO is personally driving this, the budget is already approved and they want a "
    "demo next week for a first quarter pilot, so the deal has need, authority and timing."
)
HOT = {"rating": "hot", "reason": REASON, "cited_fields": ["notes", "priority", "value"]}


@pytest.fixture
def headers(
    make_user: Callable[..., User], auth_header: Callable[[User], dict[str, str]]
) -> dict[str, str]:
    return auth_header(make_user(Role.employee, Department.sales))


def _create(client: TestClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    res = client.post(API, json=LEAD | overrides, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_lead_crud_returns_the_same_fields(client: TestClient, headers: dict[str, str]) -> None:
    lead = _create(client, headers)
    assert {k: lead[k] for k in LEAD} == LEAD
    assert lead["rating"] is None and lead["qualification"] is None

    assert client.get(f"{API}/{lead['id']}", headers=headers).json() == lead
    assert client.get(API, headers=headers).json()["items"] == [lead]

    patched = client.patch(
        f"{API}/{lead['id']}", json={"status": "qualified", "priority": "medium"}, headers=headers
    )
    assert patched.status_code == 200
    assert {k: patched.json()[k] for k in ("status", "priority", "company")} == {
        "status": "qualified",
        "priority": "medium",
        "company": "Indus Textiles",
    }
    assert (
        client.get(f"{API}?status=qualified", headers=headers).json()["items"][0]["id"]
        == lead["id"]
    )
    assert client.get(f"{API}?status=new", headers=headers).json()["items"] == []


@pytest.mark.parametrize(
    "bad", [{"email": "not-an-email"}, {"status": "maybe"}, {"value_minor": -1}, {"company": ""}]
)
def test_lead_input_is_validated(
    client: TestClient, headers: dict[str, str], bad: dict[str, Any]
) -> None:
    assert client.post(API, json=LEAD | bad, headers=headers).status_code == 422


def test_only_sales_can_change_leads(
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[[User], dict[str, str]],
) -> None:
    finance = auth_header(make_user(Role.employee, Department.finance))
    executive = auth_header(make_user(Role.executive, Department.finance))

    assert client.get(API, headers=finance).status_code == 403
    assert client.get(API, headers=executive).status_code == 200
    assert client.post(API, json=LEAD, headers=executive).status_code == 403


def test_qualify_saves_rating_reason_and_cited_fields(
    client: TestClient, headers: dict[str, str], fake_llm: FakeLLMClient, db: Session
) -> None:
    lead = _create(client, headers)
    fake_llm.replies.append(HOT)

    res = client.post(f"{API}/{lead['id']}/qualify", headers=headers)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["rating"] == "hot"
    assert body["qualification"]["reason"] == REASON
    assert body["qualification"]["cited_fields"] == ["notes", "priority", "value"]
    assert body["qualification"]["model"] == "fake"
    QualificationResult.model_validate(body["qualification"])

    # The agent got the facts it needs, without the person's name or full email.
    [call] = fake_llm.calls
    assert "Indus Textiles" in call.user and "industextiles.example.com" in call.user
    assert "Ayesha" not in call.user and "ayesha@" not in call.user

    tasks = db.scalars(select(AgentTask).order_by(AgentTask.created_at)).all()
    assert [(t.agent, t.tool) for t in tasks] == [
        ("lead_qualifier", "get_lead"),
        ("lead_qualifier", None),
        ("lead_qualifier", "update_lead_status"),
    ]
    assert client.get(f"{API}?rating=hot", headers=headers).json()["items"][0]["id"] == lead["id"]


@pytest.mark.parametrize(
    "bad",
    [
        HOT | {"reason": "Looks promising, budget approved."},  # fewer than 20 words
        HOT | {"cited_fields": []},
        HOT | {"cited_fields": ["salary"]},
        HOT | {"rating": "lukewarm"},
    ],
)
def test_invalid_qualification_is_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        QualificationResult.model_validate(bad)


def test_short_reason_is_retried_then_accepted(
    client: TestClient, headers: dict[str, str], fake_llm: FakeLLMClient, db: Session
) -> None:
    lead = _create(client, headers)
    fake_llm.replies += [HOT | {"reason": "Hot lead."}, HOT]

    assert client.post(f"{API}/{lead['id']}/qualify", headers=headers).json()["rating"] == "hot"
    agent_rows = db.scalars(select(AgentTask).where(AgentTask.tool.is_(None))).all()
    assert sorted(t.status for t in agent_rows) == ["failed", "succeeded"]


def test_qualify_unknown_lead_is_404(
    client: TestClient, headers: dict[str, str], fake_llm: FakeLLMClient
) -> None:
    res = client.post(f"{API}/00000000-0000-0000-0000-000000000000/qualify", headers=headers)
    assert res.status_code == 404


@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1 and LIVE_LLM_API_KEY"
)
def test_live_vultr_qualification() -> None:
    from app.agents.lead_qualifier import LeadQualifier
    from app.config import get_settings
    from app.llm.vultr import VultrLLMClient
    from app.schemas.sales import LeadForQualification

    settings = get_settings()
    llm = VultrLLMClient(
        base_url=settings.llm_base_url,
        api_key=os.environ["LIVE_LLM_API_KEY"],
        model=settings.llm_model,
    )
    hot = LeadForQualification(
        company="Indus Textiles",
        email_domain="industextiles.example.com",
        status="contacted",
        priority="high",
        value="48,000.00 USD",
        notes=LEAD["notes"],
    )
    cold = LeadForQualification(
        company="Student project",
        email_domain="gmail.com",
        status="new",
        priority="low",
        value="0.00 USD",
        notes="Downloaded the brochure for a university assignment. No budget.",
    )

    hot_result = LeadQualifier().run(hot, llm)
    cold_result = LeadQualifier().run(cold, llm)

    assert hot_result.rating == "hot" and "notes" in hot_result.cited_fields
    assert cold_result.rating == "cold"


def test_summary_counts_stages_and_weekly_trend(
    client: TestClient, headers: dict[str, str]
) -> None:
    won = _create(client, headers, value_minor=1000000)
    _create(client, headers, value_minor=250000, status="new", email="omar@other.example.com")
    client.patch(f"{API}/{won['id']}", json={"status": "won"}, headers=headers)

    res = client.get("/api/sales/summary", headers=headers)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["currency"] == "USD"
    stages = {s["stage"]: (s["count"], s["value_minor"]) for s in body["stages"]}
    assert stages["won"] == (1, 1000000) and stages["new"] == (1, 250000)
    assert stages["lost"] == (0, 0)
    assert len(body["weeks"]) == 8
    this_week = body["weeks"][-1]
    assert (this_week["new_leads"], this_week["new_value_minor"]) == (2, 1250000)
    assert (this_week["won"], this_week["won_minor"]) == (1, 1000000)
    # The quarterly target travels with it, so the Sales page shows (and the CEO edits) it too.
    target = body["target"]
    assert (target["won_minor"], target["currency"], target["set_by"]) == (1000000, "USD", None)
    assert target["target_minor"] == 250_000_00 and target["quarter"].startswith("Q")


def test_weeks_are_counted_in_utc() -> None:
    """Sunday 23:30 UTC is already Monday in a +05:00 database session; it stays in the UTC week
    (before, it mapped to a week missing from the chart and the summary answered 500)."""
    from datetime import UTC, date, datetime, timedelta, timezone

    from app.services.sales import week_of

    sunday_late = datetime(2026, 11, 8, 23, 30, tzinfo=UTC)
    as_seen_in_pkt = sunday_late.astimezone(timezone(timedelta(hours=5)))

    assert as_seen_in_pkt.date() == date(2026, 11, 9)  # Monday locally
    assert week_of(as_seen_in_pkt) == week_of(sunday_late) == date(2026, 11, 2)


def test_summary_is_for_the_sales_department_only(
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[[User], dict[str, str]],
) -> None:
    finance = auth_header(make_user(Role.employee, Department.finance))
    assert client.get("/api/sales/summary", headers=finance).status_code == 403
