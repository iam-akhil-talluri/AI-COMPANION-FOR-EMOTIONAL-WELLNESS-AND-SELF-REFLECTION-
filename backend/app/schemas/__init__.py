"""Shared API schemas. Datetimes are serialized as UTC ISO 8601."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    detail: str
