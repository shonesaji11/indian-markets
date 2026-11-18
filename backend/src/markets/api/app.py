from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from markets.api.routers import calcs, data, data_quality, instruments, market, scans, views
from markets.bootstrap import Container, build_container
from markets.config import get_settings


def create_app(container: Optional[Container] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned = container is None
        app.state.container = container or build_container()
        yield
        if owned:
            app.state.container.close()

    app = FastAPI(title="Indian Markets", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (market.router, instruments.router, data.router, calcs.router, scans.router, views.router,
                   data_quality.router):
        app.include_router(router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    return app
