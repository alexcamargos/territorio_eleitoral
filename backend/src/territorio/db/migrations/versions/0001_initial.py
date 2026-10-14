"""Initial schema DDL and materialized views for Território Eleitoral.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-12 10:00:00
"""

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

UPGRADE_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE SCHEMA IF NOT EXISTS staging;

CREATE OR REPLACE FUNCTION unaccent_immutable(text) RETURNS text
  LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
  AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$;

-- ===================== TERRITÓRIO =====================
CREATE TABLE IF NOT EXISTS municipality (
  cd_ibge      integer PRIMARY KEY CHECK (cd_ibge BETWEEN 1100000 AND 5399999),
  cd_ibge6     integer GENERATED ALWAYS AS (cd_ibge / 10) STORED,
  cd_tse       integer UNIQUE,
  name         text    NOT NULL,
  name_norm    text    GENERATED ALWAYS AS (lower(unaccent_immutable(name))) STORED,
  uf           char(2) NOT NULL,
  uf_code      smallint NOT NULL,
  region       text    NOT NULL,
  is_capital   boolean NOT NULL DEFAULT false,
  area_km2     double precision,
  label_point  geometry(Point, 4326),
  bbox         geometry(Polygon, 4326)
);
CREATE INDEX IF NOT EXISTS idx_municipality_uf ON municipality (uf);
CREATE INDEX IF NOT EXISTS idx_municipality_name_norm ON municipality (name_norm);
CREATE INDEX IF NOT EXISTS idx_municipality_name_gin
  ON municipality USING gin (to_tsvector('simple', unaccent_immutable(name)));

CREATE TABLE IF NOT EXISTS municipality_geom (
  cd_ibge integer  NOT NULL REFERENCES municipality ON DELETE CASCADE,
  lod     smallint NOT NULL CHECK (lod IN (0, 1, 2)),
  geom    geometry(MultiPolygon, 3857) NOT NULL,
  PRIMARY KEY (cd_ibge, lod)
);
CREATE INDEX IF NOT EXISTS idx_municipality_geom_gist
  ON municipality_geom USING gist (geom);

CREATE TABLE IF NOT EXISTS uf_geom (
  uf   char(2)  NOT NULL,
  lod  smallint NOT NULL,
  geom geometry(MultiPolygon, 3857) NOT NULL,
  PRIMARY KEY (uf, lod)
);
CREATE INDEX IF NOT EXISTS idx_uf_geom_gist ON uf_geom USING gist (geom);

-- ===================== ELEIÇÕES =====================
CREATE TABLE IF NOT EXISTS election (
  id               serial PRIMARY KEY,
  year             smallint NOT NULL,
  round            smallint NOT NULL CHECK (round IN (1, 2)),
  office           text NOT NULL CHECK (office IN
                     ('president','governor','senator','federal_deputy','state_deputy','district_deputy',
                      'mayor','councillor')),
  system           text NOT NULL CHECK (system IN ('majoritarian','proportional')),
  scope            text NOT NULL CHECK (scope IN ('national','state','municipal')),
  votes_per_voter  smallint NOT NULL DEFAULT 1,
  election_date    date NOT NULL,
  tse_cd_eleicao   integer NOT NULL,
  tse_cd_cargo     smallint NOT NULL,
  source_version   text,
  UNIQUE (year, round, office)
);

CREATE TABLE IF NOT EXISTS party (
  party_code  text PRIMARY KEY,
  number      smallint,
  name        text NOT NULL
);

CREATE TABLE IF NOT EXISTS party_ideology (
  party_code  text NOT NULL REFERENCES party,
  valid_from  smallint NOT NULL,
  valid_to    smallint,
  score       numeric(4,2) NOT NULL CHECK (score BETWEEN 0 AND 10),
  bloc        text NOT NULL CHECK (bloc IN ('left','center','right')),
  method      text NOT NULL CHECK (method IN ('survey','derived','manual')),
  source      text NOT NULL,
  note        text,
  PRIMARY KEY (party_code, valid_from)
);

CREATE TABLE IF NOT EXISTS candidate (
  id            serial PRIMARY KEY,
  election_id   integer NOT NULL REFERENCES election,
  uf            char(2),
  sq_candidato  bigint  NOT NULL,
  number        integer NOT NULL,
  ballot_name   text NOT NULL,
  party_code    text NOT NULL REFERENCES party,
  federation    text,
  coalition     text,
  result_status text,
  UNIQUE (election_id, sq_candidato)
);

CREATE TABLE IF NOT EXISTS turnout (
  election_id  integer NOT NULL REFERENCES election,
  cd_ibge      integer NOT NULL REFERENCES municipality,
  eligible     integer NOT NULL,
  attendance   integer NOT NULL,
  abstentions  integer NOT NULL,
  valid        integer NOT NULL,
  blank        integer NOT NULL,
  null_votes   integer NOT NULL,
  annulled     integer NOT NULL DEFAULT 0,
  PRIMARY KEY (election_id, cd_ibge),
  CHECK (valid <= 2 * attendance AND attendance <= eligible)
);

CREATE TABLE IF NOT EXISTS party_vote (
  election_id    integer NOT NULL REFERENCES election,
  cd_ibge        integer NOT NULL REFERENCES municipality,
  party_code     text    NOT NULL REFERENCES party,
  nominal_votes  integer NOT NULL CHECK (nominal_votes >= 0),
  legend_votes   integer NOT NULL CHECK (legend_votes >= 0),
  total_votes    integer GENERATED ALWAYS AS (nominal_votes + legend_votes) STORED,
  PRIMARY KEY (election_id, cd_ibge, party_code)
);

CREATE TABLE IF NOT EXISTS candidate_vote (
  election_id   integer NOT NULL REFERENCES election,
  cd_ibge       integer NOT NULL REFERENCES municipality,
  candidate_id  integer NOT NULL REFERENCES candidate,
  votes         integer NOT NULL CHECK (votes >= 0),
  PRIMARY KEY (election_id, cd_ibge, candidate_id)
);

CREATE TABLE IF NOT EXISTS abroad_vote (
  election_id  integer NOT NULL REFERENCES election,
  party_code   text NOT NULL REFERENCES party,
  votes        integer NOT NULL,
  PRIMARY KEY (election_id, party_code)
);

-- ===================== INDICADORES =====================
CREATE TABLE IF NOT EXISTS indicator (
  code          text PRIMARY KEY,
  label         text NOT NULL,
  description   text NOT NULL,
  theme         text NOT NULL,
  tier          smallint NOT NULL,
  unit          text NOT NULL,
  value_type    text NOT NULL
                CHECK (value_type IN ('continuous','ordinal','categorical')),
  higher_is     text NOT NULL CHECK (higher_is IN ('better','worse','neutral')),
  scale_hint    text NOT NULL DEFAULT 'quantile',
  source_name   text NOT NULL,
  source_url    text NOT NULL,
  license       text,
  citation      text,
  caveat        text,
  ref_year_policy text NOT NULL DEFAULT 'latest'
);

CREATE TABLE IF NOT EXISTS indicator_value (
  indicator_code  text     NOT NULL REFERENCES indicator ON DELETE CASCADE,
  ref_year        smallint NOT NULL,
  cd_ibge         integer  NOT NULL REFERENCES municipality,
  value           double precision,
  value_text      text,
  missing_reason  text,
  PRIMARY KEY (indicator_code, ref_year, cd_ibge),
  CHECK (value IS NOT NULL OR value_text IS NOT NULL OR missing_reason IS NOT NULL)
);

-- ===================== PROVENIÊNCIA =====================
CREATE TABLE IF NOT EXISTS etl_run (
  id              bigserial PRIMARY KEY,
  step            text NOT NULL,
  source          text,
  dataset         text,
  source_url      text,
  source_version  text,
  sha256          text,
  params          jsonb NOT NULL DEFAULT '{}',
  rows_in         bigint,
  rows_out        bigint,
  dropped         jsonb NOT NULL DEFAULT '{}',
  status          text NOT NULL CHECK (status IN ('running','success','failed')),
  error           text,
  started_at      timestamptz NOT NULL DEFAULT now(),
  finished_at     timestamptz
);

CREATE TABLE IF NOT EXISTS etl_failure (
  run_id   bigint NOT NULL REFERENCES etl_run,
  item_key text   NOT NULL,
  error    text   NOT NULL,
  PRIMARY KEY (run_id, item_key)
);

CREATE TABLE IF NOT EXISTS data_quality_issue (
  id         bigserial PRIMARY KEY,
  run_id     bigint NOT NULL REFERENCES etl_run,
  check_name text NOT NULL,
  severity   text NOT NULL CHECK (severity IN ('blocking','warning','info')),
  cd_ibge    integer,
  detail     jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset_version (
  id           serial PRIMARY KEY,
  etl_run_id   bigint REFERENCES etl_run,
  git_sha      text,
  notes        text,
  published_at timestamptz NOT NULL DEFAULT now()
);

-- ===================== VIEWS MATERIALIZADAS =====================
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_bloc_share AS
WITH pv AS (
  SELECT v.election_id, v.cd_ibge, pi.bloc, SUM(v.total_votes)::bigint AS votes
  FROM party_vote v
  JOIN election e ON e.id = v.election_id
  JOIN party_ideology pi ON pi.party_code = v.party_code
   AND e.year >= pi.valid_from AND (pi.valid_to IS NULL OR e.year <= pi.valid_to)
  GROUP BY v.election_id, v.cd_ibge, pi.bloc
),
grid AS (
  SELECT t.election_id, t.cd_ibge, b.bloc, t.valid
  FROM turnout t CROSS JOIN (VALUES ('left'),('center'),('right')) b(bloc)
)
SELECT g.election_id, g.cd_ibge, g.bloc,
       COALESCE(pv.votes, 0) AS votes,
       g.valid AS valid_votes,
       CASE
         WHEN g.valid > 0 THEN COALESCE(pv.votes, 0)::double precision / g.valid
       END AS share
FROM grid g LEFT JOIN pv USING (election_id, cd_ibge, bloc);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_bloc_share
  ON mv_bloc_share (election_id, cd_ibge, bloc);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_municipality_result AS
SELECT election_id, cd_ibge,
  MAX(share) FILTER (WHERE bloc = 'left')   AS left_share,
  MAX(share) FILTER (WHERE bloc = 'center') AS center_share,
  MAX(share) FILTER (WHERE bloc = 'right')  AS right_share,
  MAX(share) FILTER (WHERE bloc = 'right')
    - MAX(share) FILTER (WHERE bloc = 'left') AS lr_balance,
  (ARRAY_AGG(bloc ORDER BY share DESC NULLS LAST))[1] AS leading_bloc,
  MAX(valid_votes) AS valid_votes
FROM mv_bloc_share GROUP BY election_id, cd_ibge;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_municipality_result
  ON mv_municipality_result (election_id, cd_ibge);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_election_mun_bloc AS
SELECT
  e.id AS election_id,
  e.year,
  e.round,
  e.office,
  t.cd_ibge,
  m.uf,
  m.region,
  t.eligible,
  t.attendance,
  t.valid AS valid_votes,
  t.blank AS blank_votes,
  t.null_votes,
  CASE WHEN t.eligible > 0
       THEN (t.attendance::double precision / t.eligible) * 100.0
       ELSE 0.0
  END AS turnout_pct,
  CASE WHEN t.attendance > 0
       THEN ((t.blank + t.null_votes)::double precision / t.attendance) * 100.0
       ELSE 0.0
  END AS blank_null_pct,
  COALESCE(MAX(bs.votes) FILTER (WHERE bs.bloc = 'left'), 0)::bigint AS left_votes,
  COALESCE(MAX(bs.votes) FILTER (WHERE bs.bloc = 'center'), 0)::bigint AS center_votes,
  COALESCE(MAX(bs.votes) FILTER (WHERE bs.bloc = 'right'), 0)::bigint AS right_votes,
  r.left_share,
  r.center_share,
  r.right_share,
  r.lr_balance,
  r.leading_bloc
FROM turnout t
JOIN election e ON e.id = t.election_id
JOIN municipality m ON m.cd_ibge = t.cd_ibge
JOIN mv_municipality_result r
  ON r.election_id = t.election_id AND r.cd_ibge = t.cd_ibge
LEFT JOIN mv_bloc_share bs
  ON bs.election_id = t.election_id AND bs.cd_ibge = t.cd_ibge
GROUP BY
  e.id, e.year, e.round, e.office,
  t.cd_ibge, m.uf, m.region,
  t.eligible, t.attendance, t.valid, t.blank, t.null_votes,
  r.left_share, r.center_share, r.right_share, r.lr_balance, r.leading_bloc;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_election_mun_bloc
  ON mv_election_mun_bloc (election_id, cd_ibge);
CREATE INDEX IF NOT EXISTS idx_mv_election_mun_bloc_lookup
  ON mv_election_mun_bloc (year, round, office, uf);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_indicator_current AS
WITH latest AS (
  SELECT DISTINCT ON (iv.indicator_code, iv.cd_ibge)
         iv.indicator_code, iv.cd_ibge, iv.ref_year,
         iv.value, iv.value_text, iv.missing_reason
  FROM indicator_value iv
  ORDER BY iv.indicator_code, iv.cd_ibge, iv.ref_year DESC
)
SELECT
  indicator_code,
  cd_ibge,
  ref_year,
  value,
  value_text,
  missing_reason,
  CASE
    WHEN value IS NOT NULL THEN
      PERCENT_RANK() OVER (
        PARTITION BY indicator_code, (value IS NOT NULL)
        ORDER BY value ASC
      )
  END AS national_percentile
FROM latest;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_indicator_current
  ON mv_indicator_current (indicator_code, cd_ibge);
"""

DOWNGRADE_SQL = """
DROP MATERIALIZED VIEW IF EXISTS mv_indicator_current;
DROP MATERIALIZED VIEW IF EXISTS mv_election_mun_bloc;
DROP MATERIALIZED VIEW IF EXISTS mv_municipality_result;
DROP MATERIALIZED VIEW IF EXISTS mv_bloc_share;
DROP TABLE IF EXISTS dataset_version;
DROP TABLE IF EXISTS data_quality_issue;
DROP TABLE IF EXISTS etl_failure;
DROP TABLE IF EXISTS etl_run;
DROP TABLE IF EXISTS indicator_value;
DROP TABLE IF EXISTS indicator;
DROP TABLE IF EXISTS abroad_vote;
DROP TABLE IF EXISTS candidate_vote;
DROP TABLE IF EXISTS party_vote;
DROP TABLE IF EXISTS turnout;
DROP TABLE IF EXISTS candidate;
DROP TABLE IF EXISTS party_ideology;
DROP TABLE IF EXISTS party;
DROP TABLE IF EXISTS election;
DROP TABLE IF EXISTS uf_geom;
DROP TABLE IF EXISTS municipality_geom;
DROP TABLE IF EXISTS municipality;
DROP FUNCTION IF EXISTS unaccent_immutable(text);
DROP SCHEMA IF EXISTS staging CASCADE;
"""


def upgrade() -> None:
    """Applies the initial database schema and materialized views."""
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    """Drops all schema objects created in 0001_initial."""
    op.execute(DOWNGRADE_SQL)
