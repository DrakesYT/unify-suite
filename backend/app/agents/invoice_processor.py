"""Invoice Processor (finance): reads invoice text and returns the fields as validated JSON.

Matching, duplicate checks and saving are deterministic code in services/finance.py.
"""

from typing import ClassVar

from app.agents.base import UNTRUSTED_TEXT_RULE, Agent, wrap_document
from app.config import DOCUMENT_MAX_CHARS
from app.llm import LLMClient
from app.models.enums import Department
from app.schemas.finance import InvoiceFields, InvoiceText

SYSTEM_PROMPT = f"""You extract fields from one supplier invoice.
{UNTRUSTED_TEXT_RULE}
Rules:
- number: the invoice number exactly as printed.
- invoice_date: the issue date as YYYY-MM-DD.
- vendor_name: the company that issued the invoice (not the customer it is billed to).
- total_amount: the final total due, digits and a decimal point only, no thousands separators.
- currency: the ISO 4217 code (USD, EUR, PKR, ...). Infer it from symbols if needed.
- po_number: the purchase order number the invoice references, or null if there is none."""


class InvoiceProcessor(Agent[InvoiceText, InvoiceFields]):
    name: ClassVar[str] = "invoice_processor"
    department = Department.finance
    input_model = InvoiceText
    output_model = InvoiceFields
    tools = frozenset({"read_upload", "get_po", "save_invoice", "flag_anomaly"})
    max_llm_calls = 1
    timeout_s = 60.0

    def run(self, data: InvoiceText, llm: LLMClient) -> InvoiceFields:
        text = data.text[:DOCUMENT_MAX_CHARS]
        return llm.complete_json(
            InvoiceFields, SYSTEM_PROMPT, wrap_document(text), timeout_s=self.timeout_s
        )
