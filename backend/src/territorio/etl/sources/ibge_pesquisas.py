"""IBGE Pesquisas / IBGE Cidades REST adapter (Source S6)."""

import hashlib
from collections.abc import Iterable
from typing import Any

import httpx
import numpy as np
import pandas as pd

from territorio.domain import UF_BY_CODE, ValueType
from territorio.etl.http import CachedHttpClient
from territorio.etl.reference import IndicatorSpec
from territorio.etl.transform.indicators import (
    parse_ibge_numeric_value,
    resolve_ref_year,
)

PESQUISAS_BASE_URL = "https://servicodados.ibge.gov.br/api/v1/pesquisas"
DEFAULT_SENTINEL_MIN = 99999999999990.0


class IbgePesquisasExtractionError(ValueError):
    """Raised when an IBGE Pesquisas response is malformed or has unmapped codes."""


def build_ibge6_to_ibge7_map(
    master_ibge_codes: Iterable[int],
) -> dict[int, int]:
    """Builds a 1-to-1 lookup mapping 6-digit IBGE code to canonical 7-digit `cd_ibge`.

    Args:
        master_ibge_codes: Canonical 7-digit IBGE municipality codes.

    Returns:
        Dictionary `{cd_ibge6: cd_ibge7}`.

    Raises:
        IbgePesquisasExtractionError: If two 7-digit codes share the same
            6-digit prefix.
    """
    mapping: dict[int, int] = {}
    for code in master_ibge_codes:
        cd7 = int(code)
        cd6 = cd7 // 10
        if cd6 in mapping and mapping[cd6] != cd7:
            raise IbgePesquisasExtractionError(
                f"Ambiguous 6-digit IBGE prefix {cd6}: {mapping[cd6]} vs {cd7}"
            )
        mapping[cd6] = cd7
    return mapping


def build_pesquisas_uf_url(
    *,
    survey: int,
    indicator_id: int,
    uf_code: int,
    period: str = "all",
    base_url: str = PESQUISAS_BASE_URL,
) -> str:
    """Constructs an IBGE Pesquisas URL for a state's municipalities (`N6[N3[uf]]`).

    Args:
        survey: IBGE survey ID (e.g. `10058` for Panorama Cidades).
        indicator_id: Indicator numeric ID (e.g. `60041` for IDEB).
        uf_code: 2-digit IBGE UF code (11..53).
        period: Period selector (`'all'`, `'last'`, or specific year `'2022'`).
        base_url: IBGE Pesquisas API base URL.

    Returns:
        Full request URL string.
    """
    base = base_url.rstrip("/")
    return (
        f"{base}/{int(survey)}/periodos/{period}/indicadores/"
        f"{int(indicator_id)}/resultados/N6[N3[{int(uf_code)}]]"
    )


def parse_pesquisas_payload(
    payload: list[dict[str, Any]],
    *,
    master_ibge_codes: Iterable[int],
    ref_year_policy: str = "latest",
    value_type: ValueType = ValueType.CONTINUOUS,
    sentinel_min: float = DEFAULT_SENTINEL_MIN,
) -> pd.DataFrame:
    """Parses one or more IBGE Pesquisas JSON responses into a municipal DataFrame.

    Converts 6-digit `localidade` codes to 7-digit `cd_ibge` via `master_ibge_codes`,
    selects the reference year according to `ref_year_policy`, and converts IBGE
    sentinel numbers (`>= 99999999999990`) into explicit `NaN`/`None` with
    `missing_reason = 'sentinela_ibge'`.

    Args:
        payload: Combined JSON list of indicator blocks from `servicodados.ibge.gov.br`.
        master_ibge_codes: Canonical 7-digit IBGE municipality codes.
        ref_year_policy: Year selection policy (`'latest'`, `'fixed:YYYY'`, etc.).
        value_type: Target indicator value type (`continuous`, `categorical`, etc.).
        sentinel_min: Lower bound for IBGE Pesquisas sentinel codes.

    Returns:
        DataFrame with columns `['cd_ibge', 'ref_year', 'value', 'value_text',
        'missing_reason']`.

    Raises:
        IbgePesquisasExtractionError: On unmapped locality code or empty years.
    """
    master_set = {int(c) for c in master_ibge_codes}
    ibge6_map = build_ibge6_to_ibge7_map(master_set)

    # First pass: collect raw {cd_ibge: {year_int: raw_val}}
    by_mun: dict[int, dict[int, Any]] = {}
    all_years: set[int] = set()

    for block in payload:
        if not isinstance(block, dict):
            continue
        res_list = block.get("res", [])
        if not isinstance(res_list, list):
            continue
        for item in res_list:
            if not isinstance(item, dict):
                continue
            loc_str = str(item.get("localidade", "")).strip()
            if not loc_str.isdigit():
                continue
            loc_int = int(loc_str)
            if len(loc_str) == 6:
                if loc_int not in ibge6_map:
                    raise IbgePesquisasExtractionError(
                        f"6-digit IBGE code {loc_int} not found in master list."
                    )
                cd_ibge = ibge6_map[loc_int]
            elif len(loc_str) == 7:
                if loc_int not in master_set:
                    raise IbgePesquisasExtractionError(
                        f"7-digit IBGE code {loc_int} not found in master list."
                    )
                cd_ibge = loc_int
            else:
                continue

            res_by_year = item.get("res", {})
            if not isinstance(res_by_year, dict):
                continue
            mun_years = by_mun.setdefault(cd_ibge, {})
            for yr_key, raw_val in res_by_year.items():
                yr_str = str(yr_key).strip()[:4]
                if yr_str.isdigit():
                    yr_int = int(yr_str)
                    mun_years[yr_int] = raw_val
                    if raw_val is not None and str(raw_val).strip() != "":
                        all_years.add(yr_int)

    if not all_years:
        if ref_year_policy.startswith("fixed:"):
            target_year = resolve_ref_year(ref_year_policy, [])
        else:
            raise IbgePesquisasExtractionError(
                "IBGE Pesquisas payload contained no valid year keys."
            )
    else:
        valid_counts: dict[int, int] = dict.fromkeys(all_years, 0)
        for mun_map in by_mun.values():
            for yr, rv in mun_map.items():
                if rv is None:
                    continue
                sv = str(rv).strip()
                if not sv or sv in {"-", "..", "...", "X", "x"}:
                    continue
                if sv.isdigit() and float(sv) >= sentinel_min:
                    continue
                valid_counts[yr] = valid_counts.get(yr, 0) + 1
        max_valid = max(valid_counts.values(), default=0)
        candidate_years = (
            {
                yr
                for yr, cnt in valid_counts.items()
                if cnt >= max(1, int(max_valid * 0.5))
            }
            if max_valid > 0
            else all_years
        )
        target_year = resolve_ref_year(ref_year_policy, candidate_years)

    rows: list[dict[str, Any]] = []
    for cd_ibge in sorted(by_mun.keys()):
        raw_val = by_mun[cd_ibge].get(target_year)
        if value_type == ValueType.CONTINUOUS:
            num, reason = parse_ibge_numeric_value(raw_val, sentinel_min=sentinel_min)
            rows.append(
                {
                    "cd_ibge": cd_ibge,
                    "ref_year": target_year,
                    "value": np.nan if num is None else float(num),
                    "value_text": None,
                    "missing_reason": reason,
                }
            )
        else:
            if raw_val is None:
                rows.append(
                    {
                        "cd_ibge": cd_ibge,
                        "ref_year": target_year,
                        "value": np.nan,
                        "value_text": None,
                        "missing_reason": "ausente_na_fonte",
                    }
                )
                continue
            s_val = str(raw_val).strip()
            if s_val.isdigit() and float(s_val) >= sentinel_min:
                rows.append(
                    {
                        "cd_ibge": cd_ibge,
                        "ref_year": target_year,
                        "value": np.nan,
                        "value_text": None,
                        "missing_reason": "sentinela_ibge",
                    }
                )
            elif not s_val or s_val in {"-", "..", "...", "X", "x"}:
                rows.append(
                    {
                        "cd_ibge": cd_ibge,
                        "ref_year": target_year,
                        "value": np.nan,
                        "value_text": None,
                        "missing_reason": "ausente_na_fonte",
                    }
                )
            else:
                rows.append(
                    {
                        "cd_ibge": cd_ibge,
                        "ref_year": target_year,
                        "value": np.nan,
                        "value_text": s_val,
                        "missing_reason": None,
                    }
                )

    return pd.DataFrame(
        rows,
        columns=["cd_ibge", "ref_year", "value", "value_text", "missing_reason"],
    )


def fetch_ibge_pesquisas_indicator(
    client: CachedHttpClient,
    spec: IndicatorSpec,
    *,
    master_ibge_codes: Iterable[int],
    uf_codes: Iterable[int] | None = None,
    base_url: str = PESQUISAS_BASE_URL,
) -> tuple[pd.DataFrame, str, str]:
    """Fetches an IBGE Pesquisas indicator batched across all 27 UFs.

    Args:
        client: Cached HTTP client.
        spec: Indicator specification with `adapter == 'ibge_pesquisas'`.
        master_ibge_codes: Canonical 7-digit IBGE municipality codes.
        uf_codes: Optional subset of UF integer codes (defaults to all 27 UFs).
        base_url: IBGE Pesquisas API base URL.

    Returns:
        Tuple `(raw_df, template_url, combined_sha256)`.

    Raises:
        IbgePesquisasExtractionError: If required params are missing.
    """
    params = spec.source_params
    if "survey" not in params or "indicator_id" not in params:
        raise IbgePesquisasExtractionError(
            f"Indicator {spec.code!r} requires 'survey' and 'indicator_id' params."
        )

    survey = int(params["survey"])
    indicator_id = int(params["indicator_id"])
    raw_period = str(params.get("period", "all"))
    api_period = "all" if raw_period == "last" else raw_period

    target_ufs = sorted(uf_codes) if uf_codes is not None else sorted(UF_BY_CODE)
    combined_blocks: list[dict[str, Any]] = []
    hasher = hashlib.sha256()

    for uf_code in target_ufs:
        url = build_pesquisas_uf_url(
            survey=survey,
            indicator_id=indicator_id,
            uf_code=uf_code,
            period=api_period,
            base_url=base_url,
        )
        try:
            data, sha = client.get_json(url)
        except httpx.HTTPStatusError:
            alt_url = (
                f"{base_url.rstrip('/')}/indicadores/"
                f"{int(indicator_id)}/resultados/N6[N3[{int(uf_code)}]]"
            )
            data, sha = client.get_json(alt_url)
        hasher.update(sha.encode("ascii"))
        if isinstance(data, list):
            combined_blocks.extend(b for b in data if isinstance(b, dict))

    sentinel_min = float(
        (spec.transform or {}).get("sentinel_min", DEFAULT_SENTINEL_MIN)
    )
    df = parse_pesquisas_payload(
        combined_blocks,
        master_ibge_codes=master_ibge_codes,
        ref_year_policy=spec.ref_year_policy,
        value_type=spec.value_type,
        sentinel_min=sentinel_min,
    )
    template_url = (
        f"{base_url.rstrip('/')}/{survey}/periodos/{api_period}/"
        f"indicadores/{indicator_id}/resultados/N6[N3[UF]]"
    )
    return df, template_url, hasher.hexdigest()
