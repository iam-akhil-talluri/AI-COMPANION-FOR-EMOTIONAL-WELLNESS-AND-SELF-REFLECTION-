from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    type: Literal["conversation", "reflection"] = "conversation"
    prompt: str | None = Field(default=None, max_length=300)
    title: str | None = Field(default=None, max_length=160)


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    title: str | None
    prompt: str | None
    created_at: datetime
    last_active: datetime
    message_count: int


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class SessionDetail(SessionSummary):
    messages: list[MessageOut]


class MessageCreate(BaseModel):
    # Hard upper bound; MAX_MESSAGE_CHARS is enforced in the chat service.
    content: str = Field(min_length=1, max_length=20000)


class ChatResponse(BaseModel):
    session_id: str
    status: Literal["ok"] = "ok"
    response: str
    created_at: datetime
