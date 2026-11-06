"""Every fixed set of values the database accepts."""

from enum import StrEnum


class Role(StrEnum):
    admin = "admin"
    manager = "manager"
    employee = "employee"
    executive = "executive"


class Department(StrEnum):
    sales = "sales"
    finance = "finance"
    hr = "hr"
    support = "support"
    procurement = "procurement"


class LeadStatus(StrEnum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    won = "won"
    lost = "lost"


class Priority(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class LeadRating(StrEnum):
    hot = "hot"
    warm = "warm"
    cold = "cold"


class OrderStatus(StrEnum):
    placed = "placed"
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"
    refunded = "refunded"


class InvoiceStatus(StrEnum):
    received = "received"
    needs_review = "needs_review"
    approved = "approved"
    rejected = "rejected"
    payment_submitted = "payment_submitted"


class MatchStatus(StrEnum):
    matched = "matched"
    mismatch = "mismatch"
    no_po = "no_po"


class AnomalyKind(StrEnum):
    duplicate = "duplicate"  # same vendor, number and amount as an existing invoice
    number_conflict = "number_conflict"  # same vendor and number, different amount
    unknown_vendor = "unknown_vendor"
    po_mismatch = "po_mismatch"
    no_po = "no_po"
    not_an_invoice = "not_an_invoice"  # a credit note, quotation or reminder: nothing to pay


class PaymentStatus(StrEnum):
    submitted = "submitted"


class PurchaseRequestStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    ordered = "ordered"


class PurchaseOrderStatus(StrEnum):
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"


class JobStatus(StrEnum):
    open = "open"
    closed = "closed"


class TicketCategory(StrEnum):
    billing = "billing"
    technical = "technical"
    shipping = "shipping"
    refund = "refund"
    legal = "legal"
    account = "account"
    other = "other"


class Urgency(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    critical = "critical"


class TicketStatus(StrEnum):
    open = "open"
    investigating = "investigating"
    escalated = "escalated"
    resolved = "resolved"
    closed = "closed"


class ExecutionStatus(StrEnum):
    running = "running"
    waiting_approval = "waiting_approval"
    approved = "approved"
    rejected = "rejected"
    failed = "failed"
    completed = "completed"


class StepStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    waiting_approval = "waiting_approval"
    rejected = "rejected"
    skipped = "skipped"


class TaskStatus(StrEnum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class EmailStatus(StrEnum):
    draft = "draft"
    pending_approval = "pending_approval"
    sent = "sent"
    failed = "failed"
    rejected = "rejected"
