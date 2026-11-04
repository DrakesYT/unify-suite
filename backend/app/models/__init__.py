"""All tables. Importing this package registers every model on `Base.metadata`."""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.finance import Invoice, InvoiceAnomaly, Transaction
from app.models.hr import Candidate, CandidateScore, Job
from app.models.procurement import PurchaseOrder, PurchaseRequest, Vendor
from app.models.sales import Customer, Lead, Order
from app.models.support import Ticket
from app.models.uploads import Upload
from app.models.users import User
from app.models.workflows import (
    AgentTask,
    ApprovalRequest,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStep,
)

__all__ = [
    "AgentTask",
    "ApprovalRequest",
    "AuditLog",
    "Base",
    "Candidate",
    "CandidateScore",
    "Customer",
    "Invoice",
    "InvoiceAnomaly",
    "Job",
    "Lead",
    "Order",
    "PurchaseOrder",
    "PurchaseRequest",
    "Ticket",
    "Transaction",
    "Upload",
    "User",
    "Vendor",
    "WorkflowDefinition",
    "WorkflowExecution",
    "WorkflowStep",
]
