"""Retrieval-augmented generation (RAG) over the app's approved wellness resources.

Pipeline:
  1. Ingest: knowledge_base.json -> split each approved document into chunks ->
     embed each chunk with OpenAI -> save to rag_index.json.
  2. Retrieve: embed the user's message -> cosine similarity against every
     chunk -> keep the top-k chunks above a minimum score.
  3. Augment: llm.py adds the retrieved passages to the system prompt.

Each chunk in the index uses this shape (see app/js.js):
  { documentId, chunkId, title, sourceUrl, text, approved, embedding }

The index is rebuilt automatically when the knowledge base or embedding model
changes. Rebuild it by hand with:  python -m app.ingest
"""

import asyncio
import hashlib
import json
import logging
import math
from dataclasses import dataclass
from typing import Any

from .config import get_settings
from .openai_client import get_client

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 800
_EMBED_BATCH = 100


@dataclass
class RetrievedChunk:
    document_id: str
    chunk_id: str
    title: str
    source_url: str
    text: str
    score: float


class RetrievalError(Exception):
    """Embedding or index loading failed."""


# ---------- Ingest ----------

def _load_documents() -> list[dict[str, Any]]:
    path = get_settings().knowledge_base_path
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["documents"]


def _kb_fingerprint(documents: list[dict[str, Any]], model: str) -> str:
    raw = json.dumps({"model": model, "docs": documents}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split on blank lines, packing paragraphs into chunks of up to max_chars."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        if current and len(current) + len(p) + 2 > max_chars:
            chunks.append(current)
            current = p
        else:
            current = f"{current}\n\n{p}" if current else p
    if current:
        chunks.append(current)
    return chunks


def build_chunks(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn approved documents into chunk records (without embeddings)."""
    chunks = []
    for doc in documents:
        if not doc.get("approved"):
            continue  # Only reviewed resources may reach the model.
        for i, text in enumerate(chunk_text(doc["text"]), start=1):
            chunks.append({
                "documentId": doc["documentId"],
                "chunkId": f"{doc['documentId']}-{i:02d}",
                "title": doc["title"],
                "sourceUrl": doc.get("sourceUrl", ""),
                "text": text,
                "approved": True,
            })
    return chunks


async def embed_texts(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), _EMBED_BATCH):
        batch = texts[start:start + _EMBED_BATCH]
        resp = await get_client().embeddings.create(model=settings.openai_embedding_model, input=batch)
        vectors.extend(item.embedding for item in sorted(resp.data, key=lambda d: d.index))
    return vectors


async def build_index() -> dict[str, Any]:
    """Embed every approved chunk and write the index file."""
    settings = get_settings()
    documents = _load_documents()
    chunks = build_chunks(documents)
    embeddings = await embed_texts([c["text"] for c in chunks]) if chunks else []
    for chunk, emb in zip(chunks, embeddings):
        chunk["embedding"] = emb

    index = {
        "fingerprint": _kb_fingerprint(documents, settings.openai_embedding_model),
        "embeddingModel": settings.openai_embedding_model,
        "chunks": chunks,
    }
    settings.rag_index_path.parent.mkdir(parents=True, exist_ok=True)
    settings.rag_index_path.write_text(json.dumps(index), encoding="utf-8")
    logger.info("RAG index built: %d chunks from %d documents", len(chunks), len(documents))
    return index


# ---------- Index loading ----------

_index: dict[str, Any] | None = None
_index_lock = asyncio.Lock()


async def get_index() -> dict[str, Any]:
    """Load the index, rebuilding it if missing or out of date."""
    global _index
    if _index is not None:
        return _index
    async with _index_lock:
        if _index is not None:
            return _index
        settings = get_settings()
        expected = _kb_fingerprint(_load_documents(), settings.openai_embedding_model)
        try:
            cached = json.loads(settings.rag_index_path.read_text(encoding="utf-8"))
            if cached.get("fingerprint") == expected:
                _index = cached
                return _index
            logger.info("Knowledge base changed; rebuilding RAG index")
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("No RAG index found; building it")
        _index = await build_index()
        return _index


# ---------- Retrieval ----------

def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def rank_chunks(query_vec: list[float], chunks: list[dict[str, Any]], top_k: int, min_score: float) -> list[RetrievedChunk]:
    scored = [(cosine(query_vec, c["embedding"]), c) for c in chunks if c.get("approved")]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        RetrievedChunk(
            document_id=c["documentId"],
            chunk_id=c["chunkId"],
            title=c["title"],
            source_url=c.get("sourceUrl", ""),
            text=c["text"],
            score=round(score, 4),
        )
        for score, c in scored[:top_k]
        if score >= min_score
    ]


async def retrieve(query: str) -> list[RetrievedChunk]:
    """Return the most relevant approved passages for the user's message."""
    settings = get_settings()
    try:
        index = await get_index()
        if not index["chunks"]:
            return []
        [query_vec] = await embed_texts([query])
    except Exception as e:  # Retrieval must never take the chat down.
        raise RetrievalError(str(e)) from e
    return rank_chunks(query_vec, index["chunks"], settings.rag_top_k, settings.rag_min_score)


def format_context(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved passages for the system prompt."""
    return "\n\n".join(f'<passage id="{c.chunk_id}" title="{c.title}">\n{c.text}\n</passage>' for c in chunks)
