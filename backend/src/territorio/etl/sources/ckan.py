"""Tesouro Transparente CKAN adapter for CAPAG Municípios (Source S9)."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from territorio.etl.http import CachedHttpClient
from territorio.etl.reference import IndicatorSpec


class CkanExtractionError(ValueError):
    """Raised when a CKAN package metadata or CAPAG spreadsheet is invalid."""


def select_latest_xlsx_resource(package_payload: dict[str, Any]) -> str:
    """Selects the latest `.xlsx` resource URL from a CKAN `package_show` payload.

    Args:
        package_payload: JSON dictionary returned by CKAN `package_show`.

    Returns:
        Resource download URL string.

    Raises:
        CkanExtractionError: If `success` is False or no `.xlsx` resource exists.
    """
    if not isinstance(package_payload, dict) or not package_payload.get("success"):
        raise CkanExtractionError("CKAN package_show response did not succeed.")

    result = package_payload.get("result", {})
    resources = result.get("resources", []) if isinstance(result, dict) else []
    if not isinstance(resources, list):
        raise CkanExtractionError("CKAN package_show result.resources is not a list.")

    xlsx_candidates: list[tuple[str, str]] = []
    for res in resources:
        if not isinstance(res, dict):
            continue
        url = str(res.get("url", "")).strip()
        fmt = str(res.get("format", "")).strip().upper()
        if url.lower().endswith(".xlsx") or fmt == "XLSX":
            created = str(res.get("last_modified") or res.get("created") or "").strip()
            xlsx_candidates.append((created, url))

    if not xlsx_candidates:
        raise CkanExtractionError("No XLSX resource found in CKAN package resources.")

    xlsx_candidates.sort(key=lambda pair: pair[0])
    return xlsx_candidates[-1][1]


def parse_capag_xlsx(
    xlsx_path: Path,
    *,
    sheet_name: str = "Prévia da CAPAG",
    fallback_sheet_name: str = "CAPAG Ano Base 2025",
    header_row: int = 2,
    ibge_column: str = "Código Município Completo",
    value_column: str = "CAPAG",
    allowed_values: list[str] | None = None,
    missing_tokens: list[str] | None = None,
    ref_year: int = 2025,
) -> pd.DataFrame:
    """Parses the CAPAG Municípios Excel spreadsheet into a municipal DataFrame.

    Args:
        xlsx_path: Path to the downloaded `.xlsx` file.
        sheet_name: Primary worksheet name.
        fallback_sheet_name: Fallback worksheet name if `sheet_name` is absent.
        header_row: 0-indexed row number containing column headers.
        ibge_column: Column containing the 7-digit IBGE municipality code.
        value_column: Column containing the CAPAG rating letter (`A+`..`D`).
        allowed_values: Allowed rating strings in descending order (`['A+', ..., 'D']`).
        missing_tokens: Tokens representing missing ratings (`['n.d.', 'n.e.', ...]`).
        ref_year: Reference year for the CAPAG release.

    Returns:
        DataFrame with columns `['cd_ibge', 'ref_year', 'value', 'value_text',
        'missing_reason']`.

    Raises:
        CkanExtractionError: If required columns or sheets are missing, or if an
            unknown rating string is encountered.
    """
    allowed = allowed_values or ["A+", "A", "B+", "B", "C", "D"]
    allowed_set = set(allowed)
    rank_map = {val: float(len(allowed) - idx) for idx, val in enumerate(allowed)}
    m_tokens = {t.lower() for t in (missing_tokens or ["n.d.", "n.e.", "#N/A", "-"])}

    try:
        excel = pd.ExcelFile(xlsx_path)
    except Exception as exc:
        raise CkanExtractionError(
            f"Failed to open CAPAG XLSX {xlsx_path}: {exc}"
        ) from exc

    selected_sheet: str | int = 0
    if sheet_name in excel.sheet_names:
        selected_sheet = sheet_name
    elif fallback_sheet_name in excel.sheet_names:
        selected_sheet = fallback_sheet_name
    elif excel.sheet_names:
        selected_sheet = excel.sheet_names[0]

    df = pd.read_excel(excel, sheet_name=selected_sheet, header=header_row)
    if ibge_column not in df.columns and header_row != 0:
        df_alt = pd.read_excel(excel, sheet_name=selected_sheet, header=0)
        if ibge_column in df_alt.columns:
            df = df_alt

    if ibge_column not in df.columns or value_column not in df.columns:
        raise CkanExtractionError(
            f"CAPAG sheet {selected_sheet!r} is missing required columns "
            f"{ibge_column!r} or {value_column!r}. Found: {list(df.columns)}"
        )

    rows: list[dict[str, Any]] = []
    for raw_cd, raw_val in zip(
        df[ibge_column].tolist(), df[value_column].tolist(), strict=True
    ):
        if pd.isna(raw_cd):
            continue
        cd_str = str(raw_cd).strip().split(".")[0]
        if not cd_str.isdigit() or len(cd_str) != 7:
            continue
        cd_ibge = int(cd_str)

        if pd.isna(raw_val):
            rows.append(
                {
                    "cd_ibge": cd_ibge,
                    "ref_year": int(ref_year),
                    "value": np.nan,
                    "value_text": None,
                    "missing_reason": "nao_disponivel_capag",
                }
            )
            continue

        txt = str(raw_val).strip()
        if not txt or txt.lower() in m_tokens:
            reason = (
                "nao_elegivel_capag"
                if txt.lower() == "n.e."
                else "nao_disponivel_capag"
            )
            rows.append(
                {
                    "cd_ibge": cd_ibge,
                    "ref_year": int(ref_year),
                    "value": np.nan,
                    "value_text": None,
                    "missing_reason": reason,
                }
            )
            continue

        if txt not in allowed_set:
            raise CkanExtractionError(
                f"Unexpected CAPAG rating {txt!r} for cd_ibge={cd_ibge}; "
                f"allowed={allowed}."
            )

        rows.append(
            {
                "cd_ibge": cd_ibge,
                "ref_year": int(ref_year),
                "value": rank_map[txt],
                "value_text": txt,
                "missing_reason": None,
            }
        )

    out = pd.DataFrame(
        rows,
        columns=["cd_ibge", "ref_year", "value", "value_text", "missing_reason"],
    )
    if not out.empty:
        out = out.drop_duplicates(subset=["cd_ibge"], keep="first").reset_index(
            drop=True
        )
    return out


def fetch_ckan_capag_indicator(
    client: CachedHttpClient,
    spec: IndicatorSpec,
    *,
    ref_year: int = 2025,
) -> tuple[pd.DataFrame, str, str]:
    """Discovers and parses the CAPAG indicator via Tesouro Transparente CKAN.

    Args:
        client: Cached HTTP client.
        spec: Indicator specification with `adapter == 'ckan'`.
        ref_year: Reference year (defaults to 2025).

    Returns:
        Tuple `(raw_df, xlsx_url, sha256_hex)`.
    """
    params = spec.source_params
    base_url = str(
        params.get(
            "base_url",
            "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show",
        )
    )
    package_id = str(params.get("package_id", "capag-municipios"))
    pkg_url = f"{base_url}?id={package_id}"

    pkg_payload, _ = client.get_json(pkg_url)
    xlsx_url = select_latest_xlsx_resource(pkg_payload)
    dl = client.download(xlsx_url, subdir="ckan")

    df = parse_capag_xlsx(
        dl.path,
        sheet_name=str(params.get("sheet_name", "Prévia da CAPAG")),
        fallback_sheet_name=str(
            params.get("fallback_sheet_name", "CAPAG Ano Base 2025")
        ),
        header_row=int(params.get("header_row", 2)),
        ibge_column=str(params.get("ibge_column", "Código Município Completo")),
        value_column=str(params.get("value_column", "CAPAG")),
        allowed_values=params.get("allowed_values"),
        missing_tokens=params.get("missing_tokens"),
        ref_year=ref_year,
    )
    return df, xlsx_url, dl.sha256
