"""Brief Writer: turns the facts code collected into a short morning brief for one person.

It only words things. Code gathers the facts, and code checks the draft: every number in it must
come from a fact, and the facts it ranks must exist. A draft that fails is retried, then replaced
by a brief written by code.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from app.agents.base import UNTRUSTED_TEXT_RULE, Agent, wrap_document
from app.llm import LLMClient, LLMOutputError
from app.models.enums import Department
from app.schemas.brief import BriefDraft, BriefInput

SYSTEM_PROMPT = f"""You are Aura, the assistant in a company operations app. Write a short morning
brief for the person described in the document, using ONLY the numbered facts in it.
{UNTRUSTED_TEXT_RULE}
Rules:
- headline: one line, under 90 characters, no greeting, says what matters most today.
- summary: at most 2 short sentences, under 260 characters, addressed to the person as "you".
  Follow the "focus" line to decide what comes first. The top facts are listed under your
  summary, so do not restate all of them. No greeting, no sign-off, no markdown.
- Keep it simple: this is a quick summary, not an analysis.
- Write every number as digits, exactly as it appears in the facts. Never compute totals,
  percentages or dates that are not written in a fact. Never add facts, names or advice that
  are not supported by the facts.
- top: the ids of up to 3 facts that matter most for this person, most important first."""

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}  # fmt: skip
_WORD = re.compile(r"\b(" + "|".join(_WORDS) + r")\b", re.IGNORECASE)


def numbers_in(text: str) -> set[Decimal]:
    """'1,250.00 USD and 13 days' → {1250, 13}. Spelled-out two..twelve count too."""
    found: set[Decimal] = set()
    for raw in _NUMBER.findall(text):
        try:
            found.add(Decimal(raw.replace(",", "")).normalize())
        except InvalidOperation:
            continue
    found.update(Decimal(_WORDS[w.lower()]) for w in _WORD.findall(text))
    return found


def check_brief(draft: BriefDraft, data: BriefInput) -> BriefDraft:
    """Reject drafts that state a number no fact contains, or rank facts that don't exist."""
    allowed = numbers_in(" ".join(f.text for f in data.facts))
    invented = numbers_in(f"{draft.headline} {draft.summary}") - allowed
    if invented:
        shown = ", ".join(sorted(f"{n:f}" for n in invented))
        raise LLMOutputError(f"brief states numbers not in the facts: {shown}")
    ids = {f.id for f in data.facts}
    top = list(dict.fromkeys(i for i in draft.top if i in ids))
    return BriefDraft(headline=draft.headline.strip(), summary=draft.summary.strip(), top=top)


class BriefWriter(Agent[BriefInput, BriefDraft]):
    name: ClassVar[str] = "brief_writer"
    department = Department.sales  # replaced per call by the reader's own department
    input_model = BriefInput
    output_model = BriefDraft
    tools = frozenset()
    requires_write = False  # it only words facts the reader may already see
    max_llm_calls = 1
    timeout_s = 20.0

    def __init__(self, department: Department) -> None:
        self.department = department  # type: ignore[misc]

    def run(self, data: BriefInput, llm: LLMClient) -> BriefDraft:
        reply = llm.complete_json(
            BriefDraft,
            SYSTEM_PROMPT,
            wrap_document(data.model_dump_json(indent=1)),
            timeout_s=self.timeout_s,
        )
        return check_brief(reply, data)
