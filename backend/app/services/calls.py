"""Call transcripts for sales leads and support tickets, and their analysis.

A transcript is saved as an upload (the same checks as every file), linked to exactly one lead or
ticket, and analysed by the Call Analyzer right away. If the model fails, the transcript is kept
and can be analysed again. Nothing on the lead or ticket changes because of a call: action items
are suggestions for people.
"""

import re
import uuid
from collections import defaultdict
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.call_analyzer import CallAnalyzer
from app.agents.runner import AgentFailed, TaskContext, call_tool, run_agent
from app.errors import ApiError
from app.llm import LLMClient
from app.models import CallTranscript, Lead, Ticket, Upload, User
from app.models.base import utcnow
from app.models.enums import Department
from app.safety import find_instruction_text
from app.schemas.calls import CallAnalysis, CallInput, CallOut, SpeakerShare
from app.services import audit
from app.services.authz import can_access
from app.services.uploads import read_text, save_upload

TITLE_MAX = 200
ERROR_MAX = 300
# "Agent: Hi Bilal" → speaker "Agent". Header lines like "Date: ..." are not speakers.
_SPEAKER_LINE = re.compile(r"^\s*([A-Za-z][\w .'-]{0,40}?)\s*:\s+(\S.*)$")
_HEADERS = {"call", "date", "duration", "time", "subject", "participants", "kit note", "note"}
_CALL_TITLE = re.compile(r"^\s*call\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def speakers(text: str) -> list[SpeakerShare]:
    """Talk share by words, counted by code. Empty unless at least two speakers are labelled."""
    turns: dict[str, int] = defaultdict(int)
    words: dict[str, int] = defaultdict(int)
    for line in text.splitlines():
        match = _SPEAKER_LINE.match(line)
        if not match or match.group(1).strip().lower() in _HEADERS:
            continue
        name = match.group(1).strip()
        turns[name] += 1
        words[name] += len(match.group(2).split())
    total = sum(words.values())
    if len(words) < 2 or not total:
        return []
    return [
        SpeakerShare(speaker=n, turns=turns[n], words=w, share_pct=round(100 * w / total))
        for n, w in sorted(words.items(), key=lambda item: -item[1])
    ]


def _title(text: str, file_name: str, given: str | None) -> str:
    if given and given.strip():
        return given.strip()[:TITLE_MAX]
    found = _CALL_TITLE.search(text)
    if found:
        return found.group(1).strip()[:TITLE_MAX]
    return PurePath(file_name).stem[:TITLE_MAX] or "Call"


def _department(db: Session, lead_id: uuid.UUID | None, ticket_id: uuid.UUID | None) -> Department:
    """Check the lead or ticket exists; its department owns the call."""
    if (lead_id is None) == (ticket_id is None):
        raise ApiError(422, "lead_or_ticket", "Link the call to exactly one lead or one ticket")
    record = db.get(Lead, lead_id) if lead_id else db.get(Ticket, ticket_id)
    if record is None:
        raise ApiError(404, "not_found", "Lead not found" if lead_id else "Ticket not found")
    return Department.sales if lead_id else Department.support


def _require(user: User, department: Department, *, write: bool) -> None:
    if not can_access(user, department, write=write):
        raise ApiError(403, "forbidden", f"No access to {department} calls")


def context_line(db: Session, call: CallTranscript) -> str:
    """The one line of context the Call Analyzer gets (also rebuilt by the Why? panel)."""
    if call.lead_id:
        lead = db.get(Lead, call.lead_id)
        assert lead is not None
        return f"Sales lead: {lead.company} (status: {lead.status})"
    ticket = db.get(Ticket, call.ticket_id)
    assert ticket is not None
    return f"Support ticket: {ticket.title} (status: {ticket.status})"


def to_out(db: Session, call: CallTranscript) -> CallOut:
    upload = db.get(Upload, call.upload_id)
    assert upload is not None
    text = read_text(upload)
    return CallOut(
        id=call.id,
        title=call.title,
        department=call.department,
        lead_id=call.lead_id,
        ticket_id=call.ticket_id,
        file_name=upload.original_name,
        transcript=text,
        speakers=speakers(text),
        analysis=CallAnalysis.model_validate(call.analysis) if call.analysis else None,
        analyzed_by_model=call.analyzed_by_model,
        analyzed_at=call.analyzed_at,
        analysis_error=call.analysis_error,
        suspicious_text=find_instruction_text(text),
        created_at=call.created_at,
    )


def get_call(db: Session, user: User, call_id: uuid.UUID) -> CallTranscript:
    call = db.get(CallTranscript, call_id)
    if call is None:
        raise ApiError(404, "not_found", "Call not found")
    _require(user, call.department, write=False)
    return call


def list_calls(
    db: Session, user: User, lead_id: uuid.UUID | None, ticket_id: uuid.UUID | None
) -> list[CallTranscript]:
    department = _department(db, lead_id, ticket_id)
    _require(user, department, write=False)
    column = CallTranscript.lead_id if lead_id else CallTranscript.ticket_id
    return list(
        db.scalars(
            select(CallTranscript)
            .where(column == (lead_id or ticket_id))
            .order_by(CallTranscript.created_at.desc())
        )
    )


def add_call(
    db: Session,
    llm: LLMClient,
    user: User,
    *,
    file_name: str,
    data: bytes,
    lead_id: uuid.UUID | None,
    ticket_id: uuid.UUID | None,
    title: str | None,
) -> CallTranscript:
    """Save the transcript (same upload checks as any file), then analyse it."""
    department = _department(db, lead_id, ticket_id)
    _require(user, department, write=True)
    upload = save_upload(db, filename=file_name, data=data, department=department, actor=user)
    call = CallTranscript(
        title=_title(read_text(upload), upload.original_name, title),
        department=department,
        lead_id=lead_id,
        ticket_id=ticket_id,
        upload_id=upload.id,
        created_by_id=user.id,
    )
    db.add(call)
    db.flush()
    audit.record(
        db,
        action="call.added",
        entity="call_transcript",
        entity_id=call.id,
        actor_id=user.id,
        detail={
            "lead_id": str(lead_id) if lead_id else None,
            "ticket_id": str(ticket_id) if ticket_id else None,
        },
    )
    db.commit()
    return analyze(db, llm, user, call.id)


def analyze(db: Session, llm: LLMClient, user: User, call_id: uuid.UUID) -> CallTranscript:
    call = get_call(db, user, call_id)
    _require(user, call.department, write=True)
    agent = CallAnalyzer(call.department)
    ctx = TaskContext(actor=user)
    upload = db.get(Upload, call.upload_id)
    assert upload is not None
    text = call_tool(
        db, agent, "read_upload", {"upload_id": str(upload.id)}, lambda: read_text(upload), ctx
    )
    context = call_tool(
        db,
        agent,
        "get_call_context",
        {"call_id": str(call.id)},
        lambda: context_line(db, call),
        ctx,
    )
    data = CallInput(context=context, transcript=text)
    try:
        result = run_agent(db, agent, data, llm, ctx)
    except AgentFailed as exc:
        call.analysis_error = exc.message[:ERROR_MAX]
        db.commit()  # the transcript stays; "Analyse again" retries
        return call

    def _save() -> dict[str, str | int]:
        call.analysis = result.model_dump(mode="json")
        call.analyzed_by_model = getattr(llm, "model", None)
        call.analyzed_at = utcnow()
        call.analysis_error = None
        audit.record(
            db,
            action="call.analyzed",
            entity="call_transcript",
            entity_id=call.id,
            actor_id=user.id,
            detail={"sentiment": result.sentiment, "action_items": len(result.action_items)},
        )
        return {"sentiment": result.sentiment, "action_items": len(result.action_items)}

    call_tool(db, agent, "save_call_analysis", {"call_id": str(call.id)}, _save, ctx)
    return call
