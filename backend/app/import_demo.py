"""Import the fictional demo data in demo_data/: sheet rows, resumes and call transcripts.

    python -m app.import_demo                 # everything; tickets, resumes, calls use the agents
    python -m app.import_demo --records-only  # sheet rows only: no model calls
    python -m app.import_demo --dry-run       # report what would be added, change nothing
                                              # (calls are counted only for leads and tickets
                                              # already in the app)

Run `python -m app.seed` first: the seeded demo users are the people who do the work (the sales rep
owns new leads, the support agent files tickets, the recruiter adds resumes).

Rules
- Records already in the app are never changed; only new ones are added, so re-running is safe and
  picks up anything a previous run could not finish.
- A lead whose email appears again in the sheet stays one lead; the repeat contact is added to its
  notes. Identical ticket rows are imported once.
- New tickets, resumes and calls go through the same agents as in the app: tickets are classified,
  resumes parsed and screened for the job they applied to, calls analysed. Leads stay unrated:
  qualifying them is a button in the app.
- Supplier invoices are not imported: uploading one starts a payment run (Workflow B). They are in
  demo_data/invoices/ for live uploads and for the accuracy check (python -m app.evaluate).
"""

import argparse
import csv
import re
import sys
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.agents.runner import AgentFailed, TaskContext
from app.config import DEMO_DOMAIN
from app.db import session_factory
from app.docx_text import DocxError, docx_text
from app.errors import ApiError
from app.llm import LLMClient, LLMError, get_llm
from app.models import (
    CallTranscript,
    Candidate,
    CandidateScore,
    Customer,
    InterviewSlot,
    Job,
    Lead,
    Order,
    OutboundEmail,
    Ticket,
    Upload,
    User,
    Vendor,
)
from app.models.enums import Department, LeadStatus, OrderStatus, Priority
from app.money import to_minor
from app.schemas.hr import JobCreate
from app.schemas.procurement import VendorCreate
from app.schemas.sales import LeadCreate
from app.schemas.support import TicketCreate
from app.services import audit, calls, hr, procurement, sales, support
from app.services.uploads import save_upload

DATA_DIR = Path(__file__).resolve().parent.parent / "demo_data"
WORKERS = 4  # resumes processed side by side (each in its own database session)
LOCK_KEY = 4_242_001  # PostgreSQL advisory lock held while an import changes data
ACTORS = {"sales": "sales.rep", "support": "support.agent", "hr": "hr.recruiter", "buyer": "buyer"}
_ORDER_NUMBER = re.compile(r"\bSO-\d+\b")
_CALL_HEADER = re.compile(r"^\s*Call:\s*(.+?)\s+-\s+", re.MULTILINE)


class DemoImportError(RuntimeError):
    """The import cannot start (missing seed, missing data folder)."""


@dataclass
class Report:
    added: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    notes: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    verbs: tuple[str, str] = ("Would add", "Added")  # (dry run, real run)

    def add(self, kind: str, n: int = 1) -> None:
        self.added[kind] += n

    def note(self, text: str) -> None:
        self.notes.append(text)

    def fail(self, text: str) -> None:
        self.failed.append(text)

    def render(self, dry_run: bool) -> str:
        verb = self.verbs[0] if dry_run else self.verbs[1]
        counts = ", ".join(f"{n} {k}" for k, n in self.added.items() if n)
        out = [f"{verb}: {counts or 'nothing'}"]
        out += [f"  - {n}" for n in self.notes]
        if self.failed:
            out.append(f"Failed ({len(self.failed)}; run again to retry):")
            out += [f"  ! {f}" for f in self.failed]
        return "\n".join(out)


def listing(items: list[str], shown: int = 5) -> str:
    """'a, b, c' for a few names; 'a, b, c, d, e and 12 more' for many."""
    if len(items) <= shown + 1:
        return ", ".join(items)
    return f"{', '.join(items[:shown])} and {len(items) - shown} more"


def read_rows(name: str, data_dir: Path) -> list[dict[str, str]]:
    with open(data_dir / name, encoding="utf-8", newline="") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def _usd(value: str) -> int:
    return to_minor(Decimal(value or "0"), "USD")


def _demo_user(db: Session, handle: str) -> User:
    user = db.scalar(select(User).where(User.email == f"{handle}@{DEMO_DOMAIN}"))
    if user is None:
        raise DemoImportError(
            f"Demo user {handle}@{DEMO_DOMAIN} is missing: run python -m app.seed"
        )
    return user


# --- sheet rows ------------------------------------------------------------------------------


def import_vendors(db: Session, rows: list[dict[str, str]], actor: User, rep: Report, dry: bool):  # type: ignore[no-untyped-def]
    known = {n.lower() for n in db.scalars(select(Vendor.name))}
    kept = []
    for row in rows:
        name = row["vendor_name"]
        if name.lower() in known:
            kept.append(name)
            continue
        known.add(name.lower())
        rep.add("vendors")
        if not dry:
            data = VendorCreate(
                name=name,
                contact=row["contact_email"] or None,
                lead_time_days=int(row["lead_time_days"]),
                on_time_rate=Decimal(row["on_time_rate"]),
            )
            procurement.create_vendor(db, data, actor)
    if kept:
        rep.note(f"{len(kept)} vendors already in the app, kept as they are: {listing(kept)}")


def import_jobs(db: Session, rows: list[dict[str, str]], actor: User, rep: Report, dry: bool):  # type: ignore[no-untyped-def]
    known = {t.lower() for t in db.scalars(select(Job.title))}
    for row in rows:
        if row["job_title"].lower() in known:
            continue
        known.add(row["job_title"].lower())
        rep.add("jobs")
        if not dry:
            skills = [s.strip() for s in row["required_skills"].split(",") if s.strip()]
            data = JobCreate(
                title=row["job_title"], required_skills=skills, min_years=int(row["min_years"] or 0)
            )
            hr.create_job(db, data, actor)


def import_leads(db: Session, rows: list[dict[str, str]], actor: User, rep: Report, dry: bool):  # type: ignore[no-untyped-def]
    existing = {e.lower() for e in db.scalars(select(Lead.email))}
    first: dict[str, dict[str, str]] = {}
    repeats: dict[str, list[dict[str, str]]] = defaultdict(list)
    skipped = []
    for row in rows:
        email = row["email"].lower()
        if email in existing:
            skipped.append(row["name"])
        elif email in first:
            repeats[email].append(row)
        else:
            first[email] = row
    for email, row in first.items():
        notes = row["notes"]
        for again in repeats[email]:
            notes += f"\n\nContacted us again as {again['name']}: {again['notes']}"
        rep.add("leads")
        if not dry:
            data = LeadCreate(
                name=row["name"],
                company=row["company"],
                email=email,
                status=LeadStatus(row["status"]),
                priority=Priority(row["priority"]),
                value_minor=_usd(row["value_usd"]),
                currency="USD",
                notes=notes[:4000],
            )
            sales.create_lead(db, data, actor)
    merged = sum(len(v) for v in repeats.values())
    if merged:
        rep.note(f"{merged} repeat lead rows (same email) added to their lead's notes")
    if skipped:
        rep.note(f"{len(skipped)} lead rows already in the app, kept as they are")


def import_customers_and_orders(db: Session, rows: list[dict[str, str]], rep: Report, dry: bool):  # type: ignore[no-untyped-def]
    customers = {c.email.lower(): c for c in db.scalars(select(Customer)) if c.email}
    numbers = set(db.scalars(select(Order.order_number)))
    kept = []
    for row in rows:
        email = row["customer_email"].lower()
        customer = customers.get(email)
        if customer is None:
            rep.add("customers")
            customer = Customer(
                name=row["customer_name"],
                company=row["company"] or None,
                email=email,
                billing_terms=row["billing_terms"] or "net_30",
            )
            if not dry:
                db.add(customer)
                db.flush()
            customers[email] = customer
        if row["order_number"] in numbers:
            kept.append(row["order_number"])
            continue
        numbers.add(row["order_number"])
        rep.add("orders")
        if not dry:
            order = Order(
                customer_id=customer.id,
                order_number=row["order_number"],
                amount_minor=_usd(row["amount_usd"]),
                currency="USD",
                status=OrderStatus(row["order_status"]),
                ordered_at=datetime.combine(date.fromisoformat(row["order_date"]), time(9), UTC),
                paid_on=date.fromisoformat(row["paid_date"]) if row["paid_date"] else None,
            )
            db.add(order)
    if not dry:
        db.commit()
    if kept:
        rep.note(f"{len(kept)} orders already in the app, kept as they are: {listing(kept)}")


def import_tickets(
    db: Session,
    rows: list[dict[str, str]],
    actor: User,
    llm: LLMClient | None,
    rep: Report,
    dry: bool,
) -> None:
    customers = {c.email.lower(): c.id for c in db.scalars(select(Customer)) if c.email}
    existing = {(t.title, t.description) for t in db.scalars(select(Ticket))}
    seen: set[tuple[str, str, str]] = set()
    repeated = 0
    for row in rows:
        key = (row["customer_email"].lower(), row["subject"], row["description"])
        if key in seen:
            repeated += 1
            continue
        seen.add(key)
        if (row["subject"], row["description"]) in existing:
            continue
        rep.add("tickets")
        if dry:
            continue
        data = TicketCreate(
            title=row["subject"],
            description=row["description"],
            customer_id=customers.get(row["customer_email"].lower()),
        )
        try:
            ticket = support.create_ticket(db, llm, data, TaskContext(actor=actor))
        except (ApiError, LLMError) as exc:
            rep.fail(f"ticket '{row['subject']}': {exc}")
            continue
        if llm is not None and ticket.category is None:
            rep.fail(f"ticket '{row['subject']}' was saved but not classified")
    if repeated:
        rep.note(f"{repeated} identical ticket rows imported once")


# --- resumes (Resume Parser, then Resume Screener for the job applied to) ----------------------


@dataclass(frozen=True)
class ResumeTask:
    file: Path
    job_title: str


def _resume_upload(db: Session, name: str) -> Upload | None:
    return db.scalar(
        select(Upload)
        .where(Upload.original_name == name, Upload.department == Department.hr)
        .order_by(Upload.created_at)
        .limit(1)
    )


def _resume_done(db: Session, task: ResumeTask, jobs: dict[str, uuid.UUID]) -> bool:
    upload = _resume_upload(db, task.file.name)
    candidate = upload and db.scalar(select(Candidate).where(Candidate.file_id == upload.id))
    if not candidate:
        return False
    return (
        db.scalar(
            select(func.count())
            .select_from(CandidateScore)
            .where(
                CandidateScore.candidate_id == candidate.id,
                CandidateScore.job_id == jobs[task.job_title],
            )
        )
        > 0
    )


def _process_resume(
    factory: sessionmaker[Session], llm: LLMClient, task: ResumeTask, actor_id: uuid.UUID
) -> str:
    """Parse and screen one resume in its own session. Resumes a half-finished earlier attempt."""
    with factory() as db:
        actor = db.get(User, actor_id)
        assert actor is not None
        ctx = TaskContext(actor=actor)
        upload = _resume_upload(db, task.file.name)
        if upload is None:
            upload = save_upload(
                db,
                filename=task.file.name,
                data=task.file.read_bytes(),
                department=Department.hr,
                actor=actor,
            )
        job = db.scalar(select(Job).where(Job.title == task.job_title))
        assert job is not None
        candidate = db.scalar(select(Candidate).where(Candidate.file_id == upload.id))
        if candidate is None:
            candidate = hr.add_candidate_from_resume(db, llm, upload, ctx, job_id=job.id)
            db.commit()
        result = hr.screen_candidate(db, llm, job, candidate, ctx)
        db.commit()
        return f"{candidate.name}: {result.score}"


def import_resumes(
    db: Session,
    factory: sessionmaker[Session],
    llm: LLMClient | None,
    data_dir: Path,
    rep: Report,
    dry: bool,
    workers: int,
    progress: Callable[[str], None],
) -> None:
    applications = read_rows("answer_keys/resumes.csv", data_dir)
    applied = {r["file"]: r["intended_job"] for r in applications if r.get("intended_job")}
    applicant = {r["file"]: r["email"].lower() for r in applications if r.get("email")}
    jobs = {title: job_id for title, job_id in db.execute(select(Job.title, Job.id))}
    if dry:  # jobs this import is about to add count as known in a dry run
        for row in read_rows("jobs.csv", data_dir):
            jobs.setdefault(row["job_title"], uuid.uuid4())
    known = {e.lower() for e in db.scalars(select(Candidate.email)) if e}
    tasks, unknown, repeats = [], [], []
    # In application order, so a person's first resume is the one kept ("x-2.pdf" sorts before
    # "x.pdf" by name). Files without an application come last and are reported.
    listed = [data_dir / "resumes" / r["file"] for r in applications]
    unlisted = sorted(set((data_dir / "resumes").glob("*.pdf")) - set(listed))
    for path in [p for p in listed if p.is_file()] + unlisted:
        job_title = applied.get(path.name)
        if job_title not in jobs:
            unknown.append(path.name)
            continue
        task = ResumeTask(path, job_title)  # type: ignore[arg-type]
        upload = _resume_upload(db, path.name)
        if upload is not None and db.scalar(
            select(Candidate.id).where(Candidate.file_id == upload.id)
        ):
            if not _resume_done(db, task, jobs):
                tasks.append(task)  # an earlier run parsed it but did not finish screening
            continue
        email = applicant.get(path.name, "")
        if email and email in known:
            repeats.append(path.name)  # the same person is already a candidate
            continue
        known.add(email)
        tasks.append(task)
    if unknown:
        rep.note(f"{len(unknown)} resumes name no known job and were left out")
    if repeats:
        rep.note(
            f"{len(repeats)} resumes come from people who are already candidates (kept the "
            f"first): {listing(repeats)}"
        )
    rep.add("resumes", len(tasks))
    if dry or not tasks:
        return
    if llm is None:
        rep.note(f"{len(tasks)} resumes left for a run with the model (no --records-only)")
        rep.add("resumes", -len(tasks))
        return
    actor_id = _demo_user(db, ACTORS["hr"]).id
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_process_resume, factory, llm, t, actor_id): t for t in tasks}
        for future in as_completed(futures):
            task = futures[future]
            done += 1
            try:
                progress(f"  resume {done}/{len(tasks)}: {future.result()}")
            except (AgentFailed, ApiError, LLMError) as exc:
                rep.fail(f"resume {task.file.name}: {exc}")


# --- call transcripts (Call Analyzer), attached to the lead or ticket they are about ------------


@dataclass(frozen=True)
class CallTarget:
    lead_id: uuid.UUID | None = None
    ticket_id: uuid.UUID | None = None


def _transcript_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        return docx_text(path.read_bytes())
    return path.read_text(encoding="utf-8")


def _latest_ticket(db: Session, customer_id: uuid.UUID, mention: str | None) -> uuid.UUID | None:
    tickets = list(
        db.scalars(
            select(Ticket)
            .where(Ticket.customer_id == customer_id)
            .order_by(Ticket.created_at.desc())
        )
    )
    if mention:
        for ticket in tickets:
            if mention in ticket.title or mention in ticket.description:
                return ticket.id
    return tickets[0].id if tickets else None


def find_call_target(db: Session, text: str) -> CallTarget | None:
    """Who a call is about: an order number it mentions (→ that customer's ticket), else the
    company in its 'Call: <company> - <topic>' line (→ a lead, else that customer's ticket)."""
    for number in _ORDER_NUMBER.findall(text):
        order = db.scalar(select(Order).where(Order.order_number == number))
        if order is not None:
            ticket_id = _latest_ticket(db, order.customer_id, number)
            if ticket_id:
                return CallTarget(ticket_id=ticket_id)
    header = _CALL_HEADER.search(text)
    company = header.group(1).strip().lower() if header else ""
    if not company:
        return None
    lead = db.scalar(
        select(Lead).where(func.lower(Lead.company) == company).order_by(Lead.created_at).limit(1)
    )
    if lead is not None:
        return CallTarget(lead_id=lead.id)
    customer = db.scalar(select(Customer).where(func.lower(Customer.company) == company).limit(1))
    if customer is not None:
        ticket_id = _latest_ticket(db, customer.id, None)
        if ticket_id:
            return CallTarget(ticket_id=ticket_id)
    return None


def import_calls(
    db: Session,
    llm: LLMClient | None,
    data_dir: Path,
    rep: Report,
    dry: bool,
    progress: Callable[[str], None],
) -> None:
    done_names = set(
        db.scalars(
            select(Upload.original_name).join(CallTranscript, CallTranscript.upload_id == Upload.id)
        )
    )
    users = {key: _demo_user(db, handle) for key, handle in ACTORS.items()}
    unattached = []
    for path in sorted((data_dir / "transcripts").iterdir()):
        name = f"{path.stem}.txt"
        if name in done_names:
            continue
        try:
            text = _transcript_text(path)
        except (DocxError, UnicodeDecodeError) as exc:
            rep.fail(f"call {path.name}: {exc}")
            continue
        target = find_call_target(db, text)
        if target is None:
            unattached.append(path.name)
            continue
        rep.add("calls")
        if dry:
            continue
        if llm is None:
            rep.add("calls", -1)
            continue
        user = users["sales"] if target.lead_id else users["support"]
        try:
            call = calls.add_call(
                db,
                llm,
                user,
                file_name=name,
                data=text.encode(),
                lead_id=target.lead_id,
                ticket_id=target.ticket_id,
                title=None,
            )
            progress(f"  call: {call.title}")
            if call.analysis is None:
                rep.fail(f"call {path.name} was saved but not analysed")
        except (ApiError, LLMError, AgentFailed) as exc:
            rep.fail(f"call {path.name}: {exc}")
    if unattached and dry:
        rep.note(
            f"{len(unattached)} transcripts have no lead or ticket in the app yet; most attach "
            "to leads and tickets this import adds (a real run shows the final list)"
        )
    elif unattached:
        rep.note(
            f"{len(unattached)} transcripts have no lead or ticket to attach to and were left "
            f"for live uploads: {listing(unattached)}"
        )
    if llm is None and not dry:
        rep.note("call transcripts need the model; run without --records-only to add them")


# --- entry point --------------------------------------------------------------------------------


def run_import(
    factory: sessionmaker[Session],
    llm: LLMClient | None,
    data_dir: Path = DATA_DIR,
    *,
    dry_run: bool = False,
    workers: int = WORKERS,
    progress: Callable[[str], None] = lambda _msg: None,
) -> Report:
    if not data_dir.is_dir():
        raise DemoImportError(f"No demo data at {data_dir}")
    rep = Report()
    with _one_at_a_time(factory, skip=dry_run), factory() as db:
        users = {key: _demo_user(db, handle) for key, handle in ACTORS.items()}
        progress("vendors and jobs...")
        import_vendors(db, read_rows("vendors.csv", data_dir), users["buyer"], rep, dry_run)
        import_jobs(db, read_rows("jobs.csv", data_dir), users["hr"], rep, dry_run)
        progress("leads...")
        import_leads(db, read_rows("leads.csv", data_dir), users["sales"], rep, dry_run)
        progress("customers and orders...")
        import_customers_and_orders(db, read_rows("orders.csv", data_dir), rep, dry_run)
        progress("tickets...")
        tickets = read_rows("tickets.csv", data_dir)
        import_tickets(db, tickets, users["support"], llm, rep, dry_run)
        if not dry_run:
            db.commit()
        progress("resumes...")
        import_resumes(db, factory, llm, data_dir, rep, dry_run, workers, progress)
        progress("call transcripts...")
        import_calls(db, llm, data_dir, rep, dry_run, progress)
    return rep


@contextmanager
def _one_at_a_time(factory: sessionmaker[Session], *, skip: bool = False) -> Iterator[None]:
    """Only one import (or clean-up) may change data at a time: two at once would both add the
    records neither has saved yet. PostgreSQL holds a lock for as long as the run lasts; a
    second run stops straight away. (Tests on SQLite run one at a time anyway.)"""
    engine = factory.kw.get("bind")
    if skip or engine is None or engine.dialect.name != "postgresql":
        yield
        return
    with engine.connect() as conn:
        if not conn.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY}):
            raise DemoImportError(
                "Another demo import is running. Wait for it to finish, then run this again."
            )
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})


def _candidate_in_use(db: Session, candidate_id: uuid.UUID) -> bool:
    """Someone has worked with this candidate: an interview time or an email exists."""
    for model in (InterviewSlot, OutboundEmail):
        count = db.scalar(
            select(func.count()).select_from(model).where(model.candidate_id == candidate_id)
        )
        if count:
            return True
    return False


def remove_duplicates(factory: sessionmaker[Session], *, dry_run: bool = False) -> Report:
    """Undo what two imports running at once leave behind: a resume read into two candidates (the
    same uploaded file) and a transcript added as two calls. One copy stays: the one someone
    already worked with (an interview slot or an email), otherwise the earliest; the others and
    their scores go, so nothing anyone did is lost. Each removal is audited."""
    rep = Report(verbs=("Would remove", "Removed"))
    with _one_at_a_time(factory, skip=dry_run), factory() as db:
        actor = _demo_user(db, ACTORS["hr"])
        by_file: dict[uuid.UUID, list[Candidate]] = defaultdict(list)
        for candidate in db.scalars(
            select(Candidate)
            .where(Candidate.file_id.is_not(None))
            .order_by(Candidate.created_at, Candidate.id)
        ):
            by_file[candidate.file_id].append(candidate)  # type: ignore[index]
        several_in_use = []
        for copies in by_file.values():
            if len(copies) < 2:
                continue
            in_use = [c for c in copies if _candidate_in_use(db, c.id)]
            keep = in_use or copies[:1]  # the copy someone worked with, else the earliest
            if len(in_use) > 1:
                several_in_use.append(copies[0].name)
            for extra in copies:
                if extra in keep:
                    continue
                rep.add("duplicate candidates")
                if dry_run:
                    continue
                db.execute(delete(CandidateScore).where(CandidateScore.candidate_id == extra.id))
                audit.record(
                    db,
                    action="demo_import.duplicate_removed",
                    entity="candidate",
                    entity_id=extra.id,
                    actor_id=actor.id,
                    detail={"kept": str(keep[0].id), "name": extra.name},
                )
                db.delete(extra)
        if several_in_use:
            rep.note(
                "kept every copy that is in use (interview slot or email): "
                + listing(several_in_use)
            )

        by_transcript: dict[tuple[Any, ...], list[tuple[CallTranscript, Upload]]] = defaultdict(
            list
        )
        for call, upload in db.execute(
            select(CallTranscript, Upload)
            .join(Upload, Upload.id == CallTranscript.upload_id)
            .order_by(CallTranscript.created_at, CallTranscript.id)
        ):
            by_transcript[(call.lead_id, call.ticket_id, upload.original_name)].append(
                (call, upload)
            )
        for copies in by_transcript.values():
            for call, upload in copies[1:]:
                rep.add("duplicate calls")
                if dry_run:
                    continue
                audit.record(
                    db,
                    action="demo_import.duplicate_removed",
                    entity="call_transcript",
                    entity_id=call.id,
                    actor_id=actor.id,
                    detail={"kept": str(copies[0][0].id), "title": call.title},
                )
                db.delete(call)
                db.flush()
                db.delete(upload)  # this copy's own file: nothing else points to it
                Path(upload.storage_path).unlink(missing_ok=True)
        if not dry_run:
            db.commit()
    return rep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--records-only", action="store_true", help="no model calls")
    parser.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    parser.add_argument("--workers", type=int, default=WORKERS, help="resumes in parallel")
    parser.add_argument("--data", type=Path, default=DATA_DIR, help="demo data folder")
    parser.add_argument(
        "--remove-duplicates",
        action="store_true",
        help="remove candidates and calls added twice by two imports run at once",
    )
    args = parser.parse_args(argv)
    if args.remove_duplicates:
        try:
            report = remove_duplicates(session_factory(), dry_run=args.dry_run)
        except DemoImportError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(report.render(args.dry_run))
        return 0
    llm = None if (args.records_only or args.dry_run) else get_llm()
    try:
        report = run_import(
            session_factory(),
            llm,
            args.data,
            dry_run=args.dry_run,
            workers=args.workers,
            progress=lambda msg: print(msg, flush=True),
        )
    except DemoImportError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(report.render(args.dry_run))
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
