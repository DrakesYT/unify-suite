"""Payment Reminder Writer (finance): drafts a polite reminder for an overdue customer order.

Code decides the order is overdue and that the customer is not in an open dispute. The agent
only drafts; a finance manager approves before anything is sent (services/outbound.py).
"""

from typing import ClassVar

from app.agents.base import UNTRUSTED_TEXT_RULE, Agent, wrap_document
from app.agents.outreach_writer import check_draft
from app.llm import LLMClient
from app.models.enums import Department
from app.schemas.outreach import EmailDraft, PaymentReminderInput

SYSTEM_PROMPT = f"""You write a short, friendly payment reminder to a business customer.
{UNTRUSTED_TEXT_RULE}
Rules:
- Use only the facts in the document. Quote the order number, the amount, the due date and how
  many days overdue it is. Never invent late fees, interest, legal steps, discounts or deadlines.
- Tone: courteous and helpful; assume an oversight. Ask them to arrange payment or reply if
  something is wrong with the order or the amount.
- Body: 2 to 3 short paragraphs, under 130 words, plain text.
- Do NOT write a greeting line or a sign-off: they are added automatically.
- No links, no email addresses, no phone numbers, no bank details and no placeholders like [Name]
  or {{{{...}}}}.
- Subject: include the order number, under 80 characters."""


class PaymentReminderWriter(Agent[PaymentReminderInput, EmailDraft]):
    name: ClassVar[str] = "payment_reminder_writer"
    department = Department.finance
    input_model = PaymentReminderInput
    output_model = EmailDraft
    tools = frozenset({"get_receivable", "save_email_draft"})
    max_llm_calls = 1
    timeout_s = 30.0

    def run(self, data: PaymentReminderInput, llm: LLMClient) -> EmailDraft:
        reply = llm.complete_json(
            EmailDraft,
            SYSTEM_PROMPT,
            wrap_document(data.model_dump_json(indent=1)),
            timeout_s=self.timeout_s,
        )
        return check_draft(reply, data.order_number)
