"""Call Analyzer (sales and support): summary, customer sentiment and action items of one call.

The model reads and summarises. Code checks that every quote it gives (for the sentiment and for
each action item) is really in the transcript; a reply that fails is invalid and retried. Talk
share per speaker is counted by code (services/calls.py), not estimated by the model.
"""

from typing import ClassVar

from app.agents.base import UNTRUSTED_TEXT_RULE, Agent, wrap_document
from app.agents.resume_screener import normalise
from app.config import DOCUMENT_MAX_CHARS
from app.llm import LLMClient, LLMOutputError
from app.models.enums import Department
from app.schemas.calls import CallAnalysis, CallInput

SYSTEM_PROMPT = f"""You analyse one recorded business call between our company ("us") and a
customer or prospect. The context line says which lead or support ticket it is about.
{UNTRUSTED_TEXT_RULE}
Rules:
- summary: 2 or 3 plain sentences: what the customer needs and what was agreed.
- sentiment: how the customer feels by the END of the call (positive, neutral, negative or mixed).
- sentiment_quote: the customer's own words that best show it, copied exactly from the transcript.
- concerns: worries or objections the customer raised, short phrases; empty if none.
- action_items: every concrete follow-up someone committed to. owner is "us" when our company
  promised it and "customer" when the customer did. due is the time exactly as said on the call
  (for example "Friday" or "next week"), or null; never invent a date. quote: the words from the
  transcript where the commitment is made, copied exactly: the whole sentence that names the
  task (at least 4 words), not a reply like "Will do." or "Great".
- Never paraphrase a quote and never add commitments that nobody made."""


MIN_ACTION_QUOTE_WORDS = 4  # "Will do." proves nothing; the sentence naming the task does


def verify(analysis: CallAnalysis, data: CallInput) -> CallAnalysis:
    """Every quote must appear in the transcript (spacing, case and curly quotes ignored), and an
    action item's quote must be long enough to show what was promised."""
    text = normalise(data.transcript)
    for item in analysis.action_items:
        if len(item.quote.split()) < MIN_ACTION_QUOTE_WORDS:
            raise LLMOutputError(f"action item quote is too short to prove it: {item.quote!r}")
    quotes = [analysis.sentiment_quote] + [a.quote for a in analysis.action_items]
    for quote in quotes:
        if normalise(quote) not in text:
            raise LLMOutputError(f"quote is not in the transcript: {quote[:60]!r}")
    return analysis


class CallAnalyzer(Agent[CallInput, CallAnalysis]):
    name: ClassVar[str] = "call_analyzer"
    department = Department.sales  # replaced per call: the lead's or ticket's department
    input_model = CallInput
    output_model = CallAnalysis
    tools = frozenset({"read_upload", "get_call_context", "save_call_analysis"})
    max_llm_calls = 1
    timeout_s = 30.0

    def __init__(self, department: Department) -> None:
        self.department = department  # type: ignore[misc]

    def run(self, data: CallInput, llm: LLMClient) -> CallAnalysis:
        text = data.transcript[:DOCUMENT_MAX_CHARS]
        reply = llm.complete_json(
            CallAnalysis,
            SYSTEM_PROMPT,
            # The context holds ticket titles, which customers write: fence it with the transcript.
            wrap_document(f"Context: {data.context}\n\n{text}"),
            timeout_s=self.timeout_s,
        )
        return verify(reply, data.model_copy(update={"transcript": text}))
