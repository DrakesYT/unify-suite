"""Ticket Investigator (support): classifies a ticket, then investigates it against order history.

Two model calls (classify, investigate). Code checks that every order number the model cites
really is one of this customer's orders.
"""

from datetime import date
from typing import ClassVar

from app.agents.base import UNTRUSTED_TEXT_RULE, Agent, wrap_document
from app.agents.writing_checks import check_writing
from app.config import DOCUMENT_MAX_CHARS
from app.llm import LLMClient, LLMOutputError
from app.models.enums import Department
from app.schemas.support import (
    Investigation,
    InvestigationInput,
    TicketClassification,
    TicketText,
)

CLASSIFY_PROMPT = f"""You triage customer support tickets.
{UNTRUSTED_TEXT_RULE}
category: billing (charges, invoices), technical (product not working), shipping (delivery),
refund (customer wants money back), legal (threats of legal action, contracts, data requests),
account (login, profile), other.
urgency: critical (outage, legal deadline, safety), high (blocked customer, money at stake),
normal (needs an answer soon), low (question or feedback)."""

INVESTIGATE_PROMPT = f"""You investigate a support ticket using the customer's order history.
{UNTRUSTED_TEXT_RULE}
Give the most likely causes, each backed by order numbers from the history. Only cite order numbers
that appear in the history. Suggest the next step for the support team and draft a short, polite
reply to the customer. Do not promise refunds or legal outcomes; a manager approves those."""


def _ticket_doc(title: str, description: str) -> str:
    return wrap_document(f"Title: {title}\n\n{description}"[:DOCUMENT_MAX_CHARS])


def verify(result: Investigation, data: InvestigationInput) -> Investigation:
    """Only order numbers that exist in this customer's history may be cited."""
    known = {o.order_number.lower(): o.order_number for o in data.orders}

    def _check(numbers: list[str]) -> list[str]:
        cleaned = []
        for number in numbers:
            real = known.get(number.strip().lower())
            if real is None:
                raise LLMOutputError(f"cites an order that is not this customer's: {number!r}")
            cleaned.append(real)
        return list(dict.fromkeys(cleaned))

    causes = [
        c.model_copy(update={"order_numbers": _check(c.order_numbers)})
        for c in result.likely_causes
    ]
    used = _check(result.order_numbers_used + [n for c in causes for n in c.order_numbers])
    check_writing(result.draft_reply, data)  # the customer reads this reply
    return result.model_copy(update={"likely_causes": causes, "order_numbers_used": used})


class _TicketInvestigatorBase:
    """Both calls run as the Ticket Investigator: same name, department, tools and limits."""

    name: ClassVar[str] = "ticket_investigator"
    department = Department.support
    tools = frozenset({"get_ticket", "get_orders", "save_classification", "save_investigation"})
    max_llm_calls = 2
    timeout_s = 30.0


class TicketClassifier(_TicketInvestigatorBase, Agent[TicketText, TicketClassification]):
    """Call 1: category and urgency."""

    input_model = TicketText
    output_model = TicketClassification

    def run(self, data: TicketText, llm: LLMClient) -> TicketClassification:
        return llm.complete_json(
            TicketClassification,
            CLASSIFY_PROMPT,
            _ticket_doc(data.title, data.description),
            timeout_s=self.timeout_s,
        )


class TicketInvestigator(_TicketInvestigatorBase, Agent[InvestigationInput, Investigation]):
    """Call 2: likely causes from the order history, checked against the real orders."""

    input_model = InvestigationInput
    output_model = Investigation

    def run(self, data: InvestigationInput, llm: LLMClient) -> Investigation:
        lines = [
            f"- {o.order_number}: {o.status}, {o.amount}, ordered {o.ordered_on}"
            for o in data.orders
        ]
        history = "\n".join(lines) or "- (no orders)"
        user = (
            f"Today is {date.today().isoformat()}.\n"
            f"Ticket category: {data.category or 'unknown'}\n"
            f"{_ticket_doc(data.title, data.description)}\n\n"
            f"Order history:\n{history}"
        )
        reply = llm.complete_json(Investigation, INVESTIGATE_PROMPT, user, timeout_s=self.timeout_s)
        return verify(reply, data)
