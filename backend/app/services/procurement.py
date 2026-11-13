import secrets
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.runner import AgentFailed, TaskContext, call_tool, run_agent
from app.agents.vendor_comparator import VendorComparator
from app.errors import ApiError
from app.llm import LLMClient
from app.models import (
    ApprovalRequest,
    PurchaseOrder,
    PurchaseRequest,
    User,
    Vendor,
    VendorQuote,
)
from app.models.base import utcnow
from app.models.enums import (
    ApprovalStatus,
    Department,
    PurchaseOrderStatus,
    PurchaseRequestStatus,
    Role,
)
from app.money import format_minor
from app.schemas.finance import PoSnapshot
from app.schemas.procurement import (
    ComparisonFacts,
    PurchaseOrderCreate,
    PurchaseRequestCreate,
    PurchaseRequestUpdate,
    QuoteCreate,
    RankedVendor,
    VendorComparison,
    VendorCreate,
    VendorUpdate,
)
from app.services import approvals, audit, deliveries
from app.services.pagination import paginate


def _get[M](db: Session, model: type[M], row_id: uuid.UUID, label: str) -> M:
    row = db.get(model, row_id)
    if row is None:
        raise ApiError(404, "not_found", f"{label} not found")
    return row


def _apply(row: Any, changes: dict[str, Any]) -> dict[str, Any]:
    for key, value in changes.items():
        setattr(row, key, value)
    return {k: str(v) for k, v in changes.items()}


# --- vendors -------------------------------------------------------------------------------


def _ensure_vendor_name_free(db: Session, name: str, except_id: uuid.UUID | None = None) -> None:
    stmt = select(Vendor.id).where(func.lower(Vendor.name) == name.lower())
    if except_id:
        stmt = stmt.where(Vendor.id != except_id)
    if db.scalar(stmt) is not None:
        raise ApiError(409, "vendor_exists", "A vendor with this name already exists")


def list_vendors(db: Session, limit: int, cursor: str | None) -> tuple[list[Vendor], str | None]:
    return paginate(db, select(Vendor), Vendor, limit, cursor)


def get_vendor(db: Session, vendor_id: uuid.UUID) -> Vendor:
    return _get(db, Vendor, vendor_id, "Vendor")


def find_vendor_by_name(db: Session, name: str) -> Vendor | None:
    return db.scalar(select(Vendor).where(func.lower(Vendor.name) == name.strip().lower()))


def create_vendor(db: Session, data: VendorCreate, actor: User) -> Vendor:
    _ensure_vendor_name_free(db, data.name)
    vendor = Vendor(**data.model_dump())
    db.add(vendor)
    db.flush()
    audit.record(
        db, action="vendor.created", entity="vendor", entity_id=vendor.id, actor_id=actor.id
    )
    db.commit()
    return vendor


def update_vendor(db: Session, vendor_id: uuid.UUID, data: VendorUpdate, actor: User) -> Vendor:
    vendor = get_vendor(db, vendor_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        _ensure_vendor_name_free(db, changes["name"], except_id=vendor.id)
    detail = _apply(vendor, changes)
    audit.record(
        db,
        action="vendor.updated",
        entity="vendor",
        entity_id=vendor.id,
        actor_id=actor.id,
        detail=detail,
    )
    db.commit()
    return vendor


# --- purchase requests ---------------------------------------------------------------------


REQUEST_ACTION = "approve_request"


def _request_payload(request: PurchaseRequest) -> dict[str, Any]:
    return {
        "request_id": str(request.id),
        "item": request.item,
        "quantity": request.quantity,
        "budget_minor": request.budget_minor,
        "amount_minor": request.budget_minor,
        "currency": request.currency,
    }


def _request_approval(db: Session, request: PurchaseRequest) -> ApprovalRequest | None:
    """The request's pending entry in the Approval Center (none for requests made before those)."""
    return db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.action == REQUEST_ACTION,
            ApprovalRequest.status == ApprovalStatus.pending,
            ApprovalRequest.payload["request_id"].as_string() == str(request.id),
        )
    )


def list_requests(
    db: Session, limit: int, cursor: str | None, status: PurchaseRequestStatus | None = None
) -> tuple[list[PurchaseRequest], str | None]:
    stmt = select(PurchaseRequest)
    if status:
        stmt = stmt.where(PurchaseRequest.status == status)
    return paginate(db, stmt, PurchaseRequest, limit, cursor)


def get_request(db: Session, request_id: uuid.UUID) -> PurchaseRequest:
    return _get(db, PurchaseRequest, request_id, "Purchase request")


def create_request(db: Session, data: PurchaseRequestCreate, actor: User) -> PurchaseRequest:
    if data.chosen_vendor_id:
        get_vendor(db, data.chosen_vendor_id)
    request = PurchaseRequest(**data.model_dump(), requested_by_id=actor.id)
    db.add(request)
    db.flush()
    approvals.create_approval(
        db,
        action=REQUEST_ACTION,
        payload=_request_payload(request),
        required_role=Role.manager,
        department=Department.procurement,
        requested_by_id=actor.id,
    )
    audit.record(
        db,
        action="purchase_request.created",
        entity="purchase_request",
        entity_id=request.id,
        actor_id=actor.id,
    )
    db.commit()
    return request


def update_request(
    db: Session, request_id: uuid.UUID, data: PurchaseRequestUpdate, actor: User
) -> PurchaseRequest:
    request = get_request(db, request_id)
    if request.status != PurchaseRequestStatus.pending:
        raise ApiError(409, "not_editable", "Only pending requests can be edited")
    changes = data.model_dump(exclude_unset=True)
    if changes.get("chosen_vendor_id"):
        get_vendor(db, changes["chosen_vendor_id"])
    detail = _apply(request, changes)
    waiting = _request_approval(db, request)
    if waiting is not None:  # the approver sees the request as it is now
        waiting.payload = _request_payload(request)
    audit.record(
        db,
        action="purchase_request.updated",
        entity="purchase_request",
        entity_id=request.id,
        actor_id=actor.id,
        detail=detail,
    )
    db.commit()
    return request


# --- purchase orders -----------------------------------------------------------------------


def list_orders(
    db: Session, limit: int, cursor: str | None
) -> tuple[list[PurchaseOrder], str | None]:
    return paginate(db, select(PurchaseOrder), PurchaseOrder, limit, cursor)


def get_order_by_number(db: Session, po_number: str) -> PurchaseOrder:
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
    if order is None:
        raise ApiError(404, "not_found", "Purchase order not found")
    return order


def create_order(
    db: Session, data: PurchaseOrderCreate, actor: User | None = None
) -> PurchaseOrder:
    """New POs start as pending_approval. Used by the seed script and tests."""
    if db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.po_number == data.po_number)):
        raise ApiError(409, "po_exists", "A purchase order with this number already exists")
    get_vendor(db, data.vendor_id)
    order = PurchaseOrder(**data.model_dump())
    db.add(order)
    db.flush()
    audit.record(
        db,
        action="purchase_order.created",
        entity="purchase_order",
        entity_id=order.id,
        actor_id=actor.id if actor else None,
    )
    db.commit()
    return order


def po_snapshot(db: Session, po_number: str) -> PoSnapshot | None:
    """The `get_po` tool: what an agent may see of a purchase order."""
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number.strip()))
    if order is None:
        return None
    vendor = get_vendor(db, order.vendor_id)
    return PoSnapshot(
        id=order.id,
        po_number=order.po_number,
        vendor_id=order.vendor_id,
        vendor_name=vendor.name,
        amount_minor=order.amount_minor,
        currency=order.currency,
        status=order.status,
    )


# --- quotes and vendor comparison (FR-PRO-02) ----------------------------------------------

COMPARATOR = VendorComparator()
# How much each factor counts in the vendor score. Plain, fixed numbers: same data, same ranking.
WEIGHTS = {"price": Decimal("0.50"), "lead_time": Decimal("0.25"), "delivery": Decimal("0.25")}
_SCORE_PLACES = Decimal("0.1")
_PART_PLACES = Decimal("0.001")


def add_quote(db: Session, request_id: uuid.UUID, data: QuoteCreate, actor: User) -> VendorQuote:
    request = get_request(db, request_id)
    get_vendor(db, data.vendor_id)
    quote = db.scalar(
        select(VendorQuote).where(
            VendorQuote.request_id == request.id, VendorQuote.vendor_id == data.vendor_id
        )
    )
    if quote is None:
        quote = VendorQuote(request_id=request.id, vendor_id=data.vendor_id, unit_price_minor=0)
        db.add(quote)
    quote.unit_price_minor = data.unit_price_minor
    quote.currency = request.currency  # quotes are in the request's currency
    db.flush()
    audit.record(
        db,
        action="quote.saved",
        entity="vendor_quote",
        entity_id=quote.id,
        actor_id=actor.id,
        detail={"request_id": str(request.id), "unit_price_minor": data.unit_price_minor},
    )
    db.commit()
    return quote


def list_quotes(db: Session, request_id: uuid.UUID) -> list[VendorQuote]:
    return list(db.scalars(select(VendorQuote).where(VendorQuote.request_id == request_id)))


def rank_vendors(
    quantity: int, budget_minor: int, offers: list[tuple[Vendor, VendorQuote]]
) -> list[RankedVendor]:
    """Score = 50% price + 25% lead time + 25% on-time rate, each relative to the best offer.

    Ties go to the cheaper offer, then to the vendor name, so the order never depends on luck.
    """
    if not offers:
        return []
    totals = {v.id: q.unit_price_minor * quantity for v, q in offers}
    cheapest = min(totals.values())
    fastest = max(min(v.lead_time_days for v, _ in offers), 1)
    rows = []
    for vendor, quote in offers:
        total = totals[vendor.id]
        price = Decimal(cheapest) / Decimal(total) if total else Decimal(1)
        lead = Decimal(fastest) / Decimal(max(vendor.lead_time_days, 1))
        delivery = Decimal(vendor.on_time_rate)
        weighted = (
            WEIGHTS["price"] * price + WEIGHTS["lead_time"] * lead + WEIGHTS["delivery"] * delivery
        )
        rows.append(
            {
                "vendor_id": vendor.id,
                "vendor_name": vendor.name,
                "total_minor": total,
                "currency": quote.currency,
                "lead_time_days": vendor.lead_time_days,
                "on_time_rate": delivery,
                "price_score": price.quantize(_PART_PLACES, ROUND_HALF_UP),
                "lead_time_score": lead.quantize(_PART_PLACES, ROUND_HALF_UP),
                "delivery_score": delivery.quantize(_PART_PLACES, ROUND_HALF_UP),
                "score": (weighted * 100).quantize(_SCORE_PLACES, ROUND_HALF_UP),
                "over_budget": total > budget_minor,
            }
        )
    rows.sort(key=lambda r: (-r["score"], r["total_minor"], r["vendor_name"].lower()))
    return [RankedVendor(rank=i, **r) for i, r in enumerate(rows, start=1)]


def _facts(request: PurchaseRequest, ranking: list[RankedVendor]) -> ComparisonFacts:
    return ComparisonFacts(
        item=request.item,
        quantity=request.quantity,
        budget=format_minor(request.budget_minor, request.currency),
        ranking=[
            {
                "rank": r.rank,
                "vendor": r.vendor_name,
                "total": format_minor(r.total_minor, r.currency),
                "lead_time_days": r.lead_time_days,
                "on_time_rate": f"{r.on_time_rate * 100:.1f}%",
                "score": str(r.score),
                "over_budget": r.over_budget,
            }
            for r in ranking
        ],
    )


def compare_vendors(
    db: Session, llm: LLMClient, request_id: uuid.UUID, ctx: TaskContext
) -> VendorComparison:
    request = get_request(db, request_id)
    rid = {"request_id": str(request.id)}

    def _offers() -> list[tuple[Vendor, VendorQuote]]:
        return [(get_vendor(db, q.vendor_id), q) for q in list_quotes(db, request.id)]

    call_tool(db, COMPARATOR, "get_request", rid, lambda: {"item": request.item}, ctx)
    offers = call_tool(db, COMPARATOR, "list_vendors", rid, _offers, ctx)
    if len(offers) < 2:
        raise ApiError(409, "not_enough_quotes", "Add quotes from at least two vendors to compare")

    def _history() -> dict[str, str]:
        return {v.name: str(v.on_time_rate) for v, _ in offers}

    call_tool(db, COMPARATOR, "get_vendor_history", rid, _history, ctx)
    ranking = rank_vendors(request.quantity, request.budget_minor, offers)
    reason, reason_error = None, None
    try:
        reason = run_agent(db, COMPARATOR, _facts(request, ranking), llm, ctx).reason
    except AgentFailed as exc:  # the ranking stands on its own; only the explanation is missing
        reason_error = exc.message
    result = VendorComparison(
        request_id=request.id,
        ranking=ranking,
        reason=reason,
        reason_error=reason_error,
        compared_at=utcnow(),
    )

    def _save() -> dict[str, str]:
        request.comparison = result.model_dump(mode="json")
        audit.record(
            db,
            action="request.compared",
            entity="purchase_request",
            entity_id=request.id,
            actor_id=ctx.actor.id,
            detail={"top_vendor": ranking[0].vendor_name},
        )
        return {"top_vendor": ranking[0].vendor_name}

    call_tool(db, COMPARATOR, "save_comparison", rid, _save, ctx)
    return result


# --- request approval and purchase orders (FR-PRO-03) --------------------------------------


def decide_request(
    db: Session, request_id: uuid.UUID, actor: User, *, approve: bool
) -> PurchaseRequest:
    """A procurement manager approves or rejects a purchase request (not their own)."""
    if actor.role not in (Role.manager, Role.admin):
        raise ApiError(403, "forbidden", "Only a procurement manager can decide requests")
    request = get_request(db, request_id)
    if request.requested_by_id == actor.id:
        raise ApiError(403, "self_approval", "You cannot approve or reject your own request")
    if request.status != PurchaseRequestStatus.pending:
        raise ApiError(409, "already_decided", f"This request is already {request.status}")
    request.status = PurchaseRequestStatus.approved if approve else PurchaseRequestStatus.rejected
    waiting = _request_approval(db, request)
    if waiting is not None:  # decided on the Procurement page: the Approval Center shows the same
        waiting.status = ApprovalStatus.approved if approve else ApprovalStatus.rejected
        waiting.decided_by_id = actor.id
        waiting.decided_at = utcnow()
    audit.record(
        db,
        action=f"purchase_request.{request.status}",
        entity="purchase_request",
        entity_id=request.id,
        actor_id=actor.id,
    )
    db.commit()
    return request


def _new_po_number(db: Session) -> str:
    while True:
        number = f"PO-{secrets.randbelow(900_000) + 100_000}"
        if db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.po_number == number)) is None:
            return number


def create_order_for_approval(
    db: Session, data: PurchaseOrderCreate, actor: User, request: PurchaseRequest | None = None
) -> tuple[PurchaseOrder, ApprovalRequest]:
    """Every PO created through the API waits for a procurement manager (approval policy)."""
    if db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.po_number == data.po_number)):
        raise ApiError(409, "po_exists", "A purchase order with this number already exists")
    vendor = get_vendor(db, data.vendor_id)
    order = PurchaseOrder(**data.model_dump(), status=PurchaseOrderStatus.pending_approval)
    db.add(order)
    db.flush()
    approval = approvals.create_approval(
        db,
        action="approve_po",
        payload={
            "po_id": str(order.id),
            "po_number": order.po_number,
            "vendor_name": vendor.name,
            "amount_minor": order.amount_minor,
            "currency": order.currency,
            "item": request.item if request else None,
            "quantity": request.quantity if request else None,
            "budget_minor": request.budget_minor if request else None,
            "over_budget": bool(request and order.amount_minor > request.budget_minor),
        },
        required_role=Role.manager,
        department=Department.procurement,
        requested_by_id=actor.id,
    )
    audit.record(
        db,
        action="purchase_order.created",
        entity="purchase_order",
        entity_id=order.id,
        actor_id=actor.id,
        detail={"approval_id": str(approval.id)},
    )
    db.commit()
    return order, approval


def order_from_request(
    db: Session, request_id: uuid.UUID, vendor_id: uuid.UUID | None, actor: User
) -> tuple[PurchaseOrder, ApprovalRequest]:
    request = get_request(db, request_id)
    if request.status != PurchaseRequestStatus.approved:
        raise ApiError(
            409, "request_not_approved", "Only approved requests can become a purchase order"
        )
    top = ((request.comparison or {}).get("ranking") or [{}])[0].get("vendor_id")
    chosen = vendor_id or request.chosen_vendor_id or (uuid.UUID(top) if top else None)
    if chosen is None:
        raise ApiError(409, "no_vendor", "Pick a vendor or compare vendors first")
    quote = db.scalar(
        select(VendorQuote).where(
            VendorQuote.request_id == request.id, VendorQuote.vendor_id == chosen
        )
    )
    if quote is None:
        raise ApiError(409, "no_quote", "That vendor has not quoted for this request")
    pending = db.scalar(
        select(PurchaseOrder.id).where(
            PurchaseOrder.request_id == request.id,
            PurchaseOrder.status == PurchaseOrderStatus.pending_approval,
        )
    )
    if pending:
        raise ApiError(409, "order_pending", "A purchase order for this request is already waiting")
    request.chosen_vendor_id = chosen
    data = PurchaseOrderCreate(
        po_number=_new_po_number(db),
        vendor_id=chosen,
        request_id=request.id,
        amount_minor=quote.unit_price_minor * request.quantity,
        currency=quote.currency,
    )
    return create_order_for_approval(db, data, actor, request)


def apply_decision(db: Session, approval: ApprovalRequest, actor: User) -> None:
    """After a PO decision: approved → PO approved and request ordered; rejected → PO rejected.
    After a purchase request decision: the request takes the same status."""
    if approval.action == REQUEST_ACTION:
        request = db.get(PurchaseRequest, uuid.UUID(approval.payload["request_id"]))
        if request is None or request.status != PurchaseRequestStatus.pending:
            return
        approved = approval.status == ApprovalStatus.approved
        request.status = (
            PurchaseRequestStatus.approved if approved else PurchaseRequestStatus.rejected
        )
        audit.record(
            db,
            action=f"purchase_request.{request.status}",
            entity="purchase_request",
            entity_id=request.id,
            actor_id=actor.id,
            detail={"approval_id": str(approval.id)},
        )
        db.commit()
        return
    if approval.action != "approve_po":
        return
    order = db.get(PurchaseOrder, uuid.UUID(approval.payload["po_id"]))
    if order is None:
        return
    approved = approval.status == ApprovalStatus.approved
    order.status = PurchaseOrderStatus.approved if approved else PurchaseOrderStatus.rejected
    if approved:
        vendor = db.get(Vendor, order.vendor_id)
        if vendor is not None:
            deliveries.start_tracking(order, vendor)
    if approved and order.request_id:
        request = db.get(PurchaseRequest, order.request_id)
        if request is not None:
            request.status = PurchaseRequestStatus.ordered
    audit.record(
        db,
        action=f"purchase_order.{order.status}",
        entity="purchase_order",
        entity_id=order.id,
        actor_id=actor.id,
        detail={"approval_id": str(approval.id)},
    )
    db.commit()
