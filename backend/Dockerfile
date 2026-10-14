# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Instalar uv oficial da imagem Astral
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copiar manifesto de dependências
COPY pyproject.toml uv.lock ./

# -------------------------------------------------------------
# Target: dev (usado em desenvolvimento com docker compose up)
# -------------------------------------------------------------
FROM base AS dev

RUN uv sync --frozen

COPY src/ ./src/
COPY data/reference/ ./data/reference/
COPY alembic.ini ./alembic.ini

EXPOSE 8000

CMD ["sh", "-c", "uv run territorio db upgrade && uv run uvicorn territorio.api.main:app --host 0.0.0.0 --port 8000 --reload"]

# -------------------------------------------------------------
# Target: prod (usado na finalização/release do sistema)
# -------------------------------------------------------------
FROM base AS prod

RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY data/reference/ ./data/reference/
COPY alembic.ini ./alembic.ini

RUN uv sync --frozen --no-dev

RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data/raw /app/data/reports && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 --start-period=10s \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"

CMD ["sh", "-c", "uv run territorio db upgrade && uv run uvicorn territorio.api.main:app --host 0.0.0.0 --port 8000 --workers 2"]
