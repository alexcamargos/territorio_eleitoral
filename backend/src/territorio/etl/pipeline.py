"""End-to-end ETL pipeline orchestrator (`territory`, `elections`, `indicators`)."""

import pandas as pd
import sqlalchemy as sa

from territorio.config import Settings
from territorio.db.engine import create_db_engine
from territorio.domain import Severity, StepResult
from territorio.etl.crosswalk import (
    apply_crosswalk_to_db,
    build_and_save_crosswalk,
    load_crosswalk_csv,
)
from territorio.etl.http import CachedHttpClient, TokenBucketRateLimiter
from territorio.etl.load import (
    publish_dataset_version,
    replace_election_contest_data,
    replace_indicator_values,
)
from territorio.etl.provenance import record_quality_issue, track_etl_run
from territorio.etl.reference import (
    IndicatorCatalog,
    IndicatorSpec,
    load_indicators_catalog,
    load_party_ideology_catalog,
    sync_reference_to_db,
)
from territorio.etl.sources.ckan import fetch_ckan_capag_indicator
from territorio.etl.sources.ibge_geo import (
    fetch_geometry,
    fetch_municipality_list,
    parse_geometry,
    parse_municipality_list,
)
from territorio.etl.sources.ibge_pesquisas import fetch_ibge_pesquisas_indicator
from territorio.etl.sources.ibge_sidra import fetch_sidra_indicator
from territorio.etl.sources.manual_file import load_manual_file_indicator
from territorio.etl.sources.siconfi import fetch_siconfi_indicator
from territorio.etl.sources.transparencia import fetch_transparencia_indicator
from territorio.etl.sources.tse import (
    fetch_tse_zip,
    parse_electorate_profile_indicator,
    read_tse_csv,
)
from territorio.etl.transform.geometry import (
    load_territory_and_derive_lods,
    prepare_municipal_geometries,
)
from territorio.etl.transform.indicators import (
    compute_derived_indicator,
    finalize_indicator_dataframe,
)
from territorio.etl.transform.votes import (
    aggregate_candidate_vote_chunks,
    aggregate_party_vote_chunks,
    aggregate_turnout_chunks,
    verify_election_integrity,
)
from territorio.etl.verify import run_database_verification


def run_territory_step(
    engine: sa.Engine,
    settings: Settings,
    *,
    force_refresh: bool = False,
) -> StepResult:
    """Runs the `territory` ETL step (5,571 municipalities, 3 LODs, and TSE crosswalk).

    Args:
        engine: SQLAlchemy database engine.
        settings: Application settings.
        force_refresh: Whether to bypass local download cache.

    Returns:
        Summary `StepResult`.
    """
    with CachedHttpClient(
        cache_root=settings.raw_dir, timeout_s=settings.http_timeout_s
    ) as client:
        loc_art = fetch_municipality_list(client, force_refresh=force_refresh)
        master_df = parse_municipality_list(loc_art.path)
        mesh_art = fetch_geometry(client, year=2025, force_refresh=force_refresh)
        raw_gdf = parse_geometry(mesh_art.path)

    with track_etl_run(
        engine,
        step="territory",
        source="ibge_geo",
        source_url=mesh_art.url,
    ) as tracker:
        prepared_gdf = prepare_municipal_geometries(raw_gdf, master_df)
        res = load_territory_and_derive_lods(
            engine,
            prepared_gdf,
            source_url=mesh_art.url,
            sha256=mesh_art.sha256,
        )
        xw_path = build_and_save_crosswalk(settings, force_refresh=force_refresh)
        xw_df = load_crosswalk_csv(xw_path)
        apply_crosswalk_to_db(engine, xw_df)
        tracker.complete(res)
        return res


def run_elections_step(
    engine: sa.Engine,
    settings: Settings,
    *,
    year: int = 2026,
    force_refresh: bool = False,
) -> StepResult:
    """Runs the `elections` ETL step for all offices and rounds in `offices.yaml`.

    Args:
        engine: SQLAlchemy database engine.
        settings: Application settings.
        year: Election year (defaults to 2026).
        force_refresh: Whether to re-download TSE archives.

    Returns:
        Summary `StepResult`.
    """
    sync_reference_to_db(engine, settings.reference_dir)
    party_cat = load_party_ideology_catalog(
        settings.reference_dir / "party_ideology.yaml"
    )
    crosswalk_df = load_crosswalk_csv(settings.reference_dir / "de_para_tse_ibge.csv")

    with CachedHttpClient(
        cache_root=settings.raw_dir, timeout_s=settings.http_timeout_s
    ) as client:
        det_dl = fetch_tse_zip(
            client, "detalhe_votacao_munzona", year=year, force_refresh=force_refresh
        )
        pv_dl = fetch_tse_zip(
            client, "votacao_partido_munzona", year=year, force_refresh=force_refresh
        )
        cand_dl = fetch_tse_zip(
            client,
            "votacao_candidato_munzona",
            year=year,
            force_refresh=force_refresh,
        )

    with track_etl_run(
        engine,
        step="elections",
        source="tse",
        source_url=pv_dl.url,
    ) as tracker:
        turnout_df, _ = aggregate_turnout_chunks(
            read_tse_csv(det_dl.path),
            crosswalk_df,
        )
        party_vote_df, abroad_party_df = aggregate_party_vote_chunks(
            read_tse_csv(pv_dl.path),
            crosswalk_df,
            aliases=party_cat.aliases,
        )
        candidates_df, candidate_votes_df = aggregate_candidate_vote_chunks(
            read_tse_csv(cand_dl.path),
            crosswalk_df,
            aliases=party_cat.aliases,
        )

        active_parties = set(party_cat.active_parties_for_year(year).keys())
        verify_election_integrity(
            turnout_df=turnout_df,
            party_vote_df=party_vote_df,
            candidate_vote_df=candidate_votes_df,
            active_parties=active_parties,
            check_expected_mun_counts=True,
        )

        with engine.connect() as conn:
            el_rows = (
                conn.execute(
                    sa.text(
                        "SELECT id, round, office, tse_cd_cargo "
                        "FROM election WHERE year = :yr"
                    ),
                    {"yr": year},
                )
                .mappings()
                .all()
            )
        el_map = {
            (int(r["round"]), int(r["tse_cd_cargo"])): int(r["id"]) for r in el_rows
        }

        total_out = 0
        with engine.begin() as conn:
            for (rnd, cargo), el_id in sorted(el_map.items()):
                t_sub = turnout_df[
                    (turnout_df["round"] == rnd) & (turnout_df["tse_cd_cargo"] == cargo)
                ]
                p_sub = party_vote_df[
                    (party_vote_df["round"] == rnd)
                    & (party_vote_df["tse_cd_cargo"] == cargo)
                ]
                c_meta_sub = candidates_df[
                    (candidates_df["round"] == rnd)
                    & (candidates_df["tse_cd_cargo"] == cargo)
                ]
                c_vote_sub = candidate_votes_df[
                    (candidate_votes_df["round"] == rnd)
                    & (candidate_votes_df["tse_cd_cargo"] == cargo)
                ]
                ab_sub = abroad_party_df[
                    (abroad_party_df["round"] == rnd)
                    & (abroad_party_df["tse_cd_cargo"] == cargo)
                ]
                total_out += replace_election_contest_data(
                    conn,
                    election_id=el_id,
                    turnout_df=t_sub,
                    party_vote_df=p_sub,
                    candidates_df=c_meta_sub,
                    candidate_vote_df=c_vote_sub,
                    abroad_df=ab_sub,
                )

        res = StepResult(
            step="elections",
            rows_in=len(turnout_df) + len(party_vote_df),
            rows_out=total_out,
            source_url=pv_dl.url,
            sha256=pv_dl.sha256,
        )
        tracker.complete(res)
        return res


def _extract_single_indicator(
    spec: IndicatorSpec,
    *,
    engine: sa.Engine,
    settings: Settings,
    master_ibge_codes: list[int],
    catalog: IndicatorCatalog,
    loaded_frames: dict[str, pd.DataFrame],
    resume: bool = True,
    force_refresh: bool = False,
    allow_unverified: bool = False,
) -> pd.DataFrame:
    """Dispatches extraction, transformation, and DB load for a single `IndicatorSpec`.

    Args:
        spec: Indicator specification from `indicators.yaml`.
        engine: SQLAlchemy database engine.
        settings: Application settings.
        master_ibge_codes: Canonical 7-digit IBGE municipality codes.
        catalog: Parsed `IndicatorCatalog`.
        loaded_frames: Cache of already-loaded indicator DataFrames for `per_capita`
            and `derived` dependencies.
        resume: Whether to resume from per-municipality checkpoints.
        force_refresh: Whether to bypass HTTP cache.
        allow_unverified: Whether to allow unverified `manual_file` indicators.

    Returns:
        Finalized indicator DataFrame.
    """
    raw_dir = settings.data_dir / "raw"
    limiter = (
        TokenBucketRateLimiter(rate_per_minute=settings.transparencia_rate_per_min)
        if spec.adapter == "transparencia"
        else None
    )
    client = CachedHttpClient(raw_dir, rate_limiter=limiter)

    denom_map: dict[int, float] | None = None
    per_capita_cfg = (spec.transform or {}).get("per_capita")
    if isinstance(per_capita_cfg, dict):
        pop_code = str(per_capita_cfg.get("population", "population_estimate"))
        if pop_code in loaded_frames:
            pop_df = loaded_frames[pop_code]
            denom_map = dict(
                zip(
                    pop_df["cd_ibge"].astype(int).tolist(),
                    pop_df["value"].astype(float).tolist(),
                    strict=True,
                )
            )

    if spec.adapter == "sidra":
        raw_df, src_url, src_sha = fetch_sidra_indicator(client, spec)
    elif spec.adapter == "ibge_pesquisas":
        raw_df, src_url, src_sha = fetch_ibge_pesquisas_indicator(
            client, spec, master_ibge_codes=master_ibge_codes
        )
    elif spec.adapter == "transparencia":
        raw_df, src_url, src_sha = fetch_transparencia_indicator(
            client,
            spec,
            master_ibge_codes=master_ibge_codes,
            api_key=settings.transparencia_api_key or "",
            cache_dir=raw_dir / "transparencia",
            resume=resume,
        )
    elif spec.adapter == "siconfi":
        raw_df, src_url, src_sha = fetch_siconfi_indicator(
            client,
            spec,
            master_ibge_codes=master_ibge_codes,
            cache_dir=raw_dir / "siconfi",
            resume=resume,
        )
    elif spec.adapter == "ckan":
        raw_df, src_url, src_sha = fetch_ckan_capag_indicator(client, spec)
    elif spec.adapter == "manual_file":
        raw_df, src_url, src_sha = load_manual_file_indicator(
            spec,
            master_ibge_codes=master_ibge_codes,
            project_root=settings.data_dir.parent,
            allow_unverified=allow_unverified,
        )
    elif spec.adapter == "ibge_geo":
        with engine.connect() as conn:
            geo_rows = (
                conn.execute(
                    sa.text("SELECT cd_ibge, area_km2 AS value FROM municipality")
                )
                .mappings()
                .all()
            )
        raw_df = pd.DataFrame(geo_rows).assign(ref_year=2025, missing_reason=None)
        src_url = spec.source_url
        src_sha = "municipality_table"
    elif spec.adapter == "tse":
        crosswalk_df = load_crosswalk_csv(
            settings.reference_dir / "de_para_tse_ibge.csv"
        )
        dl = fetch_tse_zip(
            client, "perfil_eleitorado", year=2026, force_refresh=force_refresh
        )
        raw_df = parse_electorate_profile_indicator(
            dl.path,
            crosswalk_df,
            filter_column=str(spec.source_params["filter_column"]),
            filter_values=[int(v) for v in spec.source_params["filter_values"]],
            weight_column=str(spec.source_params.get("weight_column", "QT_ELEITORES")),
            ref_year=2026,
            multiply=1.0,
        )
        src_url = dl.url
        src_sha = dl.sha256
    elif spec.adapter == "derived":
        turnout_df: pd.DataFrame | None = None
        if spec.source_params.get("table") == "election_summary":
            with engine.connect() as conn:
                t_rows = (
                    conn.execute(
                        sa.text(
                            """
                            SELECT
                                t.cd_ibge,
                                e.round,
                                e.tse_cd_cargo,
                                t.eligible AS eligible_voters,
                                t.attendance AS turnout,
                                t.abstentions AS abstention,
                                t.valid AS valid_votes,
                                t.blank AS blank_votes,
                                t.null_votes
                            FROM turnout t
                            JOIN election e ON e.id = t.election_id
                            WHERE e.year = 2026
                            """
                        )
                    )
                    .mappings()
                    .all()
                )
            turnout_df = pd.DataFrame(t_rows)

        final_df, issues = compute_derived_indicator(
            spec,
            master_ibge_codes=master_ibge_codes,
            coverage_exceptions=catalog.coverage_exceptions,
            indicator_frames=loaded_frames,
            election_turnout_df=turnout_df,
        )
        with track_etl_run(
            engine,
            step=f"indicator:{spec.code}",
            source=spec.adapter,
            dataset=spec.code,
            source_url=spec.source_url,
        ) as tracker:
            with engine.begin() as conn:
                rows_written = replace_indicator_values(
                    conn, indicator_code=spec.code, values_df=final_df
                )
                for iss in issues:
                    record_quality_issue(
                        conn,
                        run_id=tracker.run_id,
                        check_name=iss.check_name,
                        severity=Severity.WARNING,
                        detail=iss.details,
                        cd_ibge=iss.cd_ibge,
                    )
            tracker.complete(
                StepResult(
                    step=f"indicator:{spec.code}",
                    rows_in=len(final_df),
                    rows_out=rows_written,
                    warnings_count=len(issues),
                    source_url=spec.source_url,
                )
            )
        return final_df
    else:
        raise ValueError(f"Unsupported indicator adapter: {spec.adapter!r}")

    with track_etl_run(
        engine,
        step=f"indicator:{spec.code}",
        source=spec.adapter,
        dataset=spec.code,
        source_url=src_url,
    ) as tracker:
        final_df, issues = finalize_indicator_dataframe(
            raw_df,
            spec,
            master_ibge_codes=master_ibge_codes,
            coverage_exceptions=catalog.coverage_exceptions,
            denominator_by_ibge=denom_map,
        )
        with engine.begin() as conn:
            rows_written = replace_indicator_values(
                conn, indicator_code=spec.code, values_df=final_df
            )
            for iss in issues:
                record_quality_issue(
                    conn,
                    run_id=tracker.run_id,
                    check_name=iss.check_name,
                    severity=Severity.WARNING,
                    detail=iss.details,
                    cd_ibge=iss.cd_ibge,
                )
        tracker.complete(
            StepResult(
                step=f"indicator:{spec.code}",
                rows_in=len(raw_df),
                rows_out=rows_written,
                warnings_count=len(issues),
                source_url=src_url,
                sha256=src_sha,
            )
        )
        return final_df


def run_indicators_step(
    engine: sa.Engine,
    settings: Settings,
    *,
    indicator_code: str | None = None,
    only_indicators: list[str] | None = None,
    resume: bool = True,
    force_refresh: bool = False,
    allow_unverified: bool = False,
) -> StepResult:
    """Runs the `indicators` ETL step for all (or selected) catalog indicators.

    Executes base indicators (`population`, `population_estimate`, `area_km2`)
    before per-capita indicators, and executes `derived` indicators last.

    Args:
        engine: SQLAlchemy database engine.
        settings: Application settings.
        indicator_code: Optional single indicator code to run.
        only_indicators: Optional list of indicator codes to run.
        resume: Whether to resume from per-municipality checkpoints.
        force_refresh: Whether to bypass HTTP cache.
        allow_unverified: Whether to include `verified: false` manual indicators.

    Returns:
        Summary `StepResult`.
    """
    sync_reference_to_db(engine, settings.reference_dir)
    catalog = load_indicators_catalog(settings.reference_dir / "indicators.yaml")

    with engine.connect() as conn:
        master_codes = [
            int(c)
            for c in conn.execute(
                sa.text("SELECT cd_ibge FROM municipality ORDER BY cd_ibge")
            )
            .scalars()
            .all()
        ]
        existing_rows = (
            conn.execute(
                sa.text(
                    "SELECT DISTINCT ON (indicator_code, cd_ibge) "
                    "indicator_code, ref_year, cd_ibge, value "
                    "FROM indicator_value "
                    "ORDER BY indicator_code, cd_ibge, ref_year DESC"
                )
            )
            .mappings()
            .all()
        )

    loaded_frames: dict[str, pd.DataFrame] = {}
    if existing_rows:
        ex_df = pd.DataFrame(existing_rows)
        for code_val, grp in ex_df.groupby("indicator_code"):
            loaded_frames[str(code_val)] = grp.reset_index(drop=True)

    target_codes: list[str] | None = (
        [indicator_code] if indicator_code is not None else only_indicators
    )
    if target_codes:
        specs: list[IndicatorSpec] = []
        for code in target_codes:
            if code not in catalog.indicators:
                raise ValueError(f"Unknown indicator code: {code!r}")
            specs.append(catalog.indicators[code])
    else:
        all_specs = [
            s for s in catalog.indicators.values() if s.verified or allow_unverified
        ]
        base_codes = {"population", "population_estimate", "area_km2"}
        base_specs = [s for s in all_specs if s.code in base_codes]
        non_derived = [
            s for s in all_specs if s.code not in base_codes and s.adapter != "derived"
        ]
        derived_specs = [s for s in all_specs if s.adapter == "derived"]
        specs = base_specs + non_derived + derived_specs

    total_rows = 0
    for spec in specs:
        df_out = _extract_single_indicator(
            spec,
            engine=engine,
            settings=settings,
            master_ibge_codes=master_codes,
            catalog=catalog,
            loaded_frames=loaded_frames,
            resume=resume,
            force_refresh=force_refresh,
            allow_unverified=allow_unverified,
        )
        loaded_frames[spec.code] = df_out
        total_rows += len(df_out)

    return StepResult(step="indicators", rows_in=total_rows, rows_out=total_rows)


def run_publish_step(engine: sa.Engine, settings: Settings) -> int:
    """Refreshes materialized views, runs verification, and publishes a dataset version.

    Args:
        engine: SQLAlchemy database engine.
        settings: Application settings.

    Returns:
        Newly created `dataset_version.id`.
    """
    catalog = load_indicators_catalog(settings.reference_dir / "indicators.yaml")
    with track_etl_run(engine, step="publish") as tracker:
        dv_id = publish_dataset_version(engine, etl_run_id=tracker.run_id)
        run_database_verification(
            engine,
            indicator_catalog=catalog,
            reports_dir=settings.data_dir / "reports",
            run_id=tracker.run_id,
        )
        tracker.complete(StepResult(step="publish", rows_in=1, rows_out=1))
        return dv_id


def run_pipeline(
    *,
    settings: Settings,
    all_steps: bool = False,
    step: str | None = None,
    round_num: int | None = None,
    only_indicators: list[str] | None = None,
    resume: bool = False,
    force_refresh: bool = False,
    allow_unverified: bool = False,
    engine: sa.Engine | None = None,
) -> list[StepResult]:
    """Dispatches ETL pipeline steps requested via CLI (`--all` or `--step`).

    Args:
        settings: Application settings.
        all_steps: Whether to execute all main steps in sequence.
        step: Single step name if `all_steps` is False.
        round_num: Optional election round filter (reserved for CLI parity).
        only_indicators: Optional list of indicator codes to run.
        resume: Whether to resume per-municipality checkpoints.
        force_refresh: Whether to bypass HTTP cache.
        allow_unverified: Whether to include `verified: false` indicators.
        engine: Optional pre-configured SQLAlchemy engine.

    Returns:
        List of `StepResult` objects for executed steps.

    Raises:
        ValueError: If `step` is unknown and `all_steps` is False.
    """
    _ = round_num
    db_engine = engine or create_db_engine(settings.database_url)
    steps_to_run = (
        ["territory", "elections", "indicators", "publish"]
        if all_steps
        else [step or ""]
    )

    results: list[StepResult] = []
    for st in steps_to_run:
        if st == "reference":
            res_ref = sync_reference_to_db(db_engine, settings.reference_dir)
            results.append(res_ref)
        elif st in ("territory", "crosswalk"):
            results.append(
                run_territory_step(db_engine, settings, force_refresh=force_refresh)
            )
        elif st == "elections":
            results.append(
                run_elections_step(db_engine, settings, force_refresh=force_refresh)
            )
        elif st in ("indicators", "derive"):
            results.append(
                run_indicators_step(
                    db_engine,
                    settings,
                    only_indicators=only_indicators,
                    resume=resume,
                    force_refresh=force_refresh,
                    allow_unverified=allow_unverified,
                )
            )
        elif st == "verify":
            catalog = load_indicators_catalog(
                settings.reference_dir / "indicators.yaml"
            )
            rep = run_database_verification(
                db_engine,
                indicator_catalog=catalog,
                reports_dir=settings.data_dir / "reports",
            )
            results.append(
                StepResult(
                    step="verify",
                    rows_in=len(rep.checks),
                    rows_out=len(rep.checks),
                    warnings_count=rep.warning_count,
                )
            )
        elif st == "publish":
            run_publish_step(db_engine, settings)
            results.append(StepResult(step="publish", rows_in=1, rows_out=1))
        else:
            raise ValueError(f"Unknown ETL step: {st!r}")

    return results
