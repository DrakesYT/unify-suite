from typing import Literal

from fastapi import APIRouter, Depends

from app.db import DbSession
from app.deps import CurrentUser, require_roles
from app.llm import LLM, OptionalLLM
from app.models.enums import Role
from app.schemas.aura import AuraReply, AuraRequest
from app.schemas.brief import Brief, QuickAction
from app.services import aura, brief

router = APIRouter(prefix="/api/ai", tags=["aura"])
# The brief and quick actions sit in the dashboard's Aura panel: same audience as the dashboard.
LEADERS = [Depends(require_roles(Role.admin, Role.manager, Role.executive))]


@router.post("/chat")
def chat(body: AuraRequest, db: DbSession, user: CurrentUser, llm: LLM) -> AuraReply:
    """Aura: one message → one route → the department agent runs (with your permissions)."""
    return aura.chat(db, llm, body.message, user)


@router.get("/brief", dependencies=LEADERS)
def morning_brief(
    db: DbSession, user: CurrentUser, llm: OptionalLLM, writer: Literal["model", "code"] = "model"
) -> Brief:
    """Facts gathered by code, worded by the Brief Writer, then checked by code.
    `writer=code` returns the instant code-written version (shown while the model writes)."""
    return brief.morning_brief(db, llm if writer == "model" else None, user)


@router.get("/quick-actions", dependencies=LEADERS)
def quick_actions(db: DbSession, user: CurrentUser) -> list[QuickAction]:
    return brief.quick_actions(db, user)
