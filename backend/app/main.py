"""FastAPI application factory and entry point."""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, health, logs, sessions
from app.config import Settings, get_settings
from app.errors import register_error_handlers
from app.logging_config import configure_logging
from app.middleware import RequestGuardMiddleware, SecurityHeadersMiddleware
from app.services import reply_provider
from app.services.retention import retention_loop

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)
    if not reply_provider.is_configured():
        logger.warning("No reply provider is registered: sending a message will return 503 until one is")
    retention_task = None
    if settings.retention_days > 0 and settings.retention_interval_hours > 0:
        retention_task = asyncio.create_task(retention_loop(settings))
    yield
    if retention_task is not None:
        retention_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await retention_task


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    docs = settings.api_docs_enabled
    app = FastAPI(
        title="AI Companion for Emotional Wellness & Self-Reflection",
        description="Backend API: accounts, conversation sessions and memory, logging and health checks. "
        "This system is not therapy, medical care, diagnosis, or crisis intervention.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.settings = settings

    # Middleware is added innermost first: request guard, CORS, security headers.
    app.add_middleware(RequestGuardMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # Bearer tokens only; no cookies.
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware)

    register_error_handlers(app)
    for router in (health.router, auth.router, sessions.router, logs.router):
        app.include_router(router)
    return app


app = create_app()
