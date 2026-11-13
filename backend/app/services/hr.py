"""Jobs (FR-HR-01), resume intake (FR-HR-02) and screening with evidence (FR-HR-03)."""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.agents.resume_parser import ResumeParser
from app.agents.resume_screener import ResumeScreener
from app.agents.runner import TaskContext, call_tool, run_agent
from app.errors import ApiError
from app.llm import LLMClient
from app.models import Candidate, CandidateScore, Job, Upload, User
from app.models.enums import JobStatus
from app.schemas.hr import (
    EXPERIENCE,
    CandidateOut,
    EvidenceItem,
    JobCreate,
    JobUpdate,
    ResumeText,
    ScoreOut,
    ScreeningAssessment,
    ScreeningInput,
)
from app.services import audit
from app.services.pagination import paginate
from app.services.uploads import read_text

PARSER = ResumeParser()
SCREENER = ResumeScreener()
SKILL_WEIGHT = 70  # share of the score from required skills; the rest is years of experience


# --- jobs ----------------------------------------------------------------------------------


def list_jobs(
    db: Session, limit: int, cursor: str | None, status: JobStatus | None = None
) -> tuple[list[Job], str | None]:
    stmt = select(Job)
    if status:
        stmt = stmt.where(Job.status == status)
    return paginate(db, stmt, Job, limit, cursor)


def get_job(db: Session, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise ApiError(404, "not_found", "Job not found")
    return job


def create_job(db: Session, data: JobCreate, actor: User) -> Job:
    job = Job(**data.model_dump())
    db.add(job)
    db.flush()
    audit.record(db, action="job.created", entity="job", entity_id=job.id, actor_id=actor.id)
    db.commit()
    return job


def update_job(db: Session, job_id: uuid.UUID, data: JobUpdate, actor: User) -> Job:
    job = get_job(db, job_id)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(job, key, value)
    audit.record(
        db,
        action="job.updated",
        entity="job",
        entity_id=job.id,
        actor_id=actor.id,
        detail={"fields": sorted(changes)},
    )
    db.commit()
    return job


# --- candidates ----------------------------------------------------------------------------


def list_candidates(
    db: Session, limit: int, cursor: str | None
) -> tuple[list[Candidate], str | None]:
    return paginate(db, select(Candidate), Candidate, limit, cursor)


def add_candidate_from_resume(
    db: Session,
    llm: LLMClient,
    upload: Upload,
    ctx: TaskContext,
    job_id: uuid.UUID | None = None,
) -> Candidate:
    """Read a resume into a candidate; `job_id` is the job they applied for, when known."""
    if job_id is not None:
        get_job(db, job_id)  # 404 for an unknown job, before any model call
    text = call_tool(
        db, PARSER, "read_upload", {"upload_id": str(upload.id)}, lambda: read_text(upload), ctx
    )
    profile = run_agent(db, PARSER, ResumeText(text=text), llm, ctx)

    def _save() -> Candidate:
        candidate = Candidate(
            name=profile.name,
            email=profile.email,
            skills=profile.skills,
            years_experience=profile.years_experience,
            education=profile.education,
            file_id=upload.id,
            job_id=job_id,
        )
        db.add(candidate)
        db.flush()
        audit.record(
            db,
            action="candidate.added",
            entity="candidate",
            entity_id=candidate.id,
            actor_id=ctx.actor.id,
        )
        return candidate

    return call_tool(db, PARSER, "save_candidate", {"upload_id": str(upload.id)}, _save, ctx)


# --- screening -----------------------------------------------------------------------------


def compute_score(job: Job, candidate: Candidate, evidence: list[EvidenceItem]) -> int:
    """Deterministic: share of required skills with verified evidence, plus years of experience."""
    matched = {e.requirement for e in evidence if e.requirement != EXPERIENCE}
    skill_share = len(matched) / len(job.required_skills) if job.required_skills else 1.0
    years = candidate.years_experience or 0
    years_share = min(years / job.min_years, 1.0) if job.min_years else 1.0
    return round(SKILL_WEIGHT * skill_share + (100 - SKILL_WEIGHT) * years_share)


def _to_out(job: Job, candidate: Candidate, row: CandidateScore) -> ScoreOut:
    evidence = [EvidenceItem.model_validate(e) for e in row.evidence]
    matched = {e.requirement for e in evidence}
    return ScoreOut(
        candidate=CandidateOut.model_validate(candidate),
        score=row.score,
        matched_skills=[s for s in job.required_skills if s in matched],
        missing_skills=[s for s in job.required_skills if s not in matched],
        evidence=evidence,
        summary=row.summary,
        updated_at=row.updated_at,
    )


def screen_candidate(
    db: Session, llm: LLMClient, job: Job, candidate: Candidate, ctx: TaskContext
) -> ScoreOut:
    upload = db.get(Upload, candidate.file_id) if candidate.file_id else None
    if upload is None:
        raise ApiError(409, "no_resume", f"{candidate.name} has no resume on file")
    call_tool(db, SCREENER, "get_job", {"job_id": str(job.id)}, lambda: {"title": job.title}, ctx)
    text = call_tool(
        db, SCREENER, "read_upload", {"upload_id": str(upload.id)}, lambda: read_text(upload), ctx
    )
    data = ScreeningInput(
        job_title=job.title,
        required_skills=job.required_skills,
        min_years=job.min_years,
        resume_text=text,
    )
    assessment: ScreeningAssessment = run_agent(db, SCREENER, data, llm, ctx)
    score = compute_score(job, candidate, assessment.evidence)

    def _save() -> CandidateScore:
        row = db.scalar(
            select(CandidateScore).where(
                CandidateScore.candidate_id == candidate.id, CandidateScore.job_id == job.id
            )
        )
        if row is None:
            row = CandidateScore(candidate_id=candidate.id, job_id=job.id, score=score)
            db.add(row)
        row.score = score
        row.evidence = [e.model_dump() for e in assessment.evidence]
        row.summary = assessment.summary
        db.flush()
        audit.record(
            db,
            action="candidate.screened",
            entity="candidate_score",
            entity_id=row.id,
            actor_id=ctx.actor.id,
            detail={"job_id": str(job.id), "score": score},
        )
        return row

    row = call_tool(
        db,
        SCREENER,
        "save_candidate_score",
        {"candidate_id": str(candidate.id), "job_id": str(job.id)},
        _save,
        ctx,
    )
    return _to_out(job, candidate, row)


def screen_job(
    db: Session,
    llm: LLMClient,
    job_id: uuid.UUID,
    candidate_ids: list[uuid.UUID] | None,
    ctx: TaskContext,
) -> list[ScoreOut]:
    """Screen the given candidates, or else every applicant for the job not screened for it yet
    (screening each résumé costs a model call, so nobody is screened twice by accident)."""
    job = get_job(db, job_id)
    if candidate_ids:
        targets = list(
            db.scalars(
                select(Candidate).where(
                    Candidate.file_id.is_not(None), Candidate.id.in_(candidate_ids)
                )
            )
        )
    else:
        targets = unscreened(db, job)
    for candidate in targets:
        screen_candidate(db, llm, job, candidate, ctx)
    return ranked_scores(db, job_id)


def _applicants(job: Job):  # type: ignore[no-untyped-def]
    """Candidates with a resume who applied for `job` (or whose job is not recorded)."""
    return select(Candidate).where(
        Candidate.file_id.is_not(None),
        or_(Candidate.job_id == job.id, Candidate.job_id.is_(None)),
    )


def unscreened(db: Session, job: Job) -> list[Candidate]:
    scored = select(CandidateScore.candidate_id).where(CandidateScore.job_id == job.id)
    return list(db.scalars(_applicants(job).where(Candidate.id.not_in(scored))))


def applicant_counts(db: Session, job: Job) -> tuple[int, int]:
    """(applicants, of whom not screened yet) for one job."""
    total = db.scalar(select(func.count()).select_from(_applicants(job).subquery())) or 0
    return total, len(unscreened(db, job))


def ranked_scores(db: Session, job_id: uuid.UUID) -> list[ScoreOut]:
    job = get_job(db, job_id)
    rows = db.execute(
        select(CandidateScore, Candidate)
        .join(Candidate, Candidate.id == CandidateScore.candidate_id)
        .where(CandidateScore.job_id == job.id)
        # Equal scores: more experience first (the score stops counting years at the job's
        # minimum), then by name so the order never depends on luck.
        .order_by(
            CandidateScore.score.desc(),
            Candidate.years_experience.desc().nulls_last(),
            Candidate.name,
        )
    ).all()
    return [_to_out(job, candidate, row) for row, candidate in rows]
