from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.system import HealthResponse
from app.services.health_service import service_health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
@router.get("/api/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
def health(db: Session = Depends(get_db)) -> JSONResponse:
    """Readiness probe: 200 when the database is reachable and migrated, otherwise 503."""
    body = service_health(db)
    return JSONResponse(status_code=200 if body["status"] == "healthy" else 503, content=body)
