import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from sqlalchemy import select

from app.config import PAGE_LIMIT_DEFAULT, PAGE_LIMIT_MAX, UPLOAD_MAX_BYTES
from app.db import DbSession, SessionFactory
from app.deps import CurrentUser, require_department
from app.errors import ApiError
from app.llm import LLM
from app.models import ApprovalRequest, WorkflowExecution
from app.models.enums import Department, ExecutionStatus
from app.orchestrator import engine
from app.orchestrator.templates import TEMPLATES
from app.schemas.common import Page
from app.schemas.workflows import ApprovalOut, ExecutionOut, ExecutionSummary, StepOut
from app.services.pagination import paginate
from app.services.uploads import save_upload

router = APIRouter(
    prefix="/api/workflows",
    tags=["workflows"],
    dependencies=[Depends(require_department(Department.finance))],
)
Limit = Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)]


def _summary(db: DbSession, execution: WorkflowExecution) -> ExecutionSummary:
    return ExecutionSummary(
        id=execution.id,
        workflow=engine.template_of(db, execution).name,
        status=execution.status,
        input=execution.input,
        started_by_id=execution.started_by_id,
        created_at=execution.created_at,
        updated_at=execution.updated_at,
    )


def _detail(db: DbSession, execution: WorkflowExecution) -> ExecutionOut:
    template = engine.template_of(db, execution)
    steps = engine.steps_of(db, execution)
    approval = db.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.execution_id == execution.id)
        .order_by(ApprovalRequest.created_at.desc())
    )
    return ExecutionOut(
        **_summary(db, execution).model_dump(),
        steps=[
            StepOut(
                key=spec.key,
                title=spec.title,
                department=spec.department,
                status=steps[spec.key].status,
                attempts=steps[spec.key].attempts,
                output=steps[spec.key].output,
                error=steps[spec.key].error,
                started_at=steps[spec.key].started_at,
                finished_at=steps[spec.key].finished_at,
            )
            for spec in template.steps
        ],
        approval=ApprovalOut.model_validate(approval) if approval else None,
        result=execution.result,
    )


def _get(db: DbSession, execution_id: uuid.UUID) -> WorkflowExecution:
    execution = db.get(WorkflowExecution, execution_id)
    if execution is None:
        raise ApiError(404, "not_found", "Workflow run not found")
    return execution


@router.post("/{template}/start", status_code=202)
def start_workflow(
    template: str,
    file: Annotated[UploadFile, File(description="Supplier invoice (PDF or TXT, max 10 MB)")],
    po_number: Annotated[str, Form(min_length=1, max_length=40)],
    db: DbSession,
    user: CurrentUser,
    llm: LLM,
    factory: SessionFactory,
    background: BackgroundTasks,
) -> ExecutionOut:
    """Workflow B: upload the invoice and name its PO. Steps run in the background; poll GET."""
    if template not in TEMPLATES:
        raise ApiError(404, "not_found", f"Unknown workflow '{template}'")
    data = file.file.read(UPLOAD_MAX_BYTES + 1)
    upload = save_upload(
        db,
        filename=file.filename or "invoice",
        data=data,
        department=Department.finance,
        actor=user,
    )
    execution = engine.start(
        db,
        TEMPLATES[template],
        {
            "upload_id": str(upload.id),
            "file_name": upload.original_name,
            "po_number": po_number.strip(),
        },
        user,
    )
    background.add_task(engine.advance_in_background, factory, execution.id, llm, user.id)
    return _detail(db, execution)


@router.get("")
def list_workflows(
    db: DbSession,
    limit: Limit = PAGE_LIMIT_DEFAULT,
    cursor: str | None = None,
    status: ExecutionStatus | None = None,
) -> Page[ExecutionSummary]:
    stmt = select(WorkflowExecution)
    if status:
        stmt = stmt.where(WorkflowExecution.status == status)
    rows, next_cursor = paginate(db, stmt, WorkflowExecution, limit, cursor)
    return Page(items=[_summary(db, r) for r in rows], next_cursor=next_cursor)


@router.get("/{execution_id}")
def get_workflow(execution_id: uuid.UUID, db: DbSession) -> ExecutionOut:
    return _detail(db, _get(db, execution_id))


@router.post("/{execution_id}/retry", status_code=202)
def retry_workflow(
    execution_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    llm: LLM,
    factory: SessionFactory,
    background: BackgroundTasks,
) -> ExecutionOut:
    execution = engine.retry(db, execution_id, user)
    background.add_task(engine.advance_in_background, factory, execution.id, llm, user.id)
    return _detail(db, execution)
