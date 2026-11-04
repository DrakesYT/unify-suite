"""Verification Agent (cross-cutting): rule checks only, no LLM.

Confirms that the purchase order, invoice, approval and payment rows of a workflow are linked.
"""

from typing import ClassVar

from app.agents.base import Agent
from app.llm import LLMClient
from app.models.enums import ApprovalStatus, Department
from app.schemas.workflows import Check, LinkSnapshot, VerificationResult


class VerificationAgent(Agent[LinkSnapshot, VerificationResult]):
    name: ClassVar[str] = "verification_agent"
    department = Department.finance
    input_model = LinkSnapshot
    output_model = VerificationResult
    tools = frozenset({"get_workflow_steps"})
    max_llm_calls = 0
    timeout_s = 5.0

    def run(self, data: LinkSnapshot, llm: LLMClient) -> VerificationResult:
        checks = [
            Check(
                name="invoice linked to purchase order",
                ok=bool(data.po_id) and data.invoice_po_id == data.po_id,
            ),
            Check(
                name="approval is for this invoice",
                ok=bool(data.invoice_id) and data.approval_invoice_id == data.invoice_id,
            ),
        ]
        if data.approval_status == ApprovalStatus.approved:
            checks += [
                Check(name="exactly one payment", ok=data.payment_count == 1),
                Check(
                    name="payment is for this invoice",
                    ok=data.payment_invoice_id == data.invoice_id,
                ),
                Check(
                    name="payment cites the approval",
                    ok=data.payment_approval_id == data.approval_id,
                ),
                Check(
                    name="payment amount equals invoice amount",
                    ok=data.payment_amount_minor is not None
                    and data.payment_amount_minor == data.invoice_amount_minor,
                ),
                Check(
                    name="invoice marked payment_submitted",
                    ok=data.invoice_status == "payment_submitted",
                ),
            ]
        else:
            checks += [
                Check(
                    name="approval was rejected", ok=data.approval_status == ApprovalStatus.rejected
                ),
                Check(name="no payment after rejection", ok=data.payment_count == 0),
                Check(name="invoice marked rejected", ok=data.invoice_status == "rejected"),
            ]
        return VerificationResult(passed=all(c.ok for c in checks), checks=checks)
