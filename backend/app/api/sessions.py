"""Session endpoints: create, list, read, delete and send messages."""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, owned_session
from app.db.models import ConversationSession, User
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.sessions import ChatResponse, MessageCreate, MessageOut, SessionCreate, SessionDetail, SessionSummary
from app.services.chat_service import send_message
from app.services.conversation_service import create_session, delete_session, get_messages, list_sessions

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

CHAT_ERRORS = {
    404: {"model": ErrorResponse, "description": "Session not found"},
    422: {"model": ErrorResponse, "description": "Empty or too-long message"},
    429: {"model": ErrorResponse, "description": "Rate limit or conversation length limit reached"},
    503: {"model": ErrorResponse,
          "description": "safety_unavailable: the safety check could not run, so the message was not sent "
                         "(fails closed). reply_unavailable: the AI could not reply."},
}


@router.post("", response_model=SessionSummary, status_code=status.HTTP_201_CREATED)
def new_session(body: SessionCreate | None = None, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> ConversationSession:
    body = body or SessionCreate()
    return create_session(db, user.id, body.type, body.title, body.prompt)


@router.get("", response_model=list[SessionSummary])
def my_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ConversationSession]:
    """List the current user's sessions, most recently active first."""
    return list_sessions(db, user.id, limit, offset)


@router.get("/{session_id}", response_model=SessionDetail, responses={404: {"model": ErrorResponse}})
def session_detail(conversation: ConversationSession = Depends(owned_session),
                   db: Session = Depends(get_db)) -> SessionDetail:
    messages = [MessageOut.model_validate(m) for m in get_messages(db, conversation.id)]
    return SessionDetail(**SessionSummary.model_validate(conversation).model_dump(), messages=messages)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": ErrorResponse}})
def remove_session(conversation: ConversationSession = Depends(owned_session),
                   db: Session = Depends(get_db)) -> Response:
    """Delete a session and its messages."""
    delete_session(db, conversation)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{session_id}/messages", response_model=ChatResponse, responses=CHAT_ERRORS)
def post_message(body: MessageCreate, conversation: ConversationSession = Depends(owned_session),
                 db: Session = Depends(get_db)) -> ChatResponse:
    """Send a message. It is safety-checked before any AI call, and the reply is checked before it is returned."""
    outcome = send_message(db, conversation, body.content)
    return ChatResponse(session_id=outcome.session_id, status=outcome.status, response=outcome.response,
                        risk_level=outcome.risk_level, resources=outcome.resources, created_at=outcome.created_at)
