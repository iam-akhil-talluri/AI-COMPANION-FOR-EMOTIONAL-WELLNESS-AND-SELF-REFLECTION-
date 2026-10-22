from datetime import datetime

from pydantic import BaseModel


class ServiceStatus(BaseModel):
    name: str
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    environment: str
    services: list[ServiceStatus]


class LogEntry(BaseModel):
    time: datetime
    type: str
    event: str
    message: str
    status: str
    environment: str
