"""Search box in the top bar: names and numbers across the departments the user may read."""

from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Candidate,
    Customer,
    Invoice,
    Job,
    Lead,
    Order,
    PurchaseOrder,
    Ticket,
    User,
    Vendor,
)
from app.models.enums import Department
from app.money import format_minor
from app.schemas.dashboard import SearchHit
from app.services.authz import can_access

PER_KIND = 5
MAX_HITS = 20


def contains_pattern(term: str) -> str:
    """A LIKE pattern matching `term` anywhere, with % and _ in the term taken literally."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _matching(db: Session, model: Any, columns: Iterable[Any], pattern: str) -> list[Any]:
    clause = or_(*(c.ilike(pattern, escape="\\") for c in columns))
    return list(
        db.scalars(select(model).where(clause).order_by(model.created_at.desc()).limit(PER_KIND))
    )


def _sales(db: Session, p: str) -> list[SearchHit]:
    return [
        SearchHit(
            kind="lead",
            title=lead.company,
            subtitle=f"{lead.name} · {lead.status} · "
            + format_minor(lead.value_minor, lead.currency),
            link=f"/sales#lead-{lead.id}",
        )
        for lead in _matching(db, Lead, (Lead.company, Lead.name, Lead.email), p)
    ]


def _hr(db: Session, p: str) -> list[SearchHit]:
    jobs = [
        SearchHit(kind="job", title=job.title, subtitle=f"job · {job.status}", link="/hr")
        for job in _matching(db, Job, (Job.title,), p)
    ]
    candidates = [
        SearchHit(kind="candidate", title=c.name, subtitle=c.email or "candidate", link="/hr")
        for c in _matching(db, Candidate, (Candidate.name, Candidate.email), p)
    ]
    return jobs + candidates


def _support(db: Session, p: str) -> list[SearchHit]:
    return [
        SearchHit(
            kind="ticket",
            title=t.title,
            subtitle=f"ticket · {t.status}" + (f" · {t.urgency}" if t.urgency else ""),
            link=f"/support#ticket-{t.id}",
        )
        for t in _matching(db, Ticket, (Ticket.title,), p)
    ]


def _procurement(db: Session, p: str) -> list[SearchHit]:
    vendors = [
        SearchHit(
            kind="vendor",
            title=v.name,
            subtitle=f"vendor · {v.lead_time_days}-day lead time",
            link="/procurement",
        )
        for v in _matching(db, Vendor, (Vendor.name,), p)
    ]
    orders = [
        SearchHit(
            kind="purchase_order",
            title=po.po_number,
            subtitle=f"purchase order · {format_minor(po.amount_minor, po.currency)}",
            link=f"/procurement#po-{po.po_number}",
        )
        for po in _matching(db, PurchaseOrder, (PurchaseOrder.po_number,), p)
    ]
    return orders + vendors


def _finance(db: Session, p: str) -> list[SearchHit]:
    invoices = [
        SearchHit(
            kind="invoice",
            title=inv.number,
            subtitle=f"invoice · {inv.status} · {format_minor(inv.amount_minor, inv.currency)}",
            link="/payments",
        )
        for inv in _matching(db, Invoice, (Invoice.number, Invoice.po_number), p)
    ]
    rows = db.execute(
        select(Order, Customer)
        .join(Customer, Customer.id == Order.customer_id)
        .where(
            or_(
                Order.order_number.ilike(p, escape="\\"),
                Customer.name.ilike(p, escape="\\"),
                Customer.company.ilike(p, escape="\\"),
            )
        )
        .order_by(Order.created_at.desc())
        .limit(PER_KIND)
    ).all()
    orders = [
        SearchHit(
            kind="order",
            title=order.order_number,
            subtitle=f"customer order · {customer.company or customer.name}",
            link=f"/payments#order-{order.order_number}",
        )
        for order, customer in rows
    ]
    return invoices + orders


SOURCES: dict[Department, Callable[[Session, str], list[SearchHit]]] = {
    Department.sales: _sales,
    Department.hr: _hr,
    Department.support: _support,
    Department.procurement: _procurement,
    Department.finance: _finance,
}


def search(db: Session, user: User, term: str) -> list[SearchHit]:
    """Same read rule as every page: an employee only finds their own department's records."""
    pattern = contains_pattern(term.strip())
    hits: list[SearchHit] = []
    for department, source in SOURCES.items():
        if can_access(user, department, write=False):
            hits.extend(source(db, pattern))
    return hits[:MAX_HITS]
