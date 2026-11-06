"""The demo-data importer: adds only what is new, never changes existing records, and sends tickets,
resumes and calls through the same agents as the app."""

import csv
import io
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import import_demo
from app.docx_text import DocxError, docx_text
from app.llm.fake import FakeLLMClient
from app.models import (
    CallTranscript,
    Candidate,
    CandidateScore,
    Customer,
    Job,
    Lead,
    Order,
    Ticket,
    Vendor,
)
from app.seed import seed
from tests.pdf import make_pdf
from tests.test_calls import ANALYSIS, TRANSCRIPT
from tests.test_hr import SARA_ASSESSMENT, SARA_LINES, SARA_PROFILE
from tests.test_support import REFUND

REFUND_CALL = (
    TRANSCRIPT.replace("Karachi Logistics Group - pricing follow-up", "Bugti Stationers - refund")
    + "Customer: This is about my refund for SO-9002.\n"
)
STRANGER_CALL = TRANSCRIPT.replace("Karachi Logistics Group", "Nobody Trading Ltd")
# A new applicant (the seed already has Sara Malik): the same resume body, another person.
NIDA_LINES = ["Nida Farooq - nida.farooq@example.com", *SARA_LINES[1:]]
NIDA_PROFILE = SARA_PROFILE | {"name": "Nida Farooq", "email": "nida.farooq@example.com"}
APPLICATION = ["Senior Backend Engineer", "strong", "8"]


def _csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def _docx(text: str) -> bytes:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    paras = "".join(
        f"<w:p><w:r><w:t xml:space='preserve'>{line}</w:t></w:r></w:p>"
        for line in text.splitlines()
    )
    xml = f"<?xml version='1.0'?><w:document xmlns:w='{ns}'><w:body>{paras}</w:body></w:document>"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    _csv(
        tmp_path / "vendors.csv",
        ["vendor_name", "contact_email", "lead_time_days", "on_time_rate", "tricky_note"],
        [
            ["ACME Industrial Supplies Ltd.", "other@acme.example.com", "99", "0.10", ""],
            ["Delta Lubricants", "sales@delta.example.com", "6", "0.93", ""],
        ],
    )
    _csv(
        tmp_path / "jobs.csv",
        ["job_title", "required_skills", "min_years"],
        [
            ["Senior Backend Engineer", "Python, Go", "9"],
            ["Data Analyst", "Python, SQL, Power BI", "3"],
        ],
    )
    lead_cols = [
        "name",
        "company",
        "email",
        "status",
        "priority",
        "value_usd",
        "notes",
        "tricky_note",
    ]
    _csv(
        tmp_path / "leads.csv",
        lead_cols,
        [
            [
                "Ayesha Khan",
                "Indus Textiles",
                "ayesha@industextiles.example.com",
                "won",
                "low",
                "1.00",
                "Changed by the sheet",
                "",
            ],
            [
                "Sana Rehman",
                "Rehman Pharma Distribution",
                "sana@rehmanpharma.example.com",
                "qualified",
                "high",
                "72000.00",
                "CFO approved the budget.",
                "",
            ],
            [
                "S. Rehman",
                "Rehman Pharma Distribution",
                "sana@rehmanpharma.example.com",
                "new",
                "medium",
                "72000.00",
                "Asked for pricing again.",
                "Duplicate",
            ],
        ],
    )
    order_cols = [
        "customer_name",
        "company",
        "customer_email",
        "billing_terms",
        "order_number",
        "amount_usd",
        "order_status",
        "order_date",
        "paid_date",
        "tricky_note",
    ]
    _csv(
        tmp_path / "orders.csv",
        order_cols,
        [
            [
                "Hamza Iqbal",
                "Iqbal Traders",
                "hamza@iqbaltraders.example.com",
                "net_30",
                "SO-1001",
                "999.00",
                "refunded",
                "2026-10-03",
                "",
                "",
            ],
            [
                "Hamza Iqbal",
                "Iqbal Traders",
                "hamza@iqbaltraders.example.com",
                "net_30",
                "SO-9001",
                "80.00",
                "placed",
                "2026-11-01",
                "",
                "",
            ],
            [
                "Gulnaz Bugti",
                "Bugti Stationers",
                "gulnaz@bugti.example.com",
                "net_60",
                "SO-9002",
                "1990.00",
                "delivered",
                "2026-09-20",
                "2026-10-15",
                "",
            ],
        ],
    )
    ticket = ["gulnaz@bugti.example.com", "Refund status for SO-9002", "Where is my refund?", ""]
    _csv(
        tmp_path / "tickets.csv",
        ["customer_email", "subject", "description", "tricky_note"],
        [ticket, ticket, ["unknown.person@example.com", "Never arrived", "Nothing came.", ""]],
    )
    (tmp_path / "resumes").mkdir()
    (tmp_path / "resumes" / "resume-nida-farooq.pdf").write_bytes(make_pdf(NIDA_LINES))
    (tmp_path / "resumes" / "resume-nida-farooq-2.pdf").write_bytes(make_pdf(NIDA_LINES))
    (tmp_path / "resumes" / "resume-sara-malik.pdf").write_bytes(make_pdf(SARA_LINES))
    (tmp_path / "transcripts").mkdir()
    for name, text in [
        ("call-karachi-logistics.docx", TRANSCRIPT),
        ("call-bugti-stationers-refund.docx", REFUND_CALL),
        ("call-nobody-trading.docx", STRANGER_CALL),
    ]:
        (tmp_path / "transcripts" / name).write_bytes(_docx(text))
    (tmp_path / "answer_keys").mkdir()
    _csv(
        tmp_path / "answer_keys" / "resumes.csv",
        ["file", "name", "email", "intended_job", "expected_fit", "years_experience", "note"],
        [
            ["resume-nida-farooq.pdf", "Nida Farooq", "nida.farooq@example.com", *APPLICATION, ""],
            [
                "resume-nida-farooq-2.pdf",
                "Nida Farooq",
                "nida.farooq@example.com",
                *APPLICATION,
                "Applied twice",
            ],
            ["resume-sara-malik.pdf", "Sara Malik", "sara.malik@example.com", *APPLICATION, ""],
        ],
    )
    return tmp_path


@pytest.fixture
def factory(engine: Engine, db: Session) -> sessionmaker[Session]:
    seed(db, "demo-password-for-tests")
    return sessionmaker(bind=engine, expire_on_commit=False)


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_a_dry_run_reports_and_changes_nothing(
    factory: sessionmaker[Session], data_dir: Path, db: Session
) -> None:
    before = {m: _count(db, m) for m in (Vendor, Job, Lead, Customer, Order, Ticket)}

    report = import_demo.run_import(factory, None, data_dir, dry_run=True)

    assert dict(report.added) == {
        "vendors": 1,
        "jobs": 1,
        "leads": 1,
        "customers": 1,
        "orders": 2,
        "tickets": 2,
        "resumes": 1,  # Nida once; Sara is already a candidate (from the seed)
        "calls": 1,  # the refund call's ticket only exists once the import has run
    }
    assert {m: _count(db, m) for m in before} == before


def test_records_are_added_and_existing_ones_are_never_changed(
    factory: sessionmaker[Session], data_dir: Path, db: Session
) -> None:
    report = import_demo.run_import(factory, None, data_dir)

    acme = db.scalar(select(Vendor).where(Vendor.name == "ACME Industrial Supplies Ltd."))
    assert acme is not None and acme.lead_time_days == 7  # the seed's value, not the sheet's 99
    ayesha = db.scalar(select(Lead).where(Lead.email == "ayesha@industextiles.example.com"))
    assert ayesha is not None and ayesha.notes != "Changed by the sheet"
    so1001 = db.scalar(select(Order).where(Order.order_number == "SO-1001"))
    assert so1001 is not None and so1001.amount_minor == 12_500

    sana = db.scalars(select(Lead).where(Lead.email == "sana@rehmanpharma.example.com")).all()
    assert len(sana) == 1
    assert "Contacted us again as S. Rehman: Asked for pricing again." in sana[0].notes
    gulnaz = db.scalar(select(Customer).where(Customer.email == "gulnaz@bugti.example.com"))
    assert gulnaz is not None and gulnaz.billing_terms == "net_60"
    so9002 = db.scalar(select(Order).where(Order.order_number == "SO-9002"))
    assert so9002 is not None and str(so9002.paid_on) == "2026-10-15"
    assert so9002.customer_id == gulnaz.id
    tickets = db.scalars(select(Ticket).where(Ticket.title == "Refund status for SO-9002")).all()
    assert len(tickets) == 1 and tickets[0].customer_id == gulnaz.id
    assert tickets[0].category is None  # records only: no model, so not classified
    assert any("1 identical ticket rows imported once" in n for n in report.notes)
    assert report.failed == []

    again = import_demo.run_import(factory, None, data_dir)
    assert {k: v for k, v in again.added.items() if v} == {}


def test_with_the_model_tickets_resumes_and_calls_go_through_the_agents(
    factory: sessionmaker[Session], data_dir: Path, db: Session
) -> None:
    llm = FakeLLMClient()
    llm.replies += [REFUND, REFUND]  # two new tickets are classified
    llm.replies += [NIDA_PROFILE, SARA_ASSESSMENT]  # one new applicant: parsed, then screened
    llm.replies += [ANALYSIS, ANALYSIS]  # two calls are analysed

    report = import_demo.run_import(factory, llm, data_dir, workers=1)

    assert report.failed == []
    classified = db.scalars(select(Ticket.category).where(Ticket.title == "Never arrived")).all()
    assert classified == ["refund"]
    nida = db.scalars(select(Candidate).where(Candidate.email == "nida.farooq@example.com")).all()
    assert len(nida) == 1 and nida[0].file_id is not None  # applied twice: still one candidate
    saras = db.scalars(select(Candidate).where(Candidate.email == "sara.malik@example.com")).all()
    assert len(saras) == 1  # already a candidate: not added again
    assert any(
        "resume-nida-farooq-2.pdf" in n and "resume-sara-malik.pdf" in n for n in report.notes
    )
    job = db.scalar(select(Job).where(Job.title == "Senior Backend Engineer"))
    assert job is not None
    scores = db.scalars(
        select(CandidateScore).where(CandidateScore.candidate_id == nida[0].id)
    ).all()
    assert [s.job_id for s in scores] == [job.id]  # screened for the job applied to, only
    assert nida[0].job_id == job.id  # the application is recorded

    calls = {c.title: c for c in db.scalars(select(CallTranscript))}
    refund = calls["Bugti Stationers - refund"]
    ticket = db.get(Ticket, refund.ticket_id)
    assert ticket is not None and ticket.title == "Refund status for SO-9002"
    pricing = calls["Karachi Logistics Group - pricing follow-up"]
    lead = db.get(Lead, pricing.lead_id)
    assert lead is not None and lead.company == "Karachi Logistics Group"
    assert all(c.analysis for c in calls.values())
    assert any("call-nobody-trading.docx" in n for n in report.notes)

    again = import_demo.run_import(factory, llm, data_dir, workers=1)
    assert {k: v for k, v in again.added.items() if v} == {}


def test_the_import_needs_the_seed_first(engine: Engine, data_dir: Path) -> None:
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with pytest.raises(import_demo.DemoImportError, match=r"run python -m app.seed"):
        import_demo.run_import(factory, None, data_dir)


def test_word_files_become_plain_text_lines() -> None:
    text = docx_text(_docx("Call: Acme - intro\nAgent: Hello\nCustomer: Hi"))

    assert text == "Call: Acme - intro\nAgent: Hello\nCustomer: Hi"
    with pytest.raises(DocxError):
        docx_text(b"not a zip at all")


def test_duplicates_left_by_two_imports_at_once_are_removed(
    factory: sessionmaker[Session], db: Session
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.models import InterviewSlot, Upload, User
    from app.models.enums import Department
    from app.services.uploads import save_upload

    recruiter = db.scalar(select(User).where(User.email == "hr.recruiter@demo.example.com"))
    job = db.scalar(select(Job).where(Job.title == "Senior Backend Engineer"))
    lead = db.scalar(select(Lead).where(Lead.company == "Karachi Logistics Group"))
    assert recruiter and job and lead
    resume = save_upload(db, filename="cv.pdf", data=make_pdf(NIDA_LINES),
                         department=Department.hr, actor=recruiter)  # fmt: skip
    first, second, in_use = (
        Candidate(name="Nida Farooq", email="nida.farooq@example.com", file_id=resume.id)
        for _ in range(3)
    )
    db.add_all([first, second, in_use])
    db.flush()
    db.add_all(
        [CandidateScore(candidate_id=c.id, job_id=job.id, score=90) for c in (first, second)]
    )
    now = datetime.now(UTC)
    db.add(InterviewSlot(candidate_id=in_use.id, job_id=job.id, starts_at=now,
                         ends_at=now + timedelta(minutes=45)))  # fmt: skip
    copies = []
    for _ in range(2):
        upload = save_upload(db, filename="call-karachi-logistics.txt", data=TRANSCRIPT.encode(),
                             department=Department.sales, actor=recruiter)  # fmt: skip
        copies.append(upload)
        db.add(CallTranscript(title="Karachi call", department=Department.sales,
                              lead_id=lead.id, upload_id=upload.id))  # fmt: skip
        db.flush()
    db.commit()
    first_id, second_id, in_use_id = first.id, second.id, in_use.id
    kept_upload, extra_upload = copies[0].id, copies[1].id
    extra_file = Path(copies[1].storage_path)

    preview = import_demo.remove_duplicates(factory, dry_run=True)
    assert dict(preview.added) == {"duplicate candidates removed": 2, "duplicate calls removed": 1}
    assert _count(db, Candidate) >= 3  # the dry run changed nothing

    report = import_demo.remove_duplicates(factory)

    db.expire_all()
    left = db.scalars(select(Candidate).where(Candidate.email == "nida.farooq@example.com")).all()
    assert [c.id for c in left] == [in_use_id]  # the copy someone worked with is the one kept
    scored = db.scalars(select(CandidateScore.candidate_id)).all()
    assert first_id not in scored and second_id not in scored
    assert report.notes == []
    calls = db.scalars(select(CallTranscript).where(CallTranscript.lead_id == lead.id)).all()
    assert len(calls) == 1 and calls[0].upload_id == kept_upload
    assert db.get(Upload, extra_upload) is None
    assert not extra_file.exists()
    again = import_demo.remove_duplicates(factory)
    assert {k: v for k, v in again.added.items() if v} == {}
