"""Receivables: unpaid customer orders, what is overdue, and payment reminders.

Code decides everything that matters: the due date (order date + the customer's terms), whether
it is overdue, and whether the customer must not be chased because of an open dispute. The
Payment Reminder Writer only drafts; approval and sending are shared (services/outbound.py).
"""

import re
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.payment_reminder import PaymentReminderWriter
from app.agents.runner import TaskContext, call_tool, run_agent
from app.config import DEFAULT_TERMS_DAYS, SELLER_COMPANY
from app.errors import ApiError
from app.llm import LLMClient
from app.models import Customer, Order, OutboundEmail, Ticket, User
from app.models.base import utcnow
from app.models.enums import Department, OrderStatus, TicketCategory, TicketStatus
from app.money import format_minor
from app.schemas.finance import ReceivableOut
from app.schemas.outreach import EmailDraft, PaymentReminderInput
from app.services import audit, outbound

WRITER = PaymentReminderWriter()
KIND = "payment_reminder"
CLOSED_ORDERS = (OrderStatus.cancelled, OrderStatus.refunded)
OPEN_TICKETS = (TicketStatus.open, TicketStatus.investigating, TicketStatus.escalated)
DISPUTES = (TicketCategory.refund, TicketCategory.billing, TicketCategory.legal)


def terms_days(customer: Customer) -> int:
    """'net_30' → 30. Anything unreadable falls back to the default terms."""
    match = re.fullmatch(r"net_(\d{1,3})", customer.billing_terms or "")
    return int(match.group(1)) if match else DEFAULT_TERMS_DAYS


def hold_reason(db: Session, customer: Customer) -> str | None:
    """Never chase a customer who has an open refund, billing or legal ticket."""
    ticket = db.scalar(
        select(Ticket)
        .where(
            Ticket.customer_id == customer.id,
            Ticket.status.in_(OPEN_TICKETS),
            Ticket.category.in_(DISPUTES),
        )
        .order_by(Ticket.created_at)
    )
    return f"open {ticket.category} ticket: {ticket.title}" if ticket else None


def describe(db: Session, order: Order, customer: Customer, today: date) -> ReceivableOut:
    ordered_on = order.ordered_at.date()
    due_on = ordered_on + timedelta(days=terms_days(customer))
    days_overdue = max((today - due_on).days, 0)
    reason = hold_reason(db, customer) if days_overdue else None
    status = "on_hold" if reason else ("overdue" if days_overdue else "not_due")
    return ReceivableOut(
        order_id=order.id,
        order_number=order.order_number,
        customer_name=customer.name,
        customer_company=customer.company,
        customer_email=customer.email,
        amount_minor=order.amount_minor,
        currency=order.currency,
        ordered_on=ordered_on,
        due_on=due_on,
        days_overdue=days_overdue,
        status=status,
        hold_reason=reason,
    )


def list_open(db: Session) -> list[ReceivableOut]:
    """Unpaid, billable orders, most overdue first."""
    rows = db.execute(
        select(Order, Customer)
        .join(Customer, Customer.id == Order.customer_id)
        .where(Order.paid_on.is_(None), Order.status.not_in(CLOSED_ORDERS))
    ).all()
    today = utcnow().date()
    items = [describe(db, order, customer, today) for order, customer in rows]
    return sorted(items, key=lambda r: (-r.days_overdue, r.due_on, r.order_number))


def _order(db: Session, order_id: uuid.UUID) -> tuple[Order, Customer]:
    order = db.get(Order, order_id)
    if order is None:
        raise ApiError(404, "not_found", "Order not found")
    customer = db.get(Customer, order.customer_id)
    assert customer is not None
    return order, customer


def mark_paid(db: Session, order_id: uuid.UUID, actor: User) -> ReceivableOut:
    order, customer = _order(db, order_id)
    if order.paid_on is not None:
        raise ApiError(409, "already_paid", "This order is already marked paid")
    order.paid_on = utcnow().date()
    audit.record(db, action="order.paid", entity="order", entity_id=order.id, actor_id=actor.id)
    db.commit()
    return describe(db, order, customer, utcnow().date())


def _facts(db: Session, order: Order, customer: Customer) -> PaymentReminderInput:
    if order.paid_on is not None or order.status in CLOSED_ORDERS:
        raise ApiError(409, "not_open", "This order is not an open receivable")
    item = describe(db, order, customer, utcnow().date())
    if item.status == "on_hold":
        raise ApiError(409, "on_hold", f"Reminder blocked: {item.hold_reason}")
    if item.status != "overdue":
        raise ApiError(409, "not_overdue", "This order is not overdue yet")
    return PaymentReminderInput(
        order_number=order.order_number,
        customer_company=customer.company or customer.name,
        amount=format_minor(order.amount_minor, order.currency),
        ordered_on=item.ordered_on,
        due_on=item.due_on,
        days_overdue=item.days_overdue,
        billing_terms=customer.billing_terms,
        seller_company=SELLER_COMPANY,
    )


def compose_body(customer: Customer, draft: EmailDraft, sender: User) -> str:
    first_name = customer.name.split()[0]
    return (
        f"Hello {first_name},\n\n{draft.body}\n\n"
        f"Kind regards,\n{sender.full_name}\nAccounts Receivable, {SELLER_COMPANY}"
    )


def draft_reminder(
    db: Session, llm: LLMClient, order_id: uuid.UUID, ctx: TaskContext
) -> OutboundEmail:
    order, customer = _order(db, order_id)
    if not customer.email:
        raise ApiError(409, "no_customer_email", f"{customer.name} has no email address on file")
    facts = call_tool(
        db,
        WRITER,
        "get_receivable",
        {"order_number": order.order_number},
        lambda: _facts(db, order, customer),
        ctx,
    )
    draft: EmailDraft = run_agent(db, WRITER, facts, llm, ctx)
    return call_tool(
        db,
        WRITER,
        "save_email_draft",
        {"order_number": order.order_number},
        lambda: outbound.new_draft(
            db,
            kind=KIND,
            department=Department.finance,
            to_address=customer.email or "",
            subject=draft.subject,
            body=compose_body(customer, draft, ctx.actor),
            actor=ctx.actor,
            model=llm.model,
            order_id=order.id,
        ),
        ctx,
    )


def list_for_order(db: Session, order_id: uuid.UUID) -> list[OutboundEmail]:
    _order(db, order_id)
    stmt = (
        select(OutboundEmail)
        .where(OutboundEmail.order_id == order_id)
        .order_by(OutboundEmail.created_at.desc())
    )
    return list(db.scalars(stmt))


def request_approval(db: Session, email_id: uuid.UUID, actor: User) -> OutboundEmail:
    email = outbound.get_email(db, email_id, Department.finance)
    order = db.get(Order, email.order_id) if email.order_id else None
    customer = db.get(Customer, order.customer_id) if order else None
    context = {
        "order_id": str(order.id) if order else None,
        "order_number": order.order_number if order else None,
        "company": (customer.company or customer.name) if customer else None,
    }
    return outbound.request_approval(db, email_id, Department.finance, actor, context)
