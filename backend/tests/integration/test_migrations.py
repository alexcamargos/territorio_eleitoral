"""Integration tests for Alembic migrations and PostGIS schema objects."""

import pytest
import sqlalchemy as sa

from territorio.config import get_settings
from territorio.db.engine import create_db_engine, upgrade_db


@pytest.mark.integration
def test_migrations_create_tables_extensions_and_materialized_views() -> None:
    """Verifies that `upgrade head` creates all tables, extensions, and MVs."""
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"PostGIS database unavailable: {exc}")

    upgrade_db(settings.database_url)

    expected_tables = {
        "municipality",
        "municipality_geom",
        "uf_geom",
        "election",
        "party",
        "party_ideology",
        "candidate",
        "turnout",
        "party_vote",
        "candidate_vote",
        "abroad_vote",
        "indicator",
        "indicator_value",
        "etl_run",
        "etl_failure",
        "data_quality_issue",
        "dataset_version",
    }
    expected_mvs = {
        "mv_bloc_share",
        "mv_municipality_result",
        "mv_election_mun_bloc",
        "mv_indicator_current",
    }

    with engine.connect() as conn:
        ext_rows = (
            conn.execute(
                sa.text(
                    "SELECT extname FROM pg_extension "
                    "WHERE extname IN ('postgis', 'unaccent')"
                )
            )
            .scalars()
            .all()
        )
        assert set(ext_rows) == {"postgis", "unaccent"}

        table_rows = (
            conn.execute(
                sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            .scalars()
            .all()
        )
        assert expected_tables.issubset(set(table_rows))

        mv_rows = (
            conn.execute(
                sa.text(
                    "SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'"
                )
            )
            .scalars()
            .all()
        )
        assert expected_mvs.issubset(set(mv_rows))

        unaccent_check = conn.execute(
            sa.text("SELECT unaccent_immutable('São Paulo')")
        ).scalar_one()
        assert unaccent_check == "Sao Paulo"
    engine.dispose()
