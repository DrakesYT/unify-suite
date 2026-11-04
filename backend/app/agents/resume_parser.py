"""Resume parser (hr): reads a resume and returns name, skills, years of experience, education."""

from datetime import date
from typing import ClassVar

from app.agents.base import UNTRUSTED_TEXT_RULE, Agent, wrap_document
from app.config import DOCUMENT_MAX_CHARS
from app.llm import LLMClient
from app.models.enums import Department
from app.schemas.hr import ResumeProfile, ResumeText

SYSTEM_PROMPT = f"""You read one candidate resume and extract facts from it.
{UNTRUSTED_TEXT_RULE}
- name: the candidate's full name.
- email: their email address, or null.
- skills: concrete skills, tools, languages and technologies the resume names (short labels).
- years_experience: total years of professional work, from the job history dates; 0 if none.
- education: one short line per degree or certificate."""


class ResumeParser(Agent[ResumeText, ResumeProfile]):
    name: ClassVar[str] = "resume_parser"
    department = Department.hr
    input_model = ResumeText
    output_model = ResumeProfile
    tools = frozenset({"read_upload", "save_candidate"})
    max_llm_calls = 1
    timeout_s = 30.0

    def run(self, data: ResumeText, llm: LLMClient) -> ResumeProfile:
        return llm.complete_json(
            ResumeProfile,
            SYSTEM_PROMPT,
            f"Today is {date.today().isoformat()}.\n"
            + wrap_document(data.text[:DOCUMENT_MAX_CHARS]),
            timeout_s=self.timeout_s,
        )
