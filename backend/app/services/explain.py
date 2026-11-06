"""The "Why?" drawer: how one AI result came about, read back from stored records.

What the AI read is rebuilt with the same function the service used to build the agent's input.
Agent calls store only a SHA-256 of their input, so when a logged call has the same hash, the input
shown is provably the one the model saw; if the record was edited since, the drawer says so.
"""

import uuid
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.runner import input_hash
from app.agents.writing_checks import style_findings
from app.errors import ApiError
from app.models import (
    AgentTask,
    ApprovalRequest,
    AuditLog,
    Candidate,
    CandidateScore,
    OutboundEmail,
    Upload,
    User,
    WorkflowExecution,
    WorkflowStep,
)
from app.models.enums import Department
from app.money import format_minor
from app.schemas.calls import CallAnalysis, CallInput
from app.schemas.explain import AiCall, Explanation, Field, Person
from app.schemas.hr import EXPERIENCE, EvidenceItem, ScreeningInput
from app.schemas.procurement import RankedVendor, VendorComparison
from app.schemas.support import InvestigationInput, OrderFact, TicketText
from app.services import calls, hr, procurement, sales, support
from app.services.authz import can_access
from app.services.uploads import read_text

EXCERPT_CHARS = 700

# audit action → what the person did, in words
DID = {
    "lead.created": "added the lead",
    "lead.updated": "edited the lead",
    "lead.qualified": "ran the Lead Qualifier",
    "candidate.added": "uploaded the resume",
    "candidate.screened": "ran the Resume Screener",
    "ticket.created": "opened the ticket",
    "ticket.classified": "had the ticket classified",
    "ticket.investigated": "ran the Ticket Investigator",
    "ticket.escalated": "asked a manager to approve an escalation",
    "purchase_request.created": "raised the purchase request",
    "purchase_request.updated": "edited the request",
    "purchase_request.approved": "approved the request",
    "purchase_request.rejected": "rejected the request",
    "quote.saved": "entered a vendor quote",
    "request.compared": "ran the Vendor Comparator",
    "workflow.started": "uploaded the invoice and started the check",
    "workflow.retried": "retried a failed step",
    "approval.requested": "asked for a manager's approval",
    "approval.approved": "approved",
    "approval.rejected": "rejected",
    "email.drafted": "had the email drafted",
    "email.edited": "edited the draft",
    "email.sent": "sent the email",
    "email.failed": "tried to send it (failed)",
    "call.added": "added the call transcript",
    "call.analyzed": "ran the Call Analyzer",
}


def _cut(text: str, limit: int = EXCERPT_CHARS) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def _require(user: User, department: Department) -> None:
    if not can_access(user, department, write=False):
        raise ApiError(403, "forbidden", f"Your role cannot see {department} data")


def _calls(db: Session, agent: str, data: BaseModel | None, **where: Any) -> list[AiCall]:
    """Logged attempts of `agent` whose input hash equals the input we rebuilt."""
    stmt = select(AgentTask).where(AgentTask.agent == agent, AgentTask.tool.is_(None))
    if data is not None:
        stmt = stmt.where(AgentTask.input_hash == input_hash(data))
    for column, value in where.items():
        stmt = stmt.where(getattr(AgentTask, column) == value)
    return [
        AiCall(
            task_id=t.id,
            agent=t.agent,
            at=t.created_at,
            attempt=t.attempt,
            status=t.status,
            duration_ms=t.duration_ms,
            error=t.error,
        )
        for t in db.scalars(stmt.order_by(AgentTask.created_at))
    ]


def _people(db: Session, refs: Iterable[tuple[str, Any]]) -> list[Person]:
    """Audit rows about these (entity, id) pairs, oldest first, in words."""
    pairs = [(entity, str(eid)) for entity, eid in refs if eid is not None]
    if not pairs:
        return []
    rows = db.execute(
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(or_(*((AuditLog.entity == e) & (AuditLog.entity_id == i) for e, i in pairs)))
        .order_by(AuditLog.at, AuditLog.id)
    ).all()
    people = []
    for log, name in rows:
        did = DID.get(log.action)
        if did is None:
            continue  # routine bookkeeping (status flips, flags) is in the Command Center
        if log.action.startswith("approval.") and log.detail.get("comment"):
            did += f': "{log.detail["comment"]}"'
        people.append(Person(at=log.at, who=name or "System", did=did))
    return people


def _approval_people(db: Session, approval: ApprovalRequest | None) -> list[tuple[str, Any]]:
    return [("approval_request", approval.id)] if approval else []


# --- sales ---------------------------------------------------------------------------------


def lead(db: Session, user: User, lead_id: uuid.UUID) -> Explanation:
    _require(user, Department.sales)
    record = sales.get_lead(db, lead_id)
    q = record.qualification
    if not q:
        raise ApiError(409, "no_ai_result", "This lead has not been rated by the AI yet")
    data = sales._for_agent(record)
    calls = _calls(db, sales.AGENT.name, data)
    return Explanation(
        title=f"Why is {record.company} rated {q['rating']}?",
        agent="Lead Qualifier",
        model=q.get("model"),
        ai_read=[
            Field(label=k.replace("_", " "), value=str(v)) for k, v in data.model_dump().items()
        ],
        ai_read_note="Only business fields are sent, never the contact's name or full email.",
        input_verified=bool(calls),
        ai_said=[
            Field(label="rating", value=q["rating"]),
            Field(label="reason", value=q.get("reason", "")),
            Field(label="fields it relied on", value=", ".join(q.get("cited_fields", []))),
        ],
        calls=calls,
        code_decided=[
            "Checked the reply against the rating schema (hot, warm or cold, a reason of 20+ "
            "words, at least one cited field) before saving it.",
            "Saved the rating on the lead. The AI cannot change the lead's status, value or owner.",
        ],
        people=_people(db, [("lead", record.id)]),
    )


# --- hr ------------------------------------------------------------------------------------


def candidate(db: Session, user: User, job_id: uuid.UUID, candidate_id: uuid.UUID) -> Explanation:
    _require(user, Department.hr)
    job = hr.get_job(db, job_id)
    person = db.get(Candidate, candidate_id)
    row = db.scalar(
        select(CandidateScore).where(
            CandidateScore.job_id == job_id, CandidateScore.candidate_id == candidate_id
        )
    )
    if person is None or row is None:
        raise ApiError(404, "not_found", "This candidate has not been screened for this job")
    upload = db.get(Upload, person.file_id) if person.file_id else None
    text = read_text(upload) if upload else ""
    data = ScreeningInput(
        job_title=job.title,
        required_skills=job.required_skills,
        min_years=job.min_years,
        resume_text=text,
    )
    calls = _calls(db, hr.SCREENER.name, data)
    evidence = [EvidenceItem.model_validate(e) for e in row.evidence]
    matched = {e.requirement for e in evidence if e.requirement != EXPERIENCE}
    missing = [s for s in job.required_skills if s not in matched]
    years = person.years_experience or 0
    return Explanation(
        title=f"Why does {person.name} score {row.score} for {job.title}?",
        agent="Resume Screener",
        model=None,
        ai_read=[
            Field(label="job", value=job.title),
            Field(label="required skills", value=", ".join(job.required_skills)),
            Field(label="minimum years", value=str(job.min_years)),
            Field(label="resume (start)", value=_cut(text)),
        ],
        ai_read_note="The resume is treated as untrusted text: it can only shape the quotes "
        "and summary, never the score.",
        input_verified=bool(calls),
        ai_said=[
            Field(label=f'evidence for "{e.requirement}"', value=f'"{e.quote}"') for e in evidence
        ]
        + [Field(label="summary", value=row.summary)],
        calls=calls,
        code_decided=[
            "Checked every quote word for word against the resume; a quote that is not in the "
            "resume makes the reply invalid and it is retried.",
            f"Score = {hr.SKILL_WEIGHT}% x skills with evidence ({len(matched)} of "
            f"{len(job.required_skills)}) + {100 - hr.SKILL_WEIGHT}% x experience ({years} of "
            f"{job.min_years} years) = {row.score}.",
            f"Missing: {', '.join(missing)}." if missing else "Every required skill has evidence.",
        ],
        people=_people(db, [("candidate", person.id), ("candidate_score", row.id)]),
    )


# --- support -------------------------------------------------------------------------------


def ticket(db: Session, user: User, ticket_id: uuid.UUID) -> Explanation:
    _require(user, Department.support)
    record = support.get_ticket(db, ticket_id)
    found = record.investigation
    if not found and not record.category:
        raise ApiError(409, "no_ai_result", "The AI has not looked at this ticket yet")
    approval = db.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.payload["ticket_id"].as_string() == str(record.id))
        .order_by(ApprovalRequest.created_at.desc())
    )
    people = _people(db, [("ticket", record.id), *_approval_people(db, approval)])
    classify_calls = _calls(
        db, support.CLASSIFIER.name, TicketText(title=record.title, description=record.description)
    )
    if not found:
        classified_by_ai = db.scalar(
            select(AuditLog.id).where(
                AuditLog.entity == "ticket",
                AuditLog.entity_id == str(record.id),
                AuditLog.action == "ticket.classified",
            )
        )
        if classified_by_ai is None:
            raise ApiError(
                409, "no_ai_result", "A person set this ticket's category; the AI has not run on it"
            )
        return Explanation(
            title=f"Why is this ticket {record.category}, {record.urgency}?",
            agent="Ticket Classifier",
            model=None,
            ai_read=[
                Field(label="title", value=record.title),
                Field(label="description", value=_cut(record.description)),
            ],
            ai_read_note=None,
            input_verified=bool(classify_calls),
            ai_said=[
                Field(label="category", value=str(record.category)),
                Field(label="urgency", value=str(record.urgency)),
            ],
            calls=classify_calls,
            code_decided=["Accepted only a category and urgency from the fixed lists."],
            people=people,
        )
    orders = [
        OrderFact(
            order_number=o.order_number,
            status=o.status,
            amount=format_minor(o.amount_minor, o.currency),
            ordered_on=o.ordered_at.date().isoformat(),
        )
        for o in (support.customer_orders(db, record.customer_id) if record.customer_id else [])
    ]
    data = InvestigationInput(
        title=record.title,
        description=record.description,
        category=record.category,
        orders=orders,
    )
    calls = _calls(db, support.INVESTIGATOR.name, data)
    causes = found.get("likely_causes", [])
    return Explanation(
        title=f"Why does the AI think this about “{record.title}”?",
        agent="Ticket Investigator",
        model=None,
        ai_read=[
            Field(label="title", value=record.title),
            Field(label="description", value=_cut(record.description)),
            Field(label="category", value=str(record.category)),
            Field(
                label=f"the customer's last {len(orders)} orders",
                value="; ".join(f"{o.order_number} {o.status} {o.amount}" for o in orders)
                or "none",
            ),
        ],
        ai_read_note="The ticket text comes from the customer and is treated as untrusted.",
        input_verified=bool(calls),
        ai_said=[
            Field(
                label=f"likely cause {i + 1}",
                value=c["cause"]
                + (f" (orders {', '.join(c['order_numbers'])})" if c.get("order_numbers") else ""),
            )
            for i, c in enumerate(causes)
        ]
        + [
            Field(label="next step", value=found.get("next_step", "")),
            Field(
                label="draft reply (never sent automatically)", value=found.get("draft_reply", "")
            ),
        ],
        calls=calls,
        code_decided=[
            "Rejected any cited order number that is not one of this customer's orders.",
            "A refund or legal escalation waits for a support manager's approval.",
        ],
        people=people,
    )


# --- procurement ---------------------------------------------------------------------------


def purchase_request(db: Session, user: User, request_id: uuid.UUID) -> Explanation:
    _require(user, Department.procurement)
    request = procurement.get_request(db, request_id)
    if not request.comparison:
        raise ApiError(409, "no_ai_result", "These vendors have not been compared yet")
    result = VendorComparison.model_validate(request.comparison)
    ranking: list[RankedVendor] = result.ranking
    data = procurement._facts(request, ranking)
    calls = _calls(db, procurement.COMPARATOR.name, data)
    return Explanation(
        title=f"Why {ranking[0].vendor_name} for {request.quantity} x {request.item}?",
        agent="Vendor Comparator",
        model=None,
        ai_read=[
            Field(label="item", value=f"{request.quantity} x {request.item}"),
            Field(label="budget", value=data.budget),
        ]
        + [
            Field(
                label=f"#{r.rank} {r.vendor_name}",
                value=f"{format_minor(r.total_minor, r.currency)}, {r.lead_time_days} days, "
                f"{r.on_time_rate * 100:.1f}% on time, score {r.score}",
            )
            for r in ranking
        ],
        ai_read_note="The AI received the ranking after code had computed it. It only explains it.",
        input_verified=bool(calls),
        ai_said=[Field(label="reason", value=result.reason or result.reason_error or "—")],
        calls=calls,
        code_decided=[
            "Ranked the vendors: 50% price + 25% lead time + 25% on-time delivery rate.",
            *(
                f"#{r.rank} {r.vendor_name}: price {r.price_score}, lead time "
                f"{r.lead_time_score}, delivery {r.delivery_score} → {r.score}"
                + (" (over budget)" if r.over_budget else "")
                for r in ranking
            ),
            "Rejected a reason that does not name the top-ranked vendor.",
        ],
        people=_people(db, [("purchase_request", request.id)]),
    )


# --- finance: a supplier payment run (Workflow B) ----------------------------------------


def run(db: Session, user: User, execution_id: uuid.UUID) -> Explanation:
    _require(user, Department.finance)
    execution = db.get(WorkflowExecution, execution_id)
    if execution is None:
        raise ApiError(404, "not_found", "Run not found")
    steps = {
        s.step_key: s
        for s in db.scalars(select(WorkflowStep).where(WorkflowStep.execution_id == execution.id))
    }
    f1 = (steps.get("F1") and steps["F1"].output) or {}
    f2 = (steps.get("F2") and steps["F2"].output) or {}
    f3 = (steps.get("F3") and steps["F3"].output) or {}
    p1 = (steps.get("P1") and steps["P1"].output) or {}
    approval = db.scalar(
        select(ApprovalRequest).where(ApprovalRequest.execution_id == execution.id)
    )
    upload = db.get(Upload, uuid.UUID(execution.input["upload_id"]))
    excerpt = _cut(read_text(upload)) if upload else ""
    calls = _calls(db, "invoice_processor", None, execution_id=execution.id)
    decided = []
    if p1:
        decided.append(
            f"Loaded {p1.get('po_number')} from the database: "
            f"{format_minor(p1['amount_minor'], p1['currency'])}, status {p1.get('status')}."
        )
    if f2:
        decided.append(
            "Matched the invoice to the PO (approved PO, same vendor, currency, amount and PO "
            "reference) and checked that its line items add up to the total: "
            f"{f2['match_status']}."
        )
        decided += [f"Difference: {line}" for line in f3.get("lines", [])]
        decided.append("Checked for a duplicate (same vendor and invoice number): none found.")
    if f1.get("suspicious_text"):
        decided.append(
            f"Found {len(f1['suspicious_text'])} line(s) addressed to the AI; flagged them to the "
            "approver instead of obeying them."
        )
    if execution.result:
        checks = execution.result.get("checks", [])
        ok = sum(c.get("ok", False) for c in checks)
        decided.append(f"Verification: {ok} of {len(checks)} link checks passed.")
    return Explanation(
        title=f"How invoice {f2.get('invoice_number') or f1.get('number') or ''} was checked",
        agent="Invoice Processor",
        model=None,
        ai_read=[
            Field(label="file", value=upload.original_name if upload else "—"),
            Field(label="text (start)", value=excerpt),
        ],
        ai_read_note="The invoice is untrusted: the AI only extracts fields, it cannot approve.",
        input_verified=bool(calls),
        ai_said=[
            Field(label=k.replace("_", " "), value=str(f1[k]))
            for k in (
                "number",
                "vendor_name",
                "invoice_date",
                "total_amount",
                "currency",
                "po_number",
            )
            if k in f1
        ]
        + (
            [Field(label="line items", value=f"{len(f1['line_items'])} read")]
            if f1.get("line_items")
            else []
        ),
        calls=calls,
        code_decided=decided,
        people=_people(db, [("workflow_execution", execution.id), *_approval_people(db, approval)]),
    )


# --- emails drafted by an agent ------------------------------------------------------------

WRITERS = {
    "sales_outreach": ("Outreach Writer", Department.sales),
    "supplier_followup": ("Supplier Follow-up Writer", Department.procurement),
    "payment_reminder": ("Payment Reminder Writer", Department.finance),
    "interview_invite": ("Interview Invite Writer", Department.hr),
}


def email(db: Session, user: User, email_id: uuid.UUID) -> Explanation:
    record = db.get(OutboundEmail, email_id)
    if record is None:
        raise ApiError(404, "not_found", "Email not found")
    _require(user, record.department)
    agent, _ = WRITERS.get(record.kind, ("Email writer", record.department))
    approval = db.get(ApprovalRequest, record.approval_id) if record.approval_id else None
    status = {
        "draft": "Not sent: still a draft.",
        "pending_approval": "Not sent: waiting for a manager's approval.",
        "rejected": "Not sent: a manager rejected it.",
        "failed": f"Approved, but sending failed: {record.error}",
        "sent": f"Sent only after approval, to {record.delivered_to or record.to_address}.",
    }[record.status]
    return Explanation(
        title=f"How “{record.subject}” was written",
        agent=agent,
        model=record.drafted_by_model,
        ai_read=[Field(label="to", value=record.to_address)],
        ai_read_note="The writer gets only the facts code looked up for this record (no other "
        "customer data). Times, amounts and order numbers come from code, not the model.",
        input_verified=False,
        ai_said=[
            Field(label="subject", value=record.subject),
            Field(label="body", value=_cut(record.body, 1200)),
        ],
        calls=[],
        code_decided=[
            "Rejected drafts with links, email addresses or placeholders, or that leave out the "
            "company or order they are about.",
            "Rejected drafts with chatbot phrases or hype words (\u201cI hope this email finds you "
            "well\u201d, \u201cseamless\u201d, a run of em dashes).",
            "Rejected drafts stating any amount, reference, date or day count that is not in the "
            "facts it was given (so $450.00 cannot become $4,500).",
            *(
                [f"Style suggestions in the current text: {', '.join(notes)}."]
                if (notes := sorted({f.rule for f in style_findings(record.body)}))
                else ["No style suggestions in the current text."]
            ),
            "Added the greeting and signature itself.",
            status,
        ],
        people=_people(db, [("outbound_email", record.id), *_approval_people(db, approval)]),
    )


# --- calls (sales leads and support tickets) -----------------------------------------------


def call(db: Session, user: User, call_id: uuid.UUID) -> Explanation:
    record = calls.get_call(db, user, call_id)
    if not record.analysis:
        raise ApiError(409, "no_ai_result", "This call has not been analysed yet")
    upload = db.get(Upload, record.upload_id)
    text = read_text(upload) if upload else ""
    context = calls.context_line(db, record)
    found = _calls(db, "call_analyzer", CallInput(context=context, transcript=text))
    result = CallAnalysis.model_validate(record.analysis)
    shares = calls.speakers(text)
    talk = (
        "Counted talk share from the speaker labels: "
        + ", ".join(f"{s.speaker} {s.share_pct}%" for s in shares)
        + "."
        if shares
        else "The transcript has no speaker labels, so talk share was not counted."
    )
    where = "lead" if record.lead_id else "ticket"
    return Explanation(
        title=f"How “{record.title}” was analysed",
        agent="Call Analyzer",
        model=record.analyzed_by_model,
        ai_read=[
            Field(label="context", value=context),
            Field(label="transcript (start)", value=_cut(text, 1200)),
        ],
        ai_read_note="The transcript is untrusted text: it can only shape the summary and the "
        "quoted action items.",
        input_verified=bool(found),
        ai_said=[
            Field(label="summary", value=result.summary),
            Field(label=f"sentiment: {result.sentiment}", value=f'"{result.sentiment_quote}"'),
            *(Field(label="concern", value=c) for c in result.concerns),
            *(
                Field(
                    label=f"action ({a.owner}{', ' + a.due if a.due else ''})",
                    value=f'{a.task}: "{a.quote}"',
                )
                for a in result.action_items
            ),
        ],
        calls=found,
        code_decided=[
            "Checked every quote word for word against the transcript; a reply with a quote "
            "that is not in it is invalid and retried.",
            talk,
            f"Changed nothing on the {where}: action items are suggestions for people.",
        ],
        people=_people(db, [("call_transcript", record.id)]),
    )
