"""Unit tests for IBGE municipality list and 2025 geometry extraction/transformation."""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, Polygon

from territorio.etl.sources.ibge_geo import parse_municipality_list
from territorio.etl.transform.geometry import (
    TerritoryError,
    extract_area_indicator_df,
    prepare_municipal_geometries,
)


def test_parse_municipality_list_nivelado_format(tmp_path: Path) -> None:
    """Verifies parsing of `view=nivelado` JSON from IBGE Localidades API.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    payload = [
        {
            "municipio-id": 3550308,
            "municipio-nome": "São Paulo",
            "UF-sigla": "SP",
            "UF-id": 35,
            "regiao-nome": "Sudeste",
        },
        {
            "municipio-id": 5101837,
            "municipio-nome": "Boa Esperança do Norte",
            "UF-sigla": "MT",
            "UF-id": 51,
            "regiao-nome": "Centro-Oeste",
        },
    ]
    json_path = tmp_path / "municipios.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    df = parse_municipality_list(json_path, expected_count=None)
    assert list(df.columns) == [
        "cd_ibge",
        "name",
        "uf",
        "uf_code",
        "region",
        "is_capital",
    ]
    assert len(df) == 2
    sp_row = df.loc[df["cd_ibge"] == 3550308].iloc[0]
    assert bool(sp_row["is_capital"]) is True
    ben_row = df.loc[df["cd_ibge"] == 5101837].iloc[0]
    assert ben_row["name"] == "Boa Esperança do Norte"
    assert bool(ben_row["is_capital"]) is False


def test_parse_municipality_list_enforces_expected_count(tmp_path: Path) -> None:
    """Verifies that `parse_municipality_list` raises TerritoryError on count mismatch.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    payload = [
        {
            "municipio-id": 3550308,
            "municipio-nome": "São Paulo",
            "UF-sigla": "SP",
            "UF-id": 35,
            "regiao-nome": "Sudeste",
        }
    ]
    json_path = tmp_path / "municipios.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TerritoryError, match="Expected 5571 municipalities"):
        parse_municipality_list(json_path, expected_count=5571)


def test_prepare_municipal_geometries_reprojects_and_promotes_multipolygon() -> None:
    """Verifies CRS conversion to 3857, validity repair, and MultiPolygon promotion."""
    master_df = pd.DataFrame(
        {
            "cd_ibge": [3550308, 5101837],
            "name": ["São Paulo", "Boa Esperança do Norte"],
            "uf": ["SP", "MT"],
            "uf_code": [35, 51],
            "region": ["Sudeste", "Centro-Oeste"],
            "is_capital": [True, False],
        }
    )
    poly1 = Polygon([(-46.6, -23.5), (-46.5, -23.5), (-46.5, -23.4), (-46.6, -23.4)])
    poly2 = Polygon([(-55.5, -13.5), (-55.4, -13.5), (-55.4, -13.4), (-55.5, -13.4)])
    gdf = gpd.GeoDataFrame(
        {
            "cd_ibge": [3550308, 5101837],
            "area_km2": [1521.2, 4712.5],
            "geometry": [poly1, poly2],
        },
        crs="EPSG:4674",
    )

    prepared = prepare_municipal_geometries(gdf, master_df)
    assert prepared.crs is not None
    assert prepared.crs.to_epsg() == 3857
    assert len(prepared) == 2
    assert all(isinstance(geom, MultiPolygon) for geom in prepared.geometry)
    assert all(geom.is_valid for geom in prepared.geometry)

    area_df = extract_area_indicator_df(prepared, ref_year=2025)
    assert list(area_df.columns) == [
        "cd_ibge",
        "ref_year",
        "value",
        "value_text",
        "missing_reason",
    ]
    assert len(area_df) == 2
    assert area_df.loc[area_df["cd_ibge"] == 3550308, "value"].iloc[0] == 1521.2


def test_prepare_municipal_geometries_raises_on_id_mismatch() -> None:
    """Verifies that a shapefile/master ID discrepancy raises TerritoryError."""
    master_df = pd.DataFrame(
        {
            "cd_ibge": [3550308, 5101837],
            "name": ["São Paulo", "Boa Esperança do Norte"],
            "uf": ["SP", "MT"],
            "uf_code": [35, 51],
            "region": ["Sudeste", "Centro-Oeste"],
            "is_capital": [True, False],
        }
    )
    poly = Polygon([(-46.6, -23.5), (-46.5, -23.5), (-46.5, -23.4), (-46.6, -23.4)])
    gdf = gpd.GeoDataFrame(
        {
            "cd_ibge": [3550308],
            "area_km2": [1521.2],
            "geometry": [poly],
        },
        crs="EPSG:4674",
    )

    with pytest.raises(TerritoryError, match="5101837"):
        prepare_municipal_geometries(gdf, master_df)
