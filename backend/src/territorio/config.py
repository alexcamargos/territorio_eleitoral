"""Application settings loaded from environment variables and .env files."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    """Resolves default data directory whether running from backend/ or repo root.

    Returns:
        Path to the resolved data directory.
    """
    local = Path("./data")
    if local.is_dir():
        return local
    backend_local = Path("./backend/data")
    if backend_local.is_dir():
        return backend_local
    module_data = Path(__file__).resolve().parents[2] / "data"
    if module_data.is_dir():
        return module_data
    return local


class Settings(BaseSettings):
    """Typed runtime configuration for ETL and API layers.

    Attributes:
        database_url: SQLAlchemy PostgreSQL connection string using psycopg v3.
        data_dir: Base directory containing reference, raw, manual, and reports folders.
        reference_dir_override: Optional override for reference directory in tests.
        transparencia_api_key: API key for Portal da Transparência (`chave-api-dados`).
        transparencia_rate_per_min: Rate limit in requests per minute for CGU API.
        http_timeout_s: Default HTTP request timeout in seconds.
        api_cors_origins: Comma-separated list of allowed CORS origins.
        log_level: Logging level name ('DEBUG', 'INFO', 'WARNING', 'ERROR').
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://territorio:territorio@localhost:5432/territorio",
        alias="DATABASE_URL",
    )
    data_dir: Path = Field(default_factory=_default_data_dir, alias="DATA_DIR")
    reference_dir_override: Path | None = Field(default=None)
    transparencia_api_key: str = Field(default="", alias="TRANSPARENCIA_API_KEY")
    transparencia_rate_per_min: int = Field(
        default=80, alias="TRANSPARENCIA_RATE_PER_MIN"
    )
    http_timeout_s: float = Field(default=60.0, alias="HTTP_TIMEOUT_S")
    api_cors_origins: str = Field(
        default="http://localhost:5173", alias="API_CORS_ORIGINS"
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def raw_dir(self) -> Path:
        """Returns the path to the unversioned HTTP download cache directory.

        Returns:
            Path to `data/raw`.
        """
        return self.data_dir / "raw"

    @property
    def manual_dir(self) -> Path:
        """Returns the path to the manually downloaded spreadsheets directory.

        Returns:
            Path to `data/manual`.
        """
        return self.data_dir / "manual"

    @property
    def reference_dir(self) -> Path:
        """Returns the path to the versioned reference files directory.

        Returns:
            Path to `data/reference` or the configured override.
        """
        if self.reference_dir_override is not None:
            return self.reference_dir_override
        return self.data_dir / "reference"

    @property
    def reports_dir(self) -> Path:
        """Returns the path to the data quality reports directory.

        Returns:
            Path to `data/reports`.
        """
        return self.data_dir / "reports"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parses the comma-separated CORS origins into a list of strings.

        Returns:
            List of non-empty CORS origin URLs.
        """
        return [
            origin.strip()
            for origin in self.api_cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns a cached singleton Settings instance.

    Returns:
        Configured Settings instance.
    """
    return Settings()
