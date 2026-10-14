"""Structured logging configuration for ETL and API services."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects with contextual attributes."""

    def format(self, record: logging.LogRecord) -> str:
        """Serializes a log record to a JSON string.

        Args:
            record: Standard Python LogRecord instance.

        Returns:
            Single-line JSON representation of the log record.
        """
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for extra_key in ("run_id", "step", "source", "rows_in", "rows_out"):
            val = getattr(record, extra_key, None)
            if val is not None:
                payload[extra_key] = val
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """Configures the root logger for the application.

    Args:
        level: Log level name (e.g. 'DEBUG', 'INFO', 'WARNING').
        json_output: Whether to emit structured JSON lines instead of plain text.
    """
    root_logger = logging.getLogger("territorio")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    if json_output:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    root_logger.addHandler(handler)
    root_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Returns a child logger under the `territorio` namespace.

    Args:
        name: Module or component name.

    Returns:
        Configured Logger instance.
    """
    if name.startswith("territorio"):
        return logging.getLogger(name)
    return logging.getLogger(f"territorio.{name}")
