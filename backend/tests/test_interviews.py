"""Interview scheduling: code picks free office-hour times; the agent only writes the invite."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SELLER_COMPANY
from app.llm.fake import FakeLLMClient
from app.mailer.fake import FakeEmailSender
from app.models import Candidate, CandidateScore, InterviewSlot, Job
from app.models.base import utcnow
from app.scheduling import label, pick_slots
from app.seed import seed
from tests.test_seed import PASSWORD, _login

THU_3PM_PKT = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)  # Thu 5 Nov 2026, 15:00 PKT


def test_one_slot_per_working_day_from_tomorrow_skipping_the_weekend() -> None:
    slots = pick_slots(THU_3PM_PKT, [])

    assert [label(s) for s in slots] == [
        "Fri 6 Nov 2026, 10:00-10:45 PKT",
        "Mon 9 Nov 2026, 10:00-10:45 PKT",
        "Tue 10 Nov 2026, 10:00-10:45 PKT",
    ]
    assert slots[0] == datetime(2026, 11, 6, 5, 0, tzinfo=UTC)


def test_held_times_are_never_offered_twice() -> None:
    friday_10 = datetime(2026, 11, 6, 5, 0, tzinfo=UTC)
    busy = [(friday_10, friday_10 + timedelta(minutes=45))]

    assert label(pick_slots(THU_3PM_PKT, busy)[0]) == "Fri 6 Nov 2026, 11:00-11:45 PKT"


def test_a_fully_booked_day_is_skipped() -> None:
    friday = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)
    busy = [(friday, friday + timedelta(hours=24))]

    assert label(pick_slots(THU_3PM_PKT, busy)[0]).startswith("Mon 9 Nov 2026")


def test_the_day_is_taken_in_pakistan_time() -> None:
    late_friday_pkt = datetime(2026, 11, 5, 20, 0, tzinfo=UTC)  # already Fri 01:00 in PKT

    assert label(pick_slots(late_friday_pkt, [])[0]).startswith("Mon 9 Nov 2026")


# --- the invitation flow, on the demo seed ------------------------------------------------------


@pytest.fixture
def demo(client: TestClient, db: Session) -> dict[str, Any]:
    seed(db, PASSWORD)
    job = db.scalar(select(Job).where(Job.title == "Senior Backend Engineer"))
    assert job is not None
    people = {c.name.split()[0]: c for c in db.scalars(select(Candidate))}
    for first, score in (("Sara", 82), ("Mehwish", 64), ("Ali", 6)):
        evidence = [
            {"requirement": "Python", "quote": "x"},
            {"requirement": "Docker", "quote": "y"},
        ]
        db.add(
            CandidateScore(
                candidate_id=people[first].id, job_id=job.id, score=score, evidence=evidence
            )
        )
    db.commit()
    handles = ("hr.recruiter", "hr.manager", "sales.manager")
    return {
        "job": job,
        "people": people,
        "headers": {h: _login(client, h) for h in handles},
    }


def _url(demo: dict[str, Any], first: str) -> str:
    return f"/api/hr/jobs/{demo['job'].id}/candidates/{demo['people'][first].id}/emails"


def _invite_reply(slots: list[str]) -> dict[str, str]:
    lines = "\n".join(f"- {s}" for s in slots)
    return {
        "subject": "Interview for the Senior Backend Engineer role",
        "body": (
            "Thank you for applying for the Senior Backend Engineer role. Your Python and Docker "
            "experience stood out, and we would like to invite you to a 45-minute video call.\n\n"
            f"Please reply with the option that suits you best:\n{lines}"
        ),
    }


def _expected_labels(db: Session) -> list[str]:
    busy = [
        (s.starts_at, s.ends_at)
        for s in db.scalars(select(InterviewSlot).where(InterviewSlot.released.is_(False)))
    ]
    return [label(s) for s in pick_slots(utcnow(), busy)]


def test_invite_offers_code_picked_times_and_holds_them(
    client: TestClient, demo: dict[str, Any], fake_llm: FakeLLMClient, db: Session
) -> None:
    labels = _expected_labels(db)
    fake_llm.replies.append(_invite_reply(labels))

    res = client.post(_url(demo, "Sara"), headers=demo["headers"]["hr.recruiter"])

    assert res.status_code == 201, res.text
    email = res.json()
    assert email["to_address"] == "sara.malik@example.com"
    assert email["body"].startswith("Dear Sara,\n\n")
    assert email["body"].endswith(f"Talent team, {SELLER_COMPANY}")
    prompt = fake_llm.calls[-1].user
    assert all(s in prompt for s in labels) and "@" not in prompt
    held = db.scalars(select(InterviewSlot).where(InterviewSlot.released.is_(False))).all()
    assert sorted(label(s.starts_at) for s in held) == sorted(labels)


def test_a_draft_that_changes_a_time_is_retried(
    client: TestClient, demo: dict[str, Any], fake_llm: FakeLLMClient, db: Session
) -> None:
    labels = _expected_labels(db)
    wrong = _invite_reply([labels[0].replace("10:00-10:45", "09:00-09:45"), *labels[1:]])
    fake_llm.replies += [wrong, _invite_reply(labels)]

    res = client.post(_url(demo, "Sara"), headers=demo["headers"]["hr.recruiter"])

    assert res.status_code == 201
    assert len(fake_llm.calls) == 2


@pytest.mark.parametrize(("first", "code"), [("Ali", "score_too_low"), ("Hassan", "not_screened")])
def test_only_screened_strong_candidates_are_invited(
    client: TestClient, demo: dict[str, Any], fake_llm: FakeLLMClient, first: str, code: str
) -> None:
    res = client.post(_url(demo, first), headers=demo["headers"]["hr.recruiter"])

    assert res.status_code == 409 and res.json()["error"]["code"] == code
    assert fake_llm.calls == []


def test_two_candidates_never_get_the_same_time(
    client: TestClient, demo: dict[str, Any], fake_llm: FakeLLMClient, db: Session
) -> None:
    first = _expected_labels(db)
    fake_llm.replies.append(_invite_reply(first))
    client.post(_url(demo, "Sara"), headers=demo["headers"]["hr.recruiter"])
    second = _expected_labels(db)
    fake_llm.replies.append(_invite_reply(second))

    res = client.post(_url(demo, "Mehwish"), headers=demo["headers"]["hr.recruiter"])

    assert res.status_code == 201
    assert not set(first) & set(second)


def _send_for_approval(client: TestClient, demo: dict[str, Any], email_id: str) -> str:
    res = client.post(
        f"/api/hr/emails/{email_id}/request-approval", headers=demo["headers"]["hr.recruiter"]
    )
    return str(res.json()["approval_id"])


def test_hr_manager_approves_and_the_candidate_is_emailed(
    client: TestClient,
    demo: dict[str, Any],
    fake_llm: FakeLLMClient,
    fake_mailer: FakeEmailSender,
    db: Session,
) -> None:
    fake_llm.replies.append(_invite_reply(_expected_labels(db)))
    email = client.post(_url(demo, "Sara"), headers=demo["headers"]["hr.recruiter"]).json()
    approval_id = _send_for_approval(client, demo, email["id"])

    # A second invite is refused while this one is with the manager.
    again = client.post(_url(demo, "Sara"), headers=demo["headers"]["hr.recruiter"])
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_invited"
    denied = client.post(
        f"/api/approvals/{approval_id}/approve",
        headers=demo["headers"]["sales.manager"],
        json={"comment": None},
    )
    assert denied.status_code == 403

    client.post(
        f"/api/approvals/{approval_id}/approve",
        headers=demo["headers"]["hr.manager"],
        json={"comment": None},
    )

    [message] = fake_mailer.sent
    assert message.to == "sara.malik@example.com"
    assert "Senior Backend Engineer" in message.subject


def test_a_rejected_invite_frees_its_times(
    client: TestClient, demo: dict[str, Any], fake_llm: FakeLLMClient, db: Session
) -> None:
    fake_llm.replies.append(_invite_reply(_expected_labels(db)))
    email = client.post(_url(demo, "Sara"), headers=demo["headers"]["hr.recruiter"]).json()
    approval_id = _send_for_approval(client, demo, email["id"])

    client.post(
        f"/api/approvals/{approval_id}/reject",
        headers=demo["headers"]["hr.manager"],
        json={"comment": "Wait until the hiring panel is confirmed"},
    )

    db.expire_all()
    held = db.scalars(select(InterviewSlot).where(InterviewSlot.released.is_(False))).all()
    assert held == []


@pytest.mark.skipif(not os.environ.get("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1 and LLM_API_KEY")
def test_live_vultr_copies_every_time_exactly() -> None:
    """The real model's invite lists each code-picked time verbatim."""
    from app.agents.interview_invite import InterviewInviteWriter
    from app.config import get_settings
    from app.llm.vultr import VultrLLMClient
    from app.schemas.outreach import InterviewInviteInput

    settings = get_settings()
    llm = VultrLLMClient(
        base_url=settings.llm_base_url,
        api_key=os.environ["LIVE_LLM_API_KEY"],
        model=settings.llm_model,
    )
    facts = InterviewInviteInput(
        job_title="Senior Backend Engineer",
        matched_skills=["Python", "PostgreSQL", "Docker"],
        slot_options=[label(s) for s in pick_slots(THU_3PM_PKT, [])],
        duration_minutes=45,
        interview_format="video call",
        employer=SELLER_COMPANY,
    )

    draft = InterviewInviteWriter().run(facts, llm)  # raises if a time is missing or changed

    assert all(s in draft.body for s in facts.slot_options)
