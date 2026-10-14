"""IBGE SIDRA REST adapter (Source S5)."""

import hashlib
from typing import Any

import numpy as np
import pandas as pd

from territorio.etl.http import CachedHttpClient
from territorio.etl.reference import IndicatorSpec
from territorio.etl.transform.indicators import parse_ibge_numeric_value

SIDRA_BASE_URL = "https://apisidra.ibge.gov.br/values"
SIDRA_MAX_CATEGORIES_PER_CALL = 8


class SidraExtractionError(ValueError):
    """Raised when an IBGE SIDRA response is malformed or cannot be joined."""


def build_sidra_url(
    *,
    table: int,
    variable: int,
    period: str = "last",
    classifications: dict[str, str] | None = None,
    base_url: str = SIDRA_BASE_URL,
) -> str:
    """Constructs an IBGE SIDRA `/values` URL for all municipalities (`n6/all`).

    Args:
        table: SIDRA table number (`t`).
        variable: SIDRA variable code (`v`).
        period: Period selector (`p`), e.g. `'2022'` or `'last'`.
        classifications: Optional mapping of classification keys (e.g.
            `'c86': '2777,2779'`).
        base_url: SIDRA API base URL.

    Returns:
        Full SIDRA request URL string.
    """
    parts = [
        base_url.rstrip("/"),
        "t",
        str(int(table)),
        "n6",
        "all",
        "v",
        str(int(variable)),
        "p",
        str(period),
    ]
    if classifications:
        for key, val in classifications.items():
            clean_key = str(key).lstrip("/")
            parts.extend([clean_key, str(val)])
    return "/".join(parts)


def parse_sidra_payload(
    payload: list[dict[str, Any]],
    *,
    agg: str | None = None,
) -> pd.DataFrame:
    """Parses a raw JSON list returned by IBGE SIDRA into a municipal DataFrame.

    Row 0 of SIDRA `/values` responses is a header dictionary describing column
    labels (`D1C == 'Município (Código)'`) and is skipped automatically.

    Args:
        payload: JSON list of dictionaries returned by `apisidra.ibge.gov.br`.
        agg: Optional aggregation rule across multiple classification categories
            per municipality (`'sum'` or `None`).

    Returns:
        DataFrame with columns `['cd_ibge', 'ref_year', 'value', 'missing_reason']`.

    Raises:
        SidraExtractionError: If `payload` is empty or lacks required SIDRA keys.
    """
    if not isinstance(payload, list) or len(payload) == 0:
        raise SidraExtractionError("SIDRA payload must be a non-empty list.")

    records: list[dict[str, Any]] = []
    for idx, row in enumerate(payload):
        if not isinstance(row, dict):
            continue
        d1c = str(row.get("D1C", "")).strip()
        if idx == 0 and not d1c.isdigit():
            continue
        if not d1c.isdigit() or len(d1c) != 7:
            raise SidraExtractionError(
                f"Invalid SIDRA municipality code D1C={d1c!r} at index {idx}."
            )
        cd_ibge = int(d1c)
        d3c = str(row.get("D3C", "")).strip()
        ref_year = int(d3c[:4]) if len(d3c) >= 4 and d3c[:4].isdigit() else 2022
        raw_v = row.get("V")
        val, reason = parse_ibge_numeric_value(raw_v)
        records.append(
            {
                "cd_ibge": cd_ibge,
                "ref_year": ref_year,
                "value": np.nan if val is None else float(val),
                "missing_reason": reason,
            }
        )

    if not records:
        return pd.DataFrame(columns=["cd_ibge", "ref_year", "value", "missing_reason"])

    df = pd.DataFrame(records)
    if agg == "sum":
        grouped_rows: list[dict[str, Any]] = []
        for (cd, yr), grp in df.groupby(["cd_ibge", "ref_year"], sort=True):
            valid_vals = grp["value"].dropna()
            if valid_vals.empty:
                first_reason = (
                    grp["missing_reason"].dropna().iloc[0]
                    if grp["missing_reason"].notna().any()
                    else "ausente_na_fonte"
                )
                grouped_rows.append(
                    {
                        "cd_ibge": int(cd),
                        "ref_year": int(yr),
                        "value": np.nan,
                        "missing_reason": str(first_reason),
                    }
                )
            else:
                grouped_rows.append(
                    {
                        "cd_ibge": int(cd),
                        "ref_year": int(yr),
                        "value": float(valid_vals.sum()),
                        "missing_reason": None,
                    }
                )
        return pd.DataFrame(grouped_rows)

    return df.reset_index(drop=True)


def fetch_sidra_indicator(
    client: CachedHttpClient,
    spec: IndicatorSpec,
    *,
    base_url: str = SIDRA_BASE_URL,
) -> tuple[pd.DataFrame, str, str]:
    """Fetches and parses a SIDRA indicator (including optional `denominator` table).

    Args:
        client: Cached HTTP client.
        spec: Indicator specification with `adapter == 'sidra'`.
        base_url: SIDRA API base URL.

    Returns:
        Tuple `(raw_df, request_url, sha256)` ready for `finalize_indicator_dataframe`.

    Raises:
        SidraExtractionError: If required params are missing or denominator join fails.
    """
    params = spec.source_params
    if "table" not in params or "variable" not in params:
        raise SidraExtractionError(
            f"SIDRA indicator {spec.code!r} requires 'table' and 'variable' params."
        )

    classifications = params.get("classifications")
    cls_dict = classifications if isinstance(classifications, dict) else None
    url = build_sidra_url(
        table=int(params["table"]),
        variable=int(params["variable"]),
        period=str(params.get("period", "last")),
        classifications=cls_dict,
        base_url=base_url,
    )

    large_key: str | None = None
    large_items: list[str] = []
    if cls_dict:
        for k, v in cls_dict.items():
            items = [x.strip() for x in str(v).split(",") if x.strip()]
            if len(items) > SIDRA_MAX_CATEGORIES_PER_CALL:
                large_key = k
                large_items = items
                break

    if large_key is not None:
        payload = []
        hasher = hashlib.sha256()
        for idx in range(0, len(large_items), SIDRA_MAX_CATEGORIES_PER_CALL):
            chunk_vals = ",".join(
                large_items[idx : idx + SIDRA_MAX_CATEGORIES_PER_CALL]
            )
            chunk_cls = {**(cls_dict or {}), large_key: chunk_vals}
            chunk_url = build_sidra_url(
                table=int(params["table"]),
                variable=int(params["variable"]),
                period=str(params.get("period", "last")),
                classifications=chunk_cls,
                base_url=base_url,
            )
            chunk_payload, chunk_sha = client.get_json(chunk_url)
            hasher.update(str(chunk_sha).encode("ascii"))
            if isinstance(chunk_payload, list):
                payload.extend(chunk_payload if not payload else chunk_payload[1:])
        sha256 = hasher.hexdigest()
    else:
        payload, sha256 = client.get_json(url)

    agg = (spec.transform or {}).get("agg")
    num_df = parse_sidra_payload(payload, agg=str(agg) if agg else None)

    denom_cfg = params.get("denominator")
    if isinstance(denom_cfg, dict):
        denom_class = denom_cfg.get("classifications")
        denom_url = build_sidra_url(
            table=int(denom_cfg["table"]),
            variable=int(denom_cfg["variable"]),
            period=str(denom_cfg.get("period", params.get("period", "last"))),
            classifications=denom_class if isinstance(denom_class, dict) else None,
            base_url=base_url,
        )
        denom_payload, _ = client.get_json(denom_url)
        denom_df = parse_sidra_payload(denom_payload)

        merged = num_df.merge(
            denom_df[["cd_ibge", "value"]].rename(columns={"value": "denom_value"}),
            on="cd_ibge",
            how="left",
            validate="one_to_one",
            indicator=True,
        )
        new_vals: list[float] = []
        new_reasons: list[str | None] = []
        for val, denom, reason, m_status in zip(
            merged["value"].tolist(),
            merged["denom_value"].tolist(),
            merged["missing_reason"].tolist(),
            merged["_merge"].tolist(),
            strict=True,
        ):
            if np.isnan(val):
                new_vals.append(np.nan)
                new_reasons.append(reason)
            elif m_status != "both" or np.isnan(denom) or denom <= 0.0:
                new_vals.append(np.nan)
                new_reasons.append("denominador_ausente")
            else:
                new_vals.append(float(val) / float(denom))
                new_reasons.append(None)

        num_df["value"] = new_vals
        num_df["missing_reason"] = new_reasons

    return num_df, url, sha256
