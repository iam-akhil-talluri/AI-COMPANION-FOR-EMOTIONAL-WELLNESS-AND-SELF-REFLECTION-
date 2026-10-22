"""HTTP middleware."""

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.errors import error_body, internal_error_response

logger = logging.getLogger(__name__)

# Upper bound on request body size.
MAX_BODY_BYTES = 256 * 1024


class RequestGuardMiddleware(BaseHTTPMiddleware):
    """Return a JSON 500 for unhandled errors, limit body size and set X-Request-ID.

    Added innermost so that error responses still receive CORS headers.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            response: Response = JSONResponse(status_code=413, content=error_body(
                "payload_too_large", "This request is too large. Try sending a shorter message."))
        else:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("Unhandled error request_id=%s path=%s", request_id, request.url.path)
                response = internal_error_response()
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api"):
            # API responses must not be cached or rendered as a page.
            response.headers["Cache-Control"] = "no-store"
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response
