"""Outreach Writer (sales): drafts a first email to a qualified lead.

It only drafts. Code adds the greeting and signature, a sales manager must approve, and only
then does the mailer send it.
"""

import re
from typing import ClassVar

from app.agents.base import UNTRUSTED_TEXT_RULE, Agent, wrap_document
from app.llm import LLMClient, LLMOutputError
from app.models.enums import Department
from app.schemas.outreach import OutreachDraft, OutreachInput

SYSTEM_PROMPT = f"""You write a short first outreach email from a B2B software company to a lead.
{UNTRUSTED_TEXT_RULE}
Rules:
- Use only the facts in the document. Never invent prices, discounts, deadlines, names or claims.
- Write as {{seller}}. Mention the lead's company by name.
- Body: 2 to 4 short paragraphs, under 180 words, plain text. Propose one concrete next step
  (for example a 30-minute call).
- Do NOT write a greeting line or a sign-off: they are added automatically.
- No links, no email addresses, no phone numbers and no placeholders like [Name] or {{{{...}}}}.
- Subject: specific to the lead, under 80 characters."""

# Things a sendable draft must never contain.
_FORBIDDEN = {
    "placeholder": re.compile(r"\[[^\]]{1,40}\]|\{\{|\}\}|<[^>]{1,40}>"),
    "link": re.compile(r"https?://|www\.", re.IGNORECASE),
    "email address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "greeting or sign-off": re.compile(
        r"^\s*(hi|hello|dear)\b|\b(best regards|kind regards|sincerely|cheers),?\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
}


_SUFFIXES = {"co", "co.", "corp", "corp.", "inc", "inc.", "ltd", "ltd.", "llc", "group", "pvt"}


def company_core(company: str) -> str:
    """'Karachi Logistics Group' → 'karachi logistics' (drafts often drop the legal suffix)."""
    words = company.lower().split()
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)


def check_draft(draft: OutreachDraft, data: OutreachInput) -> OutreachDraft:
    """Reject drafts that could embarrass us if sent as written (the runner retries)."""
    text = f"{draft.subject}\n{draft.body}"
    for what, pattern in _FORBIDDEN.items():
        if pattern.search(text):
            raise LLMOutputError(f"draft contains a {what}")
    if company_core(data.company) not in text.lower():
        raise LLMOutputError("draft does not mention the lead's company")
    return OutreachDraft(subject=draft.subject.strip(), body=draft.body.strip())


class OutreachWriter(Agent[OutreachInput, OutreachDraft]):
    name: ClassVar[str] = "outreach_writer"
    department = Department.sales
    input_model = OutreachInput
    output_model = OutreachDraft
    tools = frozenset({"get_lead", "save_email_draft"})
    max_llm_calls = 1
    timeout_s = 30.0

    def run(self, data: OutreachInput, llm: LLMClient) -> OutreachDraft:
        prompt = SYSTEM_PROMPT.replace("{seller}", data.seller_company)
        reply = llm.complete_json(
            OutreachDraft,
            prompt,
            wrap_document(data.model_dump_json(indent=1)),
            timeout_s=self.timeout_s,
        )
        return check_draft(reply, data)
