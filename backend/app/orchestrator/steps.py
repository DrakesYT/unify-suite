"""Workflow B step handlers. Each returns the step's output, or WaitForApproval to pause.

Handlers read their input from the workflow input and earlier step outputs (stored in the DB),
so a retry reuses exactly what the first attempt saw.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.runner import TaskContext, ToolUser, call_tool
from app.agents.verification import VerificationAgent
from app.llm import LLMClient
from app.models import ApprovalRequest, Invoice, Payment, Upload, WorkflowExecution, WorkflowStep
from app.models.enums import Department, InvoiceStatus, Role
from app.money import format_minor
from app.orchestrator.templates import Finished
from app.schemas.finance import InvoiceFields, PoSnapshot
from app.schemas.workflows import LinkSnapshot
from app.services import approvals, finance, procurement

ORCHESTRATOR = ToolUser(
    name="orchestrator",
    department=Department.finance,
    tools=frozenset({"get_po", "write_discrepancy_report", "create_approval", "submit_payment"}),
)
VERIFIER = VerificationAgent()


class StepError(Exception):
    """The step cannot succeed with this input (retrying will not help until something changes)."""


@dataclass(frozen=True)
class WaitForApproval:
    approval_id: uuid.UUID


@dataclass
class StepRun:
    db: Session
    llm: LLMClient | None  # None when no model is configured: only F1 needs one
    ctx: TaskContext
    execution: WorkflowExecution
    step: WorkflowStep
    done: Finished

    def output(self, key: str) -> dict[str, Any]:
        return self.done[key][1] or {}


StepResult = dict[str, Any] | WaitForApproval


def load_po(run: StepRun) -> StepResult:
    po_number = run.execution.input["po_number"]
    po = call_tool(
        run.db,
        ORCHESTRATOR,
        "get_po",
        {"po_number": po_number},
        lambda: procurement.po_snapshot(run.db, po_number),
        run.ctx,
    )
    if po is None:
        raise StepError(f"Purchase order {po_number} was not found")
    return po.model_dump(mode="json")


def extract_invoice(run: StepRun) -> StepResult:
    upload = run.db.get(Upload, uuid.UUID(run.execution.input["upload_id"]))
    if upload is None:
        raise StepError("The uploaded invoice file is missing")
    if run.llm is None:
        raise StepError("The AI service is not configured, so the invoice cannot be read")
    fields, suspicious = finance.extract_invoice(run.db, run.llm, upload, run.ctx)
    return fields.model_dump(mode="json") | {"suspicious_text": suspicious}


def match_invoice(run: StepRun) -> StepResult:
    upload = run.db.get(Upload, uuid.UUID(run.execution.input["upload_id"]))
    assert upload is not None
    fields = InvoiceFields.model_validate(run.output("F1"))
    po = PoSnapshot.model_validate(run.output("P1"))
    match, invoice, anomalies = finance.record_invoice(
        run.db, upload, fields, po, run.ctx, po_chosen=True
    )
    if invoice is None or match is None:
        if fields.document_type != "invoice":
            kind = fields.document_type.replace("_", " ")
            raise StepError(
                f"This document is a {kind}, not an invoice, so there is nothing to pay; it is "
                "recorded as an anomaly"
            )
        if fields.total_amount < 0:
            raise StepError("The total is negative, so there is nothing to pay; it is recorded")
        kinds = ", ".join(a.kind.replace("_", " ") for a in anomalies)
        raise StepError(f"Invoice was not saved ({kinds}); it is recorded as an anomaly")
    return {
        "match_status": match.status,
        "differences": [d.model_dump(mode="json") for d in match.differences],
        "invoice_id": str(invoice.id),
        "invoice_number": invoice.number,
        "vendor_name": fields.vendor_name,
        "amount_minor": invoice.amount_minor,
        "currency": invoice.currency,
    }


def _describe(diff: dict[str, Any], currency: str) -> str:
    if diff["field"] == "amount_minor":
        invoice, po = format_minor(diff["invoice"], currency), format_minor(diff["po"], currency)
        return f"amount: invoice {invoice}, PO {po}"
    if diff["field"] == "line_items_total":
        stated, real = format_minor(diff["invoice"], currency), format_minor(diff["po"], currency)
        return f"line items add up to {real}, but the total due says {stated}"
    if diff["field"] == "line_math":
        line = diff["invoice"]
        return (
            f"line '{line['description']}': {line['quantity']} x {line['unit_price']} = "
            f"{diff['po']}, but the invoice says {line['amount']}"
        )
    if diff["field"] == "po_reference":
        return f"the invoice refers to {diff['invoice']}, but this run is for {diff['po']}"
    if diff["field"] == "po_already_invoiced":
        earlier = diff["po"]
        numbers = ", ".join(earlier["invoices"])
        billed = format_minor(earlier["billed_minor"], currency)
        order = format_minor(earlier["po_amount_minor"], currency)
        return (
            f"this purchase order ({order}) was already invoiced: {numbers} ({billed}); "
            "paying this one too would pay more than the order"
        )
    if diff["field"] == "po_status":
        status = (diff["po"] or "unknown").replace("_", " ")
        return f"PO status: {status} (a PO must be approved first)"
    return f"{diff['field']}: invoice {diff['invoice']}, PO {diff['po']}"


def discrepancy_report(run: StepRun) -> StepResult:
    f2, po = run.output("F2"), run.output("P1")

    def _report() -> dict[str, Any]:
        lines = [_describe(d, f2["currency"]) for d in f2["differences"]]
        return {
            "summary": f"Invoice {f2['invoice_number']} differs from {po['po_number']} in "
            f"{len(lines)} field(s)",
            "lines": lines,
            "differences": f2["differences"],
        }

    return call_tool(
        run.db,
        ORCHESTRATOR,
        "write_discrepancy_report",
        {"invoice_id": f2["invoice_id"]},
        _report,
        run.ctx,
    )


def request_approval(run: StepRun) -> StepResult:
    f2, po = run.output("F2"), run.output("P1")
    report = run.output("F3") if "F3" in run.done else None
    payload = {
        "invoice_id": f2["invoice_id"],
        "invoice_number": f2["invoice_number"],
        "vendor_name": f2["vendor_name"],
        "po_number": po["po_number"],
        "amount_minor": f2["amount_minor"],
        "currency": f2["currency"],
        "match_status": f2["match_status"],
        "discrepancies": report["lines"] if report else [],
        "suspicious_text": run.output("F1").get("suspicious_text", []),
    }

    def _create() -> ApprovalRequest:
        return approvals.create_approval(
            run.db,
            action="pay_invoice",
            payload=payload,
            required_role=Role.manager,
            department=Department.finance,
            requested_by_id=run.execution.started_by_id,
            execution_id=run.execution.id,
            step_id=run.step.id,
        )

    approval = call_tool(
        run.db, ORCHESTRATOR, "create_approval", {"invoice_id": f2["invoice_id"]}, _create, run.ctx
    )
    return WaitForApproval(approval.id)


def submit_payment(run: StepRun) -> StepResult:
    invoice_id = uuid.UUID(run.output("F2")["invoice_id"])
    approval_id = uuid.UUID(run.output("A1")["approval_id"])

    def _pay() -> dict[str, Any]:
        payment = finance.submit_payment(
            run.db, invoice_id, approval_id, run.ctx.actor.id, run.execution.id
        )
        return {
            "payment_id": str(payment.id),
            "amount_minor": payment.amount_minor,
            "currency": payment.currency,
        }

    return call_tool(
        run.db, ORCHESTRATOR, "submit_payment", {"invoice_id": str(invoice_id)}, _pay, run.ctx
    )


def verify(run: StepRun) -> StepResult:
    def _snapshot() -> LinkSnapshot:
        f2, a1 = run.output("F2"), run.output("A1")
        invoice = run.db.get(Invoice, uuid.UUID(f2["invoice_id"]))
        approval = run.db.get(ApprovalRequest, uuid.UUID(a1["approval_id"]))
        payments = (
            list(run.db.scalars(select(Payment).where(Payment.invoice_id == invoice.id)))
            if invoice
            else []
        )
        payment = payments[0] if payments else None
        return LinkSnapshot(
            po_id=run.output("P1").get("id"),
            invoice_id=invoice.id if invoice else None,
            invoice_po_id=invoice.purchase_order_id if invoice else None,
            invoice_status=invoice.status if invoice else None,
            invoice_amount_minor=invoice.amount_minor if invoice else None,
            approval_id=approval.id if approval else None,
            approval_status=approval.status if approval else None,
            approval_invoice_id=(approval.payload or {}).get("invoice_id") if approval else None,
            payment_count=len(payments),
            payment_invoice_id=payment.invoice_id if payment else None,
            payment_approval_id=payment.approval_id if payment else None,
            payment_amount_minor=payment.amount_minor if payment else None,
        )

    snapshot = call_tool(
        run.db,
        VERIFIER,
        "get_workflow_steps",
        {"execution_id": str(run.execution.id)},
        _snapshot,
        run.ctx,
    )
    result = VERIFIER.check(run.db, snapshot, run.ctx)
    return result.model_dump(mode="json")


def mark_invoice_rejected(db: Session, step_outputs: dict[str, Any], actor_id: uuid.UUID) -> None:
    """Effect of a rejection: the invoice will not be paid."""
    invoice_id = (step_outputs.get("F2") or {}).get("invoice_id")
    if invoice_id:
        finance.set_invoice_status(db, uuid.UUID(invoice_id), InvoiceStatus.rejected, actor_id)


HANDLERS: dict[str, Callable[[StepRun], StepResult]] = {
    "P1": load_po,
    "F1": extract_invoice,
    "F2": match_invoice,
    "F3": discrepancy_report,
    "A1": request_approval,
    "F4": submit_payment,
    "V1": verify,
}
