"""The "Why?" drawer: for one AI result, what the AI read, what it said, what code decided, and
who was involved. Everything is read back from stored records; nothing is re-generated."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class Field(BaseModel):
    label: str
    value: str


class AiCall(BaseModel):
    """One logged agent attempt whose input fingerprint matches what is shown as `ai_read`."""

    task_id: uuid.UUID
    agent: str
    at: datetime
    attempt: int
    status: str
    duration_ms: int | None
    error: str | None


class Person(BaseModel):
    at: datetime
    who: str  # a user's name, or "System"
    did: str


class Explanation(BaseModel):
    title: str
    agent: str  # display name of the agent that produced the result
    model: str | None  # the model, where the record stores it
    ai_read: list[Field]
    ai_read_note: str | None  # e.g. what was deliberately left out
    input_verified: bool  # True when a logged call's input hash equals the input shown
    ai_said: list[Field]
    calls: list[AiCall]
    code_decided: list[str]
    people: list[Person]
