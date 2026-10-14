"""Indicator choropleth map endpoint (`/api/v1/indicators/{code}/map`)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response

from territorio.api.cache import check_not_modified_or_set_headers
from territorio.api.deps import get_repository
from territorio.api.repository import SqlDataRepository

router = APIRouter(prefix="/api/v1/indicators", tags=["indicators"])


@router.get("/{code}/map", response_model=None)
def get_indicator_map(
    code: str,
    request: Request,
    response: Response,
    repo: Annotated[SqlDataRepository, Depends(get_repository)],
    ref_year: Annotated[int | None, Query()] = None,
    uf: Annotated[str | None, Query()] = None,
    level: Annotated[str, Query(pattern="^(municipality|uf)$")] = "municipality",
) -> dict[str, Any] | Response:
    """Returns compact columnar municipal or UF indicator values and quantiles.

    Args:
        code: Indicator code from `indicators.yaml`.
        request: Incoming FastAPI request.
        response: Outgoing FastAPI response.
        repo: Injected read-only SQL data repository.
        ref_year: Optional explicit reference year.
        uf: Optional 2-letter UF filter.
        level: Territorial aggregation level ('municipality' or 'uf').

    Returns:
        Columnar indicator map dictionary or `304 Not Modified` response.
    """
    dv_id = repo.get_dataset_version_id()
    short_circuit = check_not_modified_or_set_headers(request, response, dv_id)
    if short_circuit is not None:
        return short_circuit
    return repo.get_indicator_map(code, ref_year=ref_year, uf=uf, level=level)
