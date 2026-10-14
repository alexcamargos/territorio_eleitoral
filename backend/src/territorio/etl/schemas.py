"""Pandera schemas for boundary validation of ETL DataFrames."""

import pandas as pd
import pandera.pandas as pa

IBGE_MIN = 1100000
IBGE_MAX = 5399999

MunicipalitySchema = pa.DataFrameSchema(
    columns={
        "cd_ibge": pa.Column(
            int,
            checks=pa.Check.in_range(IBGE_MIN, IBGE_MAX),
            unique=True,
            coerce=True,
        ),
        "name": pa.Column(str, checks=pa.Check.str_length(min_value=1)),
        "uf": pa.Column(str, checks=pa.Check.str_length(min_value=2, max_value=2)),
        "uf_code": pa.Column(int, checks=pa.Check.in_range(11, 53), coerce=True),
        "region": pa.Column(str),
        "is_capital": pa.Column(bool, coerce=True),
    },
    strict=False,
)

TurnoutSchema = pa.DataFrameSchema(
    columns={
        "cd_ibge": pa.Column(
            int,
            checks=pa.Check.in_range(IBGE_MIN, IBGE_MAX),
            coerce=True,
        ),
        "eligible": pa.Column(int, checks=pa.Check.ge(0), coerce=True),
        "attendance": pa.Column(int, checks=pa.Check.ge(0), coerce=True),
        "abstentions": pa.Column(int, checks=pa.Check.ge(0), coerce=True),
        "valid": pa.Column(int, checks=pa.Check.ge(0), coerce=True),
        "blank": pa.Column(int, checks=pa.Check.ge(0), coerce=True),
        "null_votes": pa.Column(int, checks=pa.Check.ge(0), coerce=True),
        "annulled": pa.Column(int, checks=pa.Check.ge(0), coerce=True),
    },
    checks=[
        pa.Check(
            lambda df: (
                (df["valid"] <= df["attendance"]) & (df["attendance"] <= df["eligible"])
            ),
            error="Turnout invariant violated: valid <= attendance <= eligible",
        )
    ],
    strict=False,
)

PartyVoteSchema = pa.DataFrameSchema(
    columns={
        "cd_ibge": pa.Column(
            int,
            checks=pa.Check.in_range(IBGE_MIN, IBGE_MAX),
            coerce=True,
        ),
        "party_code": pa.Column(str, checks=pa.Check.str_length(min_value=1)),
        "nominal_votes": pa.Column(int, checks=pa.Check.ge(0), coerce=True),
        "legend_votes": pa.Column(int, checks=pa.Check.ge(0), coerce=True),
    },
    strict=False,
)

CandidateVoteSchema = pa.DataFrameSchema(
    columns={
        "cd_ibge": pa.Column(
            int,
            checks=pa.Check.in_range(IBGE_MIN, IBGE_MAX),
            coerce=True,
        ),
        "sq_candidato": pa.Column(int, coerce=True),
        "votes": pa.Column(int, checks=pa.Check.ge(0), coerce=True),
    },
    strict=False,
)

IndicatorValueSchema = pa.DataFrameSchema(
    columns={
        "cd_ibge": pa.Column(
            int,
            checks=pa.Check.in_range(IBGE_MIN, IBGE_MAX),
            coerce=True,
        ),
        "ref_year": pa.Column(
            int,
            checks=pa.Check.in_range(2000, 2035),
            coerce=True,
        ),
        "value": pa.Column(float, nullable=True, coerce=True),
        "value_text": pa.Column(str, nullable=True),
        "missing_reason": pa.Column(str, nullable=True),
    },
    checks=[
        pa.Check(
            lambda df: (
                df["value"].notna()
                | df["value_text"].notna()
                | df["missing_reason"].notna()
            ),
            error=(
                "Every indicator row must have `value`, `value_text`, "
                "or an explicit `missing_reason`."
            ),
        )
    ],
    strict=False,
)


def validate_dataframe(
    df: pd.DataFrame,
    schema: pa.DataFrameSchema,
) -> pd.DataFrame:
    """Validates a pandas DataFrame against a Pandera schema.

    Args:
        df: Input DataFrame to validate.
        schema: Target Pandera DataFrameSchema.

    Returns:
        Validated (and type-coerced) DataFrame.

    Raises:
        pa.errors.SchemaError: If any column or row check fails.
    """
    return schema.validate(df, lazy=True)
