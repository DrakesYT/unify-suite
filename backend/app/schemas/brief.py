from typing import Annotated, Literal

from pydantic import BaseModel, Field

Tone = Literal["alert", "warn", "good", "info"]


class BriefFact(BaseModel):
    """One true statement about live data, worded by code."""

    id: int
    text: str
    link: str
    tone: Tone


class BriefInput(BaseModel):
    """What the Brief Writer sees: who it writes for and the facts it may use. Nothing else."""

    first_name: str
    role: str
    department: str
    weekday: str
    focus: str  # what this reader cares about, decided by code from the role
    facts: list[BriefFact]


class BriefDraft(BaseModel):
    headline: Annotated[str, Field(min_length=3, max_length=90)]
    summary: Annotated[str, Field(min_length=10, max_length=320)]
    top: Annotated[list[int], Field(max_length=3)] = Field(
        description="ids of the facts that matter most for this person, most important first"
    )


class Brief(BaseModel):
    headline: str
    summary: str
    items: list[BriefFact]  # most important first
    written_by: Literal["model", "code"]  # "code" when the model is off or its draft failed checks
    model: str | None


class QuickAction(BaseModel):
    """A tile under the Aura chat: ask Aura something about a real record, or open a page."""

    kind: Literal["ask", "open"]
    icon: Literal["approvals", "lead", "hiring", "ticket", "supplier"]
    label: str
    detail: str
    prompt: str | None = None
    link: str | None = None
