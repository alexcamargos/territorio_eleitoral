"""Health and bootstrap metadata endpoints (`/api/v1/health`, `/api/v1/meta`)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from territorio.api.cache import check_not_modified_or_set_headers
from territorio.api.deps import get_repository
from territorio.api.repository import SqlDataRepository

router = APIRouter(prefix="/api/v1", tags=["meta"])


@router.get("/health")
def get_health(
    repo: Annotated[SqlDataRepository, Depends(get_repository)],
) -> dict[str, Any]:
    """Returns database health, PostGIS version, and dataset metadata.

    Args:
        repo: Injected read-only SQL data repository.

    Returns:
        Health check payload dictionary.
    """
    return repo.get_health()


@router.get("/meta", response_model=None)
def get_meta(
    request: Request,
    response: Response,
    repo: Annotated[SqlDataRepository, Depends(get_repository)],
) -> dict[str, Any] | Response:
    """Returns bootstrap metadata (`elections`, `indicators`, `ufs`, `party_ideology`).

    Args:
        request: Incoming FastAPI request.
        response: Outgoing FastAPI response.
        repo: Injected read-only SQL data repository.

    Returns:
        Metadata dictionary or `304 Not Modified` response.
    """
    dv_id = repo.get_dataset_version_id()
    short_circuit = check_not_modified_or_set_headers(request, response, dv_id)
    if short_circuit is not None:
        return short_circuit
    return repo.get_meta()
