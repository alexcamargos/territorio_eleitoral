"""Mapbox Vector Tiles (`MVT`) endpoint (`/tiles/municipalities/{z}/{x}/{y}.pbf`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from territorio.api.cache import check_not_modified_or_set_headers
from territorio.api.deps import get_repository
from territorio.api.repository import SqlDataRepository

router = APIRouter(prefix="/tiles", tags=["tiles"])

MVT_MEDIA_TYPE = "application/vnd.mapbox-vector-tile"


@router.get("/municipalities/{z}/{x}/{y}.pbf")
def get_municipality_tile(
    z: int,
    x: int,
    y: int,
    request: Request,
    response: Response,
    repo: Annotated[SqlDataRepository, Depends(get_repository)],
) -> Response:
    """Serves a PostGIS Mapbox Vector Tile (`municipalities` + `ufs` layers).

    Args:
        z: Tile zoom level (`0..12`).
        x: Tile X coordinate (`0..2^z - 1`).
        y: Tile Y coordinate (`0..2^z - 1`).
        request: Incoming FastAPI request.
        response: Outgoing FastAPI response.
        repo: Injected read-only SQL data repository.

    Returns:
        Binary `application/vnd.mapbox-vector-tile` response or `304 Not Modified`.
    """
    dv_id = repo.get_dataset_version_id()
    short_circuit = check_not_modified_or_set_headers(
        request, response, dv_id, is_tile=True
    )
    if short_circuit is not None:
        return short_circuit

    pbf = repo.get_mvt_tile(dv_id, z, x, y)
    return Response(
        content=pbf,
        media_type=MVT_MEDIA_TYPE,
        headers=dict(response.headers),
    )
