"""All tables. Importing this package registers every model on `Base.metadata`."""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.calls import CallTranscript
from app.models.email import OutboundEmail
from app.models.finance import Invoice, InvoiceAnomaly, Payment, Transaction
from app.models.hr import Candidate, CandidateScore, InterviewSlot, Job
from app.models.procurement import PurchaseOrder, PurchaseRequest, Vendor, VendorQuote
from app.models.sales import Customer, Lead, Order
from app.models.sessions import UserSession
from app.models.settings import AppSetting
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
    "AppSetting",
    "ApprovalRequest",
    "AuditLog",
    "Base",
    "CallTranscript",
    "Candidate",
    "CandidateScore",
    "Customer",
    "InterviewSlot",
    "Invoice",
    "InvoiceAnomaly",
    "Job",
    "Lead",
    "Order",
    "OutboundEmail",
    "Payment",
    "PurchaseOrder",
    "PurchaseRequest",
    "Ticket",
    "Transaction",
    "Upload",
    "User",
    "UserSession",
    "Vendor",
    "VendorQuote",
    "WorkflowDefinition",
    "WorkflowExecution",
    "WorkflowStep",
]
