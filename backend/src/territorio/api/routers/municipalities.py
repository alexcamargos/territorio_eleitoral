"""Municipality autocomplete search and Stage 3 profile endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response

from territorio.api.cache import check_not_modified_or_set_headers
from territorio.api.deps import get_repository
from territorio.api.repository import SqlDataRepository

router = APIRouter(prefix="/api/v1/municipalities", tags=["municipalities"])


@router.get("/search", response_model=None)
def search_municipalities(
    request: Request,
    response: Response,
    repo: Annotated[SqlDataRepository, Depends(get_repository)],
    q: Annotated[str, Query(min_length=2)],
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> dict[str, Any] | Response:
    """Searches municipalities by accent-insensitive name substring.

    Args:
        request: Incoming FastAPI request.
        response: Outgoing FastAPI response.
        repo: Injected read-only SQL data repository.
        q: Query string (minimum 2 characters).
        limit: Maximum number of results (1..25, default 10).

    Returns:
        Dictionary `{'items': [...]}` or `304 Not Modified` response.
    """
    dv_id = repo.get_dataset_version_id()
    short_circuit = check_not_modified_or_set_headers(request, response, dv_id)
    if short_circuit is not None:
        return short_circuit
    return {"items": repo.search_municipalities(q, limit=limit)}


@router.get("/{cd_ibge}", response_model=None)
def get_municipality_profile(
    cd_ibge: int,
    request: Request,
    response: Response,
    repo: Annotated[SqlDataRepository, Depends(get_repository)],
    year: Annotated[int, Query()] = 2026,
    round_num: Annotated[int, Query(alias="round")] = 1,
) -> dict[str, Any] | Response:
    """Returns full electoral and socio-economic profile for one municipality.

    Args:
        cd_ibge: Canonical 7-digit IBGE municipality code.
        request: Incoming FastAPI request.
        response: Outgoing FastAPI response.
        repo: Injected read-only SQL data repository.
        year: Election year (defaults to 2026).
        round_num: Election round (defaults to 1).

    Returns:
        Municipality profile dictionary or `304 Not Modified` response.
    """
    dv_id = repo.get_dataset_version_id()
    short_circuit = check_not_modified_or_set_headers(request, response, dv_id)
    if short_circuit is not None:
        return short_circuit
    return repo.get_municipality_detail(cd_ibge, year=year, round_num=round_num)
