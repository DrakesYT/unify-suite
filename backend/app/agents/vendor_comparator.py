"""Vendor Comparator (procurement): explains a vendor ranking that code has already computed.

The ranking and scores are deterministic (services/procurement.py). The model only writes the
reason, and that reason must name the top-ranked vendor.
"""

from typing import ClassVar

from app.agents.base import Agent
from app.llm import LLMClient, LLMOutputError
from app.models.enums import Department
from app.schemas.procurement import ComparisonFacts, ComparisonReason

SYSTEM_PROMPT = """You are a procurement analyst. A ranking of vendors for one purchase request has
already been computed from price, lead time and on-time delivery record. Do not change the order.
Explain in two or three sentences why the vendor ranked 1 is recommended over the others, naming it
and citing the concrete numbers (total price, lead time, on-time rate).
Say so if it is over budget."""


class VendorComparator(Agent[ComparisonFacts, ComparisonReason]):
    name: ClassVar[str] = "vendor_comparator"
    department = Department.procurement
    input_model = ComparisonFacts
    output_model = ComparisonReason
    tools = frozenset({"get_request", "list_vendors", "get_vendor_history", "save_comparison"})
    max_llm_calls = 1
    timeout_s = 20.0

    def run(self, data: ComparisonFacts, llm: LLMClient) -> ComparisonReason:
        reply = llm.complete_json(
            ComparisonReason,
            SYSTEM_PROMPT,
            data.model_dump_json(indent=1),
            timeout_s=self.timeout_s,
        )
        top = str(data.ranking[0]["vendor"])
        if top.lower() not in reply.reason.lower():
            raise LLMOutputError(f"the reason does not name the top-ranked vendor {top!r}")
        return reply
