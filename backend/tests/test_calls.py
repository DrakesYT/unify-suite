"""Call transcript analyzer: summary, sentiment and action items, every quote checked by code."""

import os
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.call_analyzer import verify
from app.llm import LLMOutputError
from app.llm.fake import FakeLLMClient
from app.models import AgentTask, CallTranscript, Lead, Ticket, User
from app.models.enums import Department, LeadStatus, Role
from app.schemas.calls import CallAnalysis, CallInput
from app.services.calls import speakers

AuthHeader = Callable[[User], dict[str, str]]
MakeUser = Callable[..., User]

# The example from the demo-data kit sent to the team, as plain text.
TRANSCRIPT = """Call: Karachi Logistics Group - pricing follow-up
Date: 2026-11-03   Duration: about 2 minutes
Agent: Hi Bilal, this is Sana from UNIFY Demo Corp, following up on your pricing question.
Customer: Thanks for calling. We want to automate invoice checks across our three warehouses.
Agent: How many supplier invoices do you handle in a month?
Customer: Around 1,200. Two people check them by hand and we still pay duplicates now and then.
Agent: Duplicates are exactly what our matching catches. Who else is involved in the decision?
Customer: Our CFO signs off. She wants to see it working on our own invoices first.
Agent: Then a two-week pilot on one warehouse makes sense. Could I send a proposal by Friday?
Customer: Yes, Friday works. Please include what the pilot costs.
Agent: Will do. I'll also book a 30-minute demo with your CFO next week.
Customer: Great, talk then.
"""

ANALYSIS: dict[str, Any] = {
    "summary": "Karachi Logistics wants to automate invoice checks across three warehouses and "
    "keeps paying duplicates. The CFO decides and wants a pilot on their own invoices.",
    "sentiment": "positive",
    "sentiment_quote": "Yes, Friday works.",
    "concerns": ["Duplicate payments", "CFO wants proof on their own invoices"],
    "action_items": [
        {
            "owner": "us",
            "task": "Send a pilot proposal including the cost",
            "due": "Friday",
            "quote": "Could I send a proposal by Friday?",
        },
        {
            "owner": "us",
            "task": "Book a 30-minute demo with the CFO",
            "due": "next week",
            "quote": "I'll also book a 30-minute demo with your CFO next week.",
        },
    ],
}


@pytest.fixture
def lead(db: Session) -> Lead:
    row = Lead(
        name="Bilal",
        company="Karachi Logistics Group",
        email="bilal@khi.example.com",
        status=LeadStatus.contacted,
    )
    db.add(row)
    db.commit()
    return row


def _add(client: TestClient, headers: dict[str, str], **form: Any) -> Any:
    files = form.pop("files", None)
    return client.post("/api/calls", headers=headers, data=form, files=files)


def test_speaker_share_is_counted_by_code() -> None:
    shares = {s.speaker: s for s in speakers(TRANSCRIPT)}

    assert set(shares) == {"Agent", "Customer"}  # "Call:" and "Date:" are headers, not people
    assert (shares["Agent"].turns, shares["Customer"].turns) == (5, 5)
    assert shares["Agent"].share_pct + shares["Customer"].share_pct == 100


def test_an_unlabelled_transcript_has_no_speaker_share() -> None:
    assert speakers("We talked about pricing and they liked the pilot idea.") == []


def test_a_quote_that_is_not_in_the_transcript_is_rejected() -> None:
    data = CallInput(context="Sales lead", transcript=TRANSCRIPT)
    bad = CallAnalysis.model_validate(ANALYSIS | {"sentiment_quote": "We will sign today."})
    with pytest.raises(LLMOutputError, match="not in the transcript"):
        verify(bad, data)
    assert verify(CallAnalysis.model_validate(ANALYSIS), data).sentiment == "positive"
    vague = ANALYSIS | {"action_items": [ANALYSIS["action_items"][0] | {"quote": "Will do."}]}
    with pytest.raises(LLMOutputError, match="too short"):
        verify(CallAnalysis.model_validate(vague), data)


def test_upload_for_a_lead_is_analysed_and_logged(
    client: TestClient,
    db: Session,
    lead: Lead,
    fake_llm: FakeLLMClient,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    h = auth_header(make_user(Role.employee, Department.sales))
    fake_llm.replies.append(ANALYSIS)

    res = _add(
        client,
        h,
        lead_id=str(lead.id),
        files={"file": ("karachi-call.txt", TRANSCRIPT.encode(), "text/plain")},
    )

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["title"] == "Karachi Logistics Group - pricing follow-up"  # from the "Call:" line
    assert body["department"] == "sales"
    assert body["analysis"]["sentiment"] == "positive"
    assert [a["due"] for a in body["analysis"]["action_items"]] == ["Friday", "next week"]
    assert body["analyzed_by_model"] == "fake"
    assert {s["speaker"] for s in body["speakers"]} == {"Agent", "Customer"}
    assert "Sales lead: Karachi Logistics Group" in fake_llm.calls[0].user
    assert "<document>" in fake_llm.calls[0].user
    tools = {
        t.tool: t for t in db.scalars(select(AgentTask).where(AgentTask.agent == "call_analyzer"))
    }
    assert set(tools) == {"read_upload", "get_call_context", None, "save_call_analysis"}
    assert "Bilal" not in str(tools["get_call_context"].output)  # the log never holds the text

    listed = client.get(f"/api/calls?lead_id={lead.id}", headers=h).json()
    assert [c["id"] for c in listed] == [body["id"]]
    assert db.get(Lead, lead.id).status == LeadStatus.contacted  # a call changes nothing by itself


def test_pasted_text_for_a_ticket_goes_to_support(
    client: TestClient,
    db: Session,
    fake_llm: FakeLLMClient,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    ticket = Ticket(title="Charged twice", description="")
    db.add(ticket)
    db.commit()
    h = auth_header(make_user(Role.employee, Department.support))
    fake_llm.replies.append(ANALYSIS)

    res = _add(client, h, ticket_id=str(ticket.id), text=TRANSCRIPT, title="Refund call")

    assert res.status_code == 201, res.text
    assert (res.json()["title"], res.json()["department"]) == ("Refund call", "support")
    assert "Support ticket: Charged twice" in fake_llm.calls[0].user


def test_a_failed_analysis_keeps_the_transcript_and_can_be_retried(
    client: TestClient,
    lead: Lead,
    fake_llm: FakeLLMClient,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    h = auth_header(make_user(Role.employee, Department.sales))
    invented = ANALYSIS | {"sentiment_quote": "We will sign the contract today."}
    fake_llm.replies += [invented, invented, invented, ANALYSIS]

    first = _add(client, h, lead_id=str(lead.id), text=TRANSCRIPT).json()

    assert first["analysis"] is None
    assert "not in the transcript" in first["analysis_error"]
    again = client.post(f"/api/calls/{first['id']}/analyze", headers=h)
    assert again.status_code == 200, again.text
    assert again.json()["analysis"]["sentiment"] == "positive"
    assert again.json()["analysis_error"] is None


@pytest.mark.parametrize(
    ("form", "status"),
    [
        ({"text": TRANSCRIPT}, 422),  # neither lead nor ticket
        ({}, 422),  # no transcript at all
        (
            {"files": {"file": ("call.docx", b"PK\x03\x04", "application/octet-stream")}},
            415,
        ),
    ],
)
def test_bad_requests_are_refused(
    client: TestClient,
    lead: Lead,
    fake_llm: FakeLLMClient,
    make_user: MakeUser,
    auth_header: AuthHeader,
    form: dict[str, Any],
    status: int,
) -> None:
    h = auth_header(make_user(Role.employee, Department.sales))
    if form and "text" not in form:
        form = form | {"lead_id": str(lead.id)}
    elif not form:
        form = {"lead_id": str(lead.id)}
    assert _add(client, h, **form).status_code == status


def test_departments_only_see_their_own_calls(
    client: TestClient,
    db: Session,
    lead: Lead,
    fake_llm: FakeLLMClient,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    hr_clerk = auth_header(make_user(Role.employee, Department.hr))
    assert _add(client, hr_clerk, lead_id=str(lead.id), text=TRANSCRIPT).status_code == 403
    assert client.get(f"/api/calls?lead_id={lead.id}", headers=hr_clerk).status_code == 403
    support_manager = auth_header(make_user(Role.manager, Department.support))
    assert client.get(f"/api/calls?lead_id={lead.id}", headers=support_manager).status_code == 200
    assert db.scalar(select(CallTranscript.id)) is None


def test_why_panel_shows_the_verified_input_and_the_checks(
    client: TestClient,
    lead: Lead,
    fake_llm: FakeLLMClient,
    make_user: MakeUser,
    auth_header: AuthHeader,
) -> None:
    h = auth_header(make_user(Role.employee, Department.sales))
    fake_llm.replies.append(ANALYSIS)
    call = _add(client, h, lead_id=str(lead.id), text=TRANSCRIPT).json()

    why = client.get(f"/api/explain/call/{call['id']}", headers=h).json()

    assert why["agent"] == "Call Analyzer"
    assert why["input_verified"] is True
    assert why["code_decided"][1].startswith("Counted talk share from the speaker labels: Agent")
    assert any(f["label"] == "action (us, Friday)" for f in why["ai_said"])
    assert [p["did"] for p in why["people"]] == [
        "added the call transcript",
        "ran the Call Analyzer",
    ]


@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1 and LIVE_LLM_API_KEY"
)
def test_live_model_analyses_the_kit_transcript() -> None:
    from app.agents.call_analyzer import CallAnalyzer
    from app.config import get_settings
    from app.llm.vultr import VultrLLMClient

    settings = get_settings()
    llm = VultrLLMClient(
        base_url=settings.llm_base_url,
        api_key=os.environ["LIVE_LLM_API_KEY"],
        model=settings.llm_model,
    )
    data = CallInput(
        context="Sales lead: Karachi Logistics Group (status: contacted)", transcript=TRANSCRIPT
    )

    result = CallAnalyzer(Department.sales).run(data, llm)  # raises if a quote is invented

    assert result.sentiment in ("positive", "mixed")
    assert any("proposal" in a.task.lower() for a in result.action_items)
    print("\n", result.model_dump_json(indent=1))
