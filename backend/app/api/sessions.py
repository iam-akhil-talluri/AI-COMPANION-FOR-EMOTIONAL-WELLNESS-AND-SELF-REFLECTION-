"""Session endpoints: create, list (History), export, read, delete and send messages."""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, owned_session
from app.db.models import ConversationSession, User
from app.db.session import get_db
from app.db.types import utc_now
from app.errors import AppError
from app.schemas import ErrorResponse
from app.schemas.sessions import (
    ChatResponse,
    ExportedJournalEntry,
    HistoryExport,
    MessageCreate,
    MessageOut,
    SessionCreate,
    SessionDetail,
    SessionSummary,
)
from app.services.chat_service import send_message
from app.services.conversation_service import (
    count_sessions,
    create_session,
    delete_all_sessions,
    delete_session,
    export_history,
    get_messages,
    list_sessions,
)
from app.services.event_log import log_event
from app.services.journal_service import list_entries
from app.services.memory_service import summarize_user_sessions
from app.services.rate_limiter import limiter

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

EXPORTS_PER_HOUR = 10

CHAT_ERRORS = {
    404: {"model": ErrorResponse, "description": "Session not found"},
    422: {"model": ErrorResponse, "description": "Empty or too-long message"},
    429: {"model": ErrorResponse, "description": "Rate limit or conversation length limit reached"},
    503: {"model": ErrorResponse,
          "description": "safety_unavailable: the safety check could not run, so the message was not sent "
                         "(fails closed). reply_unavailable: the AI could not reply."},
}


def _detail(conversation: ConversationSession, messages: list) -> SessionDetail:
    return SessionDetail(**SessionSummary.model_validate(conversation).model_dump(),
                         messages=[MessageOut.model_validate(m) for m in messages])


@router.post("", response_model=SessionSummary, status_code=status.HTTP_201_CREATED)
def new_session(background: BackgroundTasks, body: SessionCreate | None = None, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> ConversationSession:
    body = body or SessionCreate()
    conversation = create_session(db, user.id, body.type, body.title, body.prompt)
    # The user has moved on from their earlier sessions: write their memory notes now (after the response).
    background.add_task(summarize_user_sessions, user.id, conversation.id)
    return conversation


@router.get("", response_model=list[SessionSummary])
def my_sessions(
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    type: Literal["conversation", "reflection"] | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100, description="Search titles and message text"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ConversationSession]:
    """List the current user's sessions, most recently active first. X-Total-Count holds the number of matches."""
    response.headers["X-Total-Count"] = str(count_sessions(db, user.id, type, q))
    return list_sessions(db, user.id, limit, offset, type, q)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def remove_all_sessions(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    """Delete all of the user's sessions, their messages and memory notes."""
    deleted = delete_all_sessions(db, user.id)
    log_event(db, "history_cleared", detail=f"sessions={deleted}")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Declared before /{session_id} so "export" is not read as a session ID.
@router.get("/export", response_model=HistoryExport, responses={429: {"model": ErrorResponse}})
def export_sessions(user: User = Depends(current_user), db: Session = Depends(get_db)) -> HistoryExport:
    """Download the user's whole History (sessions and messages) and journal as JSON."""
    if not limiter.allow(f"export:user:{user.id}", EXPORTS_PER_HOUR, 3600):
        raise AppError("rate_limited", 429, "You've downloaded your history several times recently. "
                       "Please try again later.", headers={"Retry-After": "3600"})
    sessions = [_detail(conversation, messages) for conversation, messages in export_history(db, user.id)]
    journal = [ExportedJournalEntry.model_validate(e) for e in list_entries(db, user.id, limit=100_000)]
    log_event(db, "history_exported", detail=f"sessions={len(sessions)} journal_entries={len(journal)}")
    db.commit()
    return HistoryExport(exported_at=utc_now(), username=user.username, sessions=sessions, journal=journal)


@router.get("/{session_id}", response_model=SessionDetail, responses={404: {"model": ErrorResponse}})
def session_detail(conversation: ConversationSession = Depends(owned_session),
                   db: Session = Depends(get_db)) -> SessionDetail:
    return _detail(conversation, get_messages(db, conversation.id))


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": ErrorResponse}})
def remove_session(conversation: ConversationSession = Depends(owned_session),
                   db: Session = Depends(get_db)) -> Response:
    """Delete a session, its messages and its memory note."""
    delete_session(db, conversation)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{session_id}/messages", response_model=ChatResponse, responses=CHAT_ERRORS)
def post_message(body: MessageCreate, conversation: ConversationSession = Depends(owned_session),
                 db: Session = Depends(get_db)) -> ChatResponse:
    """Send a message. It is safety-checked before any AI call, and the reply is checked before it is returned."""
    outcome = send_message(db, conversation, body.content)
    return ChatResponse(session_id=outcome.session_id, status=outcome.status, response=outcome.response,
                        risk_level=outcome.risk_level, resources=outcome.resources, created_at=outcome.created_at)
