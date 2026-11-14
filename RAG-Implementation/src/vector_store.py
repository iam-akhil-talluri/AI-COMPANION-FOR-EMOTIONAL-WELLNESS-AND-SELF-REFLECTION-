"""Two interchangeable vector stores with the same search() result shape.

LocalVectorStore
    Chunk vectors in embeddings/embeddings.npy, chunk metadata in
    vector_db/index.json. Search = cosine similarity (dot product of
    normalised vectors).

OpenAIFileSearchStore
    A hosted OpenAI vector store. OpenAI chunks and embeds the uploaded
    documents; search goes through the vector_stores.search endpoint.
"""

import hashlib
import io
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .chunking import Chunk
from .document_loader import Document

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    chunk_id: str
    document_id: str
    title: str
    source_url: str
    text: str
    score: float


# ---------- Local ----------

class LocalVectorStore:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray, fingerprint: str = "", model: str = ""):
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        self.chunks = chunks
        self.vectors = vectors
        self.fingerprint = fingerprint
        self.model = model

    def search(self, query_vec: np.ndarray, top_k: int, min_score: float) -> list[SearchResult]:
        if not self.chunks:
            return []
        scores = self.vectors @ query_vec
        order = np.argsort(-scores)[:top_k]
        return [
            SearchResult(score=round(float(scores[i]), 4), **asdict(self.chunks[i]))
            for i in order
            if scores[i] >= min_score
        ]

    def save(self, embeddings_path: Path, index_path: Path) -> None:
        embeddings_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(embeddings_path, self.vectors)
        index_path.write_text(json.dumps({
            "fingerprint": self.fingerprint,
            "embeddingModel": self.model,
            "chunks": [asdict(c) for c in self.chunks],
        }, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, embeddings_path: Path, index_path: Path) -> "LocalVectorStore":
        meta = json.loads(index_path.read_text(encoding="utf-8"))
        vectors = np.load(embeddings_path)
        chunks = [Chunk(**c) for c in meta["chunks"]]
        return cls(chunks, vectors, meta.get("fingerprint", ""), meta.get("embeddingModel", ""))


# ---------- OpenAI File Search ----------

def content_hash(doc: Document) -> str:
    raw = json.dumps([doc.title, doc.source_url, doc.text])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def plan_sync(documents: list[Document], existing: list[dict[str, Any]]) -> tuple[list[Document], list[str]]:
    """Return (documents to upload, file ids to remove) so the store matches `documents`."""
    wanted = {d.document_id: d for d in documents}
    keep: set[str] = set()
    remove = []
    for f in existing:
        attrs = f.get("attributes") or {}
        doc = wanted.get(attrs.get("documentId"))
        if doc and attrs.get("contentHash") == content_hash(doc) and doc.document_id not in keep:
            keep.add(doc.document_id)
        else:
            remove.append(f["id"])
    return [d for i, d in wanted.items() if i not in keep], remove


class OpenAIFileSearchStore:
    NAME = "rag-implementation-wellness-documents"

    def __init__(self, client: Any, vector_store_id: str = "", state_path: Path | None = None):
        self.client = client
        self.state_path = state_path
        self.vector_store_id = vector_store_id or self._saved_id()

    def _saved_id(self) -> str:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))["vectorStoreId"]
        except (AttributeError, FileNotFoundError, KeyError, json.JSONDecodeError):
            return ""

    def _ensure(self) -> str:
        if not self.vector_store_id:
            vs = self.client.vector_stores.create(name=self.NAME)
            self.vector_store_id = vs.id
            if self.state_path:
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                self.state_path.write_text(json.dumps({"vectorStoreId": vs.id, "name": self.NAME}), encoding="utf-8")
            logger.info("Created vector store %s", vs.id)
        return self.vector_store_id

    def list_files(self) -> list[dict[str, Any]]:
        return [
            {"id": f.id, "attributes": f.attributes or {}, "status": f.status}
            for f in self.client.vector_stores.files.list(vector_store_id=self._ensure(), limit=100)
        ]

    def sync(self, documents: list[Document]) -> dict[str, Any]:
        vs_id = self._ensure()
        upload, remove = plan_sync(documents, self.list_files())
        failed = []
        for doc in upload:
            body = f"# {doc.title}\n\n{doc.text}\n".encode("utf-8")
            uploaded = self.client.files.create(
                file=(f"{doc.document_id}.md", io.BytesIO(body), "text/markdown"), purpose="assistants"
            )
            vs_file = self.client.vector_stores.files.create_and_poll(
                uploaded.id,
                vector_store_id=vs_id,
                attributes={"documentId": doc.document_id, "title": doc.title[:512],
                            "sourceUrl": doc.source_url[:512], "approved": True,
                            "contentHash": content_hash(doc)},
            )
            if vs_file.status != "completed":
                failed.append(doc.document_id)
        for file_id in remove:
            self.client.vector_stores.files.delete(file_id, vector_store_id=vs_id)
            try:
                self.client.files.delete(file_id)
            except Exception as e:
                logger.warning("Could not delete file %s: %s", file_id, e)
        return {"vectorStoreId": vs_id, "uploaded": [d.document_id for d in upload],
                "removed": remove, "failed": failed, "unchanged": len(documents) - len(upload)}

    def search(self, query: str, top_k: int, min_score: float) -> list[SearchResult]:
        if not self.vector_store_id:
            raise RuntimeError("no vector store yet: run  python -m src.retriever --rebuild")
        page = self.client.vector_stores.search(
            self.vector_store_id,
            query=query,
            max_num_results=top_k,
            ranking_options={"score_threshold": min_score},
            filters={"type": "eq", "key": "approved", "value": True},
            rewrite_query=False,
        )
        results, counts = [], {}
        for r in page.data:
            attrs = r.attributes or {}
            text = "\n".join(c.text for c in r.content if c.text).strip()
            if attrs.get("approved") is not True or not text or r.score < min_score:
                continue
            doc_id = str(attrs.get("documentId") or r.filename.rsplit(".", 1)[0])
            counts[doc_id] = counts.get(doc_id, 0) + 1
            results.append(SearchResult(
                chunk_id=f"{doc_id}-fs{counts[doc_id]:02d}", document_id=doc_id,
                title=str(attrs.get("title", doc_id)), source_url=str(attrs.get("sourceUrl", "")),
                text=text, score=round(float(r.score), 4),
            ))
        return results[:top_k]
