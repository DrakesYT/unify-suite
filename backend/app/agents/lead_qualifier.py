"""Lead Qualifier (sales): rates a lead hot, warm or cold and explains why, citing lead fields."""

from typing import ClassVar

from app.agents.base import UNTRUSTED_TEXT_RULE, Agent, wrap_document
from app.llm import LLMClient
from app.models.enums import Department
from app.schemas.sales import MIN_REASON_WORDS, LeadForQualification, QualificationResult

SYSTEM_PROMPT = f"""You qualify B2B sales leads for an enterprise software company.
{UNTRUSTED_TEXT_RULE}
Rate the lead:
- hot: clear need, budget or timeline, and a decision maker involved; likely to buy soon.
- warm: real interest but something important is missing (budget, timeline or authority).
- cold: little evidence of need, very early research, or a poor fit.
Write the reason in at least {MIN_REASON_WORDS} words of plain sentences, using only lead data.
List in cited_fields every field your reason relies on (company, email_domain, status, priority,
value, notes)."""


class LeadQualifier(Agent[LeadForQualification, QualificationResult]):
    name: ClassVar[str] = "lead_qualifier"
    department = Department.sales
    input_model = LeadForQualification
    output_model = QualificationResult
    tools = frozenset({"get_lead", "update_lead_status"})
    max_llm_calls = 1
    timeout_s = 20.0

    def run(self, data: LeadForQualification, llm: LLMClient) -> QualificationResult:
        return llm.complete_json(
            QualificationResult,
            SYSTEM_PROMPT,
            wrap_document(data.model_dump_json(indent=1)),
            timeout_s=self.timeout_s,
        )
