"""FastAPI application factory, CORS configuration, and router registration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from territorio import __version__
from territorio.api.errors import register_exception_handlers
from territorio.api.repository import SqlDataRepository
from territorio.api.routers import (
    analysis,
    elections,
    indicators,
    meta,
    municipalities,
    tiles,
)
from territorio.config import get_settings


def create_app(repository: SqlDataRepository | None = None) -> FastAPI:
    """Creates and configures the FastAPI application instance.

    Args:
        repository: Optional pre-configured `SqlDataRepository` (used in tests).

    Returns:
        Configured `FastAPI` application using `ORJSONResponse` by default.
    """
    settings = get_settings()
    app = FastAPI(
        title="Território Eleitoral API",
        version=__version__,
        default_response_class=ORJSONResponse,
    )
    if repository is not None:
        app.state.repository = repository

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["ETag", "X-Dataset-Version", "Cache-Control"],
    )

    register_exception_handlers(app)
    app.include_router(meta.router)
    app.include_router(elections.router)
    app.include_router(indicators.router)
    app.include_router(analysis.router)
    app.include_router(municipalities.router)
    app.include_router(tiles.router)

    return app


app = create_app()
