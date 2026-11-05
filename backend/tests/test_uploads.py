from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config import UPLOAD_MAX_BYTES, get_settings
from app.errors import ApiError
from app.models import Upload, User
from app.models.enums import Department
from app.services.uploads import read_text, save_upload
from tests.pdf import make_blank_pdf, make_pdf


@pytest.fixture
def actor(make_user: Callable[..., User]) -> User:
    return make_user(department=Department.finance)


def _save(db: Session, actor: User, filename: str, data: bytes):  # type: ignore[no-untyped-def]
    return save_upload(db, filename=filename, data=data, department=Department.finance, actor=actor)


def test_pdf_is_stored_and_its_text_read(db: Session, actor: User) -> None:
    upload = _save(db, actor, "Invoice 42.PDF", make_pdf(["Invoice INV-42", "Total 10.00"]))

    assert upload.content_type == "application/pdf"
    assert upload.original_name == "Invoice 42.PDF"
    assert len(upload.sha256) == 64
    assert Path(upload.storage_path).exists()
    assert "INV-42" in read_text(upload)


def test_text_file_is_read(db: Session, actor: User) -> None:
    upload = _save(db, actor, "notes.txt", b"Invoice INV-7\n")

    assert read_text(upload) == "Invoice INV-7\n"


@pytest.mark.parametrize(
    ("filename", "data", "status", "code"),
    [
        ("invoice.exe", b"MZ\x90\x00", 415, "unsupported_file_type"),
        ("invoice.pdf", b"hello, I am not a pdf", 415, "content_mismatch"),
        ("invoice.txt", b"%PDF-1.4\x00\x01binary", 415, "content_mismatch"),
        ("big.txt", b"a" * (UPLOAD_MAX_BYTES + 1), 413, "file_too_large"),
        ("resume.docx", b"PK\x03\x04word", 415, "unsupported_file_type"),
        ("photo.pdf", b"\xff\xd8\xff\xe0JFIF", 415, "image_not_supported"),
        ("scan.png", b"\x89PNG\r\n\x1a\n", 415, "unsupported_file_type"),
        ("photo.txt", b"\x89PNG\r\n\x1a\n", 415, "image_not_supported"),
        ("empty.txt", b"", 415, "content_mismatch"),
        ("scan.pdf", make_blank_pdf(), 422, "no_text"),
        ("broken.pdf", b"%PDF-1.4 cut off here", 422, "unreadable_pdf"),
    ],
)
def test_bad_uploads_are_refused(
    db: Session, actor: User, filename: str, data: bytes, status: int, code: str
) -> None:
    with pytest.raises(ApiError) as exc:
        _save(db, actor, filename, data)
    assert (exc.value.status_code, exc.value.code) == (status, code)


def test_word_files_are_told_how_to_fix_it(db: Session, actor: User) -> None:
    with pytest.raises(ApiError) as exc:
        _save(db, actor, "invoice.docx", b"PK\x03\x04")
    assert "Save it as a PDF" in exc.value.message


def test_a_scanned_pdf_is_refused_before_anything_is_stored(db: Session, actor: User) -> None:
    folder = Path(get_settings().upload_dir)
    before = set(folder.glob("*")) if folder.exists() else set()

    with pytest.raises(ApiError) as exc:
        _save(db, actor, "scan.pdf", make_blank_pdf())

    assert exc.value.code == "no_text"
    assert "selectable text" in exc.value.message
    assert (set(folder.glob("*")) if folder.exists() else set()) == before
    assert db.query(Upload).count() == 0
