"""Interview invitations: code decides who qualifies and which times are free; the Interview
Invite Writer only drafts. Approval and sending are shared (services/outbound.py)."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.interview_invite import InterviewInviteWriter
from app.agents.runner import TaskContext, call_tool, run_agent
from app.config import INTERVIEW_MIN_SCORE, INTERVIEW_MINUTES, SELLER_COMPANY
from app.errors import ApiError
from app.llm import LLMClient
from app.models import (
    ApprovalRequest,
    Candidate,
    CandidateScore,
    InterviewSlot,
    Job,
    OutboundEmail,
    User,
)
from app.models.base import utcnow
from app.models.enums import ApprovalStatus, Department, EmailStatus, JobStatus
from app.scheduling import label, pick_slots
from app.schemas.hr import SlotOut
from app.schemas.outreach import EmailDraft, InterviewInviteInput
from app.services import audit, outbound

WRITER = InterviewInviteWriter()
KIND = "interview_invite"
FORMAT = "video call"


def _eligible(
    db: Session, job_id: uuid.UUID, candidate_id: uuid.UUID
) -> tuple[Job, Candidate, CandidateScore]:
    job = db.get(Job, job_id)
    candidate = db.get(Candidate, candidate_id)
    if job is None or candidate is None:
        raise ApiError(404, "not_found", "Job or candidate not found")
    if job.status != JobStatus.open:
        raise ApiError(409, "job_closed", "This job is closed")
    score = db.scalar(
        select(CandidateScore).where(
            CandidateScore.job_id == job.id, CandidateScore.candidate_id == candidate.id
        )
    )
    if score is None:
        raise ApiError(409, "not_screened", "Screen this candidate for the job first")
    if score.score < INTERVIEW_MIN_SCORE:
        raise ApiError(
            409, "score_too_low", f"Only candidates scoring {INTERVIEW_MIN_SCORE}+ are invited"
        )
    if not candidate.email:
        raise ApiError(409, "no_candidate_email", f"{candidate.name} has no email address on file")
    return job, candidate, score


def _held(db: Session, job_id: uuid.UUID, candidate_id: uuid.UUID) -> list[InterviewSlot]:
    return list(
        db.scalars(
            select(InterviewSlot).where(
                InterviewSlot.job_id == job_id,
                InterviewSlot.candidate_id == candidate_id,
                InterviewSlot.released.is_(False),
            )
        )
    )


def _release_unsent(db: Session, job_id: uuid.UUID, candidate_id: uuid.UUID) -> None:
    """A new draft replaces an unsent one; an invite already with a manager or sent blocks it."""
    for slot in _held(db, job_id, candidate_id):
        email = db.get(OutboundEmail, slot.email_id) if slot.email_id else None
        if email is not None and email.status not in (EmailStatus.draft, EmailStatus.failed):
            raise ApiError(409, "already_invited", "This candidate already has an invite out")
        slot.released = True


def _free_slots(db: Session, now: datetime) -> list[datetime]:
    busy = db.execute(
        select(InterviewSlot.starts_at, InterviewSlot.ends_at).where(
            InterviewSlot.released.is_(False), InterviewSlot.ends_at > now
        )
    ).all()
    return pick_slots(now, [(s, e) for s, e in busy])


def compose_body(candidate: Candidate, draft: EmailDraft, sender: User) -> str:
    first_name = candidate.name.split()[0]
    return (
        f"Dear {first_name},\n\n{draft.body}\n\n"
        f"Best regards,\n{sender.full_name}\nTalent team, {SELLER_COMPANY}"
    )


def draft_invite(
    db: Session, llm: LLMClient, job_id: uuid.UUID, candidate_id: uuid.UUID, ctx: TaskContext
) -> OutboundEmail:
    job, candidate, score = _eligible(db, job_id, candidate_id)
    _release_unsent(db, job.id, candidate.id)
    starts = call_tool(
        db,
        WRITER,
        "find_free_slots",
        {"job_id": str(job.id), "candidate_id": str(candidate.id)},
        lambda: _free_slots(db, utcnow()),
        ctx,
    )
    if not starts:
        raise ApiError(409, "no_free_slots", "No free interview times in the next three weeks")
    facts = call_tool(
        db,
        WRITER,
        "get_candidate",
        {"candidate_id": str(candidate.id)},
        lambda: InterviewInviteInput(
            job_title=job.title,
            matched_skills=[e["requirement"] for e in score.evidence][:5],
            slot_options=[label(s) for s in starts],
            duration_minutes=INTERVIEW_MINUTES,
            interview_format=FORMAT,
            employer=SELLER_COMPANY,
        ),
        ctx,
    )
    draft: EmailDraft = run_agent(db, WRITER, facts, llm, ctx)

    def _save() -> OutboundEmail:
        email = outbound.new_draft(
            db,
            kind=KIND,
            department=Department.hr,
            to_address=candidate.email or "",
            subject=draft.subject,
            body=compose_body(candidate, draft, ctx.actor),
            actor=ctx.actor,
            model=llm.model,
            candidate_id=candidate.id,
            job_id=job.id,
        )
        for start in starts:
            db.add(
                InterviewSlot(
                    candidate_id=candidate.id,
                    job_id=job.id,
                    starts_at=start,
                    ends_at=start + timedelta(minutes=INTERVIEW_MINUTES),
                    email_id=email.id,
                )
            )
        audit.record(
            db,
            action="interview.slots_held",
            entity="candidate",
            entity_id=candidate.id,
            actor_id=ctx.actor.id,
            detail={"job_id": str(job.id), "slots": [s.isoformat() for s in starts]},
        )
        return email

    return call_tool(
        db, WRITER, "save_email_draft", {"candidate_id": str(candidate.id)}, _save, ctx
    )


def list_for(db: Session, job_id: uuid.UUID, candidate_id: uuid.UUID) -> list[OutboundEmail]:
    stmt = (
        select(OutboundEmail)
        .where(OutboundEmail.job_id == job_id, OutboundEmail.candidate_id == candidate_id)
        .order_by(OutboundEmail.created_at.desc())
    )
    return list(db.scalars(stmt))


def request_approval(db: Session, email_id: uuid.UUID, actor: User) -> OutboundEmail:
    email = outbound.get_email(db, email_id, Department.hr)
    candidate = db.get(Candidate, email.candidate_id) if email.candidate_id else None
    job = db.get(Job, email.job_id) if email.job_id else None
    context = {
        "candidate_id": str(email.candidate_id) if email.candidate_id else None,
        "job_title": job.title if job else None,
        "company": candidate.name if candidate else None,
    }
    return outbound.request_approval(db, email_id, Department.hr, actor, context)


def release_if_rejected(db: Session, approval: ApprovalRequest) -> None:
    """A rejected invite frees its times for other candidates."""
    if approval.action != outbound.ACTION or approval.status != ApprovalStatus.rejected:
        return
    email_id = uuid.UUID(approval.payload["email_id"])
    slots = db.scalars(select(InterviewSlot).where(InterviewSlot.email_id == email_id)).all()
    for slot in slots:
        slot.released = True
    if slots:
        db.commit()


# --- the candidate answered: keep the chosen time, free the others -----------------------------


def _invite(db: Session, email_id: uuid.UUID) -> OutboundEmail:
    email = outbound.get_email(db, email_id, Department.hr)
    if email.kind != KIND:
        raise ApiError(404, "not_found", "Interview invitation not found")
    return email


def _offered(db: Session, email_id: uuid.UUID) -> list[InterviewSlot]:
    return list(
        db.scalars(
            select(InterviewSlot)
            .where(InterviewSlot.email_id == email_id)
            .order_by(InterviewSlot.starts_at)
        )
    )


def slots_out(db: Session, email_id: uuid.UUID) -> list[SlotOut]:
    """The times still held for an invitation. Exactly one left means it is booked."""
    email = _invite(db, email_id)
    held = [s for s in _offered(db, email.id) if not s.released]
    return [
        SlotOut(
            id=s.id,
            starts_at=s.starts_at,
            ends_at=s.ends_at,
            label=label(s.starts_at),
            booked=len(held) == 1 and email.status == EmailStatus.sent,
        )
        for s in held
    ]


def book_slot(db: Session, email_id: uuid.UUID, slot_id: uuid.UUID, actor: User) -> list[SlotOut]:
    """The candidate replied with a time: that one stays held, the others are free for other
    candidates again. Only a sent invitation can be answered."""
    email = _invite(db, email_id)
    if email.status != EmailStatus.sent:
        raise ApiError(409, "not_sent", "The invitation has not been sent yet")
    held = [s for s in _offered(db, email.id) if not s.released]
    chosen = next((s for s in held if s.id == slot_id), None)
    if chosen is None:
        raise ApiError(404, "not_found", "That time is not one of the times offered")
    if len(held) == 1:
        raise ApiError(409, "already_booked", "This interview is already booked")
    for slot in held:
        slot.released = slot.id != chosen.id
    audit.record(
        db,
        action="interview.booked",
        entity="candidate",
        entity_id=chosen.candidate_id,
        actor_id=actor.id,
        detail={"job_id": str(chosen.job_id), "starts_at": chosen.starts_at.isoformat()},
    )
    db.commit()
    return slots_out(db, email_id)
