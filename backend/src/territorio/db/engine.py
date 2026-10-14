"""SQLAlchemy Engine factory and Alembic programmatic migration helpers."""

from functools import lru_cache
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from territorio.config import get_settings


def create_db_engine(database_url: str | None = None) -> sa.Engine:
    """Creates a SQLAlchemy Core Engine configured for PostgreSQL + psycopg v3.

    Args:
        database_url: Optional connection URL; defaults to Settings.database_url.

    Returns:
        Configured SQLAlchemy Engine.
    """
    url = database_url or get_settings().database_url
    return sa.create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={"connect_timeout": 3},
        future=True,
    )


@lru_cache(maxsize=1)
def get_engine() -> sa.Engine:
    """Returns a cached singleton SQLAlchemy Engine for the default database URL.

    Returns:
        Singleton SQLAlchemy Engine.
    """
    return create_db_engine()


def _build_alembic_config(database_url: str | None = None) -> Config:
    """Builds an Alembic Config instance pointing to the package migrations directory.

    Args:
        database_url: Optional database URL override.

    Returns:
        Alembic Config object.
    """
    migrations_dir = Path(__file__).resolve().parent / "migrations"
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", database_url or get_settings().database_url)
    return cfg


def upgrade_db(database_url: str | None = None, revision: str = "head") -> None:
    """Applies Alembic migrations up to the target revision.

    Args:
        database_url: Optional database connection URL override.
        revision: Target Alembic revision identifier (defaults to 'head').
    """
    cfg = _build_alembic_config(database_url)
    command.upgrade(cfg, revision)


def downgrade_db(database_url: str | None = None, revision: str = "base") -> None:
    """Reverts Alembic migrations down to the target revision.

    Args:
        database_url: Optional database connection URL override.
        revision: Target Alembic revision identifier (defaults to 'base').
    """
    cfg = _build_alembic_config(database_url)
    command.downgrade(cfg, revision)
