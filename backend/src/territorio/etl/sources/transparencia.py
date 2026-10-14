"""Portal da Transparência (CGU) REST adapter (Source S7)."""

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from territorio.etl.http import CachedHttpClient
from territorio.etl.reference import IndicatorSpec

TRANSPARENCIA_BASE_URL = "https://api.portaldatransparencia.gov.br/api-de-dados"


class TransparenciaExtractionError(ValueError):
    """Raised when Portal da Transparência configuration or payload is invalid."""


class TransparenciaConfigurationError(TransparenciaExtractionError):
    """Raised when `TRANSPARENCIA_API_KEY` is missing or empty."""


def compute_rolling_months(ref_month: str, months: int) -> list[str]:
    """Computes a chronological list of `YYYYMM` strings ending at `ref_month`.

    Args:
        ref_month: Final reference month in `YYYYMM` format (e.g. `'202609'`).
        months: Number of consecutive months to include (`>= 1`).

    Returns:
        Chronological list of `YYYYMM` strings of length `months`.

    Raises:
        TransparenciaExtractionError: If `ref_month` is malformed or `months < 1`.
    """
    clean = str(ref_month).strip()
    if len(clean) != 6 or not clean.isdigit() or months < 1:
        raise TransparenciaExtractionError(
            f"Invalid ref_month={ref_month!r} or months={months}."
        )
    year = int(clean[:4])
    month = int(clean[4:6])
    if not (1 <= month <= 12):
        raise TransparenciaExtractionError(f"Month out of range in {ref_month!r}.")

    result: list[str] = []
    cur_y, cur_m = year, month
    for _ in range(months):
        result.append(f"{cur_y:04d}{cur_m:02d}")
        cur_m -= 1
        if cur_m == 0:
            cur_m = 12
            cur_y -= 1
    result.reverse()
    return result


def extract_transparencia_field(
    payload: list[dict[str, Any]] | dict[str, Any],
    field: str,
    *,
    zero_when_absent: bool = False,
) -> tuple[float | None, str | None]:
    """Extracts and sums a numeric field from a Portal da Transparência JSON response.

    Args:
        payload: Parsed JSON response (typically a list of monthly municipal records).
        field: Field name (`'valor'` or `'quantidadeBeneficiados'`).
        zero_when_absent: Whether an empty list `[]` should be treated as `0.0`
            (used for seasonal programs like Garantia-Safra and Seguro-Defeso).

    Returns:
        Tuple `(numeric_value, missing_reason)`.
    """
    items: list[dict[str, Any]]
    if isinstance(payload, list):
        items = [x for x in payload if isinstance(x, dict)]
    elif isinstance(payload, dict):
        items = [payload]
    else:
        items = []

    if not items:
        if zero_when_absent:
            return 0.0, None
        return None, "ausente_na_fonte"

    total = 0.0
    found_any = False
    for item in items:
        raw_val = item.get(field)
        if raw_val is None:
            continue
        try:
            total += float(raw_val)
            found_any = True
        except (TypeError, ValueError):
            continue

    if not found_any:
        if zero_when_absent:
            return 0.0, None
        return None, "ausente_na_fonte"
    return total, None


def fetch_transparencia_municipality_month(
    client: CachedHttpClient,
    *,
    endpoint: str,
    mes_ano: str,
    cd_ibge: int,
    api_key: str,
    cache_dir: Path | None = None,
    resume: bool = True,
    base_url: str = TRANSPARENCIA_BASE_URL,
) -> tuple[list[dict[str, Any]], str]:
    """Fetches or loads from disk cache a single `(endpoint, mesAno, cd_ibge)` JSON.

    Args:
        client: Cached HTTP client (configured with rate limiting).
        endpoint: Endpoint slug (e.g. `'novo-bolsa-familia-por-municipio'`).
        mes_ano: Reference month in `YYYYMM` format.
        cd_ibge: Canonical 7-digit IBGE municipality code.
        api_key: Portal da Transparência API token (`chave-api-dados`).
        cache_dir: Optional directory for per-municipality checkpoint files.
        resume: Whether to reuse existing checkpoint files on disk.
        base_url: Portal da Transparência API base URL.

    Returns:
        Tuple `(json_list, sha256_hex)`.

    Raises:
        TransparenciaConfigurationError: If `api_key` is empty.
    """
    if not api_key or not api_key.strip():
        raise TransparenciaConfigurationError(
            "TRANSPARENCIA_API_KEY is required to query Portal da Transparência."
        )

    if cache_dir is not None:
        checkpoint_path = cache_dir / endpoint / mes_ano / f"{int(cd_ibge)}.json"
        if resume and checkpoint_path.exists():
            raw_bytes = checkpoint_path.read_bytes()
            sha = hashlib.sha256(raw_bytes).hexdigest()
            data = json.loads(raw_bytes.decode("utf-8"))
            return (data if isinstance(data, list) else [data]), sha

    url = (
        f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        f"?mesAno={mes_ano}&codigoIbge={int(cd_ibge)}&pagina=1"
    )
    data, sha = client.get_json(
        url,
        headers={"chave-api-dados": api_key.strip(), "Accept": "application/json"},
    )
    normalized: list[dict[str, Any]] = (
        [x for x in data if isinstance(x, dict)]
        if isinstance(data, list)
        else ([data] if isinstance(data, dict) else [])
    )

    if cache_dir is not None:
        checkpoint_path = cache_dir / endpoint / mes_ano / f"{int(cd_ibge)}.json"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        raw_out = json.dumps(normalized, ensure_ascii=False).encode("utf-8")
        checkpoint_path.write_bytes(raw_out)

    return normalized, sha


def fetch_transparencia_indicator(
    client: CachedHttpClient,
    spec: IndicatorSpec,
    *,
    master_ibge_codes: Iterable[int],
    api_key: str,
    cache_dir: Path | None = None,
    resume: bool = True,
    base_url: str = TRANSPARENCIA_BASE_URL,
) -> tuple[pd.DataFrame, str, str]:
    """Fetches a Portal da Transparência indicator across all municipalities and months.

    Supports single-month snapshots (`months: 1`) and 12-month seasonal windows
    (`months: 12`, `agg: "sum"`, `zero_when_absent: true`).

    Args:
        client: Cached HTTP client.
        spec: Indicator specification with `adapter == 'transparencia'`.
        master_ibge_codes: Canonical 7-digit IBGE municipality codes.
        api_key: Portal da Transparência API key (`chave-api-dados`).
        cache_dir: Optional directory for per-municipality checkpoint files.
        resume: Whether to reuse existing checkpoint files on disk.
        base_url: Portal da Transparência API base URL.

    Returns:
        Tuple `(raw_df, template_url, combined_sha256)`.

    Raises:
        TransparenciaConfigurationError: If `api_key` is missing.
        TransparenciaExtractionError: If required `source.params` are missing.
    """
    if not api_key or not api_key.strip():
        raise TransparenciaConfigurationError(
            f"Indicator {spec.code!r} requires TRANSPARENCIA_API_KEY."
        )

    params = spec.source_params
    endpoint = str(params.get("endpoint", "")).strip()
    field = str(params.get("field", "")).strip()
    ref_month = str(params.get("ref_month", "202609")).strip()
    months_count = int(params.get("months", 1))
    zero_when_absent = bool(params.get("zero_when_absent", False))

    if not endpoint or not field:
        raise TransparenciaExtractionError(
            f"Indicator {spec.code!r} requires 'endpoint' and 'field' params."
        )

    month_list = compute_rolling_months(ref_month, months_count)
    ref_year = int(ref_month[:4])
    hasher = hashlib.sha256()
    rows: list[dict[str, Any]] = []

    for cd_ibge in sorted({int(c) for c in master_ibge_codes}):
        month_vals: list[float] = []
        last_reason: str | None = None
        for m_str in month_list:
            payload, sha = fetch_transparencia_municipality_month(
                client,
                endpoint=endpoint,
                mes_ano=m_str,
                cd_ibge=cd_ibge,
                api_key=api_key,
                cache_dir=cache_dir,
                resume=resume,
                base_url=base_url,
            )
            hasher.update(sha.encode("ascii"))
            val, reason = extract_transparencia_field(
                payload,
                field,
                zero_when_absent=zero_when_absent,
            )
            if val is not None:
                month_vals.append(float(val))
            else:
                last_reason = reason

        if month_vals:
            rows.append(
                {
                    "cd_ibge": cd_ibge,
                    "ref_year": ref_year,
                    "value": float(sum(month_vals)),
                    "missing_reason": None,
                }
            )
        else:
            rows.append(
                {
                    "cd_ibge": cd_ibge,
                    "ref_year": ref_year,
                    "value": np.nan,
                    "missing_reason": last_reason or "ausente_na_fonte",
                }
            )

    template_url = (
        f"{base_url.rstrip('/')}/{endpoint}?mesAno={ref_month}&codigoIbge={{cd_ibge}}"
    )
    return (
        pd.DataFrame(rows, columns=["cd_ibge", "ref_year", "value", "missing_reason"]),
        template_url,
        hasher.hexdigest(),
    )
