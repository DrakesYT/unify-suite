"""Dashboard overview: every panel of the executive dashboard in one read.

Everything here is counted and worded by plain code from live rows; no model is involved, so a
number on the dashboard is always one you can find again on the department page.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import (
    AgentTask,
    ApprovalRequest,
    Candidate,
    CandidateScore,
    Customer,
    Invoice,
    Job,
    Lead,
    OutboundEmail,
    PurchaseOrder,
    Ticket,
    Vendor,
)
from app.models.base import utcnow
from app.models.enums import (
    ApprovalStatus,
    EmailStatus,
    InvoiceStatus,
    JobStatus,
    LeadRating,
    LeadStatus,
    PurchaseOrderStatus,
    TaskStatus,
    Urgency,
)
from app.money import format_minor
from app.schemas.dashboard import (
    AgentHealth,
    Count,
    Crm,
    Deal,
    DealStage,
    Hiring,
    HiringCard,
    HiringStage,
    Insight,
    InvoiceRow,
    LateDelivery,
    Money,
    MoneyPanel,
    Overview,
    ReceivableRow,
    SupportPanel,
    TicketRow,
)
from app.services import company_settings, interviews, receivables
from app.services.dashboard import OPEN_LEADS, OPEN_TICKETS, UNPAID

CARDS_PER_STAGE = 6
TREND_DAYS = 14
TOP_DEALS = 5
TICKET_ROWS = 6
INVOICE_ROWS = 5
OVERDUE_ROWS = 3
LATE_ROWS = 3
MAX_INSIGHTS = 6

STAGE_ORDER = ("applied", "screened", "invite_pending", "invite_sent")
URGENCY_RANK = {Urgency.critical: 0, Urgency.high: 1, Urgency.normal: 2, Urgency.low: 3}


def _money(totals: dict[str, int]) -> list[Money]:
    return [Money(currency=c, amount_minor=a) for c, a in sorted(totals.items())]


def _money_text(values: list[Money]) -> str:
    return " + ".join(format_minor(v.amount_minor, v.currency) for v in values)


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


# --- Hiring -------------------------------------------------------------------------------------


def _invite_stage(status: EmailStatus) -> str | None:
    if status == EmailStatus.sent:
        return "invite_sent"
    if status in (EmailStatus.draft, EmailStatus.pending_approval):
        return "invite_pending"
    return None  # rejected or failed: the candidate is back to "screened"


def hiring(db: Session, today: date) -> Hiring:
    """Each candidate sits in the furthest stage their records prove: applied (resume in),
    screened (scored against a job), invite awaiting approval, invite sent."""
    best: dict[uuid.UUID, tuple[int, str]] = {}
    for score, job_title, candidate_id in db.execute(
        select(CandidateScore.score, Job.title, CandidateScore.candidate_id).join(
            Job, Job.id == CandidateScore.job_id
        )
    ):
        if candidate_id not in best or score > best[candidate_id][0]:
            best[candidate_id] = (score, job_title)

    invite: dict[uuid.UUID, tuple[str, str | None]] = {}
    for candidate_id, status, job_title in db.execute(
        select(OutboundEmail.candidate_id, OutboundEmail.status, Job.title)
        .outerjoin(Job, Job.id == OutboundEmail.job_id)
        .where(OutboundEmail.kind == interviews.KIND, OutboundEmail.candidate_id.is_not(None))
    ):
        stage = _invite_stage(status)
        if stage and (
            candidate_id not in invite
            or STAGE_ORDER.index(stage) > STAGE_ORDER.index(invite[candidate_id][0])
        ):
            invite[candidate_id] = (stage, job_title)

    columns: dict[str, list[HiringCard]] = {s: [] for s in STAGE_ORDER}
    for candidate in db.scalars(select(Candidate)):
        score, scored_job = best.get(candidate.id, (None, None))
        if candidate.id in invite:
            stage, job_title = invite[candidate.id]
        else:
            stage, job_title = ("screened" if score is not None else "applied"), scored_job
        columns[stage].append(
            HiringCard(
                candidate_id=candidate.id, name=candidate.name, job_title=job_title, score=score
            )
        )

    start = today - timedelta(days=TREND_DAYS - 1)
    per_day = {(start + timedelta(days=n)).isoformat(): 0 for n in range(TREND_DAYS)}
    since = datetime.combine(start, time.min, tzinfo=UTC)
    for (created_at,) in db.execute(
        select(Candidate.created_at).where(Candidate.created_at >= since)
    ):
        key = created_at.date().isoformat()
        if key in per_day:
            per_day[key] += 1

    return Hiring(
        open_jobs=db.scalar(
            select(func.count()).select_from(Job).where(Job.status == JobStatus.open)
        )
        or 0,
        stages=[
            HiringStage(
                stage=stage,  # type: ignore[arg-type]  # one of STAGE_ORDER
                count=len(cards),
                cards=sorted(cards, key=lambda c: (-(c.score or -1), c.name))[:CARDS_PER_STAGE],
            )
            for stage, cards in columns.items()
        ],
        applications_by_day=[Count(label=d, value=n) for d, n in per_day.items()],
    )


# --- Sales --------------------------------------------------------------------------------------


def crm(db: Session, today: date) -> Crm:
    counts: dict[str, int] = defaultdict(int)
    values: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    pipeline: dict[str, int] = defaultdict(int)
    for status, currency, n, total in db.execute(
        select(
            Lead.status, Lead.currency, func.count(), func.coalesce(func.sum(Lead.value_minor), 0)
        ).group_by(Lead.status, Lead.currency)
    ):
        counts[status] += n
        values[status][currency] += int(total)
        if status in OPEN_LEADS:
            pipeline[currency] += int(total)

    won, lost = counts[LeadStatus.won], counts[LeadStatus.lost]
    top = db.scalars(
        select(Lead)
        .where(Lead.status.in_(OPEN_LEADS))
        .order_by(Lead.value_minor.desc(), Lead.company)
        .limit(TOP_DEALS)
    )
    return Crm(
        stages=[DealStage(stage=s, count=counts[s], value=_money(values[s])) for s in LeadStatus],
        pipeline=_money(pipeline),
        win_rate=round(100 * won / (won + lost)) if won + lost else None,
        won=won,
        lost=lost,
        target=company_settings.quarter_target(db, today),
        top_deals=[
            Deal(
                lead_id=lead.id,
                company=lead.company,
                contact=lead.name,
                status=lead.status,
                rating=lead.rating,
                amount_minor=lead.value_minor,
                currency=lead.currency,
            )
            for lead in top
        ],
    )


# --- Support ------------------------------------------------------------------------------------


def support(db: Session) -> SupportPanel:
    open_ = Ticket.status.in_(OPEN_TICKETS)
    rank = case(
        *((Ticket.urgency == u, r) for u, r in URGENCY_RANK.items()), else_=len(URGENCY_RANK)
    )
    rows = db.execute(
        select(Ticket, Customer.name)
        .outerjoin(Customer, Customer.id == Ticket.customer_id)
        .where(open_)
        .order_by(rank, Ticket.created_at.desc())
        .limit(TICKET_ROWS)
    ).all()

    def grouped(column, missing: str) -> list[Count]:  # type: ignore[no-untyped-def]
        found = db.execute(select(column, func.count()).where(open_).group_by(column)).all()
        counts = [Count(label=str(v) if v else missing, value=n) for v, n in found]
        return sorted(counts, key=lambda c: (-c.value, c.label))

    by_urgency = {c.label: c for c in grouped(Ticket.urgency, "unrated")}
    return SupportPanel(
        open=db.scalar(select(func.count()).select_from(Ticket).where(open_)) or 0,
        by_urgency=[by_urgency[u] for u in [*map(str, URGENCY_RANK), "unrated"] if u in by_urgency],
        by_category=grouped(Ticket.category, "unclassified"),
        tickets=[
            TicketRow(
                ticket_id=t.id,
                title=t.title,
                customer_name=name,
                category=t.category,
                urgency=t.urgency,
                status=t.status,
                created_at=t.created_at,
            )
            for t, name in rows
        ],
    )


# --- Money: supplier invoices, customer payments, supplier deliveries --------------------------


def money(db: Session) -> MoneyPanel:
    unpaid: dict[str, int] = defaultdict(int)
    by_status: dict[str, int] = defaultdict(int)
    for status, currency, n, total in db.execute(
        select(
            Invoice.status,
            Invoice.currency,
            func.count(),
            func.coalesce(func.sum(Invoice.amount_minor), 0),
        )
        .where(Invoice.status.in_(UNPAID))
        .group_by(Invoice.status, Invoice.currency)
    ):
        unpaid[currency] += int(total)
        by_status[status] += n

    recent = db.execute(
        select(Invoice, Vendor.name)
        .join(Vendor, Vendor.id == Invoice.vendor_id)
        .order_by(Invoice.created_at.desc(), Invoice.id.desc())
        .limit(INVOICE_ROWS)
    ).all()

    open_receivables = receivables.list_open(db)  # most overdue first
    overdue = [r for r in open_receivables if r.status == "overdue"]
    overdue_total: dict[str, int] = defaultdict(int)
    for r in overdue:
        overdue_total[r.currency] += r.amount_minor

    in_transit = db.execute(
        select(PurchaseOrder, Vendor.name)
        .join(Vendor, Vendor.id == PurchaseOrder.vendor_id)
        .where(
            PurchaseOrder.status == PurchaseOrderStatus.approved,
            PurchaseOrder.delivered_on.is_(None),
        )
    ).all()
    late = sorted(
        (
            LateDelivery(po_number=po.po_number, vendor_name=name, days_late=po.days_late)
            for po, name in in_transit
            if po.days_late > 0
        ),
        key=lambda d: (-d.days_late, d.po_number),
    )

    return MoneyPanel(
        unpaid_invoices=_money(unpaid),
        invoices_to_review=by_status[InvoiceStatus.needs_review],
        invoices_to_pay=by_status[InvoiceStatus.approved],
        recent_invoices=[
            InvoiceRow(
                invoice_id=inv.id,
                number=inv.number,
                vendor_name=name,
                amount_minor=inv.amount_minor,
                currency=inv.currency,
                status=inv.status,
                match_status=inv.match_status,
            )
            for inv, name in recent
        ],
        receivables_open=len(open_receivables),
        receivables_overdue=len(overdue),
        overdue_amount=_money(overdue_total),
        receivables_on_hold=sum(r.status == "on_hold" for r in open_receivables),
        overdue=[
            ReceivableRow(
                order_number=r.order_number,
                customer_name=r.customer_company or r.customer_name,
                amount_minor=r.amount_minor,
                currency=r.currency,
                days_overdue=r.days_overdue,
                status=r.status,
            )
            for r in overdue[:OVERDUE_ROWS]
        ],
        deliveries_open=len(in_transit),
        late_deliveries=late[:LATE_ROWS],
    )


# --- Agents and the insight line ----------------------------------------------------------------


def agent_health(db: Session) -> AgentHealth:
    since = utcnow() - timedelta(hours=24)
    counts = dict(
        db.execute(
            select(AgentTask.status, func.count())
            .where(AgentTask.created_at >= since)
            .group_by(AgentTask.status)
        ).all()
    )
    return AgentHealth(
        calls=sum(counts.values()),
        succeeded=counts.get(TaskStatus.succeeded, 0),
        failed=counts.get(TaskStatus.failed, 0),
    )


def insights(
    db: Session, crm_: Crm, support_: SupportPanel, money_: MoneyPanel, agents: AgentHealth
) -> list[Insight]:
    """The most pressing facts first. Each links to the page where you can act on it."""
    found: list[Insight] = []
    waiting = db.scalar(
        select(func.count())
        .select_from(ApprovalRequest)
        .where(ApprovalRequest.status == ApprovalStatus.pending)
    )
    if waiting:
        found.append(
            Insight(
                tone="warn",
                text=f"{_plural(waiting, 'decision', 'decisions')} waiting for a manager",
                link="/approvals",
            )
        )
    if money_.late_deliveries:
        worst = money_.late_deliveries[0]
        found.append(
            Insight(
                tone="alert",
                text=f"{worst.po_number} from {worst.vendor_name} is "
                f"{_plural(worst.days_late, 'day', 'days')} late",
                link="/procurement",
            )
        )
    if money_.receivables_overdue:
        found.append(
            Insight(
                tone="alert",
                text=_plural(money_.receivables_overdue, "customer payment", "customer payments")
                + f" overdue ({_money_text(money_.overdue_amount)})",
                link="/payments",
            )
        )
    if money_.invoices_to_review:
        found.append(
            Insight(
                tone="warn",
                text=f"{_plural(money_.invoices_to_review, 'invoice needs', 'invoices need')}"
                " a human check",
                link="/payments",
            )
        )
    urgent = sum(
        c.value for c in support_.by_urgency if c.label in (Urgency.critical, Urgency.high)
    )
    if urgent:
        found.append(
            Insight(
                tone="warn",
                text=f"{_plural(urgent, 'urgent ticket', 'urgent tickets')} open",
                link="/support",
            )
        )
    hot = [d for d in crm_.top_deals if d.rating == LeadRating.hot]
    hot_count = db.scalar(
        select(func.count())
        .select_from(Lead)
        .where(Lead.status.in_(OPEN_LEADS), Lead.rating == LeadRating.hot)
    )
    if hot_count:
        names = ", ".join(d.company for d in hot[:2])
        found.append(
            Insight(
                tone="good",
                text=f"{_plural(hot_count, 'hot lead', 'hot leads')} in the pipeline"
                + (f" ({names})" if names else ""),
                link="/sales",
            )
        )
    if agents.calls:
        rate = round(100 * agents.succeeded / agents.calls)
        found.append(
            Insight(
                tone="info",
                text=f"Agents made {_plural(agents.calls, 'call', 'calls')} in 24 h, "
                f"{rate}% succeeded",
                link="/activity",
            )
        )
    if not found:
        found.append(
            Insight(tone="good", text="All clear: nothing is waiting on anyone", link="/activity")
        )
    return found[:MAX_INSIGHTS]


def overview(db: Session) -> Overview:
    today = utcnow().date()
    crm_, support_, money_, agents = crm(db, today), support(db), money(db), agent_health(db)
    return Overview(
        insights=insights(db, crm_, support_, money_, agents),
        hiring=hiring(db, today),
        crm=crm_,
        support=support_,
        money=money_,
        agents=agents,
    )
