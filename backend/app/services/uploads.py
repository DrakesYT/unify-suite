"""Store uploaded files and read their text. Type is checked by content, not just the name."""

import hashlib
import uuid
from io import BytesIO
from pathlib import Path, PurePath

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy.orm import Session

from app.config import PDF_MAX_PAGES, UPLOAD_MAX_BYTES, get_settings
from app.errors import ApiError
from app.models import Upload, User
from app.models.enums import Department

CONTENT_TYPES = {".pdf": "application/pdf", ".csv": "text/csv", ".txt": "text/plain"}


def _check_content(ext: str, data: bytes) -> None:
    if ext == ".pdf":
        ok = data.startswith(b"%PDF-")
    else:
        try:
            ok = b"\x00" not in data and bool(data.decode("utf-8").strip())
        except UnicodeDecodeError:
            ok = False
    if not ok:
        raise ApiError(415, "content_mismatch", f"The file content is not a valid {ext} file")


def save_upload(
    db: Session, *, filename: str, data: bytes, department: Department, actor: User
) -> Upload:
    if len(data) > UPLOAD_MAX_BYTES:
        raise ApiError(413, "file_too_large", "Files can be at most 10 MB")
    ext = PurePath(filename).suffix.lower()
    if ext not in CONTENT_TYPES:
        raise ApiError(415, "unsupported_file_type", "Only PDF, CSV and TXT files are accepted")
    _check_content(ext, data)

    upload_id = uuid.uuid4()
    directory = Path(get_settings().upload_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{upload_id}{ext}"
    path.write_bytes(data)

    upload = Upload(
        id=upload_id,
        original_name=PurePath(filename).name[:255],
        content_type=CONTENT_TYPES[ext],
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_path=str(path),
        department=department,
        uploaded_by_id=actor.id,
    )
    db.add(upload)
    db.commit()
    return upload


def read_text(upload: Upload) -> str:
    data = Path(upload.storage_path).read_bytes()
    if upload.content_type != "application/pdf":
        return data.decode("utf-8")
    try:
        reader = PdfReader(BytesIO(data))
        pages = reader.pages[:PDF_MAX_PAGES]
        text = "\n".join(page.extract_text() or "" for page in pages).strip()
    except (PdfReadError, ValueError) as exc:
        raise ApiError(422, "unreadable_pdf", "The PDF could not be read") from exc
    if not text:
        raise ApiError(422, "no_text", "The PDF has no text layer (scanned PDFs are not supported)")
    return text
