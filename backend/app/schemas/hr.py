import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import JobStatus

Skill = Annotated[str, Field(min_length=1, max_length=60)]
EXPERIENCE = "experience"  # evidence item about overall experience rather than one skill


def _clean_skills(values: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for value in values:
        cleaned = " ".join(value.split())
        if cleaned:
            seen.setdefault(cleaned.lower(), cleaned)
    return list(seen.values())


class JobCreate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=160)]
    required_skills: Annotated[list[Skill], Field(min_length=1, max_length=20)]
    min_years: Annotated[int, Field(ge=0, le=40)] = 0

    _skills = field_validator("required_skills")(_clean_skills)


class JobUpdate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    required_skills: Annotated[list[Skill], Field(min_length=1, max_length=20)] | None = None
    min_years: Annotated[int, Field(ge=0, le=40)] | None = None
    status: JobStatus | None = None

    @field_validator("required_skills")
    @classmethod
    def _skills(cls, value: list[str] | None) -> list[str] | None:
        return _clean_skills(value) if value is not None else None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    required_skills: list[str]
    min_years: int
    status: JobStatus
    created_at: datetime
    applicants: int = 0  # candidates with a resume who applied for this job
    unscreened: int = 0  # ...of whom have not been screened for it yet


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    skills: list[str]
    years_experience: int | None
    education: list[str]
    file_id: uuid.UUID | None
    job_id: uuid.UUID | None = None
    created_at: datetime


class EvidenceItem(BaseModel):
    requirement: Annotated[str, Field(min_length=1, max_length=60)] = Field(
        description=f"One of the job's required skills, or '{EXPERIENCE}'"
    )
    quote: Annotated[str, Field(min_length=3, max_length=400)] = Field(
        description="Words copied exactly from the resume that prove it"
    )


class ScoreOut(BaseModel):
    candidate: CandidateOut
    score: int
    matched_skills: list[str]
    missing_skills: list[str]
    evidence: list[EvidenceItem]
    summary: str
    updated_at: datetime


class ScreenRequest(BaseModel):
    candidate_ids: list[uuid.UUID] | None = Field(
        default=None, description="Leave empty to screen every candidate"
    )


# --- agent inputs / outputs ----------------------------------------------------------------


class ResumeText(BaseModel):
    text: Annotated[str, Field(min_length=1)]


class ResumeProfile(BaseModel):
    """Resume parser output (FR-HR-02)."""

    name: Annotated[str, Field(min_length=1, max_length=120)]
    email: Annotated[str, Field(max_length=254)] | None = None
    skills: Annotated[list[Skill], Field(max_length=50)] = Field(
        description="Concrete skills, tools and technologies named in the resume"
    )
    years_experience: Annotated[int, Field(ge=0, le=60)] = Field(
        description="Total years of professional work experience"
    )
    education: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=10)] = []

    _skills = field_validator("skills")(_clean_skills)


class ScreeningInput(BaseModel):
    job_title: str
    required_skills: list[str]
    min_years: int
    resume_text: str


class ScreeningAssessment(BaseModel):
    """Resume screener output. Code checks every quote against the resume and computes the score."""

    evidence: Annotated[list[EvidenceItem], Field(min_length=1, max_length=25)]
    summary: Annotated[str, Field(min_length=1, max_length=800)] = Field(
        description="Two or three sentences on fit, including what is missing"
    )
