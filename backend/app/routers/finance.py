from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.agents.runner import TaskContext
from app.config import PAGE_LIMIT_DEFAULT, PAGE_LIMIT_MAX, UPLOAD_MAX_BYTES
from app.db import DbSession
from app.deps import CurrentUser, require_department
from app.llm import LLM
from app.models.enums import AnomalyKind, Department, InvoiceStatus, MatchStatus
from app.schemas.common import Page
from app.schemas.finance import AnomalyOut, InvoiceOut, InvoiceUploadResult
from app.services import finance
from app.services.uploads import save_upload

router = APIRouter(
    prefix="/api/finance",
    tags=["finance"],
    dependencies=[Depends(require_department(Department.finance))],
)
Limit = Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)]


@router.post("/invoices/upload", status_code=201)
def upload_invoice(
    file: Annotated[UploadFile, File(description="Invoice as PDF or TXT, max 10 MB")],
    db: DbSession,
    user: CurrentUser,
    llm: LLM,
) -> InvoiceUploadResult:
    data = file.file.read(UPLOAD_MAX_BYTES + 1)  # one byte over the limit is enough to refuse it
    upload = save_upload(
        db, filename=file.filename or "upload", data=data, department=Department.finance, actor=user
    )
    return finance.process_invoice_upload(db, llm, upload, TaskContext(actor=user))


@router.get("/invoices")
def list_invoices(
    db: DbSession,
    limit: Limit = PAGE_LIMIT_DEFAULT,
    cursor: str | None = None,
    status: InvoiceStatus | None = None,
    match_status: MatchStatus | None = None,
) -> Page[InvoiceOut]:
    rows, next_cursor = finance.list_invoices(db, limit, cursor, status, match_status)
    return Page(items=[InvoiceOut.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.get("/anomalies")
def list_anomalies(
    db: DbSession,
    limit: Limit = PAGE_LIMIT_DEFAULT,
    cursor: str | None = None,
    kind: AnomalyKind | None = None,
) -> Page[AnomalyOut]:
    rows, next_cursor = finance.list_anomalies(db, limit, cursor, kind)
    return Page(items=[AnomalyOut.model_validate(r) for r in rows], next_cursor=next_cursor)
