import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import LeadRating, LeadStatus, Priority
from app.schemas.common import Currency, MinorAmount

MIN_REASON_WORDS = 20

LeadName = Annotated[str, Field(min_length=1, max_length=120)]
Company = Annotated[str, Field(min_length=1, max_length=160)]
Notes = Annotated[str, Field(max_length=4000)]


class LeadCreate(BaseModel):
    name: LeadName
    company: Company
    email: EmailStr
    status: LeadStatus = LeadStatus.new
    priority: Priority = Priority.medium
    value_minor: MinorAmount = 0
    currency: Currency = "USD"
    notes: Notes = ""


class LeadUpdate(BaseModel):
    name: LeadName | None = None
    company: Company | None = None
    email: EmailStr | None = None
    status: LeadStatus | None = None
    priority: Priority | None = None
    value_minor: MinorAmount | None = None
    currency: Currency | None = None
    notes: Notes | None = None


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    company: str
    email: str
    status: LeadStatus
    priority: Priority
    value_minor: int
    currency: str
    notes: str
    rating: LeadRating | None
    qualification: dict[str, Any] | None
    owner_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# --- Lead Qualifier ------------------------------------------------------------------------

CitableField = Literal["company", "email_domain", "status", "priority", "value", "notes"]


class LeadForQualification(BaseModel):
    """Only what the agent needs: no person's name, no full email address."""

    company: str
    email_domain: str
    status: LeadStatus
    priority: Priority
    value: str = Field(description="Estimated deal value, e.g. '12,000.00 USD'")
    notes: str


class QualificationResult(BaseModel):
    rating: LeadRating = Field(description="hot, warm or cold")
    reason: Annotated[str, Field(max_length=1500)] = Field(
        description=f"Why, in plain sentences, at least {MIN_REASON_WORDS} words"
    )
    cited_fields: Annotated[list[CitableField], Field(min_length=1)] = Field(
        description="The lead fields the reason relies on"
    )

    @field_validator("reason")
    @classmethod
    def _long_enough(cls, value: str) -> str:
        if len(value.split()) < MIN_REASON_WORDS:
            raise ValueError(f"reason must have at least {MIN_REASON_WORDS} words")
        return value.strip()

    @field_validator("cited_fields")
    @classmethod
    def _unique(cls, value: list[CitableField]) -> list[CitableField]:
        return list(dict.fromkeys(value))
