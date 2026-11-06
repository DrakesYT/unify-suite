import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Department

Quote = Annotated[str, Field(min_length=3, max_length=300)]


class CallInput(BaseModel):
    """What the Call Analyzer sees: the record the call is about, and the transcript."""

    context: str  # e.g. "Sales lead: Karachi Logistics Group (status: contacted)"
    transcript: str


class ActionItem(BaseModel):
    owner: Literal["us", "customer"] = Field(
        description="'us' if our company promised it, 'customer' if the customer did"
    )
    task: Annotated[str, Field(min_length=3, max_length=200)]
    due: Annotated[str, Field(max_length=60)] | None = Field(
        default=None, description="When, exactly as said on the call (e.g. 'Friday'), or null"
    )
    quote: Quote = Field(description="Words copied exactly from the transcript that show it")


class CallAnalysis(BaseModel):
    """Call Analyzer output. Code checks that every quote is really in the transcript."""

    summary: Annotated[str, Field(min_length=10, max_length=600)]
    sentiment: Literal["positive", "neutral", "negative", "mixed"] = Field(
        description="How the customer feels by the end of the call"
    )
    sentiment_quote: Quote = Field(
        description="The customer's own words that best show that sentiment, copied exactly"
    )
    concerns: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=5)] = Field(
        default_factory=list, description="Worries or objections the customer raised"
    )
    action_items: Annotated[list[ActionItem], Field(max_length=8)]


class SpeakerShare(BaseModel):
    """Counted by code from 'Name: words' lines; empty when the transcript has no speaker labels."""

    speaker: str
    turns: int
    words: int
    share_pct: int


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    department: Department
    lead_id: uuid.UUID | None
    ticket_id: uuid.UUID | None
    file_name: str
    transcript: str
    speakers: list[SpeakerShare]
    analysis: CallAnalysis | None
    analyzed_by_model: str | None
    analyzed_at: datetime | None
    analysis_error: str | None
    created_at: datetime
