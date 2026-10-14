"""IBGE Localidades (S4) and Malha Municipal 2025 (S3) source adapters."""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from territorio.domain import CAPITAL_CD_IBGE_SET, UF_BY_SIGLA
from territorio.etl.http import CachedArtifact, CachedHttpClient
from territorio.etl.transform.geometry import TerritoryError

IBGE_LOCALIDADES_URL = (
    "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?view=nivelado"
)
IBGE_MALHA_URL_TEMPLATE = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_municipais/municipio_{year}/Brasil/BR_Municipios_{year}.zip"
)
EXPECTED_MUNICIPALITY_COUNT = 5571
IBGE_WATER_BODY_CODES: frozenset[int] = frozenset({4300001, 4300002})


def fetch_municipality_list(
    client: CachedHttpClient,
    *,
    force_refresh: bool = False,
) -> CachedArtifact:
    """Downloads the official IBGE municipality master list (S4).

    Args:
        client: Cached HTTP client instance.
        force_refresh: If True, bypasses local disk cache.

    Returns:
        CachedArtifact pointing to the downloaded JSON file.
    """
    _, artifact = client.get_json(
        source="ibge_geo",
        url=IBGE_LOCALIDADES_URL,
        cache_key="localidades_municipios_nivelado.json",
        force_refresh=force_refresh,
    )
    return artifact


def parse_municipality_list(
    path: Path,
    *,
    expected_count: int | None = EXPECTED_MUNICIPALITY_COUNT,
) -> pd.DataFrame:
    """Parses the IBGE Localidades JSON into the canonical municipality DataFrame.

    Args:
        path: Path to the cached JSON file from IBGE Localidades.
        expected_count: Expected municipality count (defaults to 5,571; None skips).

    Returns:
        DataFrame with `cd_ibge`, `name`, `uf`, `uf_code`, `region`, `is_capital`.

    Raises:
        TerritoryError: If the row count or municipality codes are invalid.
    """
    raw_items = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, int | str | bool]] = []
    for item in raw_items:
        if "municipio-id" in item:
            cd_ibge = int(item["municipio-id"])
            name = str(item["municipio-nome"]).strip()
            uf = str(item["UF-sigla"]).strip().upper()
            uf_code = int(item.get("UF-id") or UF_BY_SIGLA[uf].uf_code)
            region = str(item.get("regiao-nome") or UF_BY_SIGLA[uf].region).strip()
        else:
            cd_ibge = int(item["id"])
            name = str(item["nome"]).strip()
            uf_obj = item["microrregiao"]["mesorregiao"]["UF"]
            uf = str(uf_obj["sigla"]).strip().upper()
            uf_code = int(uf_obj["id"])
            region = str(uf_obj["regiao"]["nome"]).strip()

        rows.append(
            {
                "cd_ibge": cd_ibge,
                "name": name,
                "uf": uf,
                "uf_code": uf_code,
                "region": region,
                "is_capital": cd_ibge in CAPITAL_CD_IBGE_SET,
            }
        )

    df = pd.DataFrame(rows).sort_values("cd_ibge").reset_index(drop=True)
    if df["cd_ibge"].duplicated().any():
        dups = df.loc[df["cd_ibge"].duplicated(), "cd_ibge"].tolist()
        raise TerritoryError(f"Duplicate cd_ibge in IBGE master list: {dups}")

    if expected_count is not None and len(df) != expected_count:
        raise TerritoryError(
            f"Expected {expected_count} municipalities in IBGE list, got {len(df)}"
        )
    return df


def fetch_geometry(
    client: CachedHttpClient,
    year: int = 2025,
    *,
    force_refresh: bool = False,
) -> CachedArtifact:
    """Downloads the IBGE Malha Municipal shapefile zip archive (S3).

    Args:
        client: Cached HTTP client instance.
        year: Reference year of the mesh (must be >= 2025 for 5,571 municipalities).
        force_refresh: If True, re-downloads even if cached.

    Returns:
        CachedArtifact pointing to the downloaded ZIP file.
    """
    url = IBGE_MALHA_URL_TEMPLATE.format(year=year)
    return client.download(
        source="ibge_geo",
        url=url,
        filename=f"BR_Municipios_{year}.zip",
        force_refresh=force_refresh,
    )


def parse_geometry(zip_path: Path) -> gpd.GeoDataFrame:
    """Reads the IBGE shapefile zip archive into a GeoDataFrame using pyogrio.

    Args:
        zip_path: Local path to `BR_Municipios_2025.zip`.

    Returns:
        GeoDataFrame with columns `cd_ibge`, `area_km2`, and `geometry`.

    Raises:
        TerritoryError: If required columns (`CD_MUN`, `AREA_KM2`) are missing.
    """
    gdf = gpd.read_file(zip_path, engine="pyogrio")
    col_map = {c.upper(): c for c in gdf.columns}
    if "CD_MUN" not in col_map or "AREA_KM2" not in col_map:
        raise TerritoryError(
            f"Shapefile missing required columns CD_MUN/AREA_KM2: {list(gdf.columns)}"
        )

    cd_col = col_map["CD_MUN"]
    area_col = col_map["AREA_KM2"]
    result = gpd.GeoDataFrame(
        {
            "cd_ibge": gdf[cd_col].astype(str).str.strip().astype(int),
            "area_km2": pd.to_numeric(gdf[area_col], errors="raise").astype(float),
            "geometry": gdf.geometry,
        },
        crs=gdf.crs,
    )
    result = result.loc[~result["cd_ibge"].isin(IBGE_WATER_BODY_CODES)].reset_index(
        drop=True
    )
    return result
