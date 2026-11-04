"""Scripted stand-in for the real model, used by tests (no network, no cost)."""

import json
from dataclasses import dataclass, field
from typing import Any

from app.llm.base import T, parse_json_output


@dataclass
class FakeCall:
    schema: str
    system: str
    user: str


@dataclass
class FakeLLMClient:
    """Returns the queued replies in order. A reply is a dict, a raw string, or an exception."""

    replies: list[dict[str, Any] | str | Exception] = field(default_factory=list)
    model: str = "fake"
    calls: list[FakeCall] = field(default_factory=list)

    def complete_json(self, schema: type[T], system: str, user: str, *, timeout_s: float) -> T:
        self.calls.append(FakeCall(schema.__name__, system, user))
        if not self.replies:
            raise AssertionError(f"FakeLLMClient has no reply queued for {schema.__name__}")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return parse_json_output(schema, reply if isinstance(reply, str) else json.dumps(reply))
