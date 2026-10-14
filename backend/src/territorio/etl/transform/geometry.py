"""Geometry validation, MultiPolygon promotion, and PostGIS LOD simplification."""

import geopandas as gpd
import pandas as pd
import shapely
import sqlalchemy as sa
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from territorio.domain import StepResult


class TerritoryError(ValueError):
    """Raised when municipal territory or geometry validation fails."""


def _promote_to_multipolygon(geom: BaseGeometry) -> MultiPolygon:
    """Converts a valid Polygon or GeometryCollection into a MultiPolygon.

    Args:
        geom: Input Shapely geometry after `make_valid`.

    Returns:
        MultiPolygon containing all polygonal parts of `geom`.

    Raises:
        TerritoryError: If the geometry is empty or contains no polygonal components.
    """
    if geom is None or geom.is_empty:
        raise TerritoryError(
            "Empty geometry encountered during MultiPolygon promotion."
        )
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    polygons = [
        part
        for part in getattr(geom, "geoms", [])
        if isinstance(part, (Polygon, MultiPolygon))
    ]
    flat_polys: list[Polygon] = []
    for item in polygons:
        if isinstance(item, Polygon):
            flat_polys.append(item)
        else:
            flat_polys.extend(item.geoms)
    if not flat_polys:
        raise TerritoryError(f"Geometry {geom.geom_type} has no polygon components.")
    return MultiPolygon(flat_polys)


def prepare_municipal_geometries(
    gdf: gpd.GeoDataFrame,
    master_df: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """Validates municipal geometries against the master list and converts to EPSG:3857.

    Args:
        gdf: Raw GeoDataFrame with `cd_ibge`, `area_km2`, and `geometry`.
        master_df: Canonical IBGE master list DataFrame with `cd_ibge`.

    Returns:
        GeoDataFrame in EPSG:3857 with valid `MultiPolygon` geometries.

    Raises:
        TerritoryError: If the set of `cd_ibge` does not match `master_df` 1:1.
    """
    geo_ids = set(gdf["cd_ibge"].astype(int).tolist())
    master_ids = set(master_df["cd_ibge"].astype(int).tolist())
    if geo_ids != master_ids:
        missing_in_geo = sorted(master_ids - geo_ids)
        extra_in_geo = sorted(geo_ids - master_ids)
        raise TerritoryError(
            f"Geometry cd_ibge mismatch: missing={missing_in_geo[:10]}, "
            f"extra={extra_in_geo[:10]}"
        )

    merged = master_df.merge(
        gdf[["cd_ibge", "area_km2", "geometry"]],
        on="cd_ibge",
        how="inner",
        validate="one_to_one",
        indicator=True,
    )
    if (merged["_merge"] != "both").any():
        raise TerritoryError(
            "Non-matching rows found when joining master list and mesh."
        )
    merged = merged.drop(columns=["_merge"])

    geo_merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=gdf.crs)
    geo_3857 = geo_merged.to_crs(epsg=3857)
    valid_geoms = shapely.make_valid(geo_3857.geometry.to_numpy())
    multi_geoms = [_promote_to_multipolygon(g) for g in valid_geoms]
    geo_3857["geometry"] = gpd.GeoSeries(multi_geoms, crs="EPSG:3857")
    return geo_3857.sort_values("cd_ibge").reset_index(drop=True)


def extract_area_indicator_df(
    prepared_gdf: gpd.GeoDataFrame,
    ref_year: int = 2025,
) -> pd.DataFrame:
    """Extracts the standardized `area_km2` indicator DataFrame from the mesh.

    Args:
        prepared_gdf: Validated GeoDataFrame containing `cd_ibge` and `area_km2`.
        ref_year: Mesh reference year (defaults to 2025).

    Returns:
        DataFrame conforming to IndicatorValueSchema (`cd_ibge`, `ref_year`, `value`,
        `value_text`, `missing_reason`).
    """
    return pd.DataFrame(
        {
            "cd_ibge": prepared_gdf["cd_ibge"].astype(int),
            "ref_year": int(ref_year),
            "value": prepared_gdf["area_km2"].astype(float),
            "value_text": None,
            "missing_reason": None,
        }
    )


def load_territory_and_derive_lods(
    engine: sa.Engine,
    prepared_gdf: gpd.GeoDataFrame,
    *,
    source_url: str | None = None,
    sha256: str | None = None,
) -> StepResult:
    """Loads municipalities and full geometries into PostGIS and derives 3 LODs.

    Args:
        engine: SQLAlchemy Engine connected to PostGIS.
        prepared_gdf: Validated GeoDataFrame in EPSG:3857 with 5,571 rows.
        source_url: Optional URL of the shapefile archive.
        sha256: Optional SHA-256 hex digest of the shapefile archive.

    Returns:
        StepResult summarizing rows read and written.

    Raises:
        TerritoryError: If PostGIS produces invalid geometries after simplification.
    """
    rows_in = len(prepared_gdf)
    mun_records = [
        {
            "cd_ibge": int(row.cd_ibge),
            "name": str(row.name),
            "uf": str(row.uf),
            "uf_code": int(row.uf_code),
            "region": str(row.region),
            "is_capital": bool(row.is_capital),
            "area_km2": float(row.area_km2),
        }
        for row in prepared_gdf.itertuples(index=False)
    ]
    geom_records = [
        {
            "cd_ibge": int(row.cd_ibge),
            "wkb": shapely.to_wkb(row.geometry, hex=False),
        }
        for row in prepared_gdf.itertuples(index=False)
    ]

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO municipality (
                    cd_ibge, name, uf, uf_code, region, is_capital, area_km2
                )
                VALUES (:cd_ibge, :name, :uf, :uf_code, :region, :is_capital, :area_km2)
                ON CONFLICT (cd_ibge) DO UPDATE SET
                    name = EXCLUDED.name,
                    uf = EXCLUDED.uf,
                    uf_code = EXCLUDED.uf_code,
                    region = EXCLUDED.region,
                    is_capital = EXCLUDED.is_capital,
                    area_km2 = EXCLUDED.area_km2
                """
            ),
            mun_records,
        )

        conn.execute(
            sa.text(
                """
                DROP TABLE IF EXISTS staging.municipality_geom_full;
                CREATE TABLE staging.municipality_geom_full (
                    cd_ibge integer PRIMARY KEY,
                    geom geometry(MultiPolygon, 3857) NOT NULL
                );
                """
            )
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO staging.municipality_geom_full (cd_ibge, geom)
                VALUES (:cd_ibge, ST_Multi(ST_MakeValid(ST_GeomFromWKB(:wkb, 3857))))
                """
            ),
            geom_records,
        )

        geos_ver_raw = str(
            conn.execute(sa.text("SELECT PostGIS_GEOS_Version()")).scalar() or "3.9.0"
        )
        geos_parts = [
            int(x) for x in geos_ver_raw.split("-")[0].split(".")[:2] if x.isdigit()
        ]
        has_coverage_geos = tuple(geos_parts) >= (3, 12)

        conn.execute(sa.text("DELETE FROM municipality_geom; DELETE FROM uf_geom;"))
        if has_coverage_geos:
            invalid_edges = int(
                conn.execute(
                    sa.text(
                        """
                        SELECT count(*) FROM (
                            SELECT ST_CoverageInvalidEdges(geom, 1.0) OVER () AS e
                            FROM staging.municipality_geom_full
                        ) s WHERE e IS NOT NULL
                        """
                    )
                ).scalar_one()
            )
            if invalid_edges > 0:
                conn.execute(
                    sa.text(
                        """
                        UPDATE staging.municipality_geom_full
                        SET geom = ST_Multi(ST_MakeValid(ST_SnapToGrid(geom, 0.5)))
                        """
                    )
                )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO municipality_geom (cd_ibge, lod, geom)
                    SELECT
                        cd_ibge,
                        l.lod,
                        ST_Multi(
                            ST_MakeValid(
                                ST_CoverageSimplify(geom, l.tol) OVER (
                                    PARTITION BY l.lod
                                )
                            )
                        )
                    FROM staging.municipality_geom_full
                    CROSS JOIN (
                        VALUES (0, 5500.0), (1, 300.0), (2, 30.0)
                    ) AS l(lod, tol)
                    """
                )
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO uf_geom (uf, lod, geom)
                    SELECT
                        m.uf,
                        l.lod,
                        ST_Multi(
                            ST_MakeValid(
                                ST_SimplifyPreserveTopology(ST_Union(f.geom), l.tol)
                            )
                        )
                    FROM staging.municipality_geom_full f
                    JOIN municipality m USING (cd_ibge)
                    CROSS JOIN (
                        VALUES (0, 5500.0), (1, 300.0), (2, 30.0)
                    ) AS l(lod, tol)
                    GROUP BY m.uf, l.lod, l.tol
                    """
                )
            )
        else:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO municipality_geom (cd_ibge, lod, geom)
                    SELECT
                        cd_ibge,
                        l.lod,
                        ST_Multi(
                            ST_MakeValid(ST_SimplifyPreserveTopology(geom, l.tol))
                        )
                    FROM staging.municipality_geom_full
                    CROSS JOIN (
                        VALUES (0, 5500.0), (1, 300.0), (2, 30.0)
                    ) AS l(lod, tol)
                    """
                )
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO uf_geom (uf, lod, geom)
                    SELECT
                        m.uf,
                        l.lod,
                        ST_Multi(
                            ST_MakeValid(
                                ST_SimplifyPreserveTopology(ST_Union(f.geom), l.tol)
                            )
                        )
                    FROM staging.municipality_geom_full f
                    JOIN municipality m USING (cd_ibge)
                    CROSS JOIN (
                        VALUES (0, 5500.0), (1, 300.0), (2, 30.0)
                    ) AS l(lod, tol)
                    GROUP BY m.uf, l.lod, l.tol
                    """
                )
            )

        conn.execute(
            sa.text(
                """
                UPDATE municipality m SET
                    label_point = ST_Transform(ST_PointOnSurface(f.geom), 4326),
                    bbox = ST_Transform(ST_Envelope(f.geom), 4326)
                FROM staging.municipality_geom_full f
                WHERE f.cd_ibge = m.cd_ibge
                """
            )
        )

        invalid_geom_count = int(
            conn.execute(
                sa.text(
                    """
                    SELECT count(*) FROM municipality_geom
                    WHERE NOT ST_IsValid(geom) OR ST_IsEmpty(geom)
                    """
                )
            ).scalar_one()
        )
        if invalid_geom_count > 0:
            raise TerritoryError(
                f"PostGIS generated {invalid_geom_count} invalid LOD geometries."
            )

    return StepResult(
        step="territory",
        rows_in=rows_in,
        rows_out=rows_in * 3,
        dropped={},
        source_url=source_url,
        sha256=sha256,
    )
