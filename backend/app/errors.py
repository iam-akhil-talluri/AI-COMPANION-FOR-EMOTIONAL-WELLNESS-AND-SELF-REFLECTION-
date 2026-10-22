"""API error type and exception handlers.

All errors are returned as {"code": ..., "detail": ...}; `detail` is safe to display.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

TEMPORARY_ERROR = "Something went wrong on our side. Please try again in a moment."

# Validation error type whose message is shown to users as-is.
FRIENDLY_ERROR = "friendly"


class AppError(Exception):
    """Expected error with an HTTP status and a user-facing message."""

    def __init__(self, code: str, status_code: int, detail: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.detail = detail
        self.headers = headers


def error_body(code: str, detail: str, **extra) -> dict:
    return {"code": code, "detail": detail, **extra}


_HTTP_CODES = {
    400: "bad_request",
    401: "not_authenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    429: "rate_limited",
}


def _validation_detail(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "The request was not valid."
    first = errors[0]
    if first.get("type") == FRIENDLY_ERROR:
        return first.get("msg", "Invalid value")
    field = ".".join(str(part) for part in first.get("loc", ()) if part not in ("body", "query", "path"))
    message = first.get("msg", "Invalid value")
    return f"{field}: {message}" if field else message


def internal_error_response() -> JSONResponse:
    return JSONResponse(status_code=500, content=error_body("internal_error", TEMPORARY_ERROR))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.detail), headers=exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        detail = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        return JSONResponse(status_code=exc.status_code, content=error_body(code, detail),
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # `errors` keeps the field-level details; `detail` is a single readable message.
        errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return JSONResponse(status_code=422,
                            content=error_body("validation_error", _validation_detail(exc), errors=errors))

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database error: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content=error_body("database_unavailable", TEMPORARY_ERROR))
