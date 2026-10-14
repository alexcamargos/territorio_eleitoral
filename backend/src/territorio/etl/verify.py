"""Post-ETL database acceptance verification (`V1`-`V8`) and report generator."""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from territorio.config import Settings
from territorio.db.engine import create_db_engine
from territorio.etl.reference import IndicatorCatalog, load_indicators_catalog


class VerificationError(RuntimeError):
    """Raised when one or more blocking acceptance checks (`V1`-`V8`) fail."""


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """Result of a single acceptance verification check.

    Attributes:
        code: Check identifier (`V1`..`V8`).
        name: Short descriptive name.
        passed: Whether the check passed.
        blocking: Whether failure aborts publication.
        details: Diagnostic values dictionary.
    """

    code: str
    name: str
    passed: bool
    blocking: bool
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Aggregated acceptance verification report across all checks.

    Attributes:
        generated_at: ISO-8601 UTC timestamp.
        all_blocking_passed: True if every blocking check passed.
        checks: Tuple of individual `CheckOutcome` records.
        markdown_path: Optional path to the generated Markdown report.
    """

    generated_at: str
    all_blocking_passed: bool
    checks: tuple[CheckOutcome, ...]
    markdown_path: Path | None = None

    @property
    def blocking_count(self) -> int:
        """Returns the number of failed blocking checks.

        Returns:
            Count of checks with `blocking=True` and `passed=False`.
        """
        return sum(1 for c in self.checks if c.blocking and not c.passed)

    @property
    def warning_count(self) -> int:
        """Returns the count of quality warnings from check V8.

        Returns:
            Integer count of warnings.
        """
        for c in self.checks:
            if c.code == "V8":
                return int(c.details.get("warning_count", 0))
        return 0


def run_database_verification(
    engine: sa.Engine,
    *,
    indicator_catalog: IndicatorCatalog | None = None,
    expected_municipalities: int = 5571,
    reports_dir: Path | None = None,
    run_id: int | str = "latest",
    raise_on_failure: bool = True,
) -> VerificationReport:
    """Executes acceptance checks `V1` through `V8` and writes `.json`/`.md` reports.

    Checks:
    - `V1`: `municipality` count equals `expected_municipalities` (5,571).
    - `V2`: `municipality_geom` has `3 * expected_municipalities` valid geometries.
    - `V3`: `uf_geom` has `3 * 27 = 81` valid geometries.
    - `V4`: No voted party lacks an active `party_ideology` classification.
    - `V5`: `turnout.valid == sum(party_vote.total)` for every `(election_id, cd_ibge)`.
    - `V6`: Every loaded indicator meets `min_coverage` (discounting exceptions).
    - `V7`: `mv_election_mun_bloc` has shares in `[0, 1]` and `lr_balance` in `[-1, 1]`.
    - `V8`: Non-blocking warning summary of unverified indicators and quality logs.

    Args:
        engine: SQLAlchemy database engine.
        indicator_catalog: Optional parsed `IndicatorCatalog` for `min_coverage` rules.
        expected_municipalities: Expected canonical municipality count (default 5571).
        reports_dir: Optional directory to write `quality_<run_id>.json` and `.md`.
        run_id: Identifier suffix for report filenames.
        raise_on_failure: If True, raises `VerificationError` when any blocking
            check fails.

    Returns:
        Completed `VerificationReport`.

    Raises:
        VerificationError: If `raise_on_failure` is True and any blocking check
            (`V1`..`V7`) fails.
    """
    outcomes: list[CheckOutcome] = []

    with engine.connect() as conn:
        # V1: Municipality count
        mun_cnt = int(
            conn.execute(sa.text("SELECT COUNT(*) FROM municipality")).scalar() or 0
        )
        outcomes.append(
            CheckOutcome(
                code="V1",
                name="Municipality master count",
                passed=(mun_cnt == expected_municipalities),
                blocking=True,
                details={
                    "actual": mun_cnt,
                    "expected": expected_municipalities,
                },
            )
        )

        # V2: Municipality geometries (3 LODs, valid & non-empty)
        geom_row = (
            conn.execute(
                sa.text(
                    """
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (
                            WHERE ST_IsEmpty(geom) OR NOT ST_IsValid(geom)
                        ) AS invalid_cnt
                    FROM municipality_geom
                    """
                )
            )
            .mappings()
            .fetchone()
        )
        geom_total = int(geom_row["total"] if geom_row else 0)
        geom_invalid = int(geom_row["invalid_cnt"] if geom_row else 0)
        expected_geom = expected_municipalities * 3
        outcomes.append(
            CheckOutcome(
                code="V2",
                name="Municipality geometries (3 LODs)",
                passed=(geom_total == expected_geom and geom_invalid == 0),
                blocking=True,
                details={
                    "total_geoms": geom_total,
                    "expected_geoms": expected_geom,
                    "invalid_or_empty": geom_invalid,
                },
            )
        )

        # V3: UF geometries (27 * 3 = 81)
        uf_geom_cnt = int(
            conn.execute(sa.text("SELECT COUNT(*) FROM uf_geom")).scalar() or 0
        )
        outcomes.append(
            CheckOutcome(
                code="V3",
                name="UF boundary geometries (3 LODs)",
                passed=(uf_geom_cnt == 81),
                blocking=True,
                details={"actual": uf_geom_cnt, "expected": 81},
            )
        )

        # V4: Party ideology coverage for all parties with votes > 0
        unclassified = (
            conn.execute(
                sa.text(
                    """
                    SELECT DISTINCT pv.party_code
                    FROM party_vote pv
                    JOIN election e ON e.id = pv.election_id
                    LEFT JOIN party_ideology pi
                        ON pi.party_code = pv.party_code
                       AND pi.valid_from <= e.year
                       AND (pi.valid_to IS NULL OR pi.valid_to >= e.year)
                    WHERE (pv.nominal_votes + pv.legend_votes) > 0
                      AND pi.party_code IS NULL
                    """
                )
            )
            .scalars()
            .all()
        )
        outcomes.append(
            CheckOutcome(
                code="V4",
                name="Party ideology completeness",
                passed=(len(unclassified) == 0),
                blocking=True,
                details={"unclassified_parties": list(unclassified)},
            )
        )

        # V5: Electoral vote sum consistency (turnout.valid == sum(party_vote))
        mismatch_cnt = int(
            conn.execute(
                sa.text(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT
                            t.election_id,
                            t.cd_ibge,
                            t.valid AS valid_votes,
                            COALESCE(
                                SUM(pv.nominal_votes + pv.legend_votes), 0
                            ) AS pv_sum
                        FROM turnout t
                        LEFT JOIN party_vote pv
                            ON pv.election_id = t.election_id
                           AND pv.cd_ibge = t.cd_ibge
                        GROUP BY t.election_id, t.cd_ibge, t.valid
                    ) s
                    WHERE s.valid_votes != s.pv_sum
                    """
                )
            ).scalar()
            or 0
        )
        outcomes.append(
            CheckOutcome(
                code="V5",
                name="Electoral vote sum consistency",
                passed=(mismatch_cnt == 0),
                blocking=True,
                details={"mismatched_municipality_contests": mismatch_cnt},
            )
        )

        # V6: Indicator coverage thresholds
        ind_cov_rows = (
            conn.execute(
                sa.text(
                    """
                    SELECT
                        indicator_code,
                        ref_year,
                        COUNT(*) FILTER (
                            WHERE value IS NOT NULL OR value_text IS NOT NULL
                        ) AS valid_cnt,
                        COUNT(*) AS total_cnt
                    FROM mv_indicator_current
                    GROUP BY indicator_code, ref_year
                    """
                )
            )
            .mappings()
            .all()
        )
        low_cov_indicators: list[dict[str, Any]] = []
        if indicator_catalog is not None:
            for r in ind_cov_rows:
                code = str(r["indicator_code"])
                spec = indicator_catalog.indicators.get(code)
                if spec is None:
                    continue
                ref_yr = int(r["ref_year"])
                exempt_cnt = sum(
                    1
                    for exc in indicator_catalog.coverage_exceptions
                    if exc.matches(adapter=spec.adapter, ref_year=ref_yr)
                )
                denom = max(1, expected_municipalities - exempt_cnt)
                ratio = int(r["valid_cnt"]) / denom
                if ratio < spec.min_coverage:
                    low_cov_indicators.append(
                        {
                            "code": code,
                            "coverage": round(ratio, 4),
                            "min_coverage": spec.min_coverage,
                        }
                    )
        outcomes.append(
            CheckOutcome(
                code="V6",
                name="Indicator minimum coverage",
                passed=(len(low_cov_indicators) == 0),
                blocking=True,
                details={"below_threshold": low_cov_indicators},
            )
        )

        # V7: Materialized view bounds check
        mv_bad_cnt = int(
            conn.execute(
                sa.text(
                    """
                    SELECT COUNT(*)
                    FROM mv_election_mun_bloc
                    WHERE left_share < -0.0001 OR left_share > 1.0001
                       OR center_share < -0.0001 OR center_share > 1.0001
                       OR right_share < -0.0001 OR right_share > 1.0001
                       OR lr_balance < -1.0001 OR lr_balance > 1.0001
                    """
                )
            ).scalar()
            or 0
        )
        outcomes.append(
            CheckOutcome(
                code="V7",
                name="Materialized view share bounds",
                passed=(mv_bad_cnt == 0),
                blocking=True,
                details={"out_of_bounds_rows": mv_bad_cnt},
            )
        )

        # V8: Non-blocking quality warning summary
        warn_cnt = int(
            conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM data_quality_issue WHERE severity = 'warning'"
                )
            ).scalar()
            or 0
        )
        outcomes.append(
            CheckOutcome(
                code="V8",
                name="Quality warnings audit",
                passed=True,
                blocking=False,
                details={"warning_count": warn_cnt},
            )
        )

    all_passed = all(c.passed for c in outcomes if c.blocking)
    md_path = reports_dir / f"quality_{run_id}.md" if reports_dir is not None else None
    report = VerificationReport(
        generated_at=datetime.now(UTC).isoformat(),
        all_blocking_passed=all_passed,
        checks=tuple(outcomes),
        markdown_path=md_path,
    )

    if reports_dir is not None:
        write_verification_reports(report, reports_dir=reports_dir, run_id=run_id)

    if raise_on_failure and not all_passed:
        failed_codes = [c.code for c in outcomes if c.blocking and not c.passed]
        raise VerificationError(f"Blocking acceptance checks failed: {failed_codes}")

    return report


def write_verification_reports(
    report: VerificationReport,
    *,
    reports_dir: Path,
    run_id: int | str = "latest",
) -> tuple[Path, Path]:
    """Writes `quality_<run_id>.json` and `quality_<run_id>.md` to `reports_dir`.

    Args:
        report: Completed `VerificationReport`.
        reports_dir: Output directory for quality reports.
        run_id: Run identifier suffix.

    Returns:
        Tuple `(json_path, md_path)`.
    """
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"quality_{run_id}.json"
    md_path = reports_dir / f"quality_{run_id}.md"

    json_path.write_text(
        json.dumps(asdict(report), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    status_global = "APROVADO" if report.all_blocking_passed else "REPROVADO"
    lines = [
        f"# Relatório de Qualidade de Dados (Run `{run_id}`)",
        "",
        f"- **Gerado em:** `{report.generated_at}`",
        f"- **Status Global:** `{status_global}`",
        "",
        "| Código | Verificação | Bloqueante | Status | Detalhes |",
        "|---|---|---|---|---|",
    ]
    for chk in report.checks:
        status_str = "OK" if chk.passed else "FALHA"
        blk_str = "Sim" if chk.blocking else "Não"
        det_str = json.dumps(chk.details, ensure_ascii=False)
        lines.append(
            f"| `{chk.code}` | {chk.name} | {blk_str} | "
            f"**{status_str}** | `{det_str}` |"
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def run_verification_cli(settings: Settings) -> VerificationReport:
    """CLI entrypoint that runs database verification and writes reports.

    Args:
        settings: Application settings.

    Returns:
        Completed `VerificationReport` (without raising so CLI can format exit).
    """
    engine = create_db_engine(settings.database_url)
    catalog = load_indicators_catalog(settings.reference_dir / "indicators.yaml")
    return run_database_verification(
        engine,
        indicator_catalog=catalog,
        reports_dir=settings.data_dir / "reports",
        run_id="latest",
        raise_on_failure=False,
    )
