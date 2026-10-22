"""Aethelburg CLI & Application Entrypoint (`python -m src.main` or `aethelburg`).

Commands:
  - `serve`: Start the FastAPI web server (`http://127.0.0.1:8050`)
  - `desktop`: Launch the native desktop window + local backend
  - `bootstrap`: Populate `dati/aethelburg.sqlite` from the real datasets in `dati/` and run FT3 scoring
  - `score`: Run cross-dataset entity resolution and all 11 FT3 shell-company detection rules
  - `export-ftm`: Export FollowTheMoney v3.x (`.ftm.json`) JSONL stream
  - `import-ftm`: Import a FollowTheMoney v3.x (`.ftm.json`) JSONL file
  - `report`: Generate a 10-section HTML/PDF intelligence dossier for a UK company
  - `stats`: Print database & FollowTheMoney ontology statistics
"""
from __future__ import annotations

from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from config.settings import get_settings
from src.core.logging import setup_logging
from src.etl.bootstrap_beta import bootstrap_beta_database
from src.intelligence.risk_scorer import RiskScorer
from src.reports.pdf_generator import ReportGenerator
from src.services.db_service import DatabaseService
from src.ui.desktop import launch_desktop
from src.ui.web_app import create_app

app = typer.Typer(
    name="aethelburg",
    help="Aethelburg — Corporate Intelligence & Shell Company Detection Platform (FollowTheMoney v3.x)",
    add_completion=False,
)
console = Console()


@app.command("serve")
def cmd_serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8050, "--port", help="Bind port"),
    auto_bootstrap: bool = typer.Option(True, "--auto-bootstrap/--no-auto-bootstrap", help="Bootstrap DB if empty"),
) -> None:
    """Start the Aethelburg web & API server."""
    setup_logging()
    db = DatabaseService()
    stats = db.get_dashboard_stats()
    if auto_bootstrap and stats["counts"]["companies"] == 0:
        console.print("[bold amber1]Database is empty — running initial Beta bootstrap from dati/...[/bold amber1]")
        bootstrap_beta_database()

    console.print(f"[bold green]Aethelburg v{get_settings().version}[/bold green] listening on [bold cyan]http://{host}:{port}[/bold cyan]")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


@app.command("desktop")
def cmd_desktop(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8050, "--port"),
) -> None:
    """Launch Aethelburg in a desktop application window."""
    setup_logging()
    db = DatabaseService()
    if db.get_dashboard_stats()["counts"]["companies"] == 0:
        console.print("[bold amber1]Bootstrapping database from dati/...[/bold amber1]")
        bootstrap_beta_database()
    launch_desktop(host=host, port=port, open_window=True)


@app.command("bootstrap")
def cmd_bootstrap(
    sanctions_limit: int = typer.Option(2500, "--sanctions-limit", help="Max unique sanctions entities to import"),
    icij_limit: int = typer.Option(1500, "--icij-limit", help="Max rows per ICIJ CSV to import"),
    companies_limit: int = typer.Option(2500, "--companies-limit", help="Max CH companies to import"),
    psc_limit: int = typer.Option(3000, "--psc-limit", help="Max PSC ownership records to import"),
) -> None:
    """Populate the FollowTheMoney-compatible database from real datasets in `dati/` and run FT3 scoring."""
    setup_logging()
    console.print("[bold cyan]Starting Aethelburg Beta Bootstrap from `dati/`...[/bold cyan]")
    summary = bootstrap_beta_database(
        sanctions_limit=sanctions_limit,
        icij_limit=icij_limit,
        companies_limit=companies_limit,
        psc_limit=psc_limit,
    )
    console.print("[bold green]Bootstrap complete![/bold green]")
    console.print_json(data=summary)


@app.command("score")
def cmd_score() -> None:
    """Run cross-dataset Entity Resolution and all 11 FT3 shell-company detection rules."""
    setup_logging()
    scorer = RiskScorer()
    res = scorer.run_all_detections()
    console.print_json(data=res)


@app.command("export-ftm")
def cmd_export_ftm(
    output: Path = typer.Option(Path("dati/exports/aethelburg.ftm.json"), "--output", "-o", help="Output .ftm.json path"),
    schema: str | None = typer.Option(None, "--schema", help="Filter by FtM schema (e.g. Company, Ownership)"),
    target_only: bool = typer.Option(False, "--target-only", help="Export only flagged target entities"),
    limit: int | None = typer.Option(None, "--limit", help="Max entities to export"),
) -> None:
    """Export entities in canonical FollowTheMoney v3.x JSONL format (`.ftm.json`)."""
    db = DatabaseService()
    count = db.export_ftm_jsonl(output, schema=schema, target_only=target_only, limit=limit)
    console.print(f"[bold green]Exported {count} FollowTheMoney entities to {output}[/bold green]")


@app.command("import-ftm")
def cmd_import_ftm(
    input_path: Path = typer.Argument(..., help="Input .ftm.json JSONL file"),
    dataset: str | None = typer.Option(None, "--dataset", help="Dataset tag override"),
) -> None:
    """Import a FollowTheMoney v3.x JSONL stream into `ftm_entities`."""
    db = DatabaseService()
    count = db.import_ftm_jsonl(input_path, dataset_override=dataset)
    console.print(f"[bold green]Imported {count} FollowTheMoney entities from {input_path}[/bold green]")


@app.command("report")
def cmd_report(
    company_number: str = typer.Argument(..., help="UK Company Registration Number (e.g. 14900101)"),
    classification: str = typer.Option("CONFIDENTIAL", "--classification"),
) -> None:
    """Generate a 10-section Intelligence Dossier Report for a UK company."""
    gen = ReportGenerator()
    res = gen.generate_company_report(company_number=company_number, classification=classification)
    console.print(f"[bold green]Generated Dossier:[/bold green] {res['file_path']} (SHA-256: {res['sha256_hash'][:16]}...)")


@app.command("stats")
def cmd_stats() -> None:
    """Display database & FollowTheMoney ontology statistics."""
    db = DatabaseService()
    st = db.get_dashboard_stats()
    table = Table(title=f"Aethelburg v{get_settings().version} — Database & FollowTheMoney Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right", style="bold green")
    for k, v in st["counts"].items():
        table.add_row(k, f"{v:,}")
    console.print(table)


if __name__ == "__main__":
    app()
