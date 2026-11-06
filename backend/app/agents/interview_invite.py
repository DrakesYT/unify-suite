"""Interview Invite Writer (hr): drafts an interview invitation offering code-picked times.

Code decides who may be invited (screened score) and which times are free. The agent only
writes the email, and must list every offered time exactly as given; an HR manager approves
before it is sent (services/outbound.py).
"""

from typing import ClassVar

from app.agents.base import UNTRUSTED_TEXT_RULE, Agent, wrap_document
from app.agents.outreach_writer import check_draft
from app.llm import LLMClient, LLMOutputError
from app.models.enums import Department
from app.schemas.outreach import EmailDraft, InterviewInviteInput

SYSTEM_PROMPT = f"""You write a short, warm interview invitation from an employer to a candidate.
{UNTRUSTED_TEXT_RULE}
Rules:
- Use only the facts in the document. Name the job title. You may mention one or two of the
  matched skills as the reason for the invite. Never invent salary, benefits, interviewers or steps.
- Offer exactly the times in slot_options. Copy each one EXACTLY as written, character for
  character, each on its own line starting with "- ". Do not add, drop, reword or convert any time.
- Say the interview is a {{duration}}-minute {{format}} and ask the candidate to reply with the
  option that suits them.
- Body: under 150 words, plain text.
- Do NOT write a greeting line or a sign-off: they are added automatically.
- No links, no email addresses, no phone numbers and no placeholders like [Name] or {{{{...}}}}.
- Subject: include the job title, under 80 characters."""


def check_slots(draft: EmailDraft, data: InterviewInviteInput) -> EmailDraft:
    """Every offered time must appear exactly; the model may not change a time."""
    missing = [s for s in data.slot_options if s not in draft.body]
    if missing:
        raise LLMOutputError(f"invite does not list the offered time {missing[0]!r} exactly")
    return draft


class InterviewInviteWriter(Agent[InterviewInviteInput, EmailDraft]):
    name: ClassVar[str] = "interview_invite_writer"
    department = Department.hr
    input_model = InterviewInviteInput
    output_model = EmailDraft
    tools = frozenset({"get_candidate", "find_free_slots", "save_email_draft"})
    max_llm_calls = 1
    timeout_s = 30.0

    def run(self, data: InterviewInviteInput, llm: LLMClient) -> EmailDraft:
        prompt = SYSTEM_PROMPT.replace("{duration}", str(data.duration_minutes)).replace(
            "{format}", data.interview_format
        )
        reply = llm.complete_json(
            EmailDraft,
            prompt,
            wrap_document(data.model_dump_json(indent=1)),
            timeout_s=self.timeout_s,
        )
        return check_slots(check_draft(reply, data.job_title, data), data)
