"""Retrieval through OpenAI File Search (a hosted OpenAI vector store).

This is an alternative to the local embedding index in rag.py. OpenAI stores,
chunks and embeds the approved resources; at chat time we call the vector
store search endpoint and get back the best-matching passages.

The search endpoint is used directly (rather than the Responses API
`file_search` tool) so the rest of the conversation workflow is unchanged:
the passages go through rag.format_context() into the same system-prompt
block, the chat call keeps its strict JSON schema and safety classification,
and the matched documents are still returned to the frontend as `sources`.

Select it with RAG_BACKEND=openai_file_search in backend/.env.

Sync the approved documents to the vector store with:
    python -m app.file_search sync
"""

import argparse
import asyncio
import hashlib
import io
import json
import logging
from typing import Any

from .config import get_settings
from .openai_client import get_client
from .rag import RetrievalError, RetrievedChunk, _load_documents

logger = logging.getLogger(__name__)

VECTOR_STORE_NAME = "emotional-wellness-approved-resources"


# ---------- Vector store id ----------

def _read_state() -> dict[str, Any]:
    try:
        return json.loads(get_settings().vector_store_state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_state(state: dict[str, Any]) -> None:
    path = get_settings().vector_store_state_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_vector_store_id() -> str:
    """OPENAI_VECTOR_STORE_ID from .env wins; otherwise the id saved by `sync`."""
    return get_settings().openai_vector_store_id or _read_state().get("vectorStoreId", "")


# ---------- Documents -> files ----------

def content_hash(doc: dict[str, Any]) -> str:
    raw = json.dumps({k: doc.get(k) for k in ("title", "sourceUrl", "text")}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def document_file(doc: dict[str, Any]) -> tuple[str, bytes]:
    """Render one approved document as a Markdown file for upload."""
    body = f"# {doc['title']}\n\n{doc['text'].strip()}\n"
    return f"{doc['documentId']}.md", body.encode("utf-8")


def document_attributes(doc: dict[str, Any]) -> dict[str, str | bool]:
    # Attributes come back with every search result, so the passage can be
    # traced to its source, and `approved` is used as a search filter.
    return {
        "documentId": doc["documentId"],
        "title": doc["title"][:512],
        "sourceUrl": doc.get("sourceUrl", "")[:512],
        "approved": True,
        "contentHash": content_hash(doc),
    }


def plan_sync(documents: list[dict[str, Any]], existing: list[dict[str, Any]]) -> tuple[list[dict], list[str]]:
    """Work out what to upload and what to remove.

    existing: [{"id": file_id, "attributes": {...}}] for files in the vector store.
    Returns (documents to upload, file ids to remove). A document whose text
    changed is re-uploaded and its old file removed; a document that was
    removed or un-approved has its file removed, so it can no longer be found.
    """
    approved = {d["documentId"]: d for d in documents if d.get("approved")}
    keep: set[str] = set()
    remove: list[str] = []
    for f in existing:
        attrs = f.get("attributes") or {}
        doc = approved.get(attrs.get("documentId"))
        if doc and attrs.get("contentHash") == content_hash(doc) and doc["documentId"] not in keep:
            keep.add(doc["documentId"])
        else:
            remove.append(f["id"])
    upload = [d for doc_id, d in approved.items() if doc_id not in keep]
    return upload, remove


# ---------- Sync ----------

async def _ensure_vector_store() -> str:
    client = get_client()
    vs_id = get_vector_store_id()
    if vs_id:
        await client.vector_stores.retrieve(vs_id)  # fails loudly if the id is wrong
        return vs_id
    vs = await client.vector_stores.create(
        name=VECTOR_STORE_NAME,
        metadata={"purpose": "approved emotional wellness resources"},
    )
    _write_state({"vectorStoreId": vs.id, "name": VECTOR_STORE_NAME})
    logger.info("Created vector store %s", vs.id)
    return vs.id


async def _list_files(vs_id: str) -> list[dict[str, Any]]:
    files = []
    async for f in get_client().vector_stores.files.list(vector_store_id=vs_id, limit=100):
        files.append({"id": f.id, "attributes": f.attributes or {}, "status": f.status})
    return files


async def sync() -> dict[str, Any]:
    """Make the vector store hold exactly the approved documents."""
    client = get_client()
    vs_id = await _ensure_vector_store()
    documents = _load_documents()
    existing = await _list_files(vs_id)
    upload, remove = plan_sync(documents, existing)

    failed = []
    for doc in upload:
        name, data = document_file(doc)
        uploaded = await client.files.create(file=(name, io.BytesIO(data), "text/markdown"), purpose="assistants")
        vs_file = await client.vector_stores.files.create_and_poll(
            uploaded.id, vector_store_id=vs_id, attributes=document_attributes(doc)
        )
        if vs_file.status != "completed":
            failed.append(doc["documentId"])
            logger.error("Indexing %s failed: %s", doc["documentId"], vs_file.last_error)
        else:
            logger.info("Uploaded %s (%s)", doc["documentId"], uploaded.id)

    for file_id in remove:
        await client.vector_stores.files.delete(file_id, vector_store_id=vs_id)
        try:
            await client.files.delete(file_id)
        except Exception as e:  # The search index no longer has it either way.
            logger.warning("Could not delete stored file %s: %s", file_id, e)
        logger.info("Removed %s", file_id)

    approved_count = sum(1 for d in documents if d.get("approved"))
    return {
        "vectorStoreId": vs_id,
        "approvedDocuments": approved_count,
        "uploaded": [d["documentId"] for d in upload],
        "removedFiles": remove,
        "failed": failed,
        "unchanged": approved_count - len(upload),
    }


# ---------- Retrieval ----------

def to_chunks(results: list[Any]) -> list[RetrievedChunk]:
    """Convert search results to the same RetrievedChunk shape the local index uses."""
    chunks = []
    seen: dict[str, int] = {}
    for r in results:
        attrs = r.attributes or {}
        if attrs.get("approved") is not True:
            continue  # Defense in depth on top of the search filter.
        doc_id = str(attrs.get("documentId") or r.filename.rsplit(".", 1)[0])
        text = "\n".join(c.text for c in r.content if c.text).strip()
        if not text:
            continue
        seen[doc_id] = seen.get(doc_id, 0) + 1
        chunks.append(RetrievedChunk(
            document_id=doc_id,
            chunk_id=f"{doc_id}-fs{seen[doc_id]:02d}",
            title=str(attrs.get("title", doc_id)),
            source_url=str(attrs.get("sourceUrl", "")),
            text=text,
            score=round(float(r.score), 4),
        ))
    return chunks


async def search(query: str) -> list[RetrievedChunk]:
    settings = get_settings()
    vs_id = get_vector_store_id()
    if not vs_id:
        raise RetrievalError("no vector store configured; run: python -m app.file_search sync")
    try:
        page = await get_client().vector_stores.search(
            vs_id,
            query=query,
            max_num_results=settings.rag_top_k,
            ranking_options={"score_threshold": settings.file_search_min_score},
            filters={"type": "eq", "key": "approved", "value": True},
            rewrite_query=False,
        )
    except Exception as e:  # Retrieval must never take the chat down.
        raise RetrievalError(str(e)) from e
    chunks = to_chunks(page.data)
    # Apply the threshold here too, in case the API's ranker treats it differently.
    return [c for c in chunks if c.score >= settings.file_search_min_score][: settings.rag_top_k]


# ---------- CLI ----------

async def _status() -> dict[str, Any]:
    vs_id = get_vector_store_id()
    if not vs_id:
        return {"vectorStoreId": None, "message": "not created yet; run: python -m app.file_search sync"}
    vs = await get_client().vector_stores.retrieve(vs_id)
    files = await _list_files(vs_id)
    return {
        "vectorStoreId": vs.id,
        "name": vs.name,
        "status": vs.status,
        "usageBytes": vs.usage_bytes,
        "fileCounts": vs.file_counts.model_dump(),
        "documents": sorted(str(f["attributes"].get("documentId")) for f in files),
    }


async def _query(text: str) -> list[dict[str, Any]]:
    return [
        {"documentId": c.document_id, "title": c.title, "score": c.score, "text": c.text[:160]}
        for c in await search(text)
    ]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="python -m app.file_search")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync", help="upload approved documents, remove stale ones")
    sub.add_parser("status", help="show the vector store and its documents")
    q = sub.add_parser("query", help="run one search and print the passages")
    q.add_argument("text")
    args = parser.parse_args()

    if args.cmd == "sync":
        result = asyncio.run(sync())
    elif args.cmd == "status":
        result = asyncio.run(_status())
    else:
        result = asyncio.run(_query(args.text))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
