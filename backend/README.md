# Território Eleitoral — Backend

Camada de dados, processamento e API do projeto **Território Eleitoral**.

## Componentes

- **Fábrica (ETL):** ingestão, validação (`pandera`), conversão De-Para TSE↔IBGE e carga no PostGIS (`src/territorio/etl`).
- **Memória:** PostgreSQL 17 + PostGIS 3.5 com migrações gerenciadas pelo Alembic (`src/territorio/db`).
- **Cérebro:** análises determinísticas (`src/territorio/analytics`) e API assíncrona FastAPI + MVT tiles (`src/territorio/api`).
- **CLI:** utilitário de linha de comando `territorio` (`src/territorio/cli.py`).

## Requisitos e Ferramentas

- Python ≥ 3.12 gerenciado por **uv**.
- PostGIS ativo via Docker Compose na raiz do repositório (`docker compose up -d db`).

## Comandos Principais

```powershell
uv sync                                   # instala dependências e ambiente virtual
uv run territorio db upgrade              # executa migrações do banco
uv run territorio etl run --all           # executa o pipeline de ETL completo
uv run territorio etl verify              # executa a verificação de integridade dos dados
uv run uvicorn territorio.api.main:app --reload  # sobe a API em http://localhost:8000
uv run ruff check . ; uv run ruff format --check . # lint e formatação
uv run pytest                             # executa a suíte de testes
```
