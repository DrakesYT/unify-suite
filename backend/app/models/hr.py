import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, JsonType, TimestampMixin, UtcDateTime, str_enum
from app.models.enums import JobStatus


class Job(IdMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (CheckConstraint("min_years >= 0", name="min_years_non_negative"),)

    title: Mapped[str] = mapped_column(String(160))
    required_skills: Mapped[list[str]] = mapped_column(JsonType, default=list)
    min_years: Mapped[int] = mapped_column(default=0)
    status: Mapped[JobStatus] = mapped_column(
        str_enum(JobStatus, "job_status"), default=JobStatus.open, index=True
    )


class Candidate(IdMixin, TimestampMixin, Base):
    __tablename__ = "candidates"

    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254), index=True)
    skills: Mapped[list[str]] = mapped_column(JsonType, default=list)
    years_experience: Mapped[int | None]
    education: Mapped[list[str]] = mapped_column(JsonType, default=list)
    file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("uploads.id"), index=True)
    # The job they applied for. None for candidates on file before applications were recorded:
    # they count as applicants for every job.
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)


class CandidateScore(IdMixin, TimestampMixin, Base):
    __tablename__ = "candidate_scores"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id"),
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), index=True)
    score: Mapped[int]  # computed by code from verified evidence, not chosen by the model
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")


class InterviewSlot(IdMixin, TimestampMixin, Base):
    """A time offered to a candidate. Held while its invite is drafted, pending or sent;
    released if the invite is rejected or replaced. Code picks these, never the model."""

    __tablename__ = "interview_slots"

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    ends_at: Mapped[datetime] = mapped_column(UtcDateTime())
    email_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("outbound_emails.id"), index=True)
    released: Mapped[bool] = mapped_column(default=False, index=True)
