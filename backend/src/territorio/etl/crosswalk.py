"""Crosswalk validation and conversion between TSE and IBGE municipality codes."""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd
import sqlalchemy as sa

from territorio.config import Settings
from territorio.domain import StepResult
from territorio.etl.http import CachedHttpClient
from territorio.etl.sources.ibge_geo import (
    fetch_municipality_list,
    parse_municipality_list,
)

COMMUNITY_SEED_URL = (
    "https://raw.githubusercontent.com/betafcc/Municipios-Brasileiros-TSE/"
    "master/municipios_brasileiros_tse.csv"
)


class CrosswalkError(ValueError):
    """Raised when the TSE-to-IBGE municipality mapping violates integrity rules."""


@dataclass(frozen=True, slots=True)
class CrosswalkReport:
    """Summary of crosswalk validation results including non-blocking X6 warnings.

    Attributes:
        total_pairs: Number of validated 1:1 municipality pairs.
        name_warnings: List of X6 spelling divergence warnings (similarity < 0.85).
    """

    total_pairs: int
    name_warnings: list[dict[str, Any]]


def normalize_municipality_name(raw_name: str) -> str:
    """Normalizes a municipality name for orthographic similarity comparison (X6).

    Applies NFKD decomposition, strips combining diacritics, converts to uppercase,
    replaces hyphens and apostrophes with spaces, and collapses whitespace.

    Args:
        raw_name: Original municipality name string.

    Returns:
        Normalized uppercase ASCII name string.
    """
    decomposed = unicodedata.normalize("NFKD", str(raw_name))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = (
        stripped.upper().replace("-", " ").replace("'", " ").replace("\u2019", " ")
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def validate_crosswalk(
    xw: pd.DataFrame,
    master: pd.DataFrame,
    tse_observed: pd.DataFrame | None = None,
) -> CrosswalkReport:
    """Validates the crosswalk against the IBGE master list and observed TSE data.

    Enforces blocking rules X1-X5 and computes non-blocking warning rule X6:
    - X1: `cd_tse` is unique.
    - X2: `cd_ibge` is unique.
    - X3: `set(xw.cd_ibge) == set(master.cd_ibge)`.
    - X4: Every `cd_tse` in `tse_observed` is present in `xw`.
    - X5: `uf` in `xw` (and `tse_observed`) matches `uf` in `master`.
    - X6: Normalized name similarity >= 0.85 (recorded as warning).

    Args:
        xw: Crosswalk DataFrame with `cd_tse`, `cd_ibge`, `uf`, `name_tse`.
        master: IBGE master list DataFrame with `cd_ibge`, `name`, `uf`.
        tse_observed: Optional DataFrame of distinct `(cd_tse, uf, name_tse)`.

    Returns:
        CrosswalkReport with non-blocking warnings.

    Raises:
        CrosswalkError: If any blocking rule (X1-X5) fails; message lists offenders.
    """
    errors: list[str] = []

    if xw["cd_tse"].duplicated().any():
        dup_tse = sorted(
            xw.loc[xw["cd_tse"].duplicated(), "cd_tse"].astype(int).tolist()
        )
        errors.append(f"Rule X1 failed (duplicate cd_tse): {dup_tse}")

    if xw["cd_ibge"].duplicated().any():
        dup_ibge = sorted(
            xw.loc[xw["cd_ibge"].duplicated(), "cd_ibge"].astype(int).tolist()
        )
        errors.append(f"Rule X2 failed (duplicate cd_ibge): {dup_ibge}")

    xw_ibge_set = set(xw["cd_ibge"].astype(int).tolist())
    master_ibge_set = set(master["cd_ibge"].astype(int).tolist())
    if xw_ibge_set != master_ibge_set:
        missing = sorted(master_ibge_set - xw_ibge_set)
        extra = sorted(xw_ibge_set - master_ibge_set)
        errors.append(
            f"Rule X3 failed (cd_ibge set mismatch): missing={missing[:20]}, "
            f"extra={extra[:20]}"
        )

    xw_tse_set = set(xw["cd_tse"].astype(int).tolist())
    if tse_observed is not None and not tse_observed.empty:
        obs_tse_set = set(tse_observed["cd_tse"].astype(int).tolist())
        unmapped_tse = sorted(obs_tse_set - xw_tse_set)
        if unmapped_tse:
            errors.append(
                f"Rule X4 failed (observed TSE codes missing from crosswalk): "
                f"{unmapped_tse[:20]}"
            )

    if errors:
        raise CrosswalkError("; ".join(errors))

    joined = xw.merge(
        master[["cd_ibge", "name", "uf"]].rename(
            columns={"name": "master_name", "uf": "master_uf"}
        ),
        on="cd_ibge",
        how="inner",
        validate="one_to_one",
        indicator=True,
    )
    if (joined["_merge"] != "both").any():
        raise CrosswalkError("Rule X3 failed during one_to_one join with master.")

    uf_mismatch = joined.loc[
        joined["uf"].astype(str).str.strip().str.upper()
        != joined["master_uf"].astype(str).str.strip().str.upper()
    ]
    if not uf_mismatch.empty:
        offenders = [
            f"{row.cd_ibge}:{row.uf}!={row.master_uf}"
            for row in uf_mismatch.itertuples(index=False)
        ]
        raise CrosswalkError(f"Rule X5 failed (UF divergence): {offenders[:20]}")

    if (
        tse_observed is not None
        and not tse_observed.empty
        and "uf" in tse_observed.columns
    ):
        obs_join = tse_observed.merge(
            xw[["cd_tse", "uf"]].rename(columns={"uf": "xw_uf"}),
            on="cd_tse",
            how="left",
            validate="many_to_one",
            indicator=True,
        )
        obs_mismatch = obs_join.loc[
            obs_join["uf"].astype(str).str.strip().str.upper()
            != obs_join["xw_uf"].astype(str).str.strip().str.upper()
        ]
        if not obs_mismatch.empty:
            offenders = [
                f"tse={row.cd_tse}:{row.uf}!={row.xw_uf}"
                for row in obs_mismatch.itertuples(index=False)
            ]
            raise CrosswalkError(
                f"Rule X5 failed (observed TSE UF divergence): {offenders[:20]}"
            )

    name_warnings: list[dict[str, Any]] = []
    for row in joined.itertuples(index=False):
        name_tse_raw = str(getattr(row, "name_tse", "") or row.master_name)
        norm_tse = normalize_municipality_name(name_tse_raw)
        norm_ibge = normalize_municipality_name(str(row.master_name))
        ratio = SequenceMatcher(None, norm_tse, norm_ibge).ratio()
        if ratio < 0.85:
            name_warnings.append(
                {
                    "cd_ibge": int(row.cd_ibge),
                    "cd_tse": int(row.cd_tse),
                    "uf": str(row.uf),
                    "name_tse": name_tse_raw,
                    "name_ibge": str(row.master_name),
                    "similarity": round(ratio, 4),
                }
            )

    return CrosswalkReport(total_pairs=len(joined), name_warnings=name_warnings)


def map_tse_to_ibge(
    votes_df: pd.DataFrame,
    crosswalk_df: pd.DataFrame,
) -> pd.DataFrame:
    """Replaces `cd_tse` with the canonical 7-digit `cd_ibge` identifier.

    Args:
        votes_df: DataFrame containing a `cd_tse` integer column.
        crosswalk_df: Validated crosswalk DataFrame with `cd_tse` and `cd_ibge`.

    Returns:
        New DataFrame with `cd_ibge` attached and `cd_tse` removed.

    Raises:
        CrosswalkError: If the merge is not `many_to_one` or leaves unmatched rows.
    """
    try:
        merged = votes_df.merge(
            crosswalk_df[["cd_tse", "cd_ibge"]],
            on="cd_tse",
            how="left",
            validate="many_to_one",
            indicator=True,
        )
    except pd.errors.MergeError as exc:
        raise CrosswalkError(f"Invalid crosswalk merge cardinality: {exc}") from exc

    unmatched = merged.loc[merged["_merge"] != "both", "cd_tse"].unique()
    if len(unmatched) > 0:
        raise CrosswalkError(f"Unmapped TSE codes found: {sorted(unmatched.tolist())}")
    return merged.drop(columns=["cd_tse", "_merge"])


def build_crosswalk_dataframe(
    seed_df: pd.DataFrame,
    overrides_df: pd.DataFrame,
    master_df: pd.DataFrame,
    *,
    seed_source_label: str = "betafcc@master",
) -> pd.DataFrame:
    """Combines community seed and manual overrides into the canonical crosswalk table.

    Args:
        seed_df: Raw community crosswalk DataFrame (`codigo_tse`, `codigo_ibge`).
        overrides_df: Manual overrides DataFrame (`cd_tse`, `cd_ibge`, `uf`, `source`).
        master_df: Official IBGE master municipality list (`cd_ibge`, `name`, `uf`).
        seed_source_label: Provenance label for rows coming from `seed_df`.

    Returns:
        Validated crosswalk DataFrame sorted by `cd_ibge`.

    Raises:
        CrosswalkError: If the resulting table fails rules X1-X5.
    """
    base = pd.DataFrame(
        {
            "cd_tse": seed_df["codigo_tse"].astype(str).str.strip().astype(int),
            "cd_ibge": seed_df["codigo_ibge"].astype(str).str.strip().astype(int),
            "uf": seed_df["uf"].astype(str).str.strip().str.upper(),
            "name_tse": seed_df["nome_municipio"].astype(str).str.strip(),
            "source": seed_source_label,
        }
    )

    if not overrides_df.empty:
        ovr = pd.DataFrame(
            {
                "cd_tse": overrides_df["cd_tse"].astype(str).str.strip().astype(int),
                "cd_ibge": overrides_df["cd_ibge"].astype(str).str.strip().astype(int),
                "uf": overrides_df["uf"].astype(str).str.strip().str.upper(),
                "name_tse": overrides_df["name_tse"].astype(str).str.strip(),
                "source": overrides_df["source"].astype(str).str.strip(),
            }
        )
        base = base.loc[
            ~base["cd_ibge"].isin(ovr["cd_ibge"]) & ~base["cd_tse"].isin(ovr["cd_tse"])
        ]
        combined = pd.concat([base, ovr], ignore_index=True)
    else:
        combined = base

    merged = combined.merge(
        master_df[["cd_ibge", "name"]].rename(columns={"name": "name_ibge"}),
        on="cd_ibge",
        how="inner",
        validate="one_to_one",
        indicator=True,
    )
    if (merged["_merge"] != "both").any():
        raise CrosswalkError("Failed to attach IBGE names to crosswalk rows.")
    result = (
        merged.drop(columns=["_merge"])[
            ["cd_tse", "cd_ibge", "uf", "name_tse", "name_ibge", "source"]
        ]
        .sort_values("cd_ibge")
        .reset_index(drop=True)
    )
    validate_crosswalk(result, master_df)
    return result


def load_crosswalk_csv(path: Path) -> pd.DataFrame:
    """Reads `de_para_tse_ibge.csv` from disk.

    Args:
        path: Path to `de_para_tse_ibge.csv`.

    Returns:
        DataFrame with typed `cd_tse` and `cd_ibge` integer columns.

    Raises:
        FileNotFoundError: If `path` does not exist.
    """
    df = pd.read_csv(path, dtype=str)
    df["cd_tse"] = df["cd_tse"].str.strip().astype(int)
    df["cd_ibge"] = df["cd_ibge"].str.strip().astype(int)
    df["uf"] = df["uf"].str.strip().str.upper()
    return df


def build_and_save_crosswalk(
    settings: Settings,
    *,
    force_refresh: bool = False,
) -> Path:
    """Downloads seed and IBGE master list, builds, and saves the crosswalk CSV.

    Args:
        settings: Application Settings instance.
        force_refresh: Whether to re-download cached seed/master files.

    Returns:
        Path to the written `de_para_tse_ibge.csv` file.
    """
    with CachedHttpClient(
        cache_root=settings.raw_dir, timeout_s=settings.http_timeout_s
    ) as client:
        master_art = fetch_municipality_list(client, force_refresh=force_refresh)
        master_df = parse_municipality_list(master_art.path)
        seed_art = client.download(
            source="crosswalk",
            url=COMMUNITY_SEED_URL,
            filename="municipios_brasileiros_tse.csv",
            force_refresh=force_refresh,
        )

    seed_df = pd.read_csv(seed_art.path, dtype=str)
    overrides_path = settings.reference_dir / "de_para_overrides.csv"
    overrides_df = (
        pd.read_csv(overrides_path, dtype=str)
        if overrides_path.exists()
        else pd.DataFrame()
    )
    xw_df = build_crosswalk_dataframe(seed_df, overrides_df, master_df)

    out_path = settings.reference_dir / "de_para_tse_ibge.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    xw_df.to_csv(out_path, index=False, encoding="utf-8")
    return out_path


def run_crosswalk_validation_cli(settings: Settings) -> CrosswalkReport:
    """Validates `data/reference/de_para_tse_ibge.csv` against the IBGE master list.

    Args:
        settings: Application Settings instance.

    Returns:
        CrosswalkReport instance.
    """
    xw_path = settings.reference_dir / "de_para_tse_ibge.csv"
    if not xw_path.exists():
        build_and_save_crosswalk(settings)
    xw_df = load_crosswalk_csv(xw_path)

    with CachedHttpClient(
        cache_root=settings.raw_dir, timeout_s=settings.http_timeout_s
    ) as client:
        master_art = fetch_municipality_list(client)
        master_df = parse_municipality_list(master_art.path)

    return validate_crosswalk(xw_df, master_df)


def apply_crosswalk_to_db(
    engine: sa.Engine,
    xw_df: pd.DataFrame,
) -> StepResult:
    """Updates `municipality.cd_tse` in PostgreSQL using the validated crosswalk.

    Args:
        engine: SQLAlchemy Engine connected to PostgreSQL.
        xw_df: Validated crosswalk DataFrame.

    Returns:
        StepResult with row counts.
    """
    records = [
        {"cd_ibge": int(row.cd_ibge), "cd_tse": int(row.cd_tse)}
        for row in xw_df.itertuples(index=False)
    ]
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                UPDATE municipality
                SET cd_tse = :cd_tse
                WHERE cd_ibge = :cd_ibge
                """
            ),
            records,
        )
    return StepResult(
        step="crosswalk",
        rows_in=len(records),
        rows_out=len(records),
        dropped={},
    )
