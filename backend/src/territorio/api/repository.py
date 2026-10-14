"""Read-only SQL repository for electoral, indicator, analysis, and MVT queries."""

import functools
import unicodedata
from typing import Any

import numpy as np
import sqlalchemy as sa

from territorio.analytics.insights import (
    DIRECTION_LABELS_PT,
    STRENGTH_LABELS_PT,
    CategoryShareSummary,
    generate_analysis_insights,
)
from territorio.analytics.stats import (
    compute_correlation,
    compute_decile_shares,
    compute_extremes_contrast,
    compute_quantiles,
    compute_trendline,
)
from territorio.api.errors import ApiError
from territorio.domain import (
    UF_BY_SIGLA,
    UFS,
    Bloc,
    Office,
    ScaleHint,
    Theme,
    ValueType,
)

MVT_QUERY_SQL = """
WITH bounds AS (
  SELECT ST_TileEnvelope(:z, :x, :y) AS env
),
mun_mvt AS (
  SELECT ST_AsMVT(m, 'municipalities', 4096, 'geom', 'feature_id') AS tile
  FROM (
    SELECT
      g.cd_ibge::bigint AS feature_id,
      g.cd_ibge::bigint AS cd_ibge,
      mu.name,
      mu.uf,
      mu.region,
      ST_AsMVTGeom(
        CASE
          WHEN :lod = 0 THEN ST_SimplifyPreserveTopology(g.geom, 5500.0)
          ELSE g.geom
        END,
        bounds.env,
        4096,
        64,
        true
      ) AS geom
    FROM municipality_geom g
    JOIN municipality mu USING (cd_ibge)
    CROSS JOIN bounds
    WHERE g.lod = :lod
      AND g.geom && bounds.env
  ) m
  WHERE m.geom IS NOT NULL
),
uf_mvt AS (
  SELECT ST_AsMVT(u, 'ufs', 4096, 'geom', 'feature_id') AS tile
  FROM (
    SELECT
      m.uf_code::bigint AS feature_id,
      ug.uf,
      m.uf_code,
      ST_AsMVTGeom(
        CASE
          WHEN :lod = 0 THEN ST_SimplifyPreserveTopology(ug.geom, 5500.0)
          ELSE ug.geom
        END,
        bounds.env,
        4096,
        64,
        true
      ) AS geom
    FROM uf_geom ug
    JOIN (SELECT DISTINCT uf, uf_code FROM municipality) m ON m.uf = ug.uf
    CROSS JOIN bounds
    WHERE ug.lod = :lod
      AND ug.geom && bounds.env
  ) u
  WHERE u.geom IS NOT NULL
)
SELECT COALESCE((SELECT tile FROM mun_mvt), ''::bytea)
    || COALESCE((SELECT tile FROM uf_mvt), ''::bytea) AS pbf;
"""


def zoom_to_lod(z: int) -> int:
    """Maps a Web Mercator zoom level `z` (`0..12`) to a PostGIS `lod` (`0..2`).

    Args:
        z: Tile zoom level.

    Returns:
        LOD integer (`0`, `1`, or `2`).

    Raises:
        ApiError: With HTTP 404 when `z < 0` or `z > 12`.
    """
    if 0 <= z <= 5:
        return 0
    if 6 <= z <= 8:
        return 1
    if 9 <= z <= 12:
        return 2
    raise ApiError(
        status_code=404,
        code="TILE_NOT_FOUND",
        message=f"Zoom {z} fora da faixa suportada (0..12).",
        details={"z": z},
    )


def validate_office_round_uf(
    office_str: str,
    round_num: int,
    uf_str: str | None = None,
) -> tuple[Office, int, str | None]:
    """Validates `office`, `round`, and optional `uf` query/path parameters.

    Args:
        office_str: Office slug string.
        round_num: Election round number (`1` or `2`).
        uf_str: Optional two-letter state code.

    Returns:
        Tuple `(office_enum, round_num, normalized_uf)`.

    Raises:
        ApiError: With HTTP 400 (`INVALID_PARAMETER`) on invalid combinations.
    """
    try:
        office = Office(office_str.strip().lower())
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            code="INVALID_PARAMETER",
            message=f"Cargo eleitoral inválido: '{office_str}'.",
            details={"office": office_str},
        ) from exc

    if round_num not in {1, 2}:
        raise ApiError(
            status_code=400,
            code="INVALID_PARAMETER",
            message=f"Turno inválido: {round_num} (permitido: 1 ou 2).",
            details={"round": round_num},
        )

    if round_num == 2 and office not in {Office.PRESIDENT, Office.GOVERNOR}:
        raise ApiError(
            status_code=400,
            code="INVALID_PARAMETER",
            message=f"O cargo '{office.value}' não possui 2º turno.",
            details={"office": office.value, "round": round_num},
        )

    clean_uf: str | None = None
    if uf_str is not None and uf_str.strip():
        clean_uf = uf_str.strip().upper()
        if clean_uf not in UF_BY_SIGLA:
            raise ApiError(
                status_code=400,
                code="INVALID_PARAMETER",
                message=f"UF inválida: '{uf_str}'.",
                details={"uf": uf_str},
            )

    return office, round_num, clean_uf


def validate_bloc(bloc_str: str) -> Bloc:
    """Validates an ideological bloc query parameter (`left`, `center`, `right`).

    Args:
        bloc_str: Raw bloc string.

    Returns:
        Validated `Bloc` enum.

    Raises:
        ApiError: With HTTP 400 (`INVALID_PARAMETER`) if invalid.
    """
    try:
        return Bloc(bloc_str.strip().lower())
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            code="INVALID_PARAMETER",
            message=f"Bloco ideológico inválido: '{bloc_str}'.",
            details={"bloc": bloc_str},
        ) from exc


def _resolve_office_db_values(office: Office) -> list[str]:
    """Expands `state_or_district_deputy` into `['state_deputy', 'district_deputy']`.

    Args:
        office: Validated `Office` enum.

    Returns:
        List of database `election.office` values.
    """
    if office == Office.STATE_OR_DISTRICT_DEPUTY:
        return [Office.STATE_DEPUTY.value, Office.DISTRICT_DEPUTY.value]
    return [office.value]


class SqlDataRepository:
    """Read-only SQLAlchemy Core repository backing all FastAPI endpoints.

    Attributes:
        engine: SQLAlchemy database engine.
    """

    def __init__(self, engine: sa.Engine) -> None:
        """Initializes the repository with a SQLAlchemy `Engine`.

        Args:
            engine: SQLAlchemy `Engine` connected to PostgreSQL/PostGIS.
        """
        self.engine = engine
        self._tile_fn = functools.lru_cache(maxsize=4096)(self._fetch_tile_uncached)

    def get_dataset_version_id(self) -> int:
        """Returns the latest published `dataset_version.id`.

        Returns:
            Integer `dataset_version.id`.

        Raises:
            ApiError: With HTTP 503 (`DATASET_NOT_READY`) if no version exists.
        """
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT id FROM dataset_version ORDER BY id DESC LIMIT 1")
            ).fetchone()
        if row is None:
            raise ApiError(
                status_code=503,
                code="DATASET_NOT_READY",
                message="Nenhuma versão de dados publicada no banco.",
            )
        return int(row[0])

    def get_health(self) -> dict[str, Any]:
        """Returns database health, PostGIS version, and published dataset metadata.

        Returns:
            Dictionary matching `HealthResponse`.
        """
        with self.engine.connect() as conn:
            pgis = conn.execute(sa.text("SELECT PostGIS_Lib_Version()")).scalar()
            mun_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM municipality")
            ).scalar()
            dv_row = conn.execute(
                sa.text(
                    "SELECT id, published_at FROM dataset_version "
                    "ORDER BY id DESC LIMIT 1"
                )
            ).fetchone()

        return {
            "status": "ok",
            "postgis_version": str(pgis or "3.5"),
            "dataset_version": int(dv_row[0]) if dv_row else None,
            "published_at": (dv_row[1].isoformat() if (dv_row and dv_row[1]) else None),
            "municipality_count": int(mun_count or 0),
        }

    def get_meta(self) -> dict[str, Any]:
        """Returns application bootstrap metadata (`GET /api/v1/meta`).

        Returns:
            Dictionary containing `dataset_version`, `default_selection`,
            `elections`, `indicators`, `ufs`, and `party_ideology`.
        """
        dv_id = self.get_dataset_version_id()
        with self.engine.connect() as conn:
            el_rows = (
                conn.execute(
                    sa.text(
                        """
                        SELECT id, year, round, office, system, scope,
                               votes_per_voter, election_date, source_version
                        FROM election
                        ORDER BY year DESC, round ASC, id ASC
                        """
                    )
                )
                .mappings()
                .all()
            )
            ind_rows = (
                conn.execute(
                    sa.text(
                        """
                        SELECT
                            i.code, i.label, i.description, i.theme, i.tier,
                            i.unit, i.value_type, i.higher_is, i.scale_hint,
                            i.source_name, i.source_url, i.caveat,
                            MAX(mc.ref_year) AS ref_year,
                            COUNT(COALESCE(mc.value::text, mc.value_text))::float
                                / NULLIF(COUNT(mc.cd_ibge), 0) AS coverage
                        FROM indicator i
                        LEFT JOIN mv_indicator_current mc
                            ON mc.indicator_code = i.code
                        GROUP BY i.code
                        ORDER BY i.tier ASC, i.theme ASC, i.code ASC
                        """
                    )
                )
                .mappings()
                .all()
            )
            pi_rows = (
                conn.execute(
                    sa.text(
                        """
                        SELECT party_code, score, bloc, method, source
                        FROM party_ideology
                        WHERE valid_from <= 2026
                          AND (valid_to IS NULL OR valid_to >= 2026)
                        ORDER BY score ASC, party_code ASC
                        """
                    )
                )
                .mappings()
                .all()
            )

        elections_out = []
        for r in el_rows:
            off_enum = Office(r["office"])
            elections_out.append(
                {
                    "id": int(r["id"]),
                    "year": int(r["year"]),
                    "round": int(r["round"]),
                    "office": r["office"],
                    "office_label": off_enum.label_pt,
                    "system": r["system"],
                    "scope": r["scope"],
                    "votes_per_voter": int(r["votes_per_voter"]),
                    "election_date": (
                        r["election_date"].isoformat() if r["election_date"] else None
                    ),
                    "source_version": r["source_version"],
                }
            )

        indicators_out = []
        for r in ind_rows:
            theme_enum = Theme(r["theme"])
            indicators_out.append(
                {
                    "code": r["code"],
                    "label": r["label"],
                    "description": r["description"],
                    "theme": r["theme"],
                    "theme_label": theme_enum.label_pt,
                    "tier": int(r["tier"]),
                    "unit": r["unit"],
                    "value_type": r["value_type"],
                    "higher_is": r["higher_is"],
                    "scale_hint": r["scale_hint"],
                    "ref_year": int(r["ref_year"]) if r["ref_year"] else None,
                    "coverage": (
                        round(float(r["coverage"]), 4)
                        if r["coverage"] is not None
                        else 0.0
                    ),
                    "source_name": r["source_name"],
                    "source_url": r["source_url"],
                    "caveat": r["caveat"],
                }
            )

        ufs_out = [
            {
                "uf": u.uf,
                "name": u.name,
                "region": u.region,
                "bbox": list(u.default_bbox),
            }
            for u in UFS
        ]

        party_out = [
            {
                "party_code": r["party_code"],
                "score": float(r["score"]),
                "bloc": r["bloc"],
                "method": r["method"],
                "source": r["source"],
            }
            for r in pi_rows
        ]

        return {
            "dataset_version": dv_id,
            "default_selection": {
                "year": 2026,
                "round": 1,
                "office": "president",
                "bloc": "right",
                "indicator": "gdp_per_capita",
            },
            "elections": elections_out,
            "indicators": indicators_out,
            "ufs": ufs_out,
            "party_ideology": party_out,
        }

    def get_election_map(
        self,
        year: int,
        office_str: str,
        round_num: int,
        *,
        uf: str | None = None,
        level: str = "municipality",
    ) -> dict[str, Any]:
        """Returns compact columnar municipal or UF electoral shares (`GET .../map`).

        Args:
            year: Election year.
            office_str: Office slug (`president`, `state_or_district_deputy`, etc.).
            round_num: Election round (1 or 2).
            uf: Optional 2-letter UF filter.
            level: Territorial aggregation level (`'municipality'` or `'uf'`).

        Returns:
            Dictionary matching `docs/08-api.md` Section 2.3.

        Raises:
            ApiError: With HTTP 404 (`ELECTION_NOT_FOUND`) if no data exists.
        """
        office, round_num, clean_uf = validate_office_round_uf(
            office_str, round_num, uf
        )
        office_values = _resolve_office_db_values(office)

        uf_clause = "AND mv.uf = :uf" if clean_uf else ""
        params: dict[str, Any] = {
            "year": year,
            "round": round_num,
            "offices": tuple(office_values),
        }
        if clean_uf:
            params["uf"] = clean_uf

        if level == "uf":
            with self.engine.connect() as conn:
                rows = (
                    conn.execute(
                        sa.text(
                            f"""
                            SELECT
                                mv.uf,
                                SUM(mv.eligible)::bigint AS eligible,
                                SUM(mv.attendance)::bigint AS attendance,
                                SUM(mv.valid_votes)::bigint AS valid_votes,
                                SUM(mv.left_votes)::bigint AS left_votes,
                                SUM(mv.center_votes)::bigint AS center_votes,
                                SUM(mv.right_votes)::bigint AS right_votes
                            FROM mv_election_mun_bloc mv
                            WHERE mv.year = :year
                              AND mv.round = :round
                              AND mv.office IN :offices
                              {uf_clause}
                            GROUP BY mv.uf
                            ORDER BY mv.uf ASC
                            """
                        ).bindparams(sa.bindparam("offices", expanding=True)),
                        params,
                    )
                    .mappings()
                    .all()
                )
                abroad_valid = 0
                if office == Office.PRESIDENT and not clean_uf:
                    abroad_val = conn.execute(
                        sa.text(
                            """
                            SELECT COALESCE(SUM(av.votes), 0)
                            FROM abroad_vote av
                            JOIN election e ON e.id = av.election_id
                            WHERE e.year = :year
                              AND e.round = :round
                              AND e.office = 'president'
                            """
                        ),
                        {"year": year, "round": round_num},
                    ).scalar()
                    abroad_valid = int(abroad_val or 0)

            if not rows:
                raise ApiError(
                    status_code=404,
                    code="ELECTION_NOT_FOUND",
                    message=(
                        f"Nenhum resultado encontrado para {office.value} "
                        f"({year}, {round_num}º turno)."
                    ),
                    details={"year": year, "office": office.value, "round": round_num},
                )

            tot_eligible = sum(int(r["eligible"] or 0) for r in rows)
            tot_attendance = sum(int(r["attendance"] or 0) for r in rows)
            tot_valid = sum(int(r["valid_votes"] or 0) for r in rows)
            tot_left = sum(int(r["left_votes"] or 0) for r in rows)
            tot_center = sum(int(r["center_votes"] or 0) for r in rows)
            tot_right = sum(int(r["right_votes"] or 0) for r in rows)

            ufs_won = {"left": 0, "center": 0, "right": 0}
            lr_vals: list[float] = []
            left_vals: list[float] = []
            center_vals: list[float] = []
            right_vals: list[float] = []
            compact_rows: list[list[Any]] = []

            for r in rows:
                uf_sigla = str(r["uf"])
                meta = UF_BY_SIGLA.get(uf_sigla)
                uf_code = meta.uf_code if meta else 0
                uf_name = meta.name if meta else uf_sigla
                vv = int(r["valid_votes"] or 0)
                denom = max(1, vv)
                ls = round(float(r["left_votes"] or 0) / denom, 4)
                cs = round(float(r["center_votes"] or 0) / denom, 4)
                rs = round(float(r["right_votes"] or 0) / denom, 4)
                lrb = round(
                    (float(r["right_votes"] or 0) - float(r["left_votes"] or 0))
                    / denom,
                    4,
                )

                if ls >= cs and ls >= rs:
                    lb = "left"
                elif cs >= ls and cs >= rs:
                    lb = "center"
                else:
                    lb = "right"
                ufs_won[lb] += 1
                leading_share = max(ls, cs, rs)

                att = int(r["attendance"] or 0)
                elig = int(r["eligible"] or 0)
                turnout_pct = round((att / max(1, elig)) * 100.0, 2)

                lr_vals.append(lrb)
                left_vals.append(ls)
                center_vals.append(cs)
                right_vals.append(rs)
                compact_rows.append(
                    [
                        uf_sigla,
                        uf_code,
                        uf_name,
                        ls,
                        cs,
                        rs,
                        lrb,
                        lb,
                        vv,
                        turnout_pct,
                        leading_share,
                    ]
                )

            denom = max(1, tot_valid)
            return {
                "election": {"year": year, "office": office.value, "round": round_num},
                "level": "uf",
                "national_summary": {
                    "eligible": tot_eligible,
                    "attendance": tot_attendance,
                    "valid_votes": tot_valid,
                    "abroad_valid_votes": abroad_valid,
                    "bloc_shares": {
                        "left": round(tot_left / denom, 4),
                        "center": round(tot_center / denom, 4),
                        "right": round(tot_right / denom, 4),
                    },
                    "municipalities_won": ufs_won,
                    "ufs_won": ufs_won,
                },
                "quantiles": {
                    "lr_balance": [
                        round(q, 4)
                        for q in compute_quantiles(
                            lr_vals, probs=(0.05, 0.2, 0.4, 0.6, 0.8, 0.95)
                        )
                    ],
                    "left_share": [
                        round(q, 4)
                        for q in compute_quantiles(
                            left_vals, probs=(0.1, 0.3, 0.5, 0.7, 0.9)
                        )
                    ],
                    "center_share": [
                        round(q, 4)
                        for q in compute_quantiles(
                            center_vals, probs=(0.1, 0.3, 0.5, 0.7, 0.9)
                        )
                    ],
                    "right_share": [
                        round(q, 4)
                        for q in compute_quantiles(
                            right_vals, probs=(0.1, 0.3, 0.5, 0.7, 0.9)
                        )
                    ],
                },
                "columns": [
                    "uf",
                    "uf_code",
                    "name",
                    "left_share",
                    "center_share",
                    "right_share",
                    "lr_balance",
                    "leading_bloc",
                    "valid_votes",
                    "turnout_pct",
                    "leading_share",
                ],
                "rows": compact_rows,
            }

        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    sa.text(
                        f"""
                        SELECT
                            mv.cd_ibge,
                            mv.eligible,
                            mv.attendance,
                            mv.valid_votes,
                            mv.left_votes,
                            mv.center_votes,
                            mv.right_votes,
                            mv.left_share,
                            mv.center_share,
                            mv.right_share,
                            mv.lr_balance,
                            mv.leading_bloc
                        FROM mv_election_mun_bloc mv
                        WHERE mv.year = :year
                          AND mv.round = :round
                          AND mv.office IN :offices
                          {uf_clause}
                        ORDER BY mv.cd_ibge ASC
                        """
                    ).bindparams(sa.bindparam("offices", expanding=True)),
                    params,
                )
                .mappings()
                .all()
            )
            abroad_valid = 0
            if office == Office.PRESIDENT and not clean_uf:
                abroad_val = conn.execute(
                    sa.text(
                        """
                        SELECT COALESCE(SUM(av.votes), 0)
                        FROM abroad_vote av
                        JOIN election e ON e.id = av.election_id
                        WHERE e.year = :year
                          AND e.round = :round
                          AND e.office = 'president'
                        """
                    ),
                    {"year": year, "round": round_num},
                ).scalar()
                abroad_valid = int(abroad_val or 0)

        if not rows:
            raise ApiError(
                status_code=404,
                code="ELECTION_NOT_FOUND",
                message=(
                    f"Nenhum resultado encontrado para {office.value} "
                    f"({year}, {round_num}º turno)."
                ),
                details={"year": year, "office": office.value, "round": round_num},
            )

        tot_eligible = sum(int(r["eligible"] or 0) for r in rows)
        tot_attendance = sum(int(r["attendance"] or 0) for r in rows)
        tot_valid = sum(int(r["valid_votes"] or 0) for r in rows)
        tot_left = sum(int(r["left_votes"] or 0) for r in rows)
        tot_center = sum(int(r["center_votes"] or 0) for r in rows)
        tot_right = sum(int(r["right_votes"] or 0) for r in rows)

        mun_won = {"left": 0, "center": 0, "right": 0}
        lr_vals: list[float] = []
        left_vals: list[float] = []
        center_vals: list[float] = []
        right_vals: list[float] = []
        compact_rows: list[list[Any]] = []

        for r in rows:
            lb = str(r["leading_bloc"] or "right")
            if lb in mun_won:
                mun_won[lb] += 1
            ls = round(float(r["left_share"] or 0.0), 4)
            cs = round(float(r["center_share"] or 0.0), 4)
            rs = round(float(r["right_share"] or 0.0), 4)
            lrb = round(float(r["lr_balance"] or 0.0), 4)
            vv = int(r["valid_votes"] or 0)

            lr_vals.append(lrb)
            left_vals.append(ls)
            center_vals.append(cs)
            right_vals.append(rs)
            compact_rows.append([int(r["cd_ibge"]), ls, cs, rs, lrb, lb, vv])

        denom = max(1, tot_valid)
        return {
            "election": {"year": year, "office": office.value, "round": round_num},
            "national_summary": {
                "eligible": tot_eligible,
                "attendance": tot_attendance,
                "valid_votes": tot_valid,
                "abroad_valid_votes": abroad_valid,
                "bloc_shares": {
                    "left": round(tot_left / denom, 4),
                    "center": round(tot_center / denom, 4),
                    "right": round(tot_right / denom, 4),
                },
                "municipalities_won": mun_won,
            },
            "quantiles": {
                "lr_balance": [
                    round(q, 4)
                    for q in compute_quantiles(
                        lr_vals, probs=(0.05, 0.2, 0.4, 0.6, 0.8, 0.95)
                    )
                ],
                "left_share": [
                    round(q, 4)
                    for q in compute_quantiles(
                        left_vals, probs=(0.1, 0.3, 0.5, 0.7, 0.9)
                    )
                ],
                "center_share": [
                    round(q, 4)
                    for q in compute_quantiles(
                        center_vals, probs=(0.1, 0.3, 0.5, 0.7, 0.9)
                    )
                ],
                "right_share": [
                    round(q, 4)
                    for q in compute_quantiles(
                        right_vals, probs=(0.1, 0.3, 0.5, 0.7, 0.9)
                    )
                ],
            },
            "columns": [
                "cd_ibge",
                "left_share",
                "center_share",
                "right_share",
                "lr_balance",
                "leading_bloc",
                "valid_votes",
            ],
            "rows": compact_rows,
        }

    def get_indicator_map(
        self,
        code: str,
        *,
        ref_year: int | None = None,
        uf: str | None = None,
        level: str = "municipality",
    ) -> dict[str, Any]:
        """Returns compact columnar municipal or UF indicator values for choropleth map.

        Args:
            code: Indicator code.
            ref_year: Optional explicit reference year.
            uf: Optional 2-letter UF filter.
            level: Territorial aggregation level (`'municipality'` or `'uf'`).

        Returns:
            Dictionary matching `docs/08-api.md` Section 2.4.

        Raises:
            ApiError: With HTTP 404 (`INDICATOR_NOT_FOUND`) if `code` does not exist.
        """
        clean_uf: str | None = None
        if uf is not None and uf.strip():
            clean_uf = uf.strip().upper()
            if clean_uf not in UF_BY_SIGLA:
                raise ApiError(
                    status_code=400,
                    code="INVALID_PARAMETER",
                    message=f"UF inválida: '{uf}'.",
                    details={"uf": uf},
                )

        with self.engine.connect() as conn:
            ind_meta = (
                conn.execute(
                    sa.text(
                        """
                        SELECT code, label, unit, scale_hint, source_name, caveat
                        FROM indicator
                        WHERE code = :code
                        """
                    ),
                    {"code": code},
                )
                .mappings()
                .fetchone()
            )
            if ind_meta is None:
                raise ApiError(
                    status_code=404,
                    code="INDICATOR_NOT_FOUND",
                    message=f"O indicador '{code}' não existe no catálogo.",
                    details={"indicator_code": code},
                )

            if ref_year is None:
                yr_val = conn.execute(
                    sa.text(
                        "SELECT MAX(ref_year) FROM indicator_value "
                        "WHERE indicator_code = :code"
                    ),
                    {"code": code},
                ).scalar()
                selected_year = int(yr_val) if yr_val is not None else 2022
            else:
                selected_year = int(ref_year)

            uf_clause = "AND m.uf = :uf" if clean_uf else ""
            q_params: dict[str, Any] = {"code": code, "ref_year": selected_year}
            if clean_uf:
                q_params["uf"] = clean_uf

            if level == "uf":
                is_sum = code in {
                    "population",
                    "population_estimate",
                    "area_km2",
                    "gdp_total",
                    "bolsa_familia_total",
                    "bolsa_familia_beneficiaries",
                }
                val_rows = (
                    conn.execute(
                        sa.text(
                            f"""
                            SELECT
                                m.uf,
                                m.uf_code,
                                COUNT(iv.value) AS count_valid,
                                COUNT(*) AS count_total,
                                SUM(iv.value) AS sum_val,
                                AVG(iv.value) AS avg_val,
                                SUM(iv.value * COALESCE(p.value, 1.0)) AS weighted_sum,
                                SUM(
                                    CASE
                                        WHEN iv.value IS NOT NULL
                                        THEN COALESCE(p.value, 1.0)
                                        ELSE 0
                                    END
                                ) AS weight_denom
                            FROM municipality m
                            LEFT JOIN indicator_value iv
                                ON iv.cd_ibge = m.cd_ibge
                               AND iv.indicator_code = :code
                               AND iv.ref_year = :ref_year
                            LEFT JOIN mv_indicator_current p
                                ON p.cd_ibge = m.cd_ibge
                               AND p.indicator_code = 'population'
                            WHERE 1=1 {uf_clause}
                            GROUP BY m.uf, m.uf_code
                            ORDER BY m.uf_code ASC
                            """
                        ),
                        q_params,
                    )
                    .mappings()
                    .all()
                )

                numeric_vals: list[float] = []
                compact_rows: list[list[Any]] = []
                count_valid = 0
                count_missing = 0

                for r in val_rows:
                    uf_sigla = str(r["uf"])
                    meta = UF_BY_SIGLA.get(uf_sigla)
                    uf_code = int(r["uf_code"])
                    uf_name = meta.name if meta else uf_sigla

                    if is_sum:
                        v = r["sum_val"]
                        uf_val = round(float(v), 4) if v is not None else None
                    else:
                        w_denom = float(r["weight_denom"] or 0)
                        w_sum = r["weighted_sum"]
                        if w_denom > 0 and w_sum is not None:
                            uf_val = round(float(w_sum) / w_denom, 4)
                        elif r["avg_val"] is not None:
                            uf_val = round(float(r["avg_val"]), 4)
                        else:
                            uf_val = None

                    if uf_val is not None:
                        numeric_vals.append(uf_val)
                        compact_rows.append([uf_sigla, uf_code, uf_name, uf_val])
                        count_valid += 1
                    else:
                        compact_rows.append([uf_sigla, uf_code, uf_name, None])
                        count_missing += 1

                q_std = compute_quantiles(
                    numeric_vals, probs=(0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0)
                )
                q_7 = compute_quantiles(
                    numeric_vals, probs=tuple(i / 7.0 for i in range(8))
                )

                return {
                    "indicator": {
                        "code": ind_meta["code"],
                        "label": ind_meta["label"],
                        "unit": ind_meta["unit"],
                        "ref_year": selected_year,
                        "scale_hint": ind_meta["scale_hint"],
                        "source_name": ind_meta["source_name"],
                        "caveat": ind_meta["caveat"],
                    },
                    "level": "uf",
                    "summary": {
                        "count_valid": count_valid,
                        "count_missing": count_missing,
                        "min": round(q_std[0], 4) if q_std else None,
                        "p10": round(q_std[1], 4) if q_std else None,
                        "p25": round(q_std[2], 4) if q_std else None,
                        "median": round(q_std[3], 4) if q_std else None,
                        "p75": round(q_std[4], 4) if q_std else None,
                        "p90": round(q_std[5], 4) if q_std else None,
                        "max": round(q_std[6], 4) if q_std else None,
                        "quantiles_7": [round(x, 4) for x in q_7],
                    },
                    "columns": ["uf", "uf_code", "name", "value"],
                    "rows": compact_rows,
                }

            val_rows = (
                conn.execute(
                    sa.text(
                        f"""
                        SELECT m.cd_ibge, iv.value, iv.value_text
                        FROM municipality m
                        LEFT JOIN indicator_value iv
                            ON iv.cd_ibge = m.cd_ibge
                           AND iv.indicator_code = :code
                           AND iv.ref_year = :ref_year
                        WHERE 1=1 {uf_clause}
                        ORDER BY m.cd_ibge ASC
                        """
                    ),
                    q_params,
                )
                .mappings()
                .all()
            )

        numeric_vals: list[float] = []
        compact_rows: list[list[Any]] = []
        count_valid = 0
        count_missing = 0

        for r in val_rows:
            v = r["value"]
            vt = r["value_text"]
            if v is not None:
                fv = float(v)
                numeric_vals.append(fv)
                compact_rows.append([int(r["cd_ibge"]), round(fv, 4)])
                count_valid += 1
            elif vt is not None:
                compact_rows.append([int(r["cd_ibge"]), vt])
                count_valid += 1
            else:
                compact_rows.append([int(r["cd_ibge"]), None])
                count_missing += 1

        q_std = compute_quantiles(
            numeric_vals, probs=(0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0)
        )
        q_7 = compute_quantiles(numeric_vals, probs=tuple(i / 7.0 for i in range(8)))

        return {
            "indicator": {
                "code": ind_meta["code"],
                "label": ind_meta["label"],
                "unit": ind_meta["unit"],
                "ref_year": selected_year,
                "scale_hint": ind_meta["scale_hint"],
                "source_name": ind_meta["source_name"],
                "caveat": ind_meta["caveat"],
            },
            "summary": {
                "count_valid": count_valid,
                "count_missing": count_missing,
                "min": round(q_std[0], 4) if q_std else None,
                "p10": round(q_std[1], 4) if q_std else None,
                "p25": round(q_std[2], 4) if q_std else None,
                "median": round(q_std[3], 4) if q_std else None,
                "p75": round(q_std[4], 4) if q_std else None,
                "p90": round(q_std[5], 4) if q_std else None,
                "max": round(q_std[6], 4) if q_std else None,
                "quantiles_7": [round(x, 4) for x in q_7],
            },
            "columns": ["cd_ibge", "value"],
            "rows": compact_rows,
        }

    def get_analysis(
        self,
        *,
        year: int,
        office_str: str,
        round_num: int,
        indicator_code: str,
        bloc_str: str = "right",
        uf: str | None = None,
        level: str = "municipality",
    ) -> dict[str, Any]:
        """Computes unified bivariate analysis (`GET /api/v1/analysis`).

        Args:
            year: Election year.
            office_str: Office slug.
            round_num: Election round (1 or 2).
            indicator_code: Indicator code.
            bloc_str: Target ideological bloc (`left`, `center`, `right`).
            uf: Optional 2-letter UF filter.
            level: Territorial aggregation level (`'municipality'` or `'uf'`).

        Returns:
            Dictionary matching `docs/08-api.md` Section 2.5.
        """
        office, round_num, clean_uf = validate_office_round_uf(
            office_str, round_num, uf
        )
        bloc = validate_bloc(bloc_str)
        office_values = _resolve_office_db_values(office)

        if level == "uf":
            is_sum = indicator_code in {
                "population",
                "population_estimate",
                "area_km2",
                "gdp_total",
                "bolsa_familia_total",
                "bolsa_familia_beneficiaries",
            }

            with self.engine.connect() as conn:
                ind_meta = (
                    conn.execute(
                        sa.text(
                            """
                            SELECT code, label, unit, value_type, scale_hint,
                                   source_name, caveat
                            FROM indicator
                            WHERE code = :code
                            """
                        ),
                        {"code": indicator_code},
                    )
                    .mappings()
                    .fetchone()
                )
                if ind_meta is None:
                    raise ApiError(
                        status_code=404,
                        code="INDICATOR_NOT_FOUND",
                        message=(
                            f"O indicador '{indicator_code}' não existe no catálogo."
                        ),
                        details={"indicator_code": indicator_code},
                    )

                uf_clause = "AND mv.uf = :uf" if clean_uf else ""
                params: dict[str, Any] = {
                    "year": year,
                    "round": round_num,
                    "offices": tuple(office_values),
                    "code": indicator_code,
                }
                if clean_uf:
                    params["uf"] = clean_uf

                joined_rows = (
                    conn.execute(
                        sa.text(
                            f"""
                            SELECT
                                mv.uf,
                                SUM(mv.valid_votes)::bigint AS valid_votes,
                                SUM(mv.left_votes)::bigint AS left_votes,
                                SUM(mv.center_votes)::bigint AS center_votes,
                                SUM(mv.right_votes)::bigint AS right_votes,
                                SUM(ic.value) AS sum_val,
                                AVG(ic.value) AS avg_val,
                                SUM(ic.value * COALESCE(p.value, 1.0)) AS weighted_sum,
                                SUM(
                                    CASE
                                        WHEN ic.value IS NOT NULL
                                        THEN COALESCE(p.value, 1.0)
                                        ELSE 0
                                    END
                                ) AS weight_denom,
                                MAX(ic.ref_year) AS ref_year
                            FROM mv_election_mun_bloc mv
                            LEFT JOIN mv_indicator_current ic
                                ON ic.cd_ibge = mv.cd_ibge
                               AND ic.indicator_code = :code
                            LEFT JOIN mv_indicator_current p
                                ON p.cd_ibge = mv.cd_ibge
                               AND p.indicator_code = 'population'
                            WHERE mv.year = :year
                              AND mv.round = :round
                              AND mv.office IN :offices
                              {uf_clause}
                            GROUP BY mv.uf
                            ORDER BY mv.uf ASC
                            """
                        ).bindparams(sa.bindparam("offices", expanding=True)),
                        params,
                    )
                    .mappings()
                    .all()
                )

            if not joined_rows:
                raise ApiError(
                    status_code=404,
                    code="ELECTION_NOT_FOUND",
                    message=(
                        "Nenhum dado encontrado para a combinação eleitoral/indicador."
                    ),
                )

            scatter_rows: list[list[Any]] = []
            x_vals: list[float] = []
            y_vals: list[float] = []
            valid_votes_list: list[int] = []
            bloc_votes_list: list[int] = []

            for r in joined_rows:
                uf_sigla = str(r["uf"])
                meta = UF_BY_SIGLA.get(uf_sigla)
                uf_code = meta.uf_code if meta else 0
                uf_name = meta.name if meta else uf_sigla
                region = meta.region if meta else "Brasil"

                vv = int(r["valid_votes"] or 0)
                if vv <= 0:
                    continue

                if bloc == Bloc.LEFT:
                    bv = int(r["left_votes"] or 0)
                elif bloc == Bloc.CENTER:
                    bv = int(r["center_votes"] or 0)
                else:
                    bv = int(r["right_votes"] or 0)

                y_share = round(bv / vv, 4)

                if is_sum:
                    v = r["sum_val"]
                    x_val = round(float(v), 4) if v is not None else None
                else:
                    w_denom = float(r["weight_denom"] or 0)
                    w_sum = r["weighted_sum"]
                    if w_denom > 0 and w_sum is not None:
                        x_val = round(float(w_sum) / w_denom, 4)
                    elif r["avg_val"] is not None:
                        x_val = round(float(r["avg_val"]), 4)
                    else:
                        x_val = None

                if x_val is not None:
                    x_vals.append(x_val)
                    y_vals.append(y_share)
                    valid_votes_list.append(vv)
                    bloc_votes_list.append(bv)
                    scatter_rows.append(
                        [
                            uf_sigla,
                            uf_code,
                            uf_name,
                            x_val,
                            y_share,
                            vv,
                            region,
                        ]
                    )

            if len(x_vals) >= 3:
                corr_stat = compute_correlation(x_vals, y_vals)
                trendline_dict = compute_trendline(
                    x_vals,
                    y_vals,
                    scale_hint=ScaleHint(ind_meta["scale_hint"]),
                )
            else:
                from territorio.domain import (
                    CorrelationDirection,
                    CorrelationStat,
                    CorrelationStrength,
                )

                corr_stat = CorrelationStat(
                    spearman_rho=0.0,
                    spearman_p=1.0,
                    pearson_r=0.0,
                    pearson_p=1.0,
                    strength=CorrelationStrength.NEGLIGIBLE,
                    direction=CorrelationDirection.NEUTRAL,
                    n_valid=len(x_vals),
                )
                trendline_dict = {"model": "linear", "points": []}

            deciles_out = compute_decile_shares(
                x_vals, y_vals, valid_votes_list, bloc_votes_list
            )
            extremes_contrast = compute_extremes_contrast(deciles_out)

            ref_yr = max(
                (int(r["ref_year"] or 2022) for r in joined_rows), default=2022
            )
            val_type = ValueType(ind_meta["value_type"])

            insights = generate_analysis_insights(
                year=year,
                round_num=round_num,
                office=office,
                bloc=bloc,
                indicator_label=ind_meta["label"],
                indicator_unit=ind_meta["unit"],
                value_type=val_type,
                ref_year=ref_yr,
                source_name=ind_meta["source_name"],
                caveat=ind_meta["caveat"],
                n_valid=len(x_vals),
                n_scope_total=len(UFS),
                correlation=corr_stat,
                deciles=deciles_out,
                extremes_contrast=extremes_contrast,
            )

            return {
                "scope": {
                    "year": year,
                    "office": office.value,
                    "round": round_num,
                    "bloc": bloc.value,
                    "uf": clean_uf,
                    "level": "uf",
                },
                "indicator": {
                    "code": ind_meta["code"],
                    "label": ind_meta["label"],
                    "unit": ind_meta["unit"],
                    "ref_year": ref_yr,
                    "scale_hint": ind_meta["scale_hint"],
                    "caveat": ind_meta["caveat"],
                },
                "sample": {
                    "total_municipalities": len(joined_rows),
                    "valid_pairs": len(x_vals),
                    "missing_pairs": len(joined_rows) - len(x_vals),
                },
                "correlation": {
                    "spearman_rho": corr_stat.spearman_rho,
                    "spearman_p": corr_stat.spearman_p,
                    "pearson_r": corr_stat.pearson_r,
                    "pearson_p": corr_stat.pearson_p,
                    "strength": corr_stat.strength.value,
                    "strength_label": corr_stat.strength.label_pt,
                    "direction": corr_stat.direction.value,
                    "direction_label": corr_stat.direction.label_pt,
                },
                "trendline": trendline_dict,
                "deciles": [
                    {
                        "decile": d.decile,
                        "municipality_count": d.municipality_count,
                        "indicator_min": d.indicator_min,
                        "indicator_max": d.indicator_max,
                        "indicator_median": d.indicator_median,
                        "valid_votes": d.valid_votes,
                        "bloc_votes": d.bloc_votes,
                        "weighted_share": d.weighted_share,
                        "unweighted_mean_share": d.unweighted_mean_share,
                    }
                    for d in deciles_out
                ],
                "scatter": {
                    "columns": [
                        "uf",
                        "uf_code",
                        "name",
                        "x",
                        "y",
                        "valid_votes",
                        "region",
                    ],
                    "rows": scatter_rows,
                },
                "insights": [
                    {
                        "template_id": ins.template_id,
                        "severity": ins.severity,
                        "title": ins.title,
                        "text": ins.text,
                        "params": ins.params,
                    }
                    for ins in insights
                ],
            }

        with self.engine.connect() as conn:
            ind_meta = (
                conn.execute(
                    sa.text(
                        """
                        SELECT code, label, unit, value_type, scale_hint,
                               source_name, caveat
                        FROM indicator
                        WHERE code = :code
                        """
                    ),
                    {"code": indicator_code},
                )
                .mappings()
                .fetchone()
            )
            if ind_meta is None:
                raise ApiError(
                    status_code=404,
                    code="INDICATOR_NOT_FOUND",
                    message=f"O indicador '{indicator_code}' não existe no catálogo.",
                    details={"indicator_code": indicator_code},
                )

            uf_clause = "AND mv.uf = :uf" if clean_uf else ""
            params: dict[str, Any] = {
                "year": year,
                "round": round_num,
                "offices": tuple(office_values),
                "code": indicator_code,
            }
            if clean_uf:
                params["uf"] = clean_uf

            joined_rows = (
                conn.execute(
                    sa.text(
                        f"""
                        SELECT
                            mv.cd_ibge,
                            mv.region,
                            mv.valid_votes,
                            mv.left_votes,
                            mv.center_votes,
                            mv.right_votes,
                            mv.left_share,
                            mv.center_share,
                            mv.right_share,
                            ic.ref_year,
                            ic.value AS ind_value,
                            ic.value_text AS ind_text
                        FROM mv_election_mun_bloc mv
                        LEFT JOIN mv_indicator_current ic
                            ON ic.cd_ibge = mv.cd_ibge
                           AND ic.indicator_code = :code
                        WHERE mv.year = :year
                          AND mv.round = :round
                          AND mv.office IN :offices
                          {uf_clause}
                        ORDER BY mv.cd_ibge ASC
                        """
                    ).bindparams(sa.bindparam("offices", expanding=True)),
                    params,
                )
                .mappings()
                .all()
            )

        if not joined_rows:
            raise ApiError(
                status_code=404,
                code="ELECTION_NOT_FOUND",
                message=(
                    f"Nenhum resultado eleitoral encontrado para {office.value} "
                    f"({year}, {round_num}º turno)."
                ),
                details={"year": year, "office": office.value, "round": round_num},
            )

        share_col = f"{bloc.value}_share"
        votes_col = f"{bloc.value}_votes"
        val_type = ValueType(ind_meta["value_type"])
        scale_hint = ScaleHint(ind_meta["scale_hint"])

        ref_years = [
            int(r["ref_year"]) for r in joined_rows if r["ref_year"] is not None
        ]
        ref_year = max(ref_years) if ref_years else 2022

        cd_list: list[int] = []
        x_list: list[float] = []
        y_list: list[float] = []
        b_votes_list: list[int] = []
        v_votes_list: list[int] = []
        scatter_rows: list[list[Any]] = []
        cat_groups: dict[str, list[tuple[int, int]]] = {}

        for r in joined_rows:
            cd = int(r["cd_ibge"])
            vv = int(r["valid_votes"] or 0)
            bv = int(r[votes_col] or 0)
            yv = float(r[share_col]) if r[share_col] is not None else np.nan
            xv = float(r["ind_value"]) if r["ind_value"] is not None else np.nan
            xt = r["ind_text"]

            cd_list.append(cd)
            x_list.append(xv)
            y_list.append(yv)
            b_votes_list.append(bv)
            v_votes_list.append(vv)

            if np.isfinite(xv) and np.isfinite(yv) and vv > 0:
                scatter_rows.append(
                    [cd, round(xv, 4), round(yv, 4), vv, str(r["region"])]
                )
            if xt is not None and vv > 0:
                cat_groups.setdefault(str(xt), []).append((bv, vv))

        corr = compute_correlation(x_list, y_list, v_votes_list, scale_hint=scale_hint)
        trend_pts = compute_trendline(
            x_list, y_list, v_votes_list, scale_hint=scale_hint
        )
        deciles = compute_decile_shares(cd_list, x_list, b_votes_list, v_votes_list)
        extremes_contrast = compute_extremes_contrast(deciles)

        cat_summaries: list[CategoryShareSummary] = []
        for cat_name, pairs in cat_groups.items():
            s_b = sum(p[0] for p in pairs)
            s_v = sum(p[1] for p in pairs)
            cat_summaries.append(
                CategoryShareSummary(
                    category=cat_name,
                    municipality_count=len(pairs),
                    weighted_share=(s_b / s_v) if s_v > 0 else 0.0,
                )
            )

        n_total = len(joined_rows)
        n_valid = (
            corr.n_valid
            if val_type == ValueType.CONTINUOUS
            else sum(c.municipality_count for c in cat_summaries)
        )

        insights = generate_analysis_insights(
            year=year,
            round_num=round_num,
            office=office,
            bloc=bloc,
            indicator_label=ind_meta["label"],
            indicator_unit=ind_meta["unit"],
            value_type=val_type,
            ref_year=ref_year,
            source_name=ind_meta["source_name"],
            caveat=ind_meta["caveat"],
            n_valid=n_valid,
            n_scope_total=n_total,
            correlation=corr,
            deciles=deciles,
            extremes_contrast=extremes_contrast,
            category_summaries=cat_summaries,
        )

        return {
            "scope": {
                "year": year,
                "office": office.value,
                "round": round_num,
                "bloc": bloc.value,
                "uf": clean_uf,
            },
            "indicator": {
                "code": ind_meta["code"],
                "label": ind_meta["label"],
                "unit": ind_meta["unit"],
                "ref_year": ref_year,
                "scale_hint": ind_meta["scale_hint"],
                "caveat": ind_meta["caveat"],
            },
            "sample": {
                "total_municipalities": n_total,
                "valid_pairs": n_valid,
                "missing_pairs": max(0, n_total - n_valid),
            },
            "correlation": {
                "spearman_rho": round(corr.spearman_rho, 4),
                "spearman_p": round(corr.spearman_p, 6),
                "pearson_r": round(corr.pearson_r, 4),
                "pearson_p": round(corr.pearson_p, 6),
                "strength": corr.strength.value,
                "strength_label": STRENGTH_LABELS_PT[corr.strength],
                "direction": corr.direction.value,
                "direction_label": DIRECTION_LABELS_PT[corr.direction],
            },
            "trendline": {
                "model": "log10" if scale_hint == ScaleHint.LOG else "linear",
                "points": [[round(px, 4), round(py, 4)] for px, py in trend_pts],
            },
            "deciles": [
                {
                    "decile": d.decile,
                    "municipality_count": d.municipality_count,
                    "indicator_min": round(d.indicator_min, 4),
                    "indicator_max": round(d.indicator_max, 4),
                    "indicator_median": round(d.indicator_median, 4),
                    "valid_votes": d.valid_votes,
                    "bloc_votes": d.bloc_votes,
                    "weighted_share": round(d.weighted_share, 4),
                    "unweighted_mean_share": round(d.unweighted_mean_share, 4),
                }
                for d in deciles
            ],
            "extremes_contrast": (
                {
                    "bottom_quintile_share": round(
                        extremes_contrast.bottom_quintile_share, 4
                    ),
                    "top_quintile_share": round(
                        extremes_contrast.top_quintile_share, 4
                    ),
                    "diff_pp": round(extremes_contrast.diff_pp, 2),
                    "bottom_indicator_range": [
                        round(extremes_contrast.bottom_indicator_range[0], 4),
                        round(extremes_contrast.bottom_indicator_range[1], 4),
                    ],
                    "top_indicator_range": [
                        round(extremes_contrast.top_indicator_range[0], 4),
                        round(extremes_contrast.top_indicator_range[1], 4),
                    ],
                    "bottom_municipality_count": (
                        extremes_contrast.bottom_municipality_count
                    ),
                    "top_municipality_count": extremes_contrast.top_municipality_count,
                    "tipping_point_decile": extremes_contrast.tipping_point_decile,
                    "tipping_point_threshold": (
                        round(extremes_contrast.tipping_point_threshold, 4)
                        if extremes_contrast.tipping_point_threshold is not None
                        else None
                    ),
                }
                if extremes_contrast is not None
                else None
            ),
            "scatter": {
                "columns": ["cd_ibge", "x", "y", "valid_votes", "region"],
                "rows": scatter_rows,
            },
            "insights": [
                {
                    "template_id": c.template_id,
                    "severity": c.severity,
                    "title": c.title,
                    "text": c.text,
                    "params": c.params,
                }
                for c in insights
            ],
        }

    def search_municipalities(
        self,
        q: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Searches municipalities by accent-insensitive name prefix/substring.

        Args:
            q: Search query string (at least 2 characters).
            limit: Maximum items to return (`1..25`).

        Returns:
            List of dictionaries matching `MunicipalitySearchItem`.
        """
        norm_q = (
            "".join(
                ch
                for ch in unicodedata.normalize("NFKD", q.strip())
                if not unicodedata.combining(ch)
            )
            .lower()
            .strip()
        )
        safe_limit = min(25, max(1, int(limit)))

        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    sa.text(
                        """
                        SELECT
                            cd_ibge,
                            name,
                            uf,
                            region,
                            CASE WHEN bbox IS NOT NULL THEN
                                ARRAY[
                                    ST_XMin(bbox),
                                    ST_YMin(bbox),
                                    ST_XMax(bbox),
                                    ST_YMax(bbox)
                                ]
                            END AS bbox
                        FROM municipality
                        WHERE name_norm LIKE :sub_pattern
                        ORDER BY
                            CASE WHEN name_norm LIKE :prefix_pattern THEN 0 ELSE 1 END,
                            is_capital DESC,
                            name ASC
                        LIMIT :lim
                        """
                    ),
                    {
                        "sub_pattern": f"%{norm_q}%",
                        "prefix_pattern": f"{norm_q}%",
                        "lim": safe_limit,
                    },
                )
                .mappings()
                .all()
            )

        return [
            {
                "cd_ibge": int(r["cd_ibge"]),
                "name": r["name"],
                "uf": r["uf"],
                "region": r["region"],
                "bbox": [float(x) for x in r["bbox"]] if r["bbox"] else [],
            }
            for r in rows
        ]

    def get_municipality_detail(
        self,
        cd_ibge: int,
        *,
        year: int = 2026,
        round_num: int = 1,
    ) -> dict[str, Any]:
        """Returns the complete electoral and indicator profile of a municipality.

        Args:
            cd_ibge: Canonical 7-digit IBGE municipality code.
            year: Election year (defaults to 2026).
            round_num: Election round (defaults to 1).

        Returns:
            Dictionary matching `docs/08-api.md` Section 2.7.

        Raises:
            ApiError: With HTTP 404 (`MUNICIPALITY_NOT_FOUND`) if `cd_ibge` is unknown.
        """
        with self.engine.connect() as conn:
            mun = (
                conn.execute(
                    sa.text(
                        """
                        SELECT
                            cd_ibge,
                            name,
                            uf,
                            region,
                            is_capital,
                            area_km2,
                            CASE WHEN bbox IS NOT NULL THEN
                                ARRAY[
                                    ST_XMin(bbox),
                                    ST_YMin(bbox),
                                    ST_XMax(bbox),
                                    ST_YMax(bbox)
                                ]
                            END AS bbox
                        FROM municipality
                        WHERE cd_ibge = :cd_ibge
                        """
                    ),
                    {"cd_ibge": cd_ibge},
                )
                .mappings()
                .fetchone()
            )
            if mun is None:
                raise ApiError(
                    status_code=404,
                    code="MUNICIPALITY_NOT_FOUND",
                    message=f"Município cd_ibge={cd_ibge} não encontrado.",
                    details={"cd_ibge": cd_ibge},
                )

            el_rows = (
                conn.execute(
                    sa.text(
                        """
                        SELECT
                            mv.election_id, mv.office, mv.eligible, mv.attendance,
                            mv.valid_votes, mv.blank_votes, mv.null_votes,
                            mv.turnout_pct, mv.blank_null_pct,
                            mv.left_share, mv.center_share, mv.right_share
                        FROM mv_election_mun_bloc mv
                        WHERE mv.cd_ibge = :cd_ibge
                          AND mv.year = :year
                          AND mv.round = :round
                        ORDER BY mv.election_id ASC
                        """
                    ),
                    {"cd_ibge": cd_ibge, "year": year, "round": round_num},
                )
                .mappings()
                .all()
            )

            elections_dict: dict[str, Any] = {}
            for er in el_rows:
                cand_rows = (
                    conn.execute(
                        sa.text(
                            """
                            SELECT
                                c.ballot_name,
                                c.party_code,
                                pi.bloc,
                                cv.votes
                            FROM candidate_vote cv
                            JOIN candidate c ON c.id = cv.candidate_id
                            LEFT JOIN party_ideology pi
                                ON pi.party_code = c.party_code
                               AND pi.valid_from <= :year
                               AND (pi.valid_to IS NULL OR pi.valid_to >= :year)
                            WHERE cv.election_id = :election_id
                              AND cv.cd_ibge = :cd_ibge
                            ORDER BY cv.votes DESC
                            LIMIT 5
                            """
                        ),
                        {
                            "election_id": int(er["election_id"]),
                            "cd_ibge": cd_ibge,
                            "year": year,
                        },
                    )
                    .mappings()
                    .all()
                )
                vv = max(1, int(er["valid_votes"] or 0))
                elections_dict[str(er["office"])] = {
                    "turnout": {
                        "eligible": int(er["eligible"] or 0),
                        "attendance": int(er["attendance"] or 0),
                        "valid": int(er["valid_votes"] or 0),
                        "turnout_pct": round(float(er["turnout_pct"] or 0.0), 2),
                        "blank_null_pct": round(float(er["blank_null_pct"] or 0.0), 2),
                    },
                    "bloc_shares": {
                        "left": round(float(er["left_share"] or 0.0), 4),
                        "center": round(float(er["center_share"] or 0.0), 4),
                        "right": round(float(er["right_share"] or 0.0), 4),
                    },
                    "top_candidates": [
                        {
                            "ballot_name": cr["ballot_name"],
                            "party_code": cr["party_code"],
                            "bloc": cr["bloc"] or "right",
                            "votes": int(cr["votes"]),
                            "share": round(int(cr["votes"]) / vv, 4),
                        }
                        for cr in cand_rows
                    ],
                }

            ind_rows = (
                conn.execute(
                    sa.text(
                        """
                        SELECT
                            i.code,
                            i.label,
                            i.unit,
                            mc.ref_year,
                            mc.value,
                            mc.value_text,
                            mc.national_percentile
                        FROM indicator i
                        JOIN mv_indicator_current mc
                            ON mc.indicator_code = i.code
                        WHERE mc.cd_ibge = :cd_ibge
                        ORDER BY i.tier ASC, i.theme ASC, i.code ASC
                        """
                    ),
                    {"cd_ibge": cd_ibge},
                )
                .mappings()
                .all()
            )

        return {
            "municipality": {
                "cd_ibge": int(mun["cd_ibge"]),
                "name": mun["name"],
                "uf": mun["uf"],
                "region": mun["region"],
                "is_capital": bool(mun["is_capital"]),
                "area_km2": float(mun["area_km2"]),
                "bbox": list(mun["bbox"]) if mun["bbox"] else [],
            },
            "elections": elections_dict,
            "indicators": [
                {
                    "code": ir["code"],
                    "label": ir["label"],
                    "value": (
                        round(float(ir["value"]), 4)
                        if ir["value"] is not None
                        else ir["value_text"]
                    ),
                    "unit": ir["unit"],
                    "ref_year": int(ir["ref_year"]),
                    "national_percentile": (
                        round(float(ir["national_percentile"]) * 100.0, 1)
                        if ir["national_percentile"] is not None
                        else None
                    ),
                }
                for ir in ind_rows
            ],
        }

    def _fetch_tile_uncached(
        self,
        _dataset_version_id: int,
        z: int,
        x: int,
        y: int,
    ) -> bytes:
        """Executes the PostGIS `ST_AsMVT` query for `(z, x, y)` without LRU cache.

        Args:
            _dataset_version_id: Published dataset version ID (used as cache key).
            z: Tile zoom level (`0..12`).
            x: Tile X coordinate.
            y: Tile Y coordinate.

        Returns:
            Raw protobuf bytes (`pbf`).
        """
        lod = zoom_to_lod(z)
        with self.engine.connect() as conn:
            pbf = conn.execute(
                sa.text(MVT_QUERY_SQL),
                {"z": z, "x": x, "y": y, "lod": lod},
            ).scalar()
        return bytes(pbf) if pbf else b""

    def get_mvt_tile(
        self,
        dataset_version_id: int,
        z: int,
        x: int,
        y: int,
    ) -> bytes:
        """Returns a cached Mapbox Vector Tile (`pbf`) for `(dataset_version, z, x, y)`.

        Args:
            dataset_version_id: Published dataset version ID.
            z: Tile zoom level (`0..12`).
            x: Tile X coordinate (`0..2^z - 1`).
            y: Tile Y coordinate (`0..2^z - 1`).

        Returns:
            Raw MVT protobuf bytes.

        Raises:
            ApiError: With HTTP 404 if `z > 12` or `x`/`y` are out of bounds.
        """
        lod = zoom_to_lod(z)
        max_coord = (1 << z) - 1
        if x < 0 or x > max_coord or y < 0 or y > max_coord:
            raise ApiError(
                status_code=404,
                code="TILE_NOT_FOUND",
                message=f"Coordenadas de tile ({z}/{x}/{y}) fora do domínio.",
                details={"z": z, "x": x, "y": y, "lod": lod},
            )
        return self._tile_fn(dataset_version_id, z, x, y)
