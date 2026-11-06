"""Plain text from a Word .docx file, for the demo-data importer only (uploads stay PDF/CSV/TXT).

A .docx is a zip of XML parts; the body text is in word/document.xml. Each paragraph becomes one
line. Only the standard library is used; nothing in the file is executed or followed (no macros,
no external links), and oversized documents are refused before parsing.
"""

import zipfile
from io import BytesIO
from xml.etree import ElementTree

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_XML_BYTES = 5 * 1024 * 1024


class DocxError(ValueError):
    pass


def docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_XML_BYTES:
                raise DocxError("document is too large")
            xml = archive.read(info)
        root = ElementTree.fromstring(xml)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise DocxError("not a readable .docx file") from exc
    lines = []
    for paragraph in root.iter(f"{_W}p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == f"{_W}t":
                parts.append(node.text or "")
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        lines.append("".join(parts))
    return "\n".join(line for line in lines if line.strip()).strip()
