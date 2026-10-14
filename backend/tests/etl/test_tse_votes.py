"""Unit tests for TSE 2026 CSV streaming, vote aggregation, and E1-E5 checks."""

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from territorio.etl.reference import UnclassifiedPartyError
from territorio.etl.sources.tse import (
    extract_tse_source_version,
    parse_electorate_profile_indicator,
    read_tse_csv,
)
from territorio.etl.transform.votes import (
    ElectionIntegrityError,
    aggregate_candidate_vote_chunks,
    aggregate_party_vote_chunks,
    aggregate_turnout_chunks,
    verify_election_integrity,
)


def _write_tse_zip(zip_path: Path, member_name: str, csv_text: str) -> None:
    """Creates a Latin-1 encoded TSE zip archive for testing.

    Args:
        zip_path: Output zip file path.
        member_name: Internal CSV filename.
        csv_text: CSV text content to encode as latin-1.
    """
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member_name, csv_text.encode("latin-1"))


def test_read_tse_csv_rejects_non_brasil_member(tmp_path: Path) -> None:
    """Verifies that `read_tse_csv` refuses per-UF files to prevent double counting.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    zpath = tmp_path / "votacao.zip"
    _write_tse_zip(zpath, "votacao_2026_SP.csv", "CD_MUNICIPIO;QT_VOTOS\n71072;10\n")

    with pytest.raises(ValueError, match=r"\*_BRASIL\.csv"):
        list(read_tse_csv(zpath, member="votacao_2026_SP.csv"))


def test_read_tse_csv_and_extract_version(tmp_path: Path) -> None:
    """Verifies Latin-1 streaming and DT_GERACAO/HH_GERACAO extraction.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    zpath = tmp_path / "detalhe_2026.zip"
    csv_body = (
        '"DT_GERACAO";"HH_GERACAO";"NR_TURNO";"CD_CARGO";"SG_UF";'
        '"CD_MUNICIPIO";"NM_MUNICIPIO";"QT_APTOS"\n'
        '"09/10/2026";"19:32:10";"1";"1";"SP";"71072";"SÃO PAULO";"1000"\n'
    )
    _write_tse_zip(zpath, "detalhe_votacao_munzona_2026_BRASIL.csv", csv_body)

    version = extract_tse_source_version(zpath)
    assert version == "09/10/2026 19:32:10"

    chunks = list(
        read_tse_csv(
            zpath,
            usecols=["NR_TURNO", "CD_CARGO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO"],
            chunksize=10,
        )
    )
    assert len(chunks) == 1
    assert chunks[0].iloc[0]["NM_MUNICIPIO"] == "SÃO PAULO"


def test_aggregate_and_verify_elections_e1_to_e5() -> None:
    """Verifies zone-to-municipality aggregation, ZZ separation, and E1-E5 checks."""
    xw = pd.DataFrame(
        {
            "cd_tse": [71072, 73709],
            "cd_ibge": [3550308, 5101837],
            "uf": ["SP", "MT"],
        }
    )

    detalhe_chunk = pd.DataFrame(
        {
            "NR_TURNO": ["1", "1", "1"],
            "CD_CARGO": ["1", "1", "1"],
            "SG_UF": ["SP", "SP", "ZZ"],
            "CD_MUNICIPIO": ["071072", "071072", "99999"],
            "NM_MUNICIPIO": ["SÃO PAULO", "SÃO PAULO", "EXTERIOR"],
            "QT_APTOS": ["1000", "500", "200"],
            "QT_COMPARECIMENTO": ["800", "400", "150"],
            "QT_ABSTENCOES": ["200", "100", "50"],
            "QT_TOTAL_VOTOS_VALIDOS": ["750", "350", "140"],
            "QT_VOTOS_BRANCOS": ["30", "30", "5"],
            "QT_TOTAL_VOTOS_NULOS": ["20", "20", "5"],
            "QT_TOTAL_VOTOS_ANULADOS": ["0", "0", "0"],
        }
    )
    turnout_mun, tse_obs = aggregate_turnout_chunks([detalhe_chunk], xw)
    assert len(turnout_mun) == 1
    assert int(turnout_mun.iloc[0]["cd_ibge"]) == 3550308
    assert int(turnout_mun.iloc[0]["valid"]) == 1100
    assert len(tse_obs) == 1

    partido_chunk = pd.DataFrame(
        {
            "NR_TURNO": ["1", "1", "1"],
            "CD_CARGO": ["1", "1", "1"],
            "SG_UF": ["SP", "SP", "ZZ"],
            "CD_MUNICIPIO": ["71072", "71072", "99999"],
            "SG_PARTIDO": ["PT", "UNIÃO", "PT"],
            "QT_VOTOS_NOMINAIS_VALIDOS": ["600", "500", "140"],
            "QT_TOTAL_VOTOS_LEG_VALIDOS": ["0", "0", "0"],
        }
    )
    party_mun, abroad_df = aggregate_party_vote_chunks(
        [partido_chunk], xw, aliases={"UNIAO": "UNIAO"}
    )
    assert len(party_mun) == 2
    assert set(party_mun["party_code"]) == {"PT", "UNIAO"}
    assert len(abroad_df) == 1
    assert int(abroad_df.iloc[0]["votes"]) == 140

    cand_chunk = pd.DataFrame(
        {
            "NR_TURNO": ["1", "1"],
            "CD_CARGO": ["1", "1"],
            "SG_UF": ["SP", "SP"],
            "CD_MUNICIPIO": ["71072", "71072"],
            "SQ_CANDIDATO": ["1001", "1002"],
            "NR_CANDIDATO": ["13", "44"],
            "NM_URNA_CANDIDATO": ["CAND ESQ", "CAND DIR"],
            "SG_PARTIDO": ["PT", "UNIÃO"],
            "SG_FEDERACAO": ["FE BRASIL", "#NULO#"],
            "NM_COLIGACAO": ["COLIG A", "COLIG B"],
            "DS_SIT_TOT_TURNO": ["2º TURNO", "2º TURNO"],
            "QT_VOTOS_NOMINAIS_VALIDOS": ["600", "500"],
        }
    )
    candidates_df, cand_votes_df = aggregate_candidate_vote_chunks(
        [cand_chunk], xw, aliases={"UNIAO": "UNIAO"}
    )
    assert len(candidates_df) == 2
    assert len(cand_votes_df) == 2

    # Should pass E1, E2, E4, E5 when expected counts check is disabled for mini-fixture
    verify_election_integrity(
        turnout_df=turnout_mun,
        party_vote_df=party_mun,
        candidate_vote_df=cand_votes_df,
        active_parties={"PT", "UNIAO"},
        check_expected_mun_counts=False,
    )

    # E4: Unclassified party must raise UnclassifiedPartyError
    with pytest.raises(UnclassifiedPartyError, match="UNIAO"):
        verify_election_integrity(
            turnout_df=turnout_mun,
            party_vote_df=party_mun,
            candidate_vote_df=cand_votes_df,
            active_parties={"PT"},
            check_expected_mun_counts=False,
        )

    # E1: Perturb party votes so sum != turnout.valid
    bad_party = party_mun.copy()
    bad_party.loc[0, "nominal_votes"] = 599
    with pytest.raises(ElectionIntegrityError, match="E1"):
        verify_election_integrity(
            turnout_df=turnout_mun,
            party_vote_df=bad_party,
            candidate_vote_df=cand_votes_df,
            active_parties={"PT", "UNIAO"},
            check_expected_mun_counts=False,
        )


def test_parse_electorate_profile_indicator(tmp_path: Path) -> None:
    """Verifies S15 electorate profile indicator computation.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    zpath = tmp_path / "perfil_eleitorado_2026.zip"
    csv_body = (
        "SG_UF;CD_MUNICIPIO;CD_GRAU_ESCOLARIDADE;CD_FAIXA_ETARIA;QT_ELEITORES\n"
        "SP;71072;8;3034;250\n"
        "SP;71072;6;6064;750\n"
        "ZZ;99990;8;3034;100\n"
    )
    _write_tse_zip(zpath, "perfil_eleitorado_2026_BRASIL.csv", csv_body)
    xw = pd.DataFrame({"cd_tse": [71072], "cd_ibge": [3550308], "uf": ["SP"]})

    df = parse_electorate_profile_indicator(
        zpath,
        xw,
        filter_column="CD_GRAU_ESCOLARIDADE",
        filter_values=[8],
        ref_year=2026,
    )
    assert len(df) == 1
    assert int(df.iloc[0]["cd_ibge"]) == 3550308
    assert abs(float(df.iloc[0]["value"]) - 25.0) < 1e-6
