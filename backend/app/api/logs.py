"""Admin access to the operational event log."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.models import User
from app.db.session import get_db
from app.schemas.system import LogEntry
from app.services.event_log import recent_logs

router = APIRouter(prefix="/api", tags=["logs"])


@router.get("/admin/logs", response_model=list[LogEntry])
def admin_logs(limit: int = Query(default=50, ge=1, le=500), _: User = Depends(require_admin),
               db: Session = Depends(get_db)) -> list[dict]:
    return recent_logs(db, limit)
