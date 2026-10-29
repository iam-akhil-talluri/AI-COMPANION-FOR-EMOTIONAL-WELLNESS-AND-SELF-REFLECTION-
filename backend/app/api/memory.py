"""Cross-session memory: each user's own notes and their memory setting.

Notes are short, safety-checked summaries of earlier sessions (app/services/memory_service.py).
Users can read, delete and turn them off. Admins never see them.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, owned_session
from app.config import get_settings
from app.db.models import ConversationSession, User
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.memory import MemoryNote, MemoryOut, MemorySettings
from app.services.memory_service import clear_notes, memory_notes, set_memory_enabled

router = APIRouter(prefix="/api/memory", tags=["memory"])


def _memory(db: Session, user: User) -> MemoryOut:
    settings = get_settings()
    notes = [MemoryNote(session_id=s.id, type=s.type, title=s.title, summary=s.summary,
                        updated_at=s.summary_updated_at, last_active=s.last_active)
             for s in memory_notes(db, user.id)]
    return MemoryOut(enabled=user.memory_enabled, available=settings.memory_enabled and settings.store_transcripts,
                     sessions_used=settings.memory_sessions, notes=notes)


@router.get("", response_model=MemoryOut)
def my_memory(user: User = Depends(current_user), db: Session = Depends(get_db)) -> MemoryOut:
    """The current user's memory setting and notes, most recently active session first."""
    return _memory(db, user)


@router.post("/settings", response_model=MemoryOut)
def update_settings(body: MemorySettings, user: User = Depends(current_user),
                    db: Session = Depends(get_db)) -> MemoryOut:
    """Turn memory on or off. Turning it off also deletes every note."""
    if body.enabled != user.memory_enabled:
        set_memory_enabled(db, user, body.enabled)
    return _memory(db, user)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def forget_everything(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    """Delete all of the user's notes. Conversations stay in History."""
    clear_notes(db, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": ErrorResponse}})
def forget_note(conversation: ConversationSession = Depends(owned_session), user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> Response:
    """Delete one session's note. The conversation stays in History."""
    clear_notes(db, user.id, conversation.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
