"""Call transcripts for leads (sales) and tickets (support). The department rule is checked in
the service, because the department comes from the lead or ticket the call is about."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile

from app.config import UPLOAD_MAX_BYTES
from app.db import DbSession
from app.deps import CurrentUser
from app.errors import ApiError
from app.llm import LLM
from app.schemas.calls import CallOut
from app.services import calls

router = APIRouter(prefix="/api/calls", tags=["calls"])
PASTED_MAX_CHARS = 20_000


@router.get("")
def list_calls(
    db: DbSession,
    user: CurrentUser,
    lead_id: Annotated[uuid.UUID | None, Query()] = None,
    ticket_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[CallOut]:
    return [calls.to_out(db, c) for c in calls.list_calls(db, user, lead_id, ticket_id)]


@router.post("", status_code=201)
def add_call(
    db: DbSession,
    user: CurrentUser,
    llm: LLM,
    file: Annotated[UploadFile | None, File(description="Transcript as TXT or PDF")] = None,
    text: Annotated[str | None, Form(max_length=PASTED_MAX_CHARS)] = None,
    title: Annotated[str | None, Form(max_length=200)] = None,
    lead_id: Annotated[uuid.UUID | None, Form()] = None,
    ticket_id: Annotated[uuid.UUID | None, Form()] = None,
) -> CallOut:
    """Upload a transcript file or paste its text; it is analysed right away."""
    if (file is None) == (not (text or "").strip()):
        raise ApiError(422, "file_or_text", "Upload a transcript file or paste its text (one)")
    if file is not None:
        name, data = file.filename or "call.txt", file.file.read(UPLOAD_MAX_BYTES + 1)
    else:
        name, data = "pasted-transcript.txt", (text or "").encode()
    call = calls.add_call(
        db,
        llm,
        user,
        file_name=name,
        data=data,
        lead_id=lead_id,
        ticket_id=ticket_id,
        title=title,
    )
    return calls.to_out(db, call)


@router.post("/{call_id}/analyze")
def analyze(call_id: uuid.UUID, db: DbSession, user: CurrentUser, llm: LLM) -> CallOut:
    return calls.to_out(db, calls.analyze(db, llm, user, call_id))
