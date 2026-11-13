"""Leads (FR-SAL-01) and their qualification (FR-SAL-02)."""

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.agents.lead_qualifier import LeadQualifier
from app.agents.runner import TaskContext, call_tool, run_agent
from app.errors import ApiError
from app.llm import LLMClient
from app.models import CallTranscript, Lead, OutboundEmail, User
from app.models.base import utcnow
from app.models.enums import LeadRating, LeadStatus, Role
from app.money import format_minor
from app.schemas.sales import (
    LeadCreate,
    LeadForQualification,
    LeadUpdate,
    QualificationResult,
    SalesSummary,
    StageSummary,
    WeekSummary,
)
from app.services import audit, company_settings
from app.services.pagination import paginate

AGENT = LeadQualifier()
SUMMARY_WEEKS = 8


def list_leads(
    db: Session,
    limit: int,
    cursor: str | None,
    status: LeadStatus | None = None,
    rating: LeadRating | None = None,
) -> tuple[list[Lead], str | None]:
    stmt = select(Lead)
    if status:
        stmt = stmt.where(Lead.status == status)
    if rating:
        stmt = stmt.where(Lead.rating == rating)
    return paginate(db, stmt, Lead, limit, cursor)


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_of(moment: datetime) -> date:
    """Monday of the UTC week `moment` falls in. Weeks are counted in UTC, like the chart's start:
    a database session in another time zone must not move a late-Sunday lead into next week."""
    return _week_start(moment.astimezone(UTC).date())


def summary(db: Session, today: date | None = None) -> SalesSummary:
    """Funnel stages plus eight weeks of new and won leads (status has no history: 'won' uses the
    lead's last update). Values are summed in the most common lead currency, USD when empty."""
    today = today or utcnow().date()
    first = _week_start(today) - timedelta(weeks=SUMMARY_WEEKS - 1)
    since = datetime.combine(first, time.min, tzinfo=UTC)

    currency = (
        db.scalar(
            select(Lead.currency).group_by(Lead.currency).order_by(func.count().desc()).limit(1)
        )
        or "USD"
    )
    counts = {s: 0 for s in LeadStatus}
    values = {s: 0 for s in LeadStatus}
    for status, cur, n, total in db.execute(
        select(
            Lead.status, Lead.currency, func.count(), func.coalesce(func.sum(Lead.value_minor), 0)
        ).group_by(Lead.status, Lead.currency)
    ):
        counts[status] += n
        if cur == currency:
            values[status] += int(total)

    weeks = {first + timedelta(weeks=i): [0, 0, 0, 0] for i in range(SUMMARY_WEEKS)}
    recent = select(Lead.status, Lead.currency, Lead.value_minor, Lead.created_at, Lead.updated_at)
    for status, cur, value, created, updated in db.execute(
        recent.where(or_(Lead.created_at >= since, Lead.updated_at >= since))
    ):
        in_currency = cur == currency
        if created >= since:
            row = weeks[week_of(created)]
            row[0] += 1
            row[1] += value if in_currency else 0
        if status == LeadStatus.won and updated >= since:
            row = weeks[week_of(updated)]
            row[2] += 1
            row[3] += value if in_currency else 0
    return SalesSummary(
        currency=currency,
        stages=[StageSummary(stage=s, count=counts[s], value_minor=values[s]) for s in LeadStatus],
        weeks=[
            WeekSummary(
                week_start=start, new_leads=r[0], new_value_minor=r[1], won=r[2], won_minor=r[3]
            )
            for start, r in weeks.items()
        ],
        target=company_settings.quarter_target(db, today),
    )


def get_lead(db: Session, lead_id: uuid.UUID) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise ApiError(404, "not_found", "Lead not found")
    return lead


OPEN = (LeadStatus.new, LeadStatus.contacted, LeadStatus.qualified)


def create_lead(db: Session, data: LeadCreate, actor: User) -> Lead:
    existing = db.scalar(
        select(Lead).where(func.lower(Lead.email) == data.email.lower(), Lead.status.in_(OPEN))
    )
    if existing is not None:  # the same contact twice would be chased twice
        raise ApiError(
            409,
            "duplicate_lead",
            f"There is already an open lead for {existing.email} ({existing.company})",
        )
    lead = Lead(**data.model_dump(), owner_id=actor.id)
    db.add(lead)
    db.flush()
    audit.record(db, action="lead.created", entity="lead", entity_id=lead.id, actor_id=actor.id)
    db.commit()
    return lead


def update_lead(db: Session, lead_id: uuid.UUID, data: LeadUpdate, actor: User) -> Lead:
    lead = get_lead(db, lead_id)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(lead, key, value)
    audit.record(
        db,
        action="lead.updated",
        entity="lead",
        entity_id=lead.id,
        actor_id=actor.id,
        detail={"fields": sorted(changes)},
    )
    db.commit()
    return lead


def delete_lead(db: Session, lead_id: uuid.UUID, actor: User) -> None:
    """Remove a lead entered by mistake (a manager's call). A lead with emails or call
    transcripts has history worth keeping: mark it lost instead."""
    if actor.role not in (Role.manager, Role.admin):
        raise ApiError(403, "forbidden", "Only a sales manager can delete a lead")
    lead = get_lead(db, lead_id)
    has_history = db.scalar(
        select(OutboundEmail.id).where(OutboundEmail.lead_id == lead.id).limit(1)
    ) or db.scalar(select(CallTranscript.id).where(CallTranscript.lead_id == lead.id).limit(1))
    if has_history:
        raise ApiError(
            409, "lead_has_history", "This lead has emails or calls on file; mark it lost instead"
        )
    audit.record(
        db,
        action="lead.deleted",
        entity="lead",
        entity_id=lead.id,
        actor_id=actor.id,
        detail={"company": lead.company, "status": lead.status},
    )
    db.delete(lead)
    db.commit()


def _for_agent(lead: Lead) -> LeadForQualification:
    return LeadForQualification(
        company=lead.company,
        email_domain=lead.email.rsplit("@", 1)[-1],
        status=lead.status,
        priority=lead.priority,
        value=format_minor(lead.value_minor, lead.currency),
        notes=lead.notes,
    )


def qualify_lead(db: Session, llm: LLMClient, lead_id: uuid.UUID, ctx: TaskContext) -> Lead:
    lead = get_lead(db, lead_id)
    facts = call_tool(
        db, AGENT, "get_lead", {"lead_id": str(lead.id)}, lambda: _for_agent(lead), ctx
    )
    result: QualificationResult = run_agent(db, AGENT, facts, llm, ctx)

    def _save() -> dict[str, str]:
        lead.rating = result.rating
        lead.qualification = result.model_dump(mode="json") | {
            "model": llm.model,
            "qualified_at": utcnow().isoformat(),
        }
        audit.record(
            db,
            action="lead.qualified",
            entity="lead",
            entity_id=lead.id,
            actor_id=ctx.actor.id,
            detail={"rating": result.rating},
        )
        return {"rating": result.rating}

    call_tool(db, AGENT, "update_lead_status", {"lead_id": str(lead.id)}, _save, ctx)
    return lead
