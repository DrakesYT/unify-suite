"""Aura's morning brief and quick actions.

Code collects the facts (the same live counts the dashboard shows, plus what waits for this
person). The Brief Writer only words them, and its draft is checked before anyone sees it.
Without a model, or when its draft fails the checks, code writes the brief itself.
"""

from datetime import timedelta

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.agents.brief_writer import BriefWriter
from app.agents.runner import AgentFailed, TaskContext, run_agent
from app.config import OFFICE_UTC_OFFSET_HOURS
from app.llm import LLMClient
from app.models import (
    ApprovalRequest,
    Candidate,
    CandidateScore,
    Job,
    Lead,
    PurchaseRequest,
    Ticket,
    User,
)
from app.models.base import utcnow
from app.models.enums import (
    ApprovalStatus,
    Department,
    JobStatus,
    PurchaseRequestStatus,
    Role,
    Urgency,
)
from app.money import format_minor
from app.schemas.brief import Brief, BriefDraft, BriefFact, BriefInput, QuickAction
from app.services import overview
from app.services.approvals import can_decide
from app.services.authz import can_access
from app.services.dashboard import OPEN_LEADS, OPEN_TICKETS

MAX_FACTS = 8
SHOWN_ITEMS = 4
MAX_ACTIONS = 4
TONE_ORDER = {"alert": 0, "warn": 1, "good": 2, "info": 3}
LINK_DEPARTMENT = {
    "/sales": Department.sales,
    "/payments": Department.finance,
    "/hr": Department.hr,
    "/support": Department.support,
    "/procurement": Department.procurement,
}


def _pending_split(db: Session, user: User) -> tuple[int, int]:
    """(decisions this user may make, decisions waiting for someone else)."""
    pending = list(
        db.scalars(select(ApprovalRequest).where(ApprovalRequest.status == ApprovalStatus.pending))
    )
    mine = sum(can_decide(user, a) for a in pending)
    return mine, len(pending) - mine


def _decisions(n: int) -> str:
    return f"{n} {'decision is' if n == 1 else 'decisions are'}"


def facts(db: Session, user: User) -> list[BriefFact]:
    """What is true right now, most relevant to this person first."""
    data = overview.overview(db)
    mine, others = _pending_split(db, user)
    first: list[tuple[str, str, str]] = []  # text, link, tone
    found: list[tuple[str, str, str]] = []
    if mine:  # said plainly, so the writer cannot mix up whose decision it is
        first.append((f"{_decisions(mine)} waiting for your approval", "/approvals", "warn"))
    if others:
        found.append(
            (f"{_decisions(others)} waiting for another manager (not yours to approve)",
             "/approvals", "info")
        )  # fmt: skip
    for insight in data.insights:
        if insight.link != "/approvals":  # replaced by the two precise lines above
            found.append((insight.text, insight.link, insight.tone))
    if data.crm.pipeline:
        open_deals = sum(s.count for s in data.crm.stages if s.stage in OPEN_LEADS)
        amounts = " + ".join(format_minor(m.amount_minor, m.currency) for m in data.crm.pipeline)
        found.append((f"Open sales pipeline: {amounts} in {open_deals} deals", "/sales", "info"))

    found.sort(key=lambda f: TONE_ORDER[f[2]])  # risks before good news before plain info
    if user.role == Role.manager:  # a manager's own department comes next
        found.sort(key=lambda f: LINK_DEPARTMENT.get(f[1]) != user.department)
    return [
        BriefFact(id=i + 1, text=text, link=link, tone=tone)  # type: ignore[arg-type]
        for i, (text, link, tone) in enumerate((first + found)[:MAX_FACTS])
    ]


def focus(user: User) -> str:
    """Tell the writer what matters to this reader, so the model does not have to guess."""
    if user.role == Role.manager:
        return (
            f"Manages {user.department}: put decisions waiting for their approval and "
            f"{user.department} facts first, then anything company-wide that is urgent."
        )
    if user.role == Role.executive:
        return "Oversees the whole company and approves nothing directly: lead with the risks."
    return "Administers the system: lead with what is waiting and what failed."


def _sentence_case(text: str) -> str:
    """'Open sales pipeline' → 'open sales pipeline', but 'PO-2001 is late' stays as it is."""
    first = text.split(" ", 1)[0]
    return (
        text if not first[:1].isupper() or not first[1:].islower() else text[0].lower() + text[1:]
    )


def code_brief(items: list[BriefFact]) -> BriefDraft:
    """The brief when no model is available: the top fact as headline, the next two as summary."""
    if not items:
        return BriefDraft(headline="All clear today", summary="Nothing is waiting on you.", top=[])
    rest = [_sentence_case(f.text) for f in items[1:3]]
    summary = ("Also: " + "; ".join(rest) + ".") if rest else "Nothing else needs a look."
    return BriefDraft(headline=items[0].text[:90], summary=summary, top=[f.id for f in items[:3]])


def morning_brief(db: Session, llm: LLMClient | None, user: User) -> Brief:
    items = facts(db, user)
    draft, written_by = code_brief(items), "code"
    if llm is not None and items:
        local_day = utcnow() + timedelta(hours=OFFICE_UTC_OFFSET_HOURS)
        data = BriefInput(
            first_name=user.full_name.split()[0],
            role=user.role,
            department=user.department,
            weekday=local_day.strftime("%A"),
            focus=focus(user),
            facts=items,
        )
        try:
            draft = run_agent(db, BriefWriter(user.department), data, llm, TaskContext(actor=user))
            written_by = "model"
        except AgentFailed:
            pass  # every attempt is in the Command Center; the reader still gets a brief
    by_id = {f.id: f for f in items}
    ranked = [by_id[i] for i in draft.top] + [f for f in items if f.id not in draft.top]
    return Brief(
        headline=draft.headline,
        summary=draft.summary,
        items=ranked[:SHOWN_ITEMS],
        written_by=written_by,  # type: ignore[arg-type]
        model=getattr(llm, "model", None) if written_by == "model" else None,
    )


def quick_actions(db: Session, user: User) -> list[QuickAction]:
    """Shortcuts built from real records: each asks Aura about one, or opens a page."""
    actions = []
    mine, _ = _pending_split(db, user)
    actions.append(
        QuickAction(
            kind="open",
            icon="approvals",
            label="Review approvals",
            detail=f"{mine} waiting for you" if mine else "nothing waiting for you",
            link="/approvals",
        )
    )

    def readable(department: Department) -> bool:
        return can_access(user, department, write=False)

    if readable(Department.sales):
        lead = db.scalar(
            select(Lead)
            .where(Lead.status.in_(OPEN_LEADS))
            .order_by(Lead.rating.is_not(None), Lead.value_minor.desc())
            .limit(1)
        )
        if lead:
            actions.append(
                QuickAction(
                    kind="ask",
                    icon="lead",
                    label="Qualify a lead",
                    detail=lead.company,
                    prompt=f"Is the {lead.company} lead worth chasing?",
                )
            )
    if readable(Department.hr):
        job = db.scalar(
            select(Job).where(Job.status == JobStatus.open).order_by(Job.created_at.desc()).limit(1)
        )
        if job and db.scalar(select(Candidate.id).limit(1)):
            screened = db.scalar(
                select(CandidateScore.id).where(CandidateScore.job_id == job.id).limit(1)
            )
            actions.append(
                QuickAction(
                    kind="ask",
                    icon="hiring",
                    label="Rank applicants" if screened is None else "Top applicants",
                    detail=job.title,
                    prompt=f"Rank the applicants for {job.title}",
                )
            )
    if readable(Department.procurement):
        request = db.scalar(
            select(PurchaseRequest)
            .where(PurchaseRequest.status == PurchaseRequestStatus.pending)
            .order_by(PurchaseRequest.created_at.desc())
            .limit(1)
        )
        if request:
            actions.append(
                QuickAction(
                    kind="ask",
                    icon="supplier",
                    label="Compare suppliers",
                    detail=request.item,
                    prompt=f"Which supplier should we buy the {request.item} from?",
                )
            )
    if readable(Department.support) and len(actions) < MAX_ACTIONS:
        rank = case(
            (Ticket.urgency == Urgency.critical, 0), (Ticket.urgency == Urgency.high, 1), else_=2
        )
        ticket = db.scalar(
            select(Ticket).where(Ticket.status.in_(OPEN_TICKETS)).order_by(rank).limit(1)
        )
        if ticket:
            actions.append(
                QuickAction(
                    kind="ask",
                    icon="ticket",
                    label="Investigate ticket",
                    detail=ticket.title,
                    prompt=f"Investigate the ticket '{ticket.title}'",
                )
            )
    return actions[:MAX_ACTIONS]
