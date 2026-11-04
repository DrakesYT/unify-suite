"""Leads (FR-SAL-01) and their qualification (FR-SAL-02)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.lead_qualifier import LeadQualifier
from app.agents.runner import TaskContext, call_tool, run_agent
from app.errors import ApiError
from app.llm import LLMClient
from app.models import Lead, User
from app.models.base import utcnow
from app.models.enums import LeadRating, LeadStatus
from app.money import format_minor
from app.schemas.sales import LeadCreate, LeadForQualification, LeadUpdate, QualificationResult
from app.services import audit
from app.services.pagination import paginate

AGENT = LeadQualifier()


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


def get_lead(db: Session, lead_id: uuid.UUID) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise ApiError(404, "not_found", "Lead not found")
    return lead


def create_lead(db: Session, data: LeadCreate, actor: User) -> Lead:
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
