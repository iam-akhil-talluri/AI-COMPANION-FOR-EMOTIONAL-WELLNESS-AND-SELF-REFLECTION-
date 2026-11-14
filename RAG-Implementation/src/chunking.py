"""Split documents into passages small enough to retrieve precisely."""

import re
from dataclasses import dataclass

from .document_loader import Document


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    title: str
    source_url: str
    text: str


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    """Split one oversized paragraph on sentence boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    parts, current = [], ""
    for s in sentences:
        if current and len(current) + len(s) + 1 > max_chars:
            parts.append(current)
            current = s
        else:
            current = f"{current} {s}".strip()
    if current:
        parts.append(current)
    # A single sentence longer than max_chars is hard-wrapped.
    return [p[i:i + max_chars] for p in parts for i in range(0, len(p), max_chars)]


def chunk_text(text: str, max_chars: int = 800) -> list[str]:
    """Pack paragraphs (split on blank lines) into chunks of up to max_chars."""
    paragraphs = []
    for p in re.split(r"\n\s*\n", text):
        p = p.strip()
        if p:
            paragraphs.extend(_split_long(p, max_chars) if len(p) > max_chars else [p])

    chunks, current = [], ""
    for p in paragraphs:
        if current and len(current) + len(p) + 2 > max_chars:
            chunks.append(current)
            current = p
        else:
            current = f"{current}\n\n{p}" if current else p
    if current:
        chunks.append(current)
    return chunks


def chunk_documents(documents: list[Document], max_chars: int = 800) -> list[Chunk]:
    return [
        Chunk(f"{d.document_id}-{i:02d}", d.document_id, d.title, d.source_url, text)
        for d in documents
        for i, text in enumerate(chunk_text(d.text, max_chars), start=1)
    ]
