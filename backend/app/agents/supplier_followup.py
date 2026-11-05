"""Supplier Follow-up Writer (procurement): drafts a polite chase for a late purchase order.

Code decides the order is late (expected delivery date vs today). The agent only drafts; a
procurement manager approves before anything is sent (services/outbound.py).
"""

from typing import ClassVar

from app.agents.base import UNTRUSTED_TEXT_RULE, Agent, wrap_document
from app.agents.outreach_writer import check_draft
from app.llm import LLMClient
from app.models.enums import Department
from app.schemas.outreach import EmailDraft, SupplierFollowUpInput

SYSTEM_PROMPT = f"""You write a short follow-up email from a buyer to a supplier about a late order.
{UNTRUSTED_TEXT_RULE}
Rules:
- Use only the facts in the document. Quote the PO number, the expected delivery date and how many
  days late the order is. Never invent penalties, contract terms, prices or new deadlines.
- Tone: polite, factual and firm. Ask for (1) a confirmed new delivery date and (2) the reason for
  the delay, and ask for a reply within two business days.
- Body: 2 to 3 short paragraphs, under 150 words, plain text.
- Do NOT write a greeting line or a sign-off: they are added automatically.
- No links, no email addresses, no phone numbers and no placeholders like [Name] or {{{{...}}}}.
- Subject: include the PO number, under 80 characters."""


class SupplierFollowUpWriter(Agent[SupplierFollowUpInput, EmailDraft]):
    name: ClassVar[str] = "supplier_followup_writer"
    department = Department.procurement
    input_model = SupplierFollowUpInput
    output_model = EmailDraft
    tools = frozenset({"get_order", "save_email_draft"})
    max_llm_calls = 1
    timeout_s = 30.0

    def run(self, data: SupplierFollowUpInput, llm: LLMClient) -> EmailDraft:
        reply = llm.complete_json(
            EmailDraft,
            SYSTEM_PROMPT,
            wrap_document(data.model_dump_json(indent=1)),
            timeout_s=self.timeout_s,
        )
        return check_draft(reply, data.po_number)
