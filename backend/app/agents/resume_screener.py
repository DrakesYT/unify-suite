"""Resume Screener (hr): finds evidence in a resume for each job requirement.

The model only points at evidence. Code checks that every quote is really in the resume and
that it names a real requirement; a reply that fails is treated as invalid (and retried).
The score itself is computed in services/hr.py from the verified evidence.
"""

import re
from datetime import date
from typing import ClassVar

from app.agents.base import UNTRUSTED_TEXT_RULE, Agent, wrap_document
from app.config import DOCUMENT_MAX_CHARS
from app.llm import LLMClient, LLMOutputError
from app.models.enums import Department
from app.schemas.hr import EXPERIENCE, EvidenceItem, ScreeningAssessment, ScreeningInput

SYSTEM_PROMPT = f"""You screen one resume against one job.
{UNTRUSTED_TEXT_RULE}
For every required skill the resume really demonstrates, add an evidence item whose
`requirement` is that skill exactly as listed and whose `quote` is copied word for word from the
resume (a short phrase or sentence). Add one item with requirement "{EXPERIENCE}" quoting the
work history that best shows their experience. Never paraphrase a quote and never invent one;
leave a skill out if the resume does not show it. Then write a short, fair summary."""

# Typographic quotes and dashes (by code point) are compared as their plain forms.
_SMART = str.maketrans(
    {0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-"}
)


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_SMART)).strip().lower()


def verify(assessment: ScreeningAssessment, data: ScreeningInput) -> ScreeningAssessment:
    """Keep the model honest: real requirements only, quotes that appear in the resume."""
    resume = normalise(data.resume_text)
    canonical = {s.lower(): s for s in data.required_skills} | {EXPERIENCE: EXPERIENCE}
    checked: list[EvidenceItem] = []
    for item in assessment.evidence:
        requirement = canonical.get(item.requirement.strip().lower())
        if requirement is None:
            raise LLMOutputError(f"evidence names an unknown requirement: {item.requirement!r}")
        quote = item.quote.strip().strip("\"'").removesuffix("...").strip()
        if normalise(quote) not in resume:
            raise LLMOutputError(f"evidence quote is not in the resume: {item.quote[:60]!r}")
        checked.append(EvidenceItem(requirement=requirement, quote=quote))
    return ScreeningAssessment(evidence=checked, summary=assessment.summary)


class ResumeScreener(Agent[ScreeningInput, ScreeningAssessment]):
    name: ClassVar[str] = "resume_screener"
    department = Department.hr
    input_model = ScreeningInput
    output_model = ScreeningAssessment
    tools = frozenset({"get_job", "read_upload", "save_candidate_score"})
    max_llm_calls = 1
    timeout_s = 30.0

    def run(self, data: ScreeningInput, llm: LLMClient) -> ScreeningAssessment:
        job = (
            f"Today is {date.today().isoformat()}.\n"
            f"Job: {data.job_title}\nRequired skills: {', '.join(data.required_skills)}\n"
            f"Minimum years of experience: {data.min_years}\n\n"
        )
        resume = wrap_document(data.resume_text[:DOCUMENT_MAX_CHARS])
        reply = llm.complete_json(
            ScreeningAssessment, SYSTEM_PROMPT, job + resume, timeout_s=self.timeout_s
        )
        return verify(reply, data)
