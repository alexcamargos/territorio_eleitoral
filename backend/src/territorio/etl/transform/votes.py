"""Electoral vote aggregation (map-reduce over chunks) and E1-E5 integrity checks."""

from collections.abc import Iterable

import pandas as pd

from territorio.etl.crosswalk import map_tse_to_ibge
from territorio.etl.reference import UnclassifiedPartyError, normalize_party_code


class ElectionIntegrityError(ValueError):
    """Raised when TSE electoral aggregation fails any of the E1-E5 integrity rules."""


TURNOUT_SUM_COLS = [
    "eligible",
    "attendance",
    "abstentions",
    "valid",
    "blank",
    "null_votes",
    "annulled",
]

EXPECTED_MUN_COUNT_BY_CARGO: dict[int, int] = {
    1: 5571,  # President
    3: 5571,  # Governor
    5: 5571,  # Senator
    6: 5571,  # Federal Deputy
    7: 5570,  # State Deputy (all except DF)
    8: 1,  # District Deputy (Brasília/DF)
}


def aggregate_turnout_chunks(
    chunks: Iterable[pd.DataFrame],
    crosswalk_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregates `detalhe_votacao_munzona` chunks to municipality level.

    Args:
        chunks: Iterable of string-typed DataFrames from `detalhe_votacao_munzona`.
        crosswalk_df: Validated TSE-to-IBGE crosswalk DataFrame.

    Returns:
        Tuple `(turnout_mun_df, tse_observed_df)` where `turnout_mun_df` is keyed by
        `(round, tse_cd_cargo, cd_ibge)` and `tse_observed_df` lists distinct
        `(cd_tse, uf, name_tse)` seen in the file (excluding ZZ).
    """
    mun_partials: list[pd.DataFrame] = []
    obs_partials: list[pd.DataFrame] = []

    for chunk in chunks:
        uf_upper = chunk["SG_UF"].astype(str).str.strip().str.upper()
        br = chunk.loc[uf_upper != "ZZ"].copy()
        if br.empty:
            continue

        br["cd_tse"] = br["CD_MUNICIPIO"].astype(str).str.strip().astype(int)
        br["uf"] = br["SG_UF"].astype(str).str.strip().str.upper()
        br["name_tse"] = br["NM_MUNICIPIO"].astype(str).str.strip()
        obs_partials.append(
            br[["cd_tse", "uf", "name_tse"]].drop_duplicates(subset=["cd_tse"])
        )

        br["round"] = pd.to_numeric(br["NR_TURNO"], errors="raise").astype(int)
        br["tse_cd_cargo"] = pd.to_numeric(br["CD_CARGO"], errors="raise").astype(int)
        br["eligible"] = pd.to_numeric(br["QT_APTOS"], errors="raise").astype(int)
        br["attendance"] = pd.to_numeric(
            br["QT_COMPARECIMENTO"], errors="raise"
        ).astype(int)
        br["abstentions"] = pd.to_numeric(br["QT_ABSTENCOES"], errors="raise").astype(
            int
        )
        br["valid"] = pd.to_numeric(
            br["QT_TOTAL_VOTOS_VALIDOS"], errors="raise"
        ).astype(int)
        br["blank"] = pd.to_numeric(br["QT_VOTOS_BRANCOS"], errors="raise").astype(int)
        br["null_votes"] = pd.to_numeric(
            br["QT_TOTAL_VOTOS_NULOS"], errors="raise"
        ).astype(int)
        annulled_col = (
            br["QT_TOTAL_VOTOS_ANULADOS"]
            if "QT_TOTAL_VOTOS_ANULADOS" in br.columns
            else 0
        )
        br["annulled"] = pd.to_numeric(annulled_col, errors="raise").astype(int)

        grouped = br.groupby(["round", "tse_cd_cargo", "cd_tse"], as_index=False)[
            TURNOUT_SUM_COLS
        ].sum()
        mun_partials.append(grouped)

    tse_observed = (
        pd.concat(obs_partials, ignore_index=True).drop_duplicates(subset=["cd_tse"])
        if obs_partials
        else pd.DataFrame(columns=["cd_tse", "uf", "name_tse"])
    )
    combined = (
        pd.concat(mun_partials, ignore_index=True)
        .groupby(["round", "tse_cd_cargo", "cd_tse"], as_index=False)[TURNOUT_SUM_COLS]
        .sum()
    )
    mapped = map_tse_to_ibge(combined, crosswalk_df)
    return (
        mapped.sort_values(["round", "tse_cd_cargo", "cd_ibge"]).reset_index(drop=True),
        tse_observed.sort_values("cd_tse").reset_index(drop=True),
    )


def aggregate_party_vote_chunks(
    chunks: Iterable[pd.DataFrame],
    crosswalk_df: pd.DataFrame,
    aliases: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregates `votacao_partido_munzona` chunks into municipal and abroad DataFrames.

    Args:
        chunks: Iterable of string-typed DataFrames from `votacao_partido_munzona`.
        crosswalk_df: Validated TSE-to-IBGE crosswalk DataFrame.
        aliases: Optional party code alias map from `party_ideology.yaml`.

    Returns:
        Tuple `(party_mun_df, abroad_df)` where `party_mun_df` contains
        `(round, tse_cd_cargo, cd_ibge, party_code, nominal_votes, legend_votes)`
        and `abroad_df` contains `(round, tse_cd_cargo, party_code, votes)` for ZZ.
    """
    mun_partials: list[pd.DataFrame] = []
    zz_partials: list[pd.DataFrame] = []

    for chunk in chunks:
        df = chunk.copy()
        df["round"] = pd.to_numeric(df["NR_TURNO"], errors="raise").astype(int)
        df["tse_cd_cargo"] = pd.to_numeric(df["CD_CARGO"], errors="raise").astype(int)
        df["nominal_votes"] = pd.to_numeric(
            df["QT_VOTOS_NOMINAIS_VALIDOS"], errors="raise"
        ).astype(int)
        df["legend_votes"] = pd.to_numeric(
            df["QT_TOTAL_VOTOS_LEG_VALIDOS"], errors="raise"
        ).astype(int)
        df["party_code"] = [
            normalize_party_code(sg, aliases) for sg in df["SG_PARTIDO"]
        ]
        uf_upper = df["SG_UF"].astype(str).str.strip().str.upper()

        zz = df.loc[uf_upper == "ZZ"].copy()
        if not zz.empty:
            zz["votes"] = zz["nominal_votes"] + zz["legend_votes"]
            zz_partials.append(
                zz.groupby(["round", "tse_cd_cargo", "party_code"], as_index=False)[
                    ["votes"]
                ].sum()
            )

        br = df.loc[uf_upper != "ZZ"].copy()
        if not br.empty:
            br["cd_tse"] = br["CD_MUNICIPIO"].astype(str).str.strip().astype(int)
            mun_partials.append(
                br.groupby(
                    ["round", "tse_cd_cargo", "cd_tse", "party_code"], as_index=False
                )[["nominal_votes", "legend_votes"]].sum()
            )

    combined_mun = (
        pd.concat(mun_partials, ignore_index=True)
        .groupby(["round", "tse_cd_cargo", "cd_tse", "party_code"], as_index=False)[
            ["nominal_votes", "legend_votes"]
        ]
        .sum()
    )
    mapped_mun = map_tse_to_ibge(combined_mun, crosswalk_df)
    mapped_mun = mapped_mun.sort_values(
        ["round", "tse_cd_cargo", "cd_ibge", "party_code"]
    ).reset_index(drop=True)

    if zz_partials:
        abroad_df = (
            pd.concat(zz_partials, ignore_index=True)
            .groupby(["round", "tse_cd_cargo", "party_code"], as_index=False)[["votes"]]
            .sum()
            .sort_values(["round", "tse_cd_cargo", "party_code"])
            .reset_index(drop=True)
        )
    else:
        abroad_df = pd.DataFrame(
            columns=["round", "tse_cd_cargo", "party_code", "votes"]
        )

    return mapped_mun, abroad_df


def aggregate_candidate_vote_chunks(
    chunks: Iterable[pd.DataFrame],
    crosswalk_df: pd.DataFrame,
    aliases: dict[str, str] | None = None,
    majoritarian_cargos: tuple[int, ...] = (1, 3, 5),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregates `votacao_candidato_munzona` chunks for majoritarian offices.

    Args:
        chunks: Iterable of string-typed DataFrames from `votacao_candidato_munzona`.
        crosswalk_df: Validated TSE-to-IBGE crosswalk DataFrame.
        aliases: Optional party code alias map from `party_ideology.yaml`.
        majoritarian_cargos: Tuple of `CD_CARGO` integers to retain
            (defaults to 1, 3, 5).

    Returns:
        Tuple `(candidates_df, candidate_votes_df)`.
    """
    cand_meta_partials: list[pd.DataFrame] = []
    vote_partials: list[pd.DataFrame] = []
    allowed_cargos = set(majoritarian_cargos)

    for chunk in chunks:
        cargo_series = pd.to_numeric(chunk["CD_CARGO"], errors="raise").astype(int)
        uf_upper = chunk["SG_UF"].astype(str).str.strip().str.upper()
        mask = cargo_series.isin(allowed_cargos) & (uf_upper != "ZZ")
        sub = chunk.loc[mask].copy()
        if sub.empty:
            continue

        sub["round"] = pd.to_numeric(sub["NR_TURNO"], errors="raise").astype(int)
        sub["tse_cd_cargo"] = pd.to_numeric(sub["CD_CARGO"], errors="raise").astype(int)
        sub["cd_tse"] = sub["CD_MUNICIPIO"].astype(str).str.strip().astype(int)
        sub["sq_candidato"] = pd.to_numeric(sub["SQ_CANDIDATO"], errors="raise").astype(
            "int64"
        )
        sub["number"] = pd.to_numeric(sub["NR_CANDIDATO"], errors="raise").astype(int)
        sub["ballot_name"] = sub["NM_URNA_CANDIDATO"].astype(str).str.strip()
        sub["party_code"] = [
            normalize_party_code(sg, aliases) for sg in sub["SG_PARTIDO"]
        ]
        sub["uf"] = sub["SG_UF"].astype(str).str.strip().str.upper()
        sub.loc[sub["tse_cd_cargo"] == 1, "uf"] = None
        sub["federation"] = (
            sub["SG_FEDERACAO"].where(sub["SG_FEDERACAO"].notna(), None)
            if "SG_FEDERACAO" in sub.columns
            else None
        )
        sub["coalition"] = (
            sub["NM_COLIGACAO"].where(sub["NM_COLIGACAO"].notna(), None)
            if "NM_COLIGACAO" in sub.columns
            else None
        )
        sub["result_status"] = (
            sub["DS_SIT_TOT_TURNO"].where(sub["DS_SIT_TOT_TURNO"].notna(), None)
            if "DS_SIT_TOT_TURNO" in sub.columns
            else None
        )
        sub["votes"] = pd.to_numeric(
            sub["QT_VOTOS_NOMINAIS_VALIDOS"], errors="raise"
        ).astype(int)

        cand_meta_partials.append(
            sub[
                [
                    "round",
                    "tse_cd_cargo",
                    "uf",
                    "sq_candidato",
                    "number",
                    "ballot_name",
                    "party_code",
                    "federation",
                    "coalition",
                    "result_status",
                ]
            ].drop_duplicates(subset=["round", "tse_cd_cargo", "sq_candidato"])
        )
        vote_partials.append(
            sub.groupby(
                ["round", "tse_cd_cargo", "cd_tse", "sq_candidato"], as_index=False
            )[["votes"]].sum()
        )

    if not vote_partials:
        return (
            pd.DataFrame(
                columns=[
                    "round",
                    "tse_cd_cargo",
                    "uf",
                    "sq_candidato",
                    "number",
                    "ballot_name",
                    "party_code",
                    "federation",
                    "coalition",
                    "result_status",
                ]
            ),
            pd.DataFrame(
                columns=["round", "tse_cd_cargo", "cd_ibge", "sq_candidato", "votes"]
            ),
        )

    candidates_df = (
        pd.concat(cand_meta_partials, ignore_index=True)
        .drop_duplicates(subset=["round", "tse_cd_cargo", "sq_candidato"])
        .sort_values(["round", "tse_cd_cargo", "sq_candidato"])
        .reset_index(drop=True)
    )
    combined_votes = (
        pd.concat(vote_partials, ignore_index=True)
        .groupby(["round", "tse_cd_cargo", "cd_tse", "sq_candidato"], as_index=False)[
            ["votes"]
        ]
        .sum()
    )
    mapped_votes = map_tse_to_ibge(combined_votes, crosswalk_df)
    return (
        candidates_df,
        mapped_votes.sort_values(
            ["round", "tse_cd_cargo", "cd_ibge", "sq_candidato"]
        ).reset_index(drop=True),
    )


def verify_election_integrity(
    *,
    turnout_df: pd.DataFrame,
    party_vote_df: pd.DataFrame,
    candidate_vote_df: pd.DataFrame,
    active_parties: set[str],
    check_expected_mun_counts: bool = True,
) -> None:
    """Enforces blocking electoral integrity rules E1 through E5.

    - E1: `sum(party_vote.total) == turnout.valid` per `(round, tse_cd_cargo, cd_ibge)`.
    - E2: For majoritarian offices,
      `sum(candidate_vote.votes) == sum(party_vote.nominal)` per
      `(round, tse_cd_cargo, cd_ibge)`.
    - E3: Municipality count per office matches `EXPECTED_MUN_COUNT_BY_CARGO`
      (in round 1).
    - E4: Every `party_code` with `total_votes > 0` exists in `active_parties`.
    - E5: Non-negative vote counts and `valid <= attendance <= eligible`.

    Args:
        turnout_df: Aggregated municipal turnout DataFrame.
        party_vote_df: Aggregated municipal party vote DataFrame.
        candidate_vote_df: Aggregated municipal candidate vote DataFrame.
        active_parties: Set of canonical `party_code` strings active in the
            election year.
        check_expected_mun_counts: Whether to enforce rule E3 (True in production).

    Raises:
        UnclassifiedPartyError: If rule E4 is violated.
        ElectionIntegrityError: If rules E1, E2, E3, or E5 are violated.
    """
    # E4: Party ideology coverage
    pv = party_vote_df.copy()
    pv["total_votes"] = pv["nominal_votes"] + pv["legend_votes"]
    voted_parties = set(pv.loc[pv["total_votes"] > 0, "party_code"].unique().tolist())
    unclassified = sorted(voted_parties - active_parties)
    if unclassified:
        raise UnclassifiedPartyError(
            f"Rule E4 failed: parties with votes missing from party_ideology.yaml: "
            f"{unclassified}"
        )

    # E5: Non-negative votes and turnout inequality (Senator cargo=5 has 2 votes/voter)
    votes_per_voter = (
        turnout_df["tse_cd_cargo"].astype(int).map(lambda c: 2 if c == 5 else 1)
    )
    if (
        (turnout_df["valid"] < 0).any()
        or (turnout_df["attendance"] < 0).any()
        or (turnout_df["eligible"] < 0).any()
        or (turnout_df["valid"] > turnout_df["attendance"] * votes_per_voter).any()
        or (turnout_df["attendance"] > turnout_df["eligible"]).any()
    ):
        raise ElectionIntegrityError(
            "Rule E5 failed: turnout violates 0 <= valid <= attendance <= eligible."
        )
    if (pv["nominal_votes"] < 0).any() or (pv["legend_votes"] < 0).any():
        raise ElectionIntegrityError("Rule E5 failed: negative party votes detected.")

    # E1: Sum of party total votes == turnout.valid
    pv_sum = pv.groupby(["round", "tse_cd_cargo", "cd_ibge"], as_index=False)[
        ["total_votes", "nominal_votes"]
    ].sum()
    e1_merged = turnout_df[["round", "tse_cd_cargo", "cd_ibge", "valid"]].merge(
        pv_sum,
        on=["round", "tse_cd_cargo", "cd_ibge"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    e1_merged["total_votes"] = e1_merged["total_votes"].fillna(0).astype(int)
    e1_diff = e1_merged.loc[e1_merged["valid"] != e1_merged["total_votes"]]
    if not e1_diff.empty:
        sample = e1_diff.head(10).to_dict(orient="records")
        raise ElectionIntegrityError(
            f"Rule E1 failed (party_vote total != turnout.valid): {sample}"
        )

    # E2: Majoritarian candidate votes == party nominal votes
    maj_pv = pv_sum.loc[pv_sum["tse_cd_cargo"].isin([1, 3, 5])].copy()
    if not maj_pv.empty and not candidate_vote_df.empty:
        cv_sum = candidate_vote_df.groupby(
            ["round", "tse_cd_cargo", "cd_ibge"], as_index=False
        )[["votes"]].sum()
        e2_merged = maj_pv.merge(
            cv_sum,
            on=["round", "tse_cd_cargo", "cd_ibge"],
            how="left",
            validate="one_to_one",
            indicator=True,
        )
        e2_merged["votes"] = e2_merged["votes"].fillna(0).astype(int)
        e2_diff = e2_merged.loc[e2_merged["nominal_votes"] != e2_merged["votes"]]
        if not e2_diff.empty:
            sample = e2_diff.head(10).to_dict(orient="records")
            raise ElectionIntegrityError(
                f"Rule E2 failed (candidate_vote != party nominal_votes): {sample}"
            )

    # E3: Expected municipality count per cargo in 1st round
    if check_expected_mun_counts:
        r1 = turnout_df.loc[turnout_df["round"] == 1]
        if not r1.empty:
            counts = r1.groupby("tse_cd_cargo")["cd_ibge"].nunique().to_dict()
            for cargo_code, actual_count in counts.items():
                expected = EXPECTED_MUN_COUNT_BY_CARGO.get(int(cargo_code))
                if expected is not None and actual_count != expected:
                    raise ElectionIntegrityError(
                        f"Rule E3 failed for cargo {cargo_code}: "
                        f"expected {expected} municipalities, got {actual_count}"
                    )
