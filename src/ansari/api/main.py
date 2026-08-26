import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from ansari.api.config import get_settings
from ansari.api.routers import deployments, environments, health, pipelines, projects

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelNamesMapping()[settings.log_level]
    ),
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
log = structlog.get_logger("ansari.api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    log.info("startup", env=settings.env)
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ANSARI API",
        description="Orchestration API for CI/CD, GitOps deployment, and environment state.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["x-request-id"] = request_id
        log.info(
            "request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    app.include_router(health.router)
    app.include_router(projects.router)
    app.include_router(environments.router)
    app.include_router(pipelines.router)
    app.include_router(deployments.router)

    return app


app = create_app()
