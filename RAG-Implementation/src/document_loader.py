"""Load approved wellness resources from data/wellness_documents/.

Supported: .md and .txt (with optional front matter) and .pdf.

Front matter at the top of a .md/.txt file:
    ---
    documentId: wellness-001
    title: Slow Breathing for Stress
    sourceUrl: https://...
    approved: true
    ---
Documents with `approved: false` are skipped, so unreviewed material never
reaches the model. Files without front matter (and PDFs) are treated as
approved, take their id from the file name and their title from the first
"# " heading or the file name.
"""

import re
from dataclasses import dataclass
from pathlib import Path

SUPPORTED = {".md", ".txt", ".pdf"}


@dataclass
class Document:
    document_id: str
    title: str
    source_url: str
    text: str
    path: str


def parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", raw, re.S)
    if not m:
        return {}, raw
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta, raw[m.end():]


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    pages = [page.extract_text() or "" for page in PdfReader(str(path)).pages]
    return "\n\n".join(p.strip() for p in pages if p.strip())


def load_document(path: Path) -> Document | None:
    if path.suffix.lower() == ".pdf":
        meta, body = {}, _read_pdf(path)
    else:
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))

    if meta.get("approved", "true").lower() not in ("true", "yes", "1"):
        return None

    body = body.strip()
    heading = re.match(r"^#\s+(.+)\n", body)
    title = meta.get("title") or (heading.group(1).strip() if heading else path.stem.replace("-", " ").title())
    if heading and heading.group(1).strip() == title:
        body = body[heading.end():].strip()  # the title is kept separately
    if not body:
        return None
    return Document(
        document_id=meta.get("documentId") or path.stem,
        title=title,
        source_url=meta.get("sourceUrl", ""),
        text=body,
        path=str(path),
    )


def load_documents(directory: Path) -> list[Document]:
    docs = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED:
            doc = load_document(path)
            if doc:
                docs.append(doc)
    ids = [d.document_id for d in docs]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"duplicate documentId(s): {sorted(duplicates)}")
    return docs
