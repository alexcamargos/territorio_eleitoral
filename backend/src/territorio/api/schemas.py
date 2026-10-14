"""Pydantic response schemas for `/api/v1/*` endpoints."""

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response model for `GET /api/v1/health`."""

    status: str
    postgis_version: str
    dataset_version: int | None
    published_at: str | None
    municipality_count: int


class MunicipalitySearchItem(BaseModel):
    """Single item in `GET /api/v1/municipalities/search`."""

    cd_ibge: int
    name: str
    uf: str
    region: str
    bbox: list[float]


class MunicipalitySearchResponse(BaseModel):
    """Response model for `GET /api/v1/municipalities/search`."""

    items: list[MunicipalitySearchItem]


class ErrorDetailModel(BaseModel):
    """Inner RFC 9457 error payload."""

    code: str
    message: str
    details: dict[str, Any]


class ErrorResponse(BaseModel):
    """Standard error envelope returned on 4xx/5xx responses."""

    error: ErrorDetailModel
