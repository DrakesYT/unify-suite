"""The workflow state machine.

Execution status: running → waiting_approval → approved/running → completed | rejected,
or failed when a step fails (fix the cause, then retry; the stored inputs are reused).
A step runs only when every step it depends on has finished (succeeded, skipped or rejected)
and its `when` condition holds; otherwise it is skipped.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.runner import TaskContext
from app.config import WORKFLOW_STALE_S
from app.errors import ApiError
from app.llm import LLMClient
from app.models import ApprovalRequest, User, WorkflowDefinition, WorkflowExecution, WorkflowStep
from app.models.base import utcnow
from app.models.enums import ApprovalStatus, ExecutionStatus, StepStatus
from app.orchestrator.steps import (
    HANDLERS,
    StepError,
    StepRun,
    WaitForApproval,
    mark_invoice_rejected,
)
from app.orchestrator.templates import TEMPLATES, Finished, Template
from app.services import audit

logger = logging.getLogger(__name__)

DONE = frozenset({StepStatus.succeeded, StepStatus.skipped, StepStatus.rejected})
ADVANCING = frozenset({ExecutionStatus.running, ExecutionStatus.approved})


def template_of(db: Session, execution: WorkflowExecution) -> Template:
    definition = db.get(WorkflowDefinition, execution.definition_id)
    assert definition is not None
    return TEMPLATES[definition.name]


def steps_of(db: Session, execution: WorkflowExecution) -> dict[str, WorkflowStep]:
    rows = db.scalars(select(WorkflowStep).where(WorkflowStep.execution_id == execution.id))
    return {s.step_key: s for s in rows}


def _definition(db: Session, template: Template) -> WorkflowDefinition:
    definition = db.scalar(
        select(WorkflowDefinition).where(WorkflowDefinition.name == template.name)
    )
    if definition is None:
        definition = WorkflowDefinition(
            name=template.name, description=template.description, steps=template.as_json()
        )
        db.add(definition)
        db.flush()
    return definition


def start(db: Session, template: Template, data: dict[str, Any], actor: User) -> WorkflowExecution:
    execution = WorkflowExecution(
        definition_id=_definition(db, template).id, started_by_id=actor.id, input=data
    )
    db.add(execution)
    db.flush()
    for spec in template.steps:
        db.add(WorkflowStep(execution_id=execution.id, step_key=spec.key))
    audit.record(
        db,
        action="workflow.started",
        entity="workflow_execution",
        entity_id=execution.id,
        actor_id=actor.id,
        detail={"workflow": template.name},
    )
    db.commit()
    return execution


def _finished(steps: dict[str, WorkflowStep]) -> Finished:
    return {k: (s.status, s.output) for k, s in steps.items() if s.status in DONE}


def _run_step(db: Session, run: StepRun) -> None:
    step = run.step
    step.status = StepStatus.running
    step.attempts += 1
    step.started_at = utcnow()
    step.error = None
    step.input = {
        "workflow_input": run.execution.input,
        "after": {k: v[1] for k, v in run.done.items()},
    }
    db.commit()
    try:
        result = HANDLERS[step.step_key](run)
    except (StepError, ApiError) as exc:
        db.rollback()
        step.status, step.error = StepStatus.failed, getattr(exc, "message", None) or str(exc)
    except Exception as exc:  # keep the workflow consistent; details go to the log
        db.rollback()
        logger.exception("workflow_step_crashed", extra={"step": step.step_key})
        step.status, step.error = StepStatus.failed, f"Unexpected error ({type(exc).__name__})"
    else:
        if isinstance(result, WaitForApproval):
            step.status, step.output = (
                StepStatus.waiting_approval,
                {"approval_id": str(result.approval_id)},
            )
        else:
            step.status, step.output = StepStatus.succeeded, result
    step.finished_at = utcnow() if step.status != StepStatus.waiting_approval else None
    db.commit()


def _settle(db: Session, execution: WorkflowExecution, steps: dict[str, WorkflowStep]) -> None:
    statuses = {s.status for s in steps.values()}
    before = execution.status
    if StepStatus.failed in statuses:
        execution.status = ExecutionStatus.failed
    elif StepStatus.waiting_approval in statuses:
        execution.status = ExecutionStatus.waiting_approval
    elif statuses <= DONE:
        rejected = StepStatus.rejected in statuses
        execution.status = ExecutionStatus.rejected if rejected else ExecutionStatus.completed
        if "V1" in steps:
            execution.result = steps["V1"].output
    if execution.status != before:
        audit.record(
            db,
            action=f"workflow.{execution.status}",
            entity="workflow_execution",
            entity_id=execution.id,
            actor_id=None,
        )
    db.commit()


def advance(
    db: Session, execution_id: uuid.UUID, llm: LLMClient | None, actor: User
) -> WorkflowExecution:
    """Run every step that can run now, then update the execution status."""
    execution = db.get(WorkflowExecution, execution_id, with_for_update=True)
    assert execution is not None
    if execution.status not in ADVANCING:
        return execution
    template = template_of(db, execution)
    while True:
        steps = steps_of(db, execution)
        progressed = False
        for spec in template.steps:
            step = steps[spec.key]
            if step.status != StepStatus.pending:
                continue
            if any(steps[dep].status not in DONE for dep in spec.after):
                continue
            done = _finished(steps)
            progressed = True
            if not spec.when(done):
                step.status, step.finished_at = StepStatus.skipped, utcnow()
                db.commit()
                continue
            ctx = TaskContext(actor=actor, execution_id=execution.id, step_id=step.id)
            _run_step(
                db, StepRun(db=db, llm=llm, ctx=ctx, execution=execution, step=step, done=done)
            )
        if not progressed:
            break
    _settle(db, execution, steps_of(db, execution))
    return execution


def resume_after_decision(
    db: Session, approval: ApprovalRequest, actor: User
) -> WorkflowExecution | None:
    """Apply a manager's decision to the paused approval step. Call advance() afterwards."""
    if approval.execution_id is None or approval.step_id is None:
        return None
    execution = db.get(WorkflowExecution, approval.execution_id, with_for_update=True)
    step = db.get(WorkflowStep, approval.step_id)
    assert execution is not None and step is not None
    approved = approval.status == ApprovalStatus.approved
    step.status = StepStatus.succeeded if approved else StepStatus.rejected
    step.output = {
        "approval_id": str(approval.id),
        "decision": approval.status,
        "comment": approval.comment,
    }
    step.finished_at = utcnow()
    if not approved:
        outputs = {k: s.output for k, s in steps_of(db, execution).items()}
        mark_invoice_rejected(db, outputs, actor.id)
    execution.status = ExecutionStatus.approved if approved else ExecutionStatus.running
    audit.record(
        db,
        action=f"workflow.{approval.status}",
        entity="workflow_execution",
        entity_id=execution.id,
        actor_id=actor.id,
    )
    db.commit()
    return execution


def _last_activity(execution: WorkflowExecution, steps: list[WorkflowStep]) -> datetime:
    moments = [execution.updated_at, execution.created_at]
    moments += [m for s in steps for m in (s.started_at, s.finished_at) if m is not None]
    return max(moments)


def _is_interrupted(execution: WorkflowExecution, steps: list[WorkflowStep]) -> bool:
    """Still marked as advancing, but nothing has happened for a while: the process that ran its
    steps was restarted (a deploy), so nothing will ever finish it by itself."""
    if execution.status not in ADVANCING:
        return False
    return utcnow() - _last_activity(execution, steps) > timedelta(seconds=WORKFLOW_STALE_S)


def _reopen_running_steps(steps: list[WorkflowStep]) -> list[WorkflowStep]:
    """A step that was cut off mid-run goes back to pending; finished steps keep their output."""
    cut_off = [s for s in steps if s.status == StepStatus.running]
    for step in cut_off:
        step.status, step.error = StepStatus.pending, None
    return cut_off


def retry(db: Session, execution_id: uuid.UUID, actor: User) -> WorkflowExecution:
    """Re-run the failed steps of a failed run, or pick up a run a restart interrupted."""
    execution = db.get(WorkflowExecution, execution_id, with_for_update=True)
    if execution is None:
        raise ApiError(404, "not_found", "Workflow run not found")
    steps = list(steps_of(db, execution).values())
    failed = [s for s in steps if s.status == StepStatus.failed]
    if execution.status == ExecutionStatus.failed and failed:
        for step in failed:
            step.status, step.error = StepStatus.pending, None
        reopened = failed
    elif _is_interrupted(execution, steps):
        reopened = _reopen_running_steps(steps)
    else:
        raise ApiError(409, "nothing_to_retry", "Only failed or interrupted runs can be retried")
    approved = any(s.step_key == "A1" and s.status == StepStatus.succeeded for s in steps)
    execution.status = ExecutionStatus.approved if approved else ExecutionStatus.running
    audit.record(
        db,
        action="workflow.retried",
        entity="workflow_execution",
        entity_id=execution.id,
        actor_id=actor.id,
        detail={"steps": [s.step_key for s in reopened]},
    )
    db.commit()
    return execution


def interrupted_runs(db: Session) -> list[uuid.UUID]:
    """Runs left mid-flight. Only meaningful at start-up, when no step can be running."""
    return list(
        db.scalars(select(WorkflowExecution.id).where(WorkflowExecution.status.in_(ADVANCING)))
    )


def recover_interrupted(
    factory: sessionmaker[Session], execution_ids: list[uuid.UUID], llm: LLMClient | None
) -> None:
    """At start-up: finish the runs the previous process left behind. Never raises."""
    for execution_id in execution_ids:
        try:
            with factory() as db:
                execution = db.get(WorkflowExecution, execution_id, with_for_update=True)
                if execution is None or execution.status not in ADVANCING:
                    continue
                actor = db.get(User, execution.started_by_id)
                if actor is None:
                    continue
                reopened = _reopen_running_steps(list(steps_of(db, execution).values()))
                audit.record(
                    db,
                    action="workflow.recovered",
                    entity="workflow_execution",
                    entity_id=execution.id,
                    actor_id=None,
                    detail={"steps": [s.step_key for s in reopened]},
                )
                db.commit()
                advance(db, execution_id, llm, actor)
        except Exception:
            logger.exception("workflow_recovery_crashed", extra={"execution_id": str(execution_id)})


def advance_in_background(
    factory: sessionmaker[Session],
    execution_id: uuid.UUID,
    llm: LLMClient | None,
    actor_id: uuid.UUID,
) -> None:
    """Entry point for FastAPI BackgroundTasks: own session, never raises."""
    try:
        with factory() as db:
            actor = db.get(User, actor_id)
            assert actor is not None
            advance(db, execution_id, llm, actor)
    except Exception:
        logger.exception("workflow_advance_crashed", extra={"execution_id": str(execution_id)})
