"""Command-line interface (`territorio`) for database migrations, crosswalk, and ETL."""

from typing import Annotated

import typer

from territorio.config import get_settings
from territorio.db.engine import downgrade_db, upgrade_db
from territorio.logging import configure_logging

app = typer.Typer(
    name="territorio",
    help="Território Eleitoral — CLI de banco de dados, crosswalk e pipeline ETL.",
    no_args_is_help=True,
)

db_app = typer.Typer(help="Gerenciamento de migrações Alembic do PostGIS.")
etl_app = typer.Typer(help="Execução e verificação do pipeline ETL.")
crosswalk_app = typer.Typer(help="Construção e validação do De-Para TSE <-> IBGE.")

app.add_typer(db_app, name="db")
app.add_typer(etl_app, name="etl")
app.add_typer(crosswalk_app, name="crosswalk")


@db_app.command("upgrade")
def db_upgrade(
    revision: Annotated[
        str, typer.Option("--revision", "-r", help="Revisão alvo do Alembic.")
    ] = "head",
) -> None:
    """Aplica migrações Alembic até a revisão especificada.

    Args:
        revision: Identificador da revisão alvo (default: 'head').
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    upgrade_db(settings.database_url, revision=revision)
    typer.echo(f"Migrações aplicadas com sucesso ({revision}).")


@db_app.command("downgrade")
def db_downgrade(
    revision: Annotated[
        str, typer.Option("--revision", "-r", help="Revisão alvo do Alembic.")
    ] = "base",
) -> None:
    """Reverte migrações Alembic até a revisão especificada.

    Args:
        revision: Identificador da revisão alvo (default: 'base').
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    downgrade_db(settings.database_url, revision=revision)
    typer.echo(f"Migrações revertidas para ({revision}).")


@crosswalk_app.command("build")
def crosswalk_build() -> None:
    """Constrói `de_para_tse_ibge.csv` a partir da semente e overrides."""
    from territorio.etl.crosswalk import build_and_save_crosswalk

    settings = get_settings()
    configure_logging(settings.log_level)
    output_path = build_and_save_crosswalk(settings)
    typer.echo(f"Crosswalk salvo em {output_path}")


@crosswalk_app.command("validate")
def crosswalk_validate() -> None:
    """Valida `data/reference/de_para_tse_ibge.csv` contra as regras X1-X6."""
    from territorio.etl.crosswalk import run_crosswalk_validation_cli

    settings = get_settings()
    configure_logging(settings.log_level)
    report = run_crosswalk_validation_cli(settings)
    typer.echo(
        f"Crosswalk válido: {report.total_pairs} municípios verificados "
        f"({len(report.name_warnings)} avisos de grafia X6)."
    )


@etl_app.command("run")
def etl_run_command(
    all_steps: Annotated[
        bool, typer.Option("--all", help="Executa todas as etapas (1 a 8) em ordem.")
    ] = False,
    step: Annotated[
        str | None,
        typer.Option(
            "--step",
            help=(
                "Etapa individual: reference|territory|crosswalk|elections|"
                "indicators|derive|verify|publish."
            ),
        ),
    ] = None,
    round_num: Annotated[
        int | None,
        typer.Option("--round", help="Filtra turno eleitoral (1 ou 2)."),
    ] = None,
    only: Annotated[
        str | None,
        typer.Option(
            "--only", help="Lista de códigos de indicadores separados por vírgula."
        ),
    ] = None,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume", help="Retoma apenas itens que falharam anteriormente."
        ),
    ] = False,
    force_refresh: Annotated[
        bool,
        typer.Option(
            "--force-refresh", help="Ignora cache em disco e baixa novamente."
        ),
    ] = False,
    allow_unverified: Annotated[
        bool,
        typer.Option(
            "--allow-unverified",
            help="Permite carregar indicadores marcados com verified: false.",
        ),
    ] = False,
) -> None:
    """Executa uma etapa ou o pipeline completo de ETL.

    Args:
        all_steps: Se verdadeiro, executa todas as etapas de `reference` a `publish`.
        step: Nome da etapa individual quando `--all` não é usado.
        round_num: Turno eleitoral opcional (1 ou 2).
        only: Filtro opcional de indicadores separados por vírgula.
        resume: Se verdadeiro, reexecuta falhas registradas.
        force_refresh: Se verdadeiro, força novo download das fontes.
        allow_unverified: Se verdadeiro, inclui indicadores com `verified: false`.

    Raises:
        typer.BadParameter: Se nem `--all` nem `--step` forem informados.
    """
    from territorio.etl.pipeline import run_pipeline

    if not all_steps and not step:
        raise typer.BadParameter("Informe --all ou --step <nome_da_etapa>.")

    settings = get_settings()
    configure_logging(settings.log_level)
    only_codes = [c.strip() for c in only.split(",") if c.strip()] if only else None

    results = run_pipeline(
        settings=settings,
        all_steps=all_steps,
        step=step,
        round_num=round_num,
        only_indicators=only_codes,
        resume=resume,
        force_refresh=force_refresh,
        allow_unverified=allow_unverified,
    )
    for res in results:
        typer.echo(
            f"[{res.step}] rows_in={res.rows_in} "
            f"rows_out={res.rows_out} dropped={res.dropped}"
        )


@etl_app.command("verify")
def etl_verify_command() -> None:
    """Executa as checagens de aceitação de dados e gera relatório JSON/Markdown."""
    from territorio.etl.verify import run_verification_cli

    settings = get_settings()
    configure_logging(settings.log_level)
    report = run_verification_cli(settings)
    typer.echo(
        f"Verificação concluída: blocking={report.blocking_count}, "
        f"warnings={report.warning_count}. Relatório em {report.markdown_path}"
    )
    if report.blocking_count > 0:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
