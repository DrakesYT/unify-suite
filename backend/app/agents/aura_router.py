"""Aura Router: turns a chat message into one route (an agent or a workflow) and its target.

The model only picks from a fixed list. Finding the record, checking permissions and running
the department agent are done by code in services/aura.py.
"""

from typing import ClassVar

from app.agents.base import Agent
from app.llm import LLMClient
from app.models.enums import Department
from app.schemas.aura import ROUTES, AuraDecision, AuraRequest

SYSTEM_PROMPT = "You are Aura, the assistant of an enterprise workforce platform. " + (
    "Read the user's message and pick exactly one route from this list:\n"
    + "\n".join(f"- {key}: {desc}" for key, desc in ROUTES.items())
    + "\nSet `target` to the words that name the record they mean (a company, job title, "
    "ticket subject or purchase item), or null. Write a one-sentence friendly `reply` saying "
    "what you will do. If nothing fits, use route `none` and say what you can help with."
)


class AuraRouter(Agent[AuraRequest, AuraDecision]):
    name: ClassVar[str] = "aura_router"
    department = Department.sales  # replaced per call by the user's own department
    requires_write = False  # routing changes nothing; the delegated agent checks its own rights
    input_model = AuraRequest
    output_model = AuraDecision
    tools = frozenset({"list_agents", "find_record", "start_workflow"})
    max_llm_calls = 1
    timeout_s = 10.0

    def __init__(self, department: Department) -> None:
        self.department = department  # type: ignore[misc]

    def run(self, data: AuraRequest, llm: LLMClient) -> AuraDecision:
        return llm.complete_json(
            AuraDecision, SYSTEM_PROMPT, data.message, timeout_s=self.timeout_s
        )
