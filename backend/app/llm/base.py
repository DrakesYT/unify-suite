"""The one interface every agent uses to talk to a language model."""

import json
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """The call failed. `retryable` is False for errors a retry cannot fix (e.g. a bad API key)."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMOutputError(LLMError):
    """The model answered, but not with JSON that fits the schema."""


class LLMClient(Protocol):
    model: str

    def complete_json(self, schema: type[T], system: str, user: str, *, timeout_s: float) -> T:
        """Ask the model for one JSON object and return it validated against `schema`."""
        ...


def json_instructions(schema: type[BaseModel]) -> str:
    return (
        "Reply with exactly one JSON object and nothing else. It must match this JSON Schema:\n"
        + json.dumps(schema.model_json_schema(), separators=(",", ":"))
    )


def parse_json_output[M: BaseModel](schema: type[M], content: str | None) -> M:
    text = (content or "").strip()
    if text.startswith("```"):  # tolerate a fenced code block
        text = text.strip("`").removeprefix("json").strip()
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ())) or "output"
        raise LLMOutputError(f"invalid model output at {where}: {first.get('msg')}") from exc
