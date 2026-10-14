"""FastAPI dependency injection providers."""

from fastapi import Request

from territorio.api.repository import SqlDataRepository
from territorio.db.engine import get_engine


def get_repository(request: Request) -> SqlDataRepository:
    """Provides the `SqlDataRepository` instance from `app.state` or default engine.

    Args:
        request: Incoming FastAPI `Request`.

    Returns:
        Configured `SqlDataRepository` instance.
    """
    repo = getattr(request.app.state, "repository", None)
    if repo is not None:
        return repo
    new_repo = SqlDataRepository(get_engine())
    request.app.state.repository = new_repo
    return new_repo
