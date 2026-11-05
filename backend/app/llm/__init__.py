"""Language-model access. Routers get a client through the `get_llm` dependency."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.config import get_settings
from app.errors import ApiError
from app.llm.base import LLMClient, LLMError, LLMOutputError
from app.llm.vultr import VultrLLMClient

__all__ = [
    "LLM",
    "LLMClient",
    "LLMError",
    "LLMOutputError",
    "OptionalLLM",
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


LLM = Annotated[LLMClient, Depends(get_llm)]


def get_optional_llm() -> LLMClient | None:
    """For features that still work without a model (they fall back to text written by code)."""
    return _vultr_client() if get_settings().llm_api_key is not None else None


OptionalLLM = Annotated[LLMClient | None, Depends(get_optional_llm)]
