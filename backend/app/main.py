import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db import get_session_factory
from app.errors import register_error_handlers
from app.llm import get_optional_llm
from app.observability import add_request_context, configure_logging
from app.orchestrator import engine
from app.routers import (
    agents,
    ai,
    approvals,
    auth,
    calls,
    dashboard,
    explain,
    finance,
    health,
    hr,
    procurement,
    sales,
    settings,
    support,
    workflows,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """A restart (every deploy is one) cuts off workflow runs whose steps were in progress.
    Pick them up again, in the background so start-up is not held up by a model call."""
    try:
        factory = app.dependency_overrides.get(get_session_factory, get_session_factory)()
        with factory() as db:
            left_behind = engine.interrupted_runs(db)
        if left_behind:
            llm = app.dependency_overrides.get(get_optional_llm, get_optional_llm)()
            threading.Thread(
                target=engine.recover_interrupted, args=(factory, left_behind, llm), daemon=True
            ).start()
    except Exception:
        logger.exception("workflow_recovery_not_started")
    yield


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)
    app = FastAPI(
        title="UNIFY SUITE API",
        version="0.1.0",
        # No Swagger page: it needs scripts from another site, which the Content Security Policy
        # (rightly) refuses. The machine-readable description below stays available.
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    register_error_handlers(app)
    add_request_context(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(sales.router)
    app.include_router(hr.router)
    app.include_router(support.router)
    app.include_router(procurement.router)
    app.include_router(finance.router)
    app.include_router(workflows.router)
    app.include_router(approvals.router)
    app.include_router(agents.router)
    app.include_router(dashboard.router)
    app.include_router(dashboard.search_router)
    app.include_router(ai.router)
    app.include_router(explain.router)
    app.include_router(calls.router)
    app.include_router(settings.router)
    return app


app = create_app()
