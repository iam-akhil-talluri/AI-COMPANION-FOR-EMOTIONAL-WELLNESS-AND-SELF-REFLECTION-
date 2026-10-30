from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.sessions import SupportResource


class JournalCreate(BaseModel):
    # Hard upper bound; MAX_JOURNAL_CHARS is enforced in the journal service.
    content: str = Field(min_length=1, max_length=20000)
    prompt: str | None = Field(default=None, max_length=300)


class JournalEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prompt: str | None
    content: str
    created_at: datetime


class JournalSaved(BaseModel):
    entry: JournalEntryOut
    # ok: saved. support: also show `resources`. crisis: open the crisis resources screen.
    status: Literal["ok", "support", "crisis"] = "ok"
    risk_level: Literal["low", "moderate", "elevated", "high"]
    resources: list[SupportResource] = Field(default_factory=list)


class JournalList(BaseModel):
    entries: list[JournalEntryOut]
    # All of the user's entries (the list may be one page).
    total: int
    # Entries older than this are deleted automatically (0 = kept until the user deletes them).
    retention_days: int
