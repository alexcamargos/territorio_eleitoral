"""SICONFI / Tesouro Nacional DCA REST adapter (Source S8)."""

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy as np
import pandas as pd

from territorio.etl.http import CachedHttpClient
from territorio.etl.reference import IndicatorSpec

SICONFI_DCA_BASE_URL = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca"
DEFAULT_SICONFI_YEAR = 2024


class SiconfiExtractionError(ValueError):
    """Raised when SICONFI parameters or payload structure are invalid."""


def extract_siconfi_account_value(
    items: list[dict[str, Any]],
    *,
    coluna: str,
    cod_conta: str,
    conta_prefix: str | None = None,
) -> float | None:
    """Extracts the numeric `valor` for a matching SICONFI DCA account line.

    Args:
        items: List of DCA account dictionaries from SICONFI `items`.
        coluna: Target `coluna` label (e.g. `'Receitas Brutas Realizadas'` or
            `'Despesas Empenhadas'`).
        cod_conta: Target `cod_conta` identifier (e.g. `'RO1.0.0.0.00.0.0'` or
            `'TotalDespesas'`).
        conta_prefix: Optional prefix matched against `conta` (e.g. `'10 - Saúde'`
            or `'12 - Educação'` in `DCA-Anexo I-E`).

    Returns:
        Matched float value (summed if multiple lines match), or `None` if absent.
    """
    target_col = coluna.strip().lower()
    target_cod = cod_conta.strip()
    target_prefix = conta_prefix.strip().lower() if conta_prefix else None

    total = 0.0
    matched = False
    for row in items:
        if not isinstance(row, dict):
            continue
        row_col = str(row.get("coluna", "")).strip().lower()
        row_cod = str(row.get("cod_conta", "")).strip()
        if row_col != target_col or row_cod != target_cod:
            continue
        if target_prefix is not None:
            row_conta = str(row.get("conta", "")).strip().lower()
            if not row_conta.startswith(target_prefix):
                continue
        raw_val = row.get("valor")
        if raw_val is None:
            continue
        try:
            total += float(raw_val)
            matched = True
        except (TypeError, ValueError):
            continue

    return total if matched else None


def parse_siconfi_municipality_items(
    items: list[dict[str, Any]],
    *,
    coluna: str,
    cod_conta: str | None = None,
    conta_prefix: str | None = None,
    numerator_cod_conta: str | None = None,
    denominator_cod_conta: str | None = None,
) -> tuple[float | None, str | None]:
    """Computes a single municipality's SICONFI indicator value from DCA `items`.

    Args:
        items: List of DCA account rows for one municipality.
        coluna: Target `coluna` name.
        cod_conta: Account code for single-account indicators.
        conta_prefix: Optional `conta` prefix filter for `DCA-Anexo I-E`.
        numerator_cod_conta: Numerator account code for ratio indicators.
        denominator_cod_conta: Denominator account code for ratio indicators.

    Returns:
        Tuple `(value, missing_reason)`.

    Raises:
        SiconfiExtractionError: If neither `cod_conta` nor ratio accounts are given.
    """
    if not items:
        return None, "nao_declarado"

    if numerator_cod_conta and denominator_cod_conta:
        num = extract_siconfi_account_value(
            items, coluna=coluna, cod_conta=numerator_cod_conta
        )
        denom = extract_siconfi_account_value(
            items, coluna=coluna, cod_conta=denominator_cod_conta
        )
        if denom is None or denom <= 0.0:
            return None, "denominador_ausente"
        if num is None:
            return 0.0, None
        return float(num) / float(denom), None

    if cod_conta:
        val = extract_siconfi_account_value(
            items,
            coluna=coluna,
            cod_conta=cod_conta,
            conta_prefix=conta_prefix,
        )
        if val is None:
            return None, "conta_ausente_no_dca"
        return float(val), None

    raise SiconfiExtractionError(
        "SICONFI spec must provide either 'cod_conta' or "
        "('numerator_cod_conta', 'denominator_cod_conta')."
    )


def fetch_siconfi_dca_municipality(
    client: CachedHttpClient,
    *,
    year: int,
    anexo: str,
    cd_ibge: int,
    cache_dir: Path | None = None,
    resume: bool = True,
    base_url: str = SICONFI_DCA_BASE_URL,
) -> tuple[list[dict[str, Any]], str]:
    """Fetches or loads from disk cache a municipality's SICONFI DCA annex items.

    Args:
        client: Cached HTTP client.
        year: Fiscal exercise year (`an_exercicio`).
        anexo: Annex name (`'DCA-Anexo I-C'` or `'DCA-Anexo I-E'`).
        cd_ibge: Canonical 7-digit IBGE municipality code (`id_ente`).
        cache_dir: Optional directory for per-municipality checkpoint files.
        resume: Whether to reuse existing checkpoint files on disk.
        base_url: SICONFI DCA API base URL.

    Returns:
        Tuple `(items_list, sha256_hex)`.
    """
    safe_anexo = anexo.replace(" ", "_").replace("/", "_")
    if cache_dir is not None:
        cp_path = cache_dir / str(int(year)) / safe_anexo / f"{int(cd_ibge)}.json"
        if resume and cp_path.exists():
            raw_bytes = cp_path.read_bytes()
            sha = hashlib.sha256(raw_bytes).hexdigest()
            data = json.loads(raw_bytes.decode("utf-8"))
            items = data.get("items", []) if isinstance(data, dict) else data
            return (
                [x for x in items if isinstance(x, dict)]
                if isinstance(items, list)
                else []
            ), sha

    encoded_anexo = quote(anexo, safe="")
    url = (
        f"{base_url.rstrip('/')}?an_exercicio={int(year)}"
        f"&no_anexo={encoded_anexo}&id_ente={int(cd_ibge)}"
    )
    payload, sha = client.get_json(url)
    items_raw = payload.get("items", []) if isinstance(payload, dict) else []
    items_clean = (
        [x for x in items_raw if isinstance(x, dict)]
        if isinstance(items_raw, list)
        else []
    )

    if cache_dir is not None:
        cp_path = cache_dir / str(int(year)) / safe_anexo / f"{int(cd_ibge)}.json"
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        cp_path.write_bytes(
            json.dumps({"items": items_clean}, ensure_ascii=False).encode("utf-8")
        )

    return items_clean, sha


def fetch_siconfi_indicator(
    client: CachedHttpClient,
    spec: IndicatorSpec,
    *,
    master_ibge_codes: Iterable[int],
    ref_year: int = DEFAULT_SICONFI_YEAR,
    cache_dir: Path | None = None,
    resume: bool = True,
    base_url: str = SICONFI_DCA_BASE_URL,
) -> tuple[pd.DataFrame, str, str]:
    """Fetches a SICONFI DCA indicator across all canonical municipalities.

    Args:
        client: Cached HTTP client.
        spec: Indicator specification with `adapter == 'siconfi'`.
        master_ibge_codes: Canonical 7-digit IBGE municipality codes.
        ref_year: Fiscal exercise year (`an_exercicio`, defaults to 2024).
        cache_dir: Optional directory for per-municipality checkpoint files.
        resume: Whether to reuse existing checkpoint files on disk.
        base_url: SICONFI DCA API base URL.

    Returns:
        Tuple `(raw_df, template_url, combined_sha256)`.

    Raises:
        SiconfiExtractionError: If required `source.params` are missing.
    """
    params = spec.source_params
    anexo = str(params.get("anexo", "")).strip()
    coluna = str(params.get("coluna", "")).strip()
    if not anexo or not coluna:
        raise SiconfiExtractionError(
            f"SICONFI indicator {spec.code!r} requires 'anexo' and 'coluna' params."
        )

    cod_conta = params.get("cod_conta")
    conta_prefix = params.get("conta_prefix")
    num_cod = params.get("numerator_cod_conta")
    denom_cod = params.get("denominator_cod_conta")

    hasher = hashlib.sha256()
    rows: list[dict[str, Any]] = []

    for cd_ibge in sorted({int(c) for c in master_ibge_codes}):
        items, sha = fetch_siconfi_dca_municipality(
            client,
            year=ref_year,
            anexo=anexo,
            cd_ibge=cd_ibge,
            cache_dir=cache_dir,
            resume=resume,
            base_url=base_url,
        )
        hasher.update(sha.encode("ascii"))
        val, reason = parse_siconfi_municipality_items(
            items,
            coluna=coluna,
            cod_conta=str(cod_conta) if cod_conta else None,
            conta_prefix=str(conta_prefix) if conta_prefix else None,
            numerator_cod_conta=str(num_cod) if num_cod else None,
            denominator_cod_conta=str(denom_cod) if denom_cod else None,
        )
        rows.append(
            {
                "cd_ibge": cd_ibge,
                "ref_year": int(ref_year),
                "value": np.nan if val is None else float(val),
                "missing_reason": reason,
            }
        )

    template_url = (
        f"{base_url.rstrip('/')}?an_exercicio={int(ref_year)}"
        f"&no_anexo={quote(anexo, safe='')}&id_ente={{cd_ibge}}"
    )
    return (
        pd.DataFrame(rows, columns=["cd_ibge", "ref_year", "value", "missing_reason"]),
        template_url,
        hasher.hexdigest(),
    )
