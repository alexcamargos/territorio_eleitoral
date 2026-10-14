"""TSE Open Data (S1, S15) archive download and chunked CSV streaming."""

import zipfile
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from territorio.etl.crosswalk import map_tse_to_ibge
from territorio.etl.http import CachedArtifact, CachedHttpClient

TSE_CDN_URL_TEMPLATE = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/{dataset}/{dataset}_{year}.zip"
)
TSE_NA_VALUES = ["#NULO", "#NULO#", "#NE", "-1", "-3"]


def fetch_tse_zip(
    client: CachedHttpClient,
    dataset: str,
    year: int = 2026,
    *,
    force_refresh: bool = False,
) -> CachedArtifact:
    """Downloads a TSE zip archive from the official CDN (S1 / S15).

    Args:
        client: Cached HTTP client instance.
        dataset: TSE dataset name (e.g. `votacao_partido_munzona`).
        year: Election year (defaults to 2026).
        force_refresh: If True, bypasses local cache.

    Returns:
        CachedArtifact pointing to the downloaded `.zip` file.
    """
    url = TSE_CDN_URL_TEMPLATE.format(dataset=dataset, year=year)
    return client.download(
        source="tse",
        url=url,
        filename=f"{dataset}_{year}.zip",
        force_refresh=force_refresh,
    )


def _resolve_brasil_member(zf: zipfile.ZipFile, member: str | None) -> str:
    """Finds and validates the `*_BRASIL.csv` member inside a TSE zip archive.

    Args:
        zf: Open ZipFile archive.
        member: Explicit member name or None to auto-discover.

    Returns:
        Validated member name ending with `_BRASIL.csv`.

    Raises:
        ValueError: If `member` does not end with `_BRASIL.csv` or none is found.
    """
    if member is not None:
        if not member.upper().endswith("_BRASIL.CSV"):
            raise ValueError(f"Only *_BRASIL.csv is allowed, got {member}")
        return member

    candidates = [
        name for name in zf.namelist() if name.upper().endswith("_BRASIL.CSV")
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"Expected exactly 1 *_BRASIL.csv member in zip, found {candidates}"
        )
    return candidates[0]


def extract_tse_source_version(
    zip_path: Path,
    member: str | None = None,
) -> str | None:
    """Extracts `DT_GERACAO HH_GERACAO` from the first data row of a TSE CSV.

    Args:
        zip_path: Local path to the TSE zip archive.
        member: Optional explicit `*_BRASIL.csv` member name.

    Returns:
        Combined generation date/time string or None if columns are absent.
    """
    with zipfile.ZipFile(zip_path) as zf:
        resolved = _resolve_brasil_member(zf, member)
        with zf.open(resolved) as fh:
            head_df = pd.read_csv(
                fh,
                sep=";",
                encoding="latin-1",
                dtype=str,
                nrows=1,
            )
    if head_df.empty:
        return None
    dt = head_df.iloc[0].get("DT_GERACAO", "")
    hh = head_df.iloc[0].get("HH_GERACAO", "")
    combined = f"{str(dt).strip()} {str(hh).strip()}".strip()
    return combined or None


def read_tse_csv(
    zip_path: Path,
    member: str | None = None,
    usecols: list[str] | None = None,
    chunksize: int = 500_000,
) -> Iterator[pd.DataFrame]:
    """Streams a TSE `*_BRASIL.csv` member from a zip archive in chunks.

    Args:
        zip_path: Local path of the TSE zip archive.
        member: Member name; MUST be the `*_BRASIL.csv` file (or None to auto-find).
        usecols: Optional list of column names to load.
        chunksize: Number of rows per chunk.

    Yields:
        DataFrames with all requested columns read as `str`.

    Raises:
        ValueError: If `member` is not a `*_BRASIL.csv` file.
    """
    with zipfile.ZipFile(zip_path) as zf:
        resolved = _resolve_brasil_member(zf, member)
        with zf.open(resolved) as fh:
            yield from pd.read_csv(
                fh,
                sep=";",
                encoding="latin-1",
                usecols=usecols,
                dtype=str,
                na_values=TSE_NA_VALUES,
                keep_default_na=False,
                chunksize=chunksize,
            )


def parse_electorate_profile_indicator(
    zip_path: Path,
    crosswalk_df: pd.DataFrame,
    *,
    filter_column: str,
    filter_values: list[int],
    weight_column: str = "QT_ELEITORES",
    ref_year: int = 2026,
    multiply: float = 100.0,
) -> pd.DataFrame:
    """Computes a municipal electorate percentage from `perfil_eleitorado` (S15).

    Args:
        zip_path: Path to `perfil_eleitorado_2026.zip`.
        crosswalk_df: Validated TSE-to-IBGE crosswalk DataFrame.
        filter_column: Grouping column to filter (e.g. `CD_GRAU_ESCOLARIDADE`).
        filter_values: Integer codes included in the numerator.
        weight_column: Electorate count column (`QT_ELEITORES`).
        ref_year: Reference year (defaults to 2026).
        multiply: Multiplier factor (100.0 for percentage).

    Returns:
        DataFrame with `cd_ibge`, `ref_year`, `value`, `value_text`, `missing_reason`.
    """
    usecols = ["SG_UF", "CD_MUNICIPIO", filter_column, weight_column]
    target_codes = {int(v) for v in filter_values}
    partials: list[pd.DataFrame] = []

    for chunk in read_tse_csv(zip_path, usecols=usecols):
        br_chunk = chunk.loc[chunk["SG_UF"].str.strip().str.upper() != "ZZ"].copy()
        if br_chunk.empty:
            continue
        br_chunk["cd_tse"] = br_chunk["CD_MUNICIPIO"].str.strip().astype(int)
        br_chunk["weight"] = pd.to_numeric(br_chunk[weight_column], errors="raise")
        code_series = pd.to_numeric(br_chunk[filter_column], errors="coerce").fillna(-1)
        br_chunk["matched_weight"] = br_chunk["weight"].where(
            code_series.astype(int).isin(target_codes), 0
        )
        grouped = br_chunk.groupby("cd_tse", as_index=False)[
            ["weight", "matched_weight"]
        ].sum()
        partials.append(grouped)

    combined = (
        pd.concat(partials, ignore_index=True)
        .groupby("cd_tse", as_index=False)[["weight", "matched_weight"]]
        .sum()
    )
    mapped = map_tse_to_ibge(combined, crosswalk_df)
    mapped["value"] = (mapped["matched_weight"] / mapped["weight"]) * multiply
    return (
        pd.DataFrame(
            {
                "cd_ibge": mapped["cd_ibge"].astype(int),
                "ref_year": int(ref_year),
                "value": mapped["value"].astype(float),
                "value_text": None,
                "missing_reason": None,
            }
        )
        .sort_values("cd_ibge")
        .reset_index(drop=True)
    )
