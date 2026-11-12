from typing import Literal

from pydantic import BaseModel, Field

# Matches the statuses the frontend already handles in App.jsx.
ChatStatus = Literal["ok", "out_of_scope", "concern", "error"]


class HistoryMessage(BaseModel):
    role: str
    text: str = ""


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    # The frontend currently uses Date.now() as a session id, so accept numbers too.
    session_id: str | int | None = None
    # Messages the frontend already shows for this chat. Only used to seed a
    # session the backend has no history for (e.g. a restored session).
    history: list[HistoryMessage] = Field(default_factory=list, max_length=100)


class Source(BaseModel):
    """An approved resource the reply drew on (from RAG retrieval)."""
    documentId: str
    title: str
    sourceUrl: str = ""


class ChatResponse(BaseModel):
    status: ChatStatus
    message: str
    session_id: str
    sources: list[Source] = Field(default_factory=list)
