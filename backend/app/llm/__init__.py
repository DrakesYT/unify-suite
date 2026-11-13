"""Language-model access. Routers get a client through the `get_llm` dependency."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request

from app.config import get_settings
from app.deps import CurrentUser, spend_ai_run
from app.errors import ApiError
from app.llm.base import LLMClient, LLMError, LLMOutputError
from app.llm.vultr import VultrLLMClient

__all__ = [
    "LLM",
    "LLMClient",
    "LLMError",
    "LLMOutputError",
    "OptionalLLM",
    "UnmeteredLLM",
    "get_llm",
    "get_optional_llm",
]


@lru_cache
def _vultr_client() -> VultrLLMClient:
    settings = get_settings()
    assert settings.llm_api_key is not None
    return VultrLLMClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
    )


def get_llm() -> LLMClient:
    if get_settings().llm_api_key is None:
        raise ApiError(503, "llm_unavailable", "The AI service is not configured")
    return _vultr_client()


def _metered_llm(
    llm: Annotated[LLMClient, Depends(get_llm)], request: Request, user: CurrentUser
) -> LLMClient:
    """Every request that gets the model spends one AI run from the caller's budget."""
    spend_ai_run(request, user)
    return llm


LLM = Annotated[LLMClient, Depends(_metered_llm)]


def get_optional_llm() -> LLMClient | None:
    """For features that still work without a model (they fall back to text written by code)."""
    return _vultr_client() if get_settings().llm_api_key is not None else None


# For work that must go on whether or not a model is available and whatever the caller's AI budget:
# a manager's decision, and the workflow steps after it, never call the model.
UnmeteredLLM = Annotated[LLMClient | None, Depends(get_optional_llm)]


def _metered_optional_llm(
    llm: Annotated[LLMClient | None, Depends(get_optional_llm)], request: Request, user: CurrentUser
) -> LLMClient | None:
    if llm is not None:
        spend_ai_run(request, user)
    return llm


OptionalLLM = Annotated[LLMClient | None, Depends(_metered_optional_llm)]
