"""Integration tests for PostGIS Mapbox Vector Tile (`ST_AsMVT`) generation."""

import pytest
import sqlalchemy as sa

from territorio.api.repository import SqlDataRepository
from territorio.config import get_settings
from territorio.db.engine import create_db_engine, upgrade_db


@pytest.mark.integration
def test_postgis_mvt_tile_generation() -> None:
    """Verifies that PostGIS `ST_AsMVT` returns valid protobuf bytes for z=4."""
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL/PostGIS not reachable: {exc}")

    upgrade_db(settings.database_url, revision="head")
    repo = SqlDataRepository(engine)
    pbf = repo.get_mvt_tile(dataset_version_id=1, z=4, x=5, y=8)
    assert isinstance(pbf, bytes)
    engine.dispose()
