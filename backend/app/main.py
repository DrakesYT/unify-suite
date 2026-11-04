from fastapi import FastAPI

from app.config import get_settings
from app.errors import register_error_handlers
from app.observability import add_request_context, configure_logging
from app.routers import (
    agents,
    approvals,
    auth,
    finance,
    health,
    procurement,
    sales,
    workflows,
)


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)
    app = FastAPI(
        title="UNIFY SUITE API",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    register_error_handlers(app)
    add_request_context(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(sales.router)
    app.include_router(procurement.router)
    app.include_router(finance.router)
    app.include_router(workflows.router)
    app.include_router(approvals.router)
    app.include_router(agents.router)
    return app


app = create_app()
