"""SQLAlchemy Core Table definitions matching docs/06-modelo-de-dados.md."""

import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData()

municipality = sa.Table(
    "municipality",
    metadata,
    sa.Column("cd_ibge", sa.Integer, primary_key=True),
    sa.Column(
        "cd_ibge6",
        sa.Integer,
        sa.Computed("cd_ibge / 10", persisted=True),
    ),
    sa.Column("cd_tse", sa.Integer, unique=True, nullable=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("uf", sa.CHAR(2), nullable=False),
    sa.Column("uf_code", sa.SmallInteger, nullable=False),
    sa.Column("region", sa.Text, nullable=False),
    sa.Column(
        "is_capital", sa.Boolean, nullable=False, server_default=sa.text("false")
    ),
    sa.Column("area_km2", sa.Double, nullable=True),
    sa.Column("label_point", Geometry("POINT", srid=4326), nullable=True),
    sa.Column("bbox", Geometry("POLYGON", srid=4326), nullable=True),
)

municipality_geom = sa.Table(
    "municipality_geom",
    metadata,
    sa.Column(
        "cd_ibge",
        sa.Integer,
        sa.ForeignKey("municipality.cd_ibge", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("lod", sa.SmallInteger, primary_key=True),
    sa.Column("geom", Geometry("MULTIPOLYGON", srid=3857), nullable=False),
)

uf_geom = sa.Table(
    "uf_geom",
    metadata,
    sa.Column("uf", sa.CHAR(2), primary_key=True),
    sa.Column("lod", sa.SmallInteger, primary_key=True),
    sa.Column("geom", Geometry("MULTIPOLYGON", srid=3857), nullable=False),
)

election = sa.Table(
    "election",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("year", sa.SmallInteger, nullable=False),
    sa.Column("round", sa.SmallInteger, nullable=False),
    sa.Column("office", sa.Text, nullable=False),
    sa.Column("system", sa.Text, nullable=False),
    sa.Column("scope", sa.Text, nullable=False),
    sa.Column("votes_per_voter", sa.SmallInteger, nullable=False, server_default="1"),
    sa.Column("election_date", sa.Date, nullable=False),
    sa.Column("tse_cd_eleicao", sa.Integer, nullable=False),
    sa.Column("tse_cd_cargo", sa.SmallInteger, nullable=False),
    sa.UniqueConstraint(
        "year", "round", "office", name="uq_election_year_round_office"
    ),
)

party = sa.Table(
    "party",
    metadata,
    sa.Column("party_code", sa.Text, primary_key=True),
    sa.Column("number", sa.SmallInteger, nullable=True),
    sa.Column("name", sa.Text, nullable=False),
)

party_ideology = sa.Table(
    "party_ideology",
    metadata,
    sa.Column(
        "party_code",
        sa.Text,
        sa.ForeignKey("party.party_code"),
        primary_key=True,
    ),
    sa.Column("valid_from", sa.SmallInteger, primary_key=True),
    sa.Column("valid_to", sa.SmallInteger, nullable=True),
    sa.Column("score", sa.Numeric(4, 2), nullable=False),
    sa.Column("bloc", sa.Text, nullable=False),
    sa.Column("method", sa.Text, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("note", sa.Text, nullable=True),
)

candidate = sa.Table(
    "candidate",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("election_id", sa.Integer, sa.ForeignKey("election.id"), nullable=False),
    sa.Column("uf", sa.CHAR(2), nullable=True),
    sa.Column("sq_candidato", sa.BigInteger, nullable=False),
    sa.Column("number", sa.Integer, nullable=False),
    sa.Column("ballot_name", sa.Text, nullable=False),
    sa.Column("party_code", sa.Text, sa.ForeignKey("party.party_code"), nullable=False),
    sa.Column("federation", sa.Text, nullable=True),
    sa.Column("coalition", sa.Text, nullable=True),
    sa.Column("result_status", sa.Text, nullable=True),
    sa.UniqueConstraint("election_id", "sq_candidato", name="uq_candidate_election_sq"),
)

turnout = sa.Table(
    "turnout",
    metadata,
    sa.Column(
        "election_id", sa.Integer, sa.ForeignKey("election.id"), primary_key=True
    ),
    sa.Column(
        "cd_ibge",
        sa.Integer,
        sa.ForeignKey("municipality.cd_ibge"),
        primary_key=True,
    ),
    sa.Column("eligible", sa.Integer, nullable=False),
    sa.Column("attendance", sa.Integer, nullable=False),
    sa.Column("abstentions", sa.Integer, nullable=False),
    sa.Column("valid", sa.Integer, nullable=False),
    sa.Column("blank", sa.Integer, nullable=False),
    sa.Column("null_votes", sa.Integer, nullable=False),
    sa.Column("annulled", sa.Integer, nullable=False, server_default="0"),
)

party_vote = sa.Table(
    "party_vote",
    metadata,
    sa.Column(
        "election_id", sa.Integer, sa.ForeignKey("election.id"), primary_key=True
    ),
    sa.Column(
        "cd_ibge",
        sa.Integer,
        sa.ForeignKey("municipality.cd_ibge"),
        primary_key=True,
    ),
    sa.Column(
        "party_code",
        sa.Text,
        sa.ForeignKey("party.party_code"),
        primary_key=True,
    ),
    sa.Column("nominal_votes", sa.Integer, nullable=False),
    sa.Column("legend_votes", sa.Integer, nullable=False),
    sa.Column(
        "total_votes",
        sa.Integer,
        sa.Computed("nominal_votes + legend_votes", persisted=True),
    ),
)

candidate_vote = sa.Table(
    "candidate_vote",
    metadata,
    sa.Column(
        "election_id", sa.Integer, sa.ForeignKey("election.id"), primary_key=True
    ),
    sa.Column(
        "cd_ibge",
        sa.Integer,
        sa.ForeignKey("municipality.cd_ibge"),
        primary_key=True,
    ),
    sa.Column(
        "candidate_id",
        sa.Integer,
        sa.ForeignKey("candidate.id"),
        primary_key=True,
    ),
    sa.Column("votes", sa.Integer, nullable=False),
)

abroad_vote = sa.Table(
    "abroad_vote",
    metadata,
    sa.Column(
        "election_id", sa.Integer, sa.ForeignKey("election.id"), primary_key=True
    ),
    sa.Column(
        "party_code",
        sa.Text,
        sa.ForeignKey("party.party_code"),
        primary_key=True,
    ),
    sa.Column("votes", sa.Integer, nullable=False),
)

indicator = sa.Table(
    "indicator",
    metadata,
    sa.Column("code", sa.Text, primary_key=True),
    sa.Column("label", sa.Text, nullable=False),
    sa.Column("description", sa.Text, nullable=False),
    sa.Column("theme", sa.Text, nullable=False),
    sa.Column("tier", sa.SmallInteger, nullable=False),
    sa.Column("unit", sa.Text, nullable=False),
    sa.Column("value_type", sa.Text, nullable=False),
    sa.Column("higher_is", sa.Text, nullable=False),
    sa.Column("scale_hint", sa.Text, nullable=False, server_default="quantile"),
    sa.Column("source_name", sa.Text, nullable=False),
    sa.Column("source_url", sa.Text, nullable=False),
    sa.Column("license", sa.Text, nullable=True),
    sa.Column("citation", sa.Text, nullable=True),
    sa.Column("caveat", sa.Text, nullable=True),
    sa.Column("ref_year_policy", sa.Text, nullable=False, server_default="latest"),
)

indicator_value = sa.Table(
    "indicator_value",
    metadata,
    sa.Column(
        "indicator_code",
        sa.Text,
        sa.ForeignKey("indicator.code", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("ref_year", sa.SmallInteger, primary_key=True),
    sa.Column(
        "cd_ibge",
        sa.Integer,
        sa.ForeignKey("municipality.cd_ibge"),
        primary_key=True,
    ),
    sa.Column("value", sa.Double, nullable=True),
    sa.Column("value_text", sa.Text, nullable=True),
    sa.Column("missing_reason", sa.Text, nullable=True),
)

etl_run = sa.Table(
    "etl_run",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
    sa.Column("step", sa.Text, nullable=False),
    sa.Column("source", sa.Text, nullable=True),
    sa.Column("dataset", sa.Text, nullable=True),
    sa.Column("source_url", sa.Text, nullable=True),
    sa.Column("source_version", sa.Text, nullable=True),
    sa.Column("sha256", sa.Text, nullable=True),
    sa.Column("params", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("rows_in", sa.BigInteger, nullable=True),
    sa.Column("rows_out", sa.BigInteger, nullable=True),
    sa.Column("dropped", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("error", sa.Text, nullable=True),
    sa.Column(
        "started_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
)

etl_failure = sa.Table(
    "etl_failure",
    metadata,
    sa.Column("run_id", sa.BigInteger, sa.ForeignKey("etl_run.id"), primary_key=True),
    sa.Column("item_key", sa.Text, primary_key=True),
    sa.Column("error", sa.Text, nullable=False),
)

data_quality_issue = sa.Table(
    "data_quality_issue",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.BigInteger, sa.ForeignKey("etl_run.id"), nullable=False),
    sa.Column("check_name", sa.Text, nullable=False),
    sa.Column("severity", sa.Text, nullable=False),
    sa.Column("cd_ibge", sa.Integer, nullable=True),
    sa.Column("detail", JSONB, nullable=False),
)

dataset_version = sa.Table(
    "dataset_version",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("etl_run_id", sa.BigInteger, sa.ForeignKey("etl_run.id"), nullable=False),
    sa.Column(
        "published_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
)

# Read-only representations of materialized views for SQLAlchemy Core queries
mv_bloc_share = sa.Table(
    "mv_bloc_share",
    metadata,
    sa.Column("election_id", sa.Integer),
    sa.Column("cd_ibge", sa.Integer),
    sa.Column("bloc", sa.Text),
    sa.Column("votes", sa.BigInteger),
    sa.Column("valid_votes", sa.Integer),
    sa.Column("share", sa.Double),
)

mv_municipality_result = sa.Table(
    "mv_municipality_result",
    metadata,
    sa.Column("election_id", sa.Integer),
    sa.Column("cd_ibge", sa.Integer),
    sa.Column("left_share", sa.Double),
    sa.Column("center_share", sa.Double),
    sa.Column("right_share", sa.Double),
    sa.Column("lr_balance", sa.Double),
    sa.Column("leading_bloc", sa.Text),
    sa.Column("valid_votes", sa.Integer),
)

mv_indicator_current = sa.Table(
    "mv_indicator_current",
    metadata,
    sa.Column("indicator_code", sa.Text),
    sa.Column("cd_ibge", sa.Integer),
    sa.Column("ref_year", sa.SmallInteger),
    sa.Column("value", sa.Double),
    sa.Column("value_text", sa.Text),
    sa.Column("missing_reason", sa.Text),
)
