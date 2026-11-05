"""Store uploaded files and read their text. Type is checked by content, not just the name.

Anything the agents could not read is refused here, before it is stored or a workflow starts.
"""

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
WORD_EXTENSIONS = {".doc", ".docx", ".odt", ".rtf"}
# jpg, png, gif, tiff (both byte orders)
IMAGE_SIGNATURES = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF8", b"II*\x00", b"MM\x00*")
NO_TEXT = (
    "This PDF has no text in it (it is a scan or a photo). Upload a PDF with selectable text, "
    "for example one saved from Word, Excel or your invoicing software."
)


def _pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
        pages = reader.pages[:PDF_MAX_PAGES]
        text = "\n".join(page.extract_text() or "" for page in pages).strip()
    except (PdfReadError, ValueError) as exc:
        raise ApiError(422, "unreadable_pdf", "The PDF could not be read") from exc
    if not text:
        raise ApiError(422, "no_text", NO_TEXT)
    return text


def _check_content(ext: str, data: bytes) -> None:
    if data.startswith(IMAGE_SIGNATURES):
        raise ApiError(
            415,
            "image_not_supported",
            "This is an image (a photo or a scan). Only documents with real text can be read: "
            "upload a PDF with selectable text.",
        )
    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ApiError(415, "content_mismatch", "The file content is not a valid .pdf file")
        _pdf_text(data)  # a scanned or broken PDF is refused here, with the reason
        return
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
    if ext in WORD_EXTENSIONS:
        raise ApiError(
            415,
            "unsupported_file_type",
            "Word files are not accepted. Save it as a PDF (File > Save As > PDF) and upload that.",
        )
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
    return _pdf_text(data)
