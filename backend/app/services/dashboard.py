"""Executive dashboard (FR-DASH-01 KPIs, FR-DASH-02 recent activity) — plain SQL aggregates."""

from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AgentTask,
    ApprovalRequest,
    AuditLog,
    Invoice,
    Job,
    Lead,
    PurchaseRequest,
    Ticket,
    User,
)
from app.models.base import utcnow
from app.models.enums import (
    ApprovalStatus,
    InvoiceStatus,
    JobStatus,
    LeadStatus,
    PurchaseRequestStatus,
    TaskStatus,
    TicketStatus,
)
from app.schemas.dashboard import ActivityItem, Charts, Count, DayCount, Kpis, Money

FEED_SIZE = 20
CHART_DAYS = 7
OPEN_LEADS = (LeadStatus.new, LeadStatus.contacted, LeadStatus.qualified)
UNPAID = (InvoiceStatus.received, InvoiceStatus.needs_review, InvoiceStatus.approved)
OPEN_TICKETS = (TicketStatus.open, TicketStatus.investigating, TicketStatus.escalated)


def _sum_by_currency(db: Session, amount, currency, *where) -> list[Money]:  # type: ignore[no-untyped-def]
    rows = db.execute(
        select(currency, func.coalesce(func.sum(amount), 0))
        .where(*where)
        .group_by(currency)
        .order_by(currency)
    ).all()
    return [Money(currency=c, amount_minor=int(total)) for c, total in rows]


def _count(db: Session, model, *where) -> int:  # type: ignore[no-untyped-def]
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def kpis(db: Session) -> Kpis:
    return Kpis(
        sales_pipeline=_sum_by_currency(
            db, Lead.value_minor, Lead.currency, Lead.status.in_(OPEN_LEADS)
        ),
        unpaid_invoices=_sum_by_currency(
            db, Invoice.amount_minor, Invoice.currency, Invoice.status.in_(UNPAID)
        ),
        open_vacancies=_count(db, Job, Job.status == JobStatus.open),
        open_tickets=_count(db, Ticket, Ticket.status.in_(OPEN_TICKETS)),
        pending_purchase_requests=_count(
            db, PurchaseRequest, PurchaseRequest.status == PurchaseRequestStatus.pending
        ),
        pending_approvals=_count(
            db, ApprovalRequest, ApprovalRequest.status == ApprovalStatus.pending
        ),
    )


def _grouped(db: Session, column, missing: str) -> list[Count]:  # type: ignore[no-untyped-def]
    rows = db.execute(select(column, func.count()).group_by(column)).all()
    counts = [Count(label=str(label) if label else missing, value=n) for label, n in rows]
    return sorted(counts, key=lambda c: (-c.value, c.label))


def charts(db: Session) -> Charts:
    """Small breakdowns for the dashboard, plus agent calls per day for the last week."""
    days = [(utcnow().date() - timedelta(days=n)) for n in reversed(range(CHART_DAYS))]
    start = datetime.combine(days[0], time.min, tzinfo=UTC)
    per_day = {d.isoformat(): {"succeeded": 0, "failed": 0} for d in days}
    tasks = db.execute(
        select(AgentTask.created_at, AgentTask.status).where(AgentTask.created_at >= start)
    )
    for created_at, status in tasks:
        bucket = per_day.get(created_at.date().isoformat())
        if bucket is not None and status in (TaskStatus.succeeded, TaskStatus.failed):
            bucket[status] += 1
    return Charts(
        leads_by_rating=_grouped(db, Lead.rating, "unrated"),
        tickets_by_category=_grouped(db, Ticket.category, "unclassified"),
        invoices_by_match=_grouped(db, Invoice.match_status, "unmatched"),
        agent_calls_by_day=[DayCount(day=day, **counts) for day, counts in per_day.items()],
    )


def recent_activity(db: Session, limit: int = FEED_SIZE) -> list[ActivityItem]:
    rows = db.execute(
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .order_by(AuditLog.at.desc(), AuditLog.id.desc())
        .limit(limit)
    ).all()
    return [
        ActivityItem(
            id=log.id,
            at=log.at,
            actor_name=name,
            action=log.action,
            entity=log.entity,
            entity_id=log.entity_id,
            detail=log.detail,
        )
        for log, name in rows
    ]
