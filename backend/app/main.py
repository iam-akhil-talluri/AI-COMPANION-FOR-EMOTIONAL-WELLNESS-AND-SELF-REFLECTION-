import logging
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import rag, sessions
from .config import get_settings
from .llm import CompanionError, generate_reply
from .safety import ESCALATION_MESSAGE, screen_message
from .schemas import ChatRequest, ChatResponse, Source

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ERROR_MESSAGE = "Sorry, I couldn't respond just now. Please try again in a moment."

app = FastAPI(title="AI Companion for Emotional Wellness")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _unique_sources(chunks: list[rag.RetrievedChunk]) -> list[Source]:
    seen: dict[str, Source] = {}
    for c in chunks:
        seen.setdefault(c.document_id, Source(documentId=c.document_id, title=c.title, sourceUrl=c.source_url))
    return list(seen.values())


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    session_id = str(req.session_id) if req.session_id is not None else uuid.uuid4().hex
    text = req.message.strip()

    # Layer 1: rules. Flagged messages never reach the model.
    if screen_message(text):
        logger.info("Safety escalation (rules) for session %s", session_id)
        return ChatResponse(status="concern", message=ESCALATION_MESSAGE, session_id=session_id)

    sessions.seed_history(session_id, [(m.role, m.text) for m in req.history])

    # RAG: find approved passages relevant to this message. If retrieval fails,
    # the companion still replies, just without reference passages.
    try:
        chunks = await rag.retrieve(text)
    except rag.RetrievalError as e:
        logger.warning("Retrieval failed for session %s: %s", session_id, e)
        chunks = []

    try:
        status, message = await generate_reply(
            sessions.get_history(session_id), text, context=rag.format_context(chunks)
        )
    except CompanionError as e:
        logger.warning("Chat failed for session %s: %s", session_id, e)
        return ChatResponse(status="error", message=ERROR_MESSAGE, session_id=session_id)

    sessions.append_turn(session_id, text, message)

    # Layer 2: the model's own classification.
    if status == "concern":
        logger.info("Safety escalation (model) for session %s", session_id)
        return ChatResponse(status="concern", message=ESCALATION_MESSAGE, session_id=session_id)

    sources = _unique_sources(chunks) if status == "ok" else []
    return ChatResponse(status=status, message=message, session_id=session_id, sources=sources)
