"""Unit tests for Tesouro Transparente CKAN CAPAG adapter (Source S9)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from territorio.etl.sources.ckan import (
    CkanExtractionError,
    parse_capag_xlsx,
    select_latest_xlsx_resource,
)


def test_select_latest_xlsx_resource() -> None:
    """Verifies selection of the newest `.xlsx` resource from CKAN `package_show`."""
    payload = {
        "success": True,
        "result": {
            "resources": [
                {
                    "format": "PDF",
                    "url": "https://example.org/methodology.pdf",
                    "last_modified": "2026-02-01",
                },
                {
                    "format": "XLSX",
                    "url": "https://example.org/capag_2024.xlsx",
                    "last_modified": "2024-12-01",
                },
                {
                    "format": "XLSX",
                    "url": "https://example.org/capag_2025.xlsx",
                    "last_modified": "2025-11-15",
                },
            ]
        },
    }
    assert select_latest_xlsx_resource(payload) == "https://example.org/capag_2025.xlsx"


def test_parse_capag_xlsx_handles_ordinal_and_missing_tokens(
    tmp_path: Path,
) -> None:
    """Verifies CAPAG Excel parsing with `header_row=2` and `'n.d.'`/`'n.e.'` tokens.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    xlsx_path = tmp_path / "capag.xlsx"
    raw_rows = [
        ["Título Institucional", ""],
        ["Subtítulo", ""],
        ["Código Município Completo", "CAPAG"],
        ["3550308", "A+"],
        ["3304557", "C"],
        ["2927408", "n.d."],
        ["5101837", "n.e."],
    ]
    df_sheet = pd.DataFrame(raw_rows)
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df_sheet.to_excel(
            writer, sheet_name="Prévia da CAPAG", index=False, header=False
        )

    parsed = parse_capag_xlsx(xlsx_path, ref_year=2025)
    by_cd = parsed.set_index("cd_ibge")
    assert by_cd.loc[3550308, "value_text"] == "A+"
    assert by_cd.loc[3550308, "value"] == 6.0
    assert by_cd.loc[3304557, "value_text"] == "C"
    assert by_cd.loc[3304557, "value"] == 2.0
    assert pd.isna(by_cd.loc[2927408, "value_text"])
    assert np.isnan(by_cd.loc[2927408, "value"])
    assert by_cd.loc[2927408, "missing_reason"] == "nao_disponivel_capag"
    assert by_cd.loc[5101837, "missing_reason"] == "nao_elegivel_capag"


def test_parse_capag_xlsx_rejects_unexpected_rating(tmp_path: Path) -> None:
    """Verifies that an unknown CAPAG rating string raises `CkanExtractionError`.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    xlsx_path = tmp_path / "bad_capag.xlsx"
    df_sheet = pd.DataFrame(
        {
            "Código Município Completo": ["3550308"],
            "CAPAG": ["Z-"],
        }
    )
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df_sheet.to_excel(writer, sheet_name="Prévia da CAPAG", index=False)

    with pytest.raises(CkanExtractionError, match="Unexpected CAPAG rating"):
        parse_capag_xlsx(xlsx_path, header_row=0)
