from __future__ import annotations

from fastapi import FastAPI

from refactor_app.api.routes.health import router as health_router
from refactor_app.api.routes.jobs import router as jobs_router
from refactor_app.api.routes.ops import router as ops_router
from refactor_app.api.routes.resources import router as resources_router


def create_app() -> FastAPI:
    app = FastAPI(title="refactor-app")
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(resources_router)
    app.include_router(ops_router)
    return app
