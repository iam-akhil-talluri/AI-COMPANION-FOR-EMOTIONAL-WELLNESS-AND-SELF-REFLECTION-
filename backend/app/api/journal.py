"""Private journal entries: list, save and delete. Only the author can read their entries."""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.journal import JournalCreate, JournalEntryOut, JournalList, JournalSaved
from app.services.journal_service import count_entries, create_entry, delete_entry, list_entries

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("", response_model=JournalList)
def my_journal(limit: int = Query(default=20, ge=1, le=200), offset: int = Query(default=0, ge=0),
               user: User = Depends(current_user), db: Session = Depends(get_db)) -> JournalList:
    """The user's journal entries, newest first."""
    entries = [JournalEntryOut.model_validate(e) for e in list_entries(db, user.id, limit, offset)]
    return JournalList(entries=entries, total=count_entries(db, user.id),
                       retention_days=get_settings().retention_days)


@router.post("", response_model=JournalSaved, status_code=status.HTTP_201_CREATED,
             responses={403: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
                        429: {"model": ErrorResponse}})
def save_entry(body: JournalCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> JournalSaved:
    """Save an entry. It is safety-checked: risky writing returns support or crisis resources."""
    outcome = create_entry(db, user, body.content, body.prompt)
    return JournalSaved(entry=JournalEntryOut.model_validate(outcome.entry), status=outcome.status,
                        risk_level=outcome.risk_level, resources=outcome.resources)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": ErrorResponse}})
def remove_entry(entry_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    delete_entry(db, user.id, entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
