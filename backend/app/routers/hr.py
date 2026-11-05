import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.agents.runner import TaskContext
from app.config import PAGE_LIMIT_DEFAULT, PAGE_LIMIT_MAX, UPLOAD_MAX_BYTES
from app.db import DbSession
from app.deps import CurrentUser, require_department
from app.llm import LLM
from app.mailer import Mailer
from app.models.enums import Department, JobStatus
from app.schemas.common import Page
from app.schemas.hr import CandidateOut, JobCreate, JobOut, JobUpdate, ScoreOut, ScreenRequest
from app.schemas.outreach import EmailDraftUpdate, OutboundEmailOut
from app.services import hr, interviews, outbound
from app.services.uploads import save_upload

router = APIRouter(
    prefix="/api/hr", tags=["hr"], dependencies=[Depends(require_department(Department.hr))]
)
Limit = Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)]


@router.get("/jobs")
def list_jobs(
    db: DbSession,
    limit: Limit = PAGE_LIMIT_DEFAULT,
    cursor: str | None = None,
    status: JobStatus | None = None,
) -> Page[JobOut]:
    rows, next_cursor = hr.list_jobs(db, limit, cursor, status)
    return Page(items=[JobOut.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.post("/jobs", status_code=201)
def create_job(data: JobCreate, db: DbSession, user: CurrentUser) -> JobOut:
    return JobOut.model_validate(hr.create_job(db, data, user))


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, db: DbSession) -> JobOut:
    return JobOut.model_validate(hr.get_job(db, job_id))


@router.patch("/jobs/{job_id}")
def update_job(job_id: uuid.UUID, data: JobUpdate, db: DbSession, user: CurrentUser) -> JobOut:
    return JobOut.model_validate(hr.update_job(db, job_id, data, user))


@router.get("/candidates")
def list_candidates(
    db: DbSession, limit: Limit = PAGE_LIMIT_DEFAULT, cursor: str | None = None
) -> Page[CandidateOut]:
    rows, next_cursor = hr.list_candidates(db, limit, cursor)
    return Page(items=[CandidateOut.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.post("/candidates/upload", status_code=201)
def upload_resume(
    file: Annotated[UploadFile, File(description="Resume as PDF or TXT, max 10 MB")],
    db: DbSession,
    user: CurrentUser,
    llm: LLM,
) -> CandidateOut:
    data = file.file.read(UPLOAD_MAX_BYTES + 1)
    upload = save_upload(
        db, filename=file.filename or "resume", data=data, department=Department.hr, actor=user
    )
    return CandidateOut.model_validate(
        hr.add_candidate_from_resume(db, llm, upload, TaskContext(actor=user))
    )


@router.post("/jobs/{job_id}/screen")
def screen_job(
    job_id: uuid.UUID, body: ScreenRequest, db: DbSession, user: CurrentUser, llm: LLM
) -> list[ScoreOut]:
    """Resume Screener: evidence quotes are verified against the resume; the score is computed."""
    return hr.screen_job(db, llm, job_id, body.candidate_ids, TaskContext(actor=user))


@router.get("/jobs/{job_id}/scores")
def job_scores(job_id: uuid.UUID, db: DbSession) -> list[ScoreOut]:
    return hr.ranked_scores(db, job_id)


# --- interview invitations ---------------------------------------------------------------------


@router.get("/jobs/{job_id}/candidates/{candidate_id}/emails")
def list_invites(
    job_id: uuid.UUID, candidate_id: uuid.UUID, db: DbSession
) -> list[OutboundEmailOut]:
    return [
        OutboundEmailOut.model_validate(e) for e in interviews.list_for(db, job_id, candidate_id)
    ]


@router.post("/jobs/{job_id}/candidates/{candidate_id}/emails", status_code=201)
def draft_invite(
    job_id: uuid.UUID, candidate_id: uuid.UUID, db: DbSession, user: CurrentUser, llm: LLM
) -> OutboundEmailOut:
    """Code holds 3 free interview times; the Interview Invite Writer drafts the invitation.
    Nothing is sent until an HR manager approves."""
    email = interviews.draft_invite(db, llm, job_id, candidate_id, TaskContext(actor=user))
    return OutboundEmailOut.model_validate(email)


@router.patch("/emails/{email_id}")
def edit_email(
    email_id: uuid.UUID, data: EmailDraftUpdate, db: DbSession, user: CurrentUser
) -> OutboundEmailOut:
    return OutboundEmailOut.model_validate(
        outbound.update_draft(db, email_id, Department.hr, data, user)
    )


@router.post("/emails/{email_id}/request-approval")
def request_email_approval(
    email_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> OutboundEmailOut:
    return OutboundEmailOut.model_validate(interviews.request_approval(db, email_id, user))


@router.post("/emails/{email_id}/retry")
def retry_email(
    email_id: uuid.UUID, db: DbSession, user: CurrentUser, mailer: Mailer
) -> OutboundEmailOut:
    return OutboundEmailOut.model_validate(
        outbound.retry(db, email_id, Department.hr, user, mailer)
    )
