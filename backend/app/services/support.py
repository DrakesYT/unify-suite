"""Tickets (FR-SUP-01 classify, FR-SUP-02 investigate, FR-SUP-03 escalate with approval)."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.runner import AgentFailed, TaskContext, call_tool, run_agent
from app.agents.ticket_investigator import TicketClassifier, TicketInvestigator
from app.errors import ApiError
from app.llm import LLMClient
from app.models import ApprovalRequest, Customer, Order, Ticket, User
from app.models.base import utcnow
from app.models.enums import (
    ApprovalStatus,
    Department,
    OrderStatus,
    Role,
    TicketCategory,
    TicketStatus,
)
from app.money import format_minor
from app.schemas.support import InvestigationInput, OrderFact, TicketCreate, TicketText
from app.services import approvals, audit
from app.services.pagination import paginate

CLASSIFIER = TicketClassifier()
INVESTIGATOR = TicketInvestigator()
ORDER_HISTORY_LIMIT = 20
# Escalations in these categories wait for a support manager (approval policy: refunds, legal).
NEEDS_APPROVAL = {TicketCategory.refund: "issue_refund", TicketCategory.legal: "legal_escalation"}
TICKET_ACTIONS = frozenset(NEEDS_APPROVAL.values())


# --- customers -----------------------------------------------------------------------------


def list_customers(db: Session) -> list[Customer]:
    return list(db.scalars(select(Customer).order_by(Customer.name)))


def create_customer(db: Session, *, name: str, company: str | None, email: str | None) -> Customer:
    """Used by the seed script and tests."""
    customer = Customer(name=name, company=company, email=email)
    db.add(customer)
    db.commit()
    return customer


def add_order(
    db: Session,
    customer_id: uuid.UUID,
    *,
    order_number: str,
    amount_minor: int,
    currency: str,
    status: OrderStatus,
    ordered_at: datetime,
) -> Order:
    """Used by the seed script and tests."""
    order = Order(
        customer_id=customer_id,
        order_number=order_number,
        amount_minor=amount_minor,
        currency=currency,
        status=status,
        ordered_at=ordered_at,
    )
    db.add(order)
    db.commit()
    return order


def customer_orders(db: Session, customer_id: uuid.UUID) -> list[Order]:
    return list(
        db.scalars(
            select(Order)
            .where(Order.customer_id == customer_id)
            .order_by(Order.ordered_at.desc())
            .limit(ORDER_HISTORY_LIMIT)
        )
    )


# --- tickets -------------------------------------------------------------------------------


def list_tickets(
    db: Session,
    limit: int,
    cursor: str | None,
    status: TicketStatus | None = None,
    category: TicketCategory | None = None,
) -> tuple[list[Ticket], str | None]:
    stmt = select(Ticket)
    if status:
        stmt = stmt.where(Ticket.status == status)
    if category:
        stmt = stmt.where(Ticket.category == category)
    return paginate(db, stmt, Ticket, limit, cursor)


def get_ticket(db: Session, ticket_id: uuid.UUID) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise ApiError(404, "not_found", "Ticket not found")
    return ticket


def classify(db: Session, llm: LLMClient, ticket: Ticket, ctx: TaskContext) -> Ticket:
    text = call_tool(
        db,
        CLASSIFIER,
        "get_ticket",
        {"ticket_id": str(ticket.id)},
        lambda: TicketText(title=ticket.title, description=ticket.description),
        ctx,
    )
    result = run_agent(db, CLASSIFIER, text, llm, ctx)

    def _save() -> dict[str, str]:
        ticket.category, ticket.urgency = result.category, result.urgency
        audit.record(
            db,
            action="ticket.classified",
            entity="ticket",
            entity_id=ticket.id,
            actor_id=ctx.actor.id,
            detail={"category": result.category, "urgency": result.urgency},
        )
        return {"category": result.category, "urgency": result.urgency, "reason": result.reason}

    call_tool(db, CLASSIFIER, "save_classification", {"ticket_id": str(ticket.id)}, _save, ctx)
    return ticket


def create_ticket(
    db: Session, llm: LLMClient | None, data: TicketCreate, ctx: TaskContext
) -> Ticket:
    """Save first, then classify. If the model is down (or not given, as in a records-only
    import) the ticket is kept, just unclassified."""
    if data.customer_id and db.get(Customer, data.customer_id) is None:
        raise ApiError(404, "not_found", "Customer not found")
    ticket = Ticket(**data.model_dump())
    db.add(ticket)
    db.flush()
    audit.record(
        db, action="ticket.created", entity="ticket", entity_id=ticket.id, actor_id=ctx.actor.id
    )
    db.commit()
    if llm is None:
        return ticket
    try:
        classify(db, llm, ticket, ctx)
    except AgentFailed:
        db.refresh(ticket)  # stays unclassified; the UI offers "Classify" again
    return ticket


def investigate(db: Session, llm: LLMClient, ticket_id: uuid.UUID, ctx: TaskContext) -> Ticket:
    ticket = get_ticket(db, ticket_id)
    if ticket.customer_id is None:
        raise ApiError(409, "no_customer", "Link the ticket to a customer to investigate orders")

    def _orders() -> list[OrderFact]:
        return [
            OrderFact(
                order_number=o.order_number,
                status=o.status,
                amount=format_minor(o.amount_minor, o.currency),
                ordered_on=o.ordered_at.date().isoformat(),
            )
            for o in customer_orders(db, ticket.customer_id)  # type: ignore[arg-type]
        ]

    orders = call_tool(
        db, INVESTIGATOR, "get_orders", {"customer_id": str(ticket.customer_id)}, _orders, ctx
    )
    data = InvestigationInput(
        title=ticket.title, description=ticket.description, category=ticket.category, orders=orders
    )
    result = run_agent(db, INVESTIGATOR, data, llm, ctx)

    def _save() -> dict[str, list[str]]:
        ticket.investigation = result.model_dump(mode="json") | {
            "investigated_at": utcnow().isoformat()
        }
        if ticket.status == TicketStatus.open:
            ticket.status = TicketStatus.investigating
        audit.record(
            db,
            action="ticket.investigated",
            entity="ticket",
            entity_id=ticket.id,
            actor_id=ctx.actor.id,
            detail={"order_numbers": result.order_numbers_used},
        )
        return {"order_numbers_used": result.order_numbers_used}

    call_tool(db, INVESTIGATOR, "save_investigation", {"ticket_id": str(ticket.id)}, _save, ctx)
    return ticket


def escalate(
    db: Session, ticket_id: uuid.UUID, note: str, actor: User
) -> tuple[Ticket, ApprovalRequest | None]:
    """FR-SUP-03: refund and legal escalations need a support manager's approval."""
    ticket = get_ticket(db, ticket_id)
    if ticket.status in (TicketStatus.resolved, TicketStatus.closed):
        raise ApiError(409, "ticket_closed", "This ticket is already resolved")
    action = NEEDS_APPROVAL.get(ticket.category) if ticket.category else None
    approval = None
    if action:
        pending = db.scalar(
            select(ApprovalRequest.id).where(
                ApprovalRequest.action == action,
                ApprovalRequest.status == ApprovalStatus.pending,
                ApprovalRequest.payload["ticket_id"].as_string() == str(ticket.id),
            )
        )
        if pending:
            raise ApiError(409, "already_escalated", "This ticket is already waiting for approval")
        customer = db.get(Customer, ticket.customer_id) if ticket.customer_id else None
        approval = approvals.create_approval(
            db,
            action=action,
            payload={
                "ticket_id": str(ticket.id),
                "title": ticket.title,
                "category": ticket.category,
                "urgency": ticket.urgency,
                "customer_name": customer.name if customer else None,
                "note": note.strip(),
                "likely_cause": ((ticket.investigation or {}).get("likely_causes") or [{}])[0].get(
                    "cause"
                ),
            },
            required_role=Role.manager,
            department=Department.support,
            requested_by_id=actor.id,
        )
    ticket.status = TicketStatus.escalated
    audit.record(
        db,
        action="ticket.escalated",
        entity="ticket",
        entity_id=ticket.id,
        actor_id=actor.id,
        detail={"needs_approval": bool(action), "note": note.strip()},
    )
    db.commit()
    return ticket, approval


def apply_decision(db: Session, approval: ApprovalRequest, actor: User) -> None:
    """After a manager decides a ticket escalation: approved → resolved, rejected → back to open."""
    if approval.action not in TICKET_ACTIONS:
        return
    ticket = db.get(Ticket, uuid.UUID(approval.payload["ticket_id"]))
    if ticket is None:
        return
    ticket.status = (
        TicketStatus.resolved if approval.status == ApprovalStatus.approved else TicketStatus.open
    )
    audit.record(
        db,
        action=f"ticket.{ticket.status}",
        entity="ticket",
        entity_id=ticket.id,
        actor_id=actor.id,
        detail={"approval_id": str(approval.id)},
    )
    db.commit()
