"""How an AI result came about (the "Why?" drawer). Read-only; the department read rule applies."""

import uuid

from fastapi import APIRouter

from app.db import DbSession
from app.deps import CurrentUser
from app.schemas.explain import Explanation
from app.services import explain

router = APIRouter(prefix="/api/explain", tags=["explain"])


@router.get("/lead/{lead_id}")
def lead(lead_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Explanation:
    return explain.lead(db, user, lead_id)


@router.get("/candidate/{job_id}/{candidate_id}")
def candidate(
    job_id: uuid.UUID, candidate_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> Explanation:
    return explain.candidate(db, user, job_id, candidate_id)


@router.get("/ticket/{ticket_id}")
def ticket(ticket_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Explanation:
    return explain.ticket(db, user, ticket_id)


@router.get("/purchase-request/{request_id}")
def purchase_request(request_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Explanation:
    return explain.purchase_request(db, user, request_id)


@router.get("/run/{execution_id}")
def run(execution_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Explanation:
    return explain.run(db, user, execution_id)


@router.get("/email/{email_id}")
def email(email_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Explanation:
    return explain.email(db, user, email_id)


@router.get("/call/{call_id}")
def call(call_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Explanation:
    return explain.call(db, user, call_id)
