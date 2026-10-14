"""Bivariate electoral vs. indicator analysis endpoint (`/api/v1/analysis`)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response

from territorio.api.cache import check_not_modified_or_set_headers
from territorio.api.deps import get_repository
from territorio.api.repository import SqlDataRepository

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.get("/analysis", response_model=None)
def get_analysis(
    request: Request,
    response: Response,
    repo: Annotated[SqlDataRepository, Depends(get_repository)],
    indicator: Annotated[str, Query()],
    year: Annotated[int, Query()] = 2026,
    round_num: Annotated[int, Query(alias="round")] = 1,
    office: Annotated[str, Query()] = "president",
    bloc: Annotated[str, Query()] = "right",
    uf: Annotated[str | None, Query()] = None,
    level: Annotated[str, Query(pattern="^(municipality|uf)$")] = "municipality",
) -> dict[str, Any] | Response:
    """Returns unified bivariate correlation, trendline, deciles, scatter, and insights.

    Args:
        request: Incoming FastAPI request.
        response: Outgoing FastAPI response.
        repo: Injected read-only SQL data repository.
        indicator: Indicator code from `indicators.yaml`.
        year: Election year (defaults to 2026).
        round_num: Election round (defaults to 1).
        office: Electoral office (defaults to `president`).
        bloc: Ideological bloc (`left`, `center`, `right`).
        uf: Optional 2-letter UF filter.
        level: Territorial aggregation level ('municipality' or 'uf').

    Returns:
        Unified analysis dictionary or `304 Not Modified` response.
    """
    dv_id = repo.get_dataset_version_id()
    short_circuit = check_not_modified_or_set_headers(request, response, dv_id)
    if short_circuit is not None:
        return short_circuit
    return repo.get_analysis(
        year=year,
        office_str=office,
        round_num=round_num,
        indicator_code=indicator,
        bloc_str=bloc,
        uf=uf,
        level=level,
    )
