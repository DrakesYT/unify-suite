from fastapi import APIRouter

from app.db import DbSession
from app.deps import CurrentUser
from app.llm import LLM
from app.schemas.aura import AuraReply, AuraRequest
from app.services import aura

router = APIRouter(prefix="/api/ai", tags=["aura"])


@router.post("/chat")
def chat(body: AuraRequest, db: DbSession, user: CurrentUser, llm: LLM) -> AuraReply:
    """Aura: one message → one route → the department agent runs (with your permissions)."""
    return aura.chat(db, llm, body.message, user)
