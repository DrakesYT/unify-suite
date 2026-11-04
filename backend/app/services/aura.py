"""Aura chat (FR-AURA-01): route the message, find the record, run the department agent."""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.aura_router import AuraRouter
from app.agents.runner import AgentFailed, TaskContext, call_tool, run_agent
from app.errors import ApiError
from app.llm import LLMClient
from app.models import Job, Lead, PurchaseRequest, Ticket, User
from app.models.enums import Department, JobStatus
from app.schemas.aura import ROUTES, AuraDecision, AuraReply, AuraRequest
from app.services import hr, procurement, sales, support
from app.services.authz import can_access

# route → (department agent, department, model, searchable column, app page)
TARGETS = {
    "sales.qualify_lead": ("lead_qualifier", Department.sales, Lead, Lead.company, "/sales"),
    "hr.screen_candidates": ("resume_screener", Department.hr, Job, Job.title, "/hr"),
    "support.investigate_ticket": (
        "ticket_investigator",
        Department.support,
        Ticket,
        Ticket.title,
        "/support",
    ),
    "procurement.compare_vendors": (
        "vendor_comparator",
        Department.procurement,
        PurchaseRequest,
        PurchaseRequest.item,
        "/procurement",
    ),
}


AGENT_NAMES = {
    "lead_qualifier": "Lead Qualifier",
    "resume_screener": "Resume Screener",
    "ticket_investigator": "Ticket Investigator",
    "vendor_comparator": "Vendor Comparator",
}


def _find(db: Session, model, column, target: str | None):  # type: ignore[no-untyped-def]
    stmt = select(model).order_by(model.created_at.desc()).limit(1)
    if target:
        words = [w for w in target.replace(",", " ").split() if len(w) > 2] or [target]
        for word in words:
            stmt = stmt.where(column.ilike(f"%{word}%"))
    if model is Job:
        stmt = stmt.where(Job.status == JobStatus.open)
    return db.scalar(stmt)


def _run(db: Session, llm: LLMClient, route: str, record, ctx: TaskContext) -> str:  # type: ignore[no-untyped-def]
    actions: dict[str, Callable[[], str]] = {
        "sales.qualify_lead": lambda: (
            f"{record.company} is rated {sales.qualify_lead(db, llm, record.id, ctx).rating}."
        ),
        "hr.screen_candidates": lambda: _screen_summary(
            hr.screen_job(db, llm, record.id, None, ctx), record
        ),
        "support.investigate_ticket": lambda: _ticket_summary(
            support.investigate(db, llm, record.id, ctx)
        ),
        "procurement.compare_vendors": lambda: _compare_summary(
            procurement.compare_vendors(db, llm, record.id, ctx)
        ),
    }
    return actions[route]()


def _screen_summary(scores: list, job: Job) -> str:  # type: ignore[type-arg]
    if not scores:
        return f"No candidates with a resume to screen for {job.title}."
    top = scores[0]
    return (
        f"Screened {len(scores)} for {job.title}; top is {top.candidate.name} with {top.score}/100."
    )


def _ticket_summary(ticket: Ticket) -> str:
    causes = (ticket.investigation or {}).get("likely_causes") or [{}]
    return f"Investigated '{ticket.title}': {causes[0].get('cause', 'no clear cause found')}"


def _compare_summary(result) -> str:  # type: ignore[no-untyped-def]
    top = result.ranking[0]
    return f"{top.vendor_name} ranks first ({top.score}/100) of {len(result.ranking)} vendors."


def _current_state(db: Session, route: str, record) -> str:  # type: ignore[no-untyped-def]
    """What is already known about the record, for users who may look but not act."""
    if route == "sales.qualify_lead":
        return (
            f"{record.company} is {'rated ' + record.rating if record.rating else 'not rated yet'}."
        )
    if route == "hr.screen_candidates":
        scores = hr.ranked_scores(db, record.id)
        if not scores:
            return f"No one has been screened for {record.title} yet."
        return (
            f"Top candidate for {record.title}: {scores[0].candidate.name} ({scores[0].score}/100)."
        )
    if route == "support.investigate_ticket":
        causes = (record.investigation or {}).get("likely_causes")
        return f"Likely cause: {causes[0]['cause']}" if causes else "Not investigated yet."
    ranking = (record.comparison or {}).get("ranking")
    if not ranking:
        return f"Vendors for {record.item} have not been compared yet."
    return f"{ranking[0]['vendor_name']} ranked first for {record.item}."


def chat(db: Session, llm: LLMClient, message: str, user: User) -> AuraReply:
    router = AuraRouter(user.department)
    ctx = TaskContext(actor=user)
    call_tool(db, router, "list_agents", {}, lambda: sorted(ROUTES), ctx)
    decision: AuraDecision = run_agent(db, router, AuraRequest(message=message), llm, ctx)

    def reply(
        outcome: str,
        summary: str,
        link: str | None = None,
        agent: str | None = None,
        text: str
        | None = None,  # replaces the model's line when it promised something we didn't do
    ) -> AuraReply:
        return AuraReply(
            route=decision.route,
            agent=agent,
            reply=text or decision.reply,
            outcome=outcome,  # type: ignore[arg-type]
            summary=summary,
            link=link,
        )

    if decision.route == "none":
        return reply(
            "no_route",
            "I can rate leads, screen candidates, investigate tickets, compare vendors "
            "and verify supplier invoices.",
        )
    if decision.route == "finance.verify_invoice":
        if not can_access(user, Department.finance, write=True):
            return reply(
                "not_allowed",
                "Only finance can start invoice verification.",
                "/payments",
                "invoice_processor",
            )
        call_tool(
            db,
            router,
            "start_workflow",
            {"workflow": "supplier-payment"},
            lambda: {"needs": "invoice file"},
            ctx,
        )
        return reply(
            "needs_input",
            "Upload the invoice and its PO number to start the check.",
            "/payments",
            "invoice_processor",
        )

    agent, department, model, column, link = TARGETS[decision.route]
    if not can_access(user, department, write=False):
        return reply("not_allowed", f"Your role cannot see {department} data.", link, agent)
    record = call_tool(
        db,
        router,
        "find_record",
        {"route": decision.route, "target": decision.target},
        lambda: _find(db, model, column, decision.target),
        ctx,
    )
    if record is None:
        return reply(
            "not_found", f"I could not find a match for '{decision.target or 'that'}'.", link, agent
        )
    if not can_access(user, department, write=True):  # read-only: report, don't run
        who = AGENT_NAMES[agent]
        return reply(
            "not_allowed",
            f"{_current_state(db, decision.route, record)} Someone in {department} can run "
            f"the {who} to update this.",
            link,
            agent,
            text=f"Your access is read-only, so I looked this up instead of running the {who}.",
        )
    try:
        summary = _run(db, llm, decision.route, record, ctx)
    except (AgentFailed, ApiError) as exc:
        return reply("failed", exc.message, link, agent)
    return reply("done", summary, link, agent)
