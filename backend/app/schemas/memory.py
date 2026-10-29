from datetime import datetime

from pydantic import BaseModel


class MemoryNote(BaseModel):
    session_id: str
    type: str
    title: str | None
    summary: str
    updated_at: datetime | None
    last_active: datetime


class MemoryOut(BaseModel):
    # False when the user turned memory off.
    enabled: bool
    # False when the server has memory switched off (MEMORY_ENABLED=false or transcripts not stored).
    available: bool
    # Notes from this many of the newest sessions go with each reply.
    sessions_used: int
    notes: list[MemoryNote]


class MemorySettings(BaseModel):
    enabled: bool
