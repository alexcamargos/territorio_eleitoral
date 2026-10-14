"""Unit tests for manual file adapter (Sources S10-S13)."""

from pathlib import Path

import pandas as pd
import pytest

from territorio.domain import HigherIs, ScaleHint, Theme, ValueType
from territorio.etl.provenance import compute_file_sha256
from territorio.etl.reference import IndicatorSpec
from territorio.etl.sources.manual_file import (
    ManualFileExtractionError,
    UnverifiedIndicatorError,
    load_manual_file_indicator,
)


def _manual_spec(
    path: str,
    *,
    verified: bool = False,
    sha256: str | None = None,
) -> IndicatorSpec:
    """Helper to build a `manual_file` `IndicatorSpec` for testing.

    Args:
        path: Relative or absolute file path.
        verified: Whether the indicator is marked verified.
        sha256: Expected SHA-256 hex digest.

    Returns:
        Configured `IndicatorSpec`.
    """
    return IndicatorSpec(
        code="ifdm",
        label="IFDM Geral",
        description="IFDM",
        theme=Theme.COMPOSITE,
        tier=2,
        unit="índice 0-1",
        value_type=ValueType.CONTINUOUS,
        higher_is=HigherIs.BETTER,
        scale_hint=ScaleHint.LINEAR,
        valid_range=(0.0, 1.0),
        adapter="manual_file",
        source_params={
            "path": path,
            "sha256": sha256,
            "ibge_column": "cd_ibge",
            "value_column": "ifdm",
        },
        source_name="Firjan",
        source_url="https://www.firjan.com.br/ifdm/",
        license="Public",
        citation="FIRJAN",
        transform=None,
        ref_year_policy="fixed:2023",
        min_coverage=0.9,
        caveat=None,
        verified=verified,
    )


def test_manual_file_guard_and_sha256_verification(tmp_path: Path) -> None:
    """Verifies `--allow-unverified` guard, SHA-256 checking, and 6/7-digit parsing.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    xlsx_path = tmp_path / "ifdm.xlsx"
    df_in = pd.DataFrame(
        {
            "cd_ibge": [3550308, 330455],  # Mix of 7-digit and 6-digit codes
            "ifdm": [0.85, "0,78"],
        }
    )
    df_in.to_excel(xlsx_path, index=False)
    actual_sha = compute_file_sha256(xlsx_path)

    unverified_spec = _manual_spec(str(xlsx_path), verified=False, sha256=None)
    with pytest.raises(UnverifiedIndicatorError, match="--allow-unverified"):
        load_manual_file_indicator(
            unverified_spec,
            master_ibge_codes=[3550308, 3304557],
            allow_unverified=False,
        )

    df_out, _, sha_out = load_manual_file_indicator(
        unverified_spec,
        master_ibge_codes=[3550308, 3304557],
        allow_unverified=True,
    )
    assert sha_out == actual_sha
    by_cd = df_out.set_index("cd_ibge")
    assert by_cd.loc[3550308, "value"] == pytest.approx(0.85)
    assert by_cd.loc[3304557, "value"] == pytest.approx(0.78)

    mismatch_spec = _manual_spec(str(xlsx_path), verified=True, sha256="0" * 64)
    with pytest.raises(ManualFileExtractionError, match="SHA-256 mismatch"):
        load_manual_file_indicator(
            mismatch_spec,
            master_ibge_codes=[3550308, 3304557],
            allow_unverified=False,
        )
