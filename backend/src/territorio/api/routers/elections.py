"""Electoral map and summary endpoints (`/api/v1/elections/...`)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response

from territorio.api.cache import check_not_modified_or_set_headers
from territorio.api.deps import get_repository
from territorio.api.repository import SqlDataRepository

router = APIRouter(prefix="/api/v1/elections", tags=["elections"])


@router.get("/{year}/{office}/{round}/map", response_model=None)
def get_election_map(
    year: int,
    office: str,
    round: int,
    request: Request,
    response: Response,
    repo: Annotated[SqlDataRepository, Depends(get_repository)],
    uf: Annotated[str | None, Query()] = None,
    level: Annotated[str, Query(pattern="^(municipality|uf)$")] = "municipality",
) -> dict[str, Any] | Response:
    """Returns compact columnar municipal or UF electoral shares for map choropleth.

    Args:
        year: Election year (e.g. 2026).
        office: Electoral office identifier.
        round: Election round (1 or 2).
        request: Incoming FastAPI request.
        response: Outgoing FastAPI response.
        repo: Injected read-only SQL data repository.
        uf: Optional 2-letter UF filter.
        level: Territorial aggregation level ('municipality' or 'uf').

    Returns:
        Columnar map dictionary or `304 Not Modified` response.
    """
    dv_id = repo.get_dataset_version_id()
    short_circuit = check_not_modified_or_set_headers(request, response, dv_id)
    if short_circuit is not None:
        return short_circuit
    return repo.get_election_map(year, office, round, uf=uf, level=level)
