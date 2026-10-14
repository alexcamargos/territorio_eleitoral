"""Idempotent transactional database loaders for elections and indicators."""

import math
from typing import Any

import pandas as pd
import sqlalchemy as sa


def replace_election_contest_data(
    conn: sa.Connection,
    *,
    election_id: int,
    turnout_df: pd.DataFrame,
    party_vote_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    candidate_vote_df: pd.DataFrame,
    abroad_df: pd.DataFrame,
) -> int:
    """Atomically replaces all electoral fact rows for a single `election_id`.

    Executes `DELETE` for the target `election_id` followed by bulk `INSERT` of
    `turnout`, `party_vote`, `candidate`, `candidate_vote`, and `abroad_vote`
    within the caller's transaction.

    Args:
        conn: Active SQLAlchemy transactional Connection.
        election_id: Primary key in `election`.
        turnout_df: Filtered turnout rows for this contest.
        party_vote_df: Filtered party vote rows for this contest.
        candidates_df: Filtered candidate metadata rows for this contest.
        candidate_vote_df: Filtered candidate vote rows for this contest.
        abroad_df: Filtered abroad (ZZ) vote rows for this contest.

    Returns:
        Total number of fact rows inserted across all electoral tables.
    """
    conn.execute(
        sa.text("DELETE FROM candidate_vote WHERE election_id = :eid"),
        {"eid": election_id},
    )
    conn.execute(
        sa.text("DELETE FROM candidate WHERE election_id = :eid"),
        {"eid": election_id},
    )
    conn.execute(
        sa.text("DELETE FROM party_vote WHERE election_id = :eid"),
        {"eid": election_id},
    )
    conn.execute(
        sa.text("DELETE FROM turnout WHERE election_id = :eid"),
        {"eid": election_id},
    )
    conn.execute(
        sa.text("DELETE FROM abroad_vote WHERE election_id = :eid"),
        {"eid": election_id},
    )

    rows_written = 0

    if not turnout_df.empty:
        t_records = [
            {
                "election_id": election_id,
                "cd_ibge": int(r.cd_ibge),
                "eligible": int(r.eligible),
                "attendance": int(r.attendance),
                "abstentions": int(r.abstentions),
                "valid": int(r.valid),
                "blank": int(r.blank),
                "null_votes": int(r.null_votes),
                "annulled": int(r.annulled),
            }
            for r in turnout_df.itertuples(index=False)
        ]
        conn.execute(
            sa.text(
                """
                INSERT INTO turnout (
                    election_id, cd_ibge, eligible, attendance, abstentions,
                    valid, blank, null_votes, annulled
                )
                VALUES (
                    :election_id, :cd_ibge, :eligible, :attendance, :abstentions,
                    :valid, :blank, :null_votes, :annulled
                )
                """
            ),
            t_records,
        )
        rows_written += len(t_records)

    if not party_vote_df.empty:
        pv_records = [
            {
                "election_id": election_id,
                "cd_ibge": int(r.cd_ibge),
                "party_code": str(r.party_code),
                "nominal_votes": int(r.nominal_votes),
                "legend_votes": int(r.legend_votes),
            }
            for r in party_vote_df.itertuples(index=False)
        ]
        conn.execute(
            sa.text(
                """
                INSERT INTO party_vote (
                    election_id, cd_ibge, party_code, nominal_votes, legend_votes
                )
                VALUES (
                    :election_id, :cd_ibge, :party_code, :nominal_votes, :legend_votes
                )
                """
            ),
            pv_records,
        )
        rows_written += len(pv_records)

    if not candidates_df.empty:
        c_records = [
            {
                "election_id": election_id,
                "uf": str(r.uf) if pd.notna(r.uf) and r.uf else None,
                "sq_candidato": int(r.sq_candidato),
                "number": int(r.number),
                "ballot_name": str(r.ballot_name),
                "party_code": str(r.party_code),
                "federation": (
                    str(r.federation)
                    if pd.notna(r.federation) and r.federation
                    else None
                ),
                "coalition": (
                    str(r.coalition) if pd.notna(r.coalition) and r.coalition else None
                ),
                "result_status": (
                    str(r.result_status)
                    if pd.notna(r.result_status) and r.result_status
                    else None
                ),
            }
            for r in candidates_df.itertuples(index=False)
        ]
        conn.execute(
            sa.text(
                """
                INSERT INTO candidate (
                    election_id, uf, sq_candidato, number, ballot_name,
                    party_code, federation, coalition, result_status
                )
                VALUES (
                    :election_id, :uf, :sq_candidato, :number, :ballot_name,
                    :party_code, :federation, :coalition, :result_status
                )
                """
            ),
            c_records,
        )
        sq_to_id = dict(
            conn.execute(
                sa.text(
                    "SELECT sq_candidato, id FROM candidate WHERE election_id = :eid"
                ),
                {"eid": election_id},
            ).all()
        )
        if not candidate_vote_df.empty:
            cv_records = [
                {
                    "election_id": election_id,
                    "cd_ibge": int(r.cd_ibge),
                    "candidate_id": int(sq_to_id[int(r.sq_candidato)]),
                    "votes": int(r.votes),
                }
                for r in candidate_vote_df.itertuples(index=False)
                if int(r.sq_candidato) in sq_to_id
            ]
            if cv_records:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO candidate_vote (
                            election_id, cd_ibge, candidate_id, votes
                        )
                        VALUES (:election_id, :cd_ibge, :candidate_id, :votes)
                        """
                    ),
                    cv_records,
                )
                rows_written += len(cv_records)

    if not abroad_df.empty:
        ab_records = [
            {
                "election_id": election_id,
                "party_code": str(r.party_code),
                "votes": int(r.votes),
            }
            for r in abroad_df.itertuples(index=False)
        ]
        conn.execute(
            sa.text(
                """
                INSERT INTO abroad_vote (election_id, party_code, votes)
                VALUES (:election_id, :party_code, :votes)
                """
            ),
            ab_records,
        )
        rows_written += len(ab_records)

    return rows_written


def replace_indicator_values(
    conn: sa.Connection,
    *,
    indicator_code: str,
    values_df: pd.DataFrame,
) -> int:
    """Atomically replaces `indicator_value` rows for `(indicator_code, ref_year)`.

    Args:
        conn: Active SQLAlchemy transactional Connection.
        indicator_code: Target indicator code.
        values_df: Validated DataFrame with `cd_ibge`, `ref_year`, `value`,
            `value_text`, `missing_reason`.

    Returns:
        Number of rows written into `indicator_value`.
    """
    if values_df.empty:
        return 0

    ref_years = sorted(values_df["ref_year"].astype(int).unique().tolist())
    for ry in ref_years:
        conn.execute(
            sa.text(
                """
                DELETE FROM indicator_value
                WHERE indicator_code = :code AND ref_year = :ry
                """
            ),
            {"code": indicator_code, "ry": ry},
        )

    records: list[dict[str, Any]] = []
    for row in values_df.itertuples(index=False):
        raw_val = row.value
        val_clean: float | None = (
            None
            if raw_val is None or (isinstance(raw_val, float) and math.isnan(raw_val))
            else float(raw_val)
        )
        val_text = (
            str(row.value_text)
            if row.value_text is not None and pd.notna(row.value_text)
            else None
        )
        missing = (
            str(row.missing_reason)
            if row.missing_reason is not None and pd.notna(row.missing_reason)
            else None
        )
        records.append(
            {
                "indicator_code": indicator_code,
                "ref_year": int(row.ref_year),
                "cd_ibge": int(row.cd_ibge),
                "value": val_clean,
                "value_text": val_text,
                "missing_reason": missing,
            }
        )

    conn.execute(
        sa.text(
            """
            INSERT INTO indicator_value (
                indicator_code, ref_year, cd_ibge, value, value_text, missing_reason
            )
            VALUES (
                :indicator_code, :ref_year, :cd_ibge,
                :value, :value_text, :missing_reason
            )
            """
        ),
        records,
    )
    return len(records)


def publish_dataset_version(
    engine: sa.Engine,
    *,
    etl_run_id: int | None = None,
) -> int:
    """Refreshes materialized views and publishes a new `dataset_version` record.

    Args:
        engine: SQLAlchemy database engine.
        etl_run_id: Optional `etl_run.id` associated with the publication.

    Returns:
        Newly created `dataset_version.id`.
    """
    with engine.begin() as conn:
        conn.execute(sa.text("REFRESH MATERIALIZED VIEW mv_bloc_share"))
        conn.execute(sa.text("REFRESH MATERIALIZED VIEW mv_municipality_result"))
        conn.execute(sa.text("REFRESH MATERIALIZED VIEW mv_election_mun_bloc"))
        conn.execute(sa.text("REFRESH MATERIALIZED VIEW mv_indicator_current"))
        dv_id = int(
            conn.execute(
                sa.text(
                    """
                    INSERT INTO dataset_version (etl_run_id, git_sha, notes)
                    VALUES (:etl_run_id, 'HEAD', 'Automated ETL publication')
                    RETURNING id
                    """
                ),
                {"etl_run_id": etl_run_id},
            ).scalar_one()
        )
    return dv_id
