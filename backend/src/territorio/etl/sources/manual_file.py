"""Manual file (XLSX/CSV) adapter for Tier 2 composite indices (Sources S10-S13)."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from territorio.etl.provenance import compute_file_sha256
from territorio.etl.reference import IndicatorSpec
from territorio.etl.sources.ibge_pesquisas import build_ibge6_to_ibge7_map
from territorio.etl.transform.indicators import (
    parse_ibge_numeric_value,
    resolve_ref_year,
)


class ManualFileExtractionError(ValueError):
    """Raised when a manual file is missing, corrupted, or fails SHA-256 check."""


class UnverifiedIndicatorError(ManualFileExtractionError):
    """Raised when loading an unverified indicator without `--allow-unverified`."""


def load_manual_file_indicator(
    spec: IndicatorSpec,
    *,
    master_ibge_codes: Iterable[int],
    project_root: Path | None = None,
    allow_unverified: bool = False,
    default_ref_year: int = 2024,
) -> tuple[pd.DataFrame, str, str]:
    """Reads and validates a `manual_file` indicator from disk.

    Enforces `verified: true` and `sha256` verification unless `allow_unverified`
    is explicitly enabled. Supports both 7-digit and 6-digit IBGE municipality codes.

    Args:
        spec: Indicator specification with `adapter == 'manual_file'`.
        master_ibge_codes: Canonical 7-digit IBGE municipality codes.
        project_root: Base directory for resolving relative `source.params.path`.
        allow_unverified: Whether to permit loading when `spec.verified` is False
            or `sha256` is null.
        default_ref_year: Fallback reference year when `ref_year_policy == 'latest'`.

    Returns:
        Tuple `(raw_df, file_uri, sha256_hex)`.

    Raises:
        UnverifiedIndicatorError: If `not spec.verified` and `not allow_unverified`.
        ManualFileExtractionError: If the file does not exist, fails SHA-256
            verification, or lacks required columns.
    """
    params = spec.source_params
    expected_sha = params.get("sha256")
    if (not spec.verified or not expected_sha) and not allow_unverified:
        raise UnverifiedIndicatorError(
            f"Indicator {spec.code!r} is marked verified={spec.verified} "
            f"(sha256={expected_sha!r}). Pass --allow-unverified or pin sha256 in "
            "data/reference/indicators.yaml."
        )

    rel_path = str(params.get("path", "")).strip()
    if not rel_path:
        raise ManualFileExtractionError(
            f"Manual indicator {spec.code!r} is missing 'path' in source.params."
        )

    file_path = Path(rel_path)
    if not file_path.is_absolute() and project_root is not None:
        file_path = project_root / file_path

    if not file_path.exists():
        raise ManualFileExtractionError(
            f"Manual file for {spec.code!r} not found at {file_path}. "
            f"Download from {spec.source_url} before running."
        )

    actual_sha = compute_file_sha256(file_path)
    if expected_sha and str(expected_sha).strip().lower() != actual_sha.lower():
        raise ManualFileExtractionError(
            f"SHA-256 mismatch for {file_path}: expected {expected_sha}, "
            f"got {actual_sha}."
        )

    ibge_col = str(params.get("ibge_column", "cd_ibge")).strip()
    val_col = str(params.get("value_column", spec.code)).strip()
    sheet_name = params.get("sheet_name", 0)

    if file_path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
    elif file_path.suffix.lower() == ".csv":
        df = pd.read_csv(file_path)
    else:
        raise ManualFileExtractionError(
            f"Unsupported manual file extension: {file_path.suffix}"
        )

    if ibge_col not in df.columns or val_col not in df.columns:
        raise ManualFileExtractionError(
            f"Manual file {file_path.name} missing required columns "
            f"{ibge_col!r} or {val_col!r}. Found: {list(df.columns)}"
        )

    master_set = {int(c) for c in master_ibge_codes}
    ibge6_map = build_ibge6_to_ibge7_map(master_set)
    ref_year = resolve_ref_year(spec.ref_year_policy, [default_ref_year])

    rows: list[dict[str, Any]] = []
    for raw_cd, raw_val in zip(
        df[ibge_col].tolist(), df[val_col].tolist(), strict=True
    ):
        if pd.isna(raw_cd):
            continue
        cd_str = str(raw_cd).strip().split(".")[0]
        if not cd_str.isdigit():
            continue
        cd_int = int(cd_str)
        if len(cd_str) == 6:
            if cd_int not in ibge6_map:
                raise ManualFileExtractionError(
                    f"Unknown 6-digit IBGE code {cd_int} in {file_path.name}."
                )
            cd_ibge = ibge6_map[cd_int]
        elif len(cd_str) == 7:
            if cd_int not in master_set:
                raise ManualFileExtractionError(
                    f"Unknown 7-digit IBGE code {cd_int} in {file_path.name}."
                )
            cd_ibge = cd_int
        else:
            continue

        num, reason = parse_ibge_numeric_value(raw_val)
        rows.append(
            {
                "cd_ibge": cd_ibge,
                "ref_year": ref_year,
                "value": np.nan if num is None else float(num),
                "missing_reason": reason,
            }
        )

    out = pd.DataFrame(rows, columns=["cd_ibge", "ref_year", "value", "missing_reason"])
    return out, str(file_path), actual_sha
