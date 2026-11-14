"""Web app for the RAG wellness companion.

Run:   .venv\\Scripts\\activate   then   uvicorn app:app --reload --port 8001
Open:  http://localhost:8001

The OpenAI key is only read on the server (from .env); the browser talks to
/api/* and never sees it.
"""

import logging
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import get_settings
from src.document_loader import load_documents
from src.rag_pipeline import RAGPipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
for _name in ("httpx", "httpx2"):
    logging.getLogger(_name).setLevel(logging.WARNING)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="RAG Wellness Companion")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

pipeline = RAGPipeline()
_index_lock = threading.Lock()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class ResetRequest(BaseModel):
    session_id: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "backend": s.vector_backend,
        "chatModel": s.chat_model,
        "documents": len(load_documents(s.documents_dir)),
        "keyConfigured": bool(s.openai_api_key) and not s.openai_api_key.startswith("sk-your"),
    }


@app.get("/api/documents")
def documents() -> list[dict]:
    return [{"documentId": d.document_id, "title": d.title, "sourceUrl": d.source_url}
            for d in load_documents(get_settings().documents_dir)]


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    session_id = req.session_id or uuid.uuid4().hex
    with _index_lock:  # the first call may build the index; don't build it twice
        if pipeline.retriever.backend == "local":
            try:
                pipeline.retriever.local_store()
            except Exception as e:
                logging.getLogger(__name__).warning("Index not available: %s", e)
    return {**pipeline.chat(req.message, session_id).to_dict(), "session_id": session_id}


@app.post("/api/reset")
def reset(req: ResetRequest) -> dict:
    pipeline.reset(req.session_id)
    return {"status": "ok"}


@app.post("/api/reindex")
def reindex() -> dict:
    with _index_lock:
        try:
            return pipeline.retriever.rebuild()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Re-indexing failed: {e}") from e
