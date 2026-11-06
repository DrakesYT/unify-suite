from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request

from app.db import DbSession
from app.deps import CurrentUser, require_roles, spend_ai_run
from app.llm import LLM, LLMClient, get_optional_llm
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
    request: Request,
    db: DbSession,
    user: CurrentUser,
    llm: Annotated[LLMClient | None, Depends(get_optional_llm)],
    writer: Literal["model", "code"] = "model",
) -> Brief:
    """Facts gathered by code, worded by the Brief Writer, then checked by code.
    `writer=code` returns the instant code-written version (shown while the model writes);
    only the model-written one spends an AI run."""
    model = llm if writer == "model" else None
    if model is not None:
        spend_ai_run(request, user)
    return brief.morning_brief(db, model, user)


@router.get("/quick-actions", dependencies=LEADERS)
def quick_actions(db: DbSession, user: CurrentUser) -> list[QuickAction]:
    return brief.quick_actions(db, user)
