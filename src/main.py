"""Aethelburg CLI & Application Entrypoint (`python -m src.main` or `aethelburg`).

Commands:
  - `serve`: Start the FastAPI web server (`http://127.0.0.1:8050`)
  - `desktop`: Launch the native desktop window + local backend
  - `bootstrap`: Populate `dati/aethelburg.sqlite` from the real datasets in `dati/` and run FT3 scoring
  - `import-onspd`: Import exact postcode centroids (ONS Postcode Directory CSV) for the map
  - `score`: Run cross-dataset entity resolution and all 11 FT3 shell-company detection rules
  - `export-ftm`: Export FollowTheMoney v3.x (`.ftm.json`) JSONL stream
  - `import-ftm`: Import a FollowTheMoney v3.x (`.ftm.json`) JSONL file
  - `report`: Generate a 10-section HTML/PDF intelligence dossier for a UK company
  - `data location [PATH] [--move]`: Show or change the data folder (downloads, database, exports)
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
from src.datasources.catalog import SOURCES, latest_release
from src.datasources.downloader import download_source, local_releases
from src.datasources.pipeline import refresh_all
from src.datasources.runs import mark_interrupted
from src.datasources.storage import describe_location, set_location
from src.datasources.streaming import StreamWorker
from src.etl.bootstrap_beta import bootstrap_beta_database
from src.etl.import_onspd import import_onspd
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


def _prepare_database(auto_bootstrap: bool) -> None:
    """Flag imports interrupted by a previous run; explain how to load data into an empty database."""
    db = DatabaseService()
    conn = db.connect()
    try:
        interrupted = mark_interrupted(conn)
    finally:
        conn.close()
    if interrupted:
        console.print(f"[bold amber1]{interrupted} import step(s) were interrupted; Run import resumes them.[/bold amber1]")
    if db.get_dashboard_stats()["counts"]["companies"] == 0:
        if auto_bootstrap:
            console.print("[bold amber1]Database is empty — building the demo database from the data folder...[/bold amber1]")
            bootstrap_beta_database()
        else:
            console.print("[bold amber1]Database is empty: open the '6. Data & Updates' tab to download and import data.[/bold amber1]")


@app.command("serve")
def cmd_serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8050, "--port", help="Bind port"),
    auto_bootstrap: bool = typer.Option(
        False, "--auto-bootstrap/--no-auto-bootstrap", help="Build the small demo database if empty"
    ),
) -> None:
    """Start the Aethelburg web & API server."""
    setup_logging()
    _prepare_database(auto_bootstrap)

    console.print(f"[bold green]Aethelburg v{get_settings().version}[/bold green] listening on [bold cyan]http://{host}:{port}[/bold cyan]")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


@app.command("desktop")
def cmd_desktop(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8050, "--port"),
) -> None:
    """Launch Aethelburg in a desktop application window."""
    setup_logging()
    _prepare_database(auto_bootstrap=False)
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


@app.command("import-onspd")
def cmd_import_onspd(
    csv_path: Path = typer.Argument(..., help="ONSPD CSV (columns pcds, lat, long)"),
    limit: int | None = typer.Option(None, "--limit", help="Max postcodes to import"),
) -> None:
    """Import exact UK postcode centroids from the ONS Postcode Directory for the map."""
    setup_logging()
    if not csv_path.exists():
        console.print(f"[bold red]File not found:[/bold red] {csv_path}")
        raise typer.Exit(code=1)
    res = import_onspd(csv_path=csv_path, limit=limit)
    console.print_json(data=res)


@app.command("score")
def cmd_score() -> None:
    """Run cross-dataset Entity Resolution and all 11 FT3 shell-company detection rules."""
    setup_logging()
    scorer = RiskScorer()
    res = scorer.run_all_detections()
    console.print_json(data=res)


@app.command("export-ftm")
def cmd_export_ftm(
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output .ftm.json path (default: <data folder>/exports/aethelburg.ftm.json)"
    ),
    schema: str | None = typer.Option(None, "--schema", help="Filter by FtM schema (e.g. Company, Ownership)"),
    target_only: bool = typer.Option(False, "--target-only", help="Export only flagged target entities"),
    limit: int | None = typer.Option(None, "--limit", help="Max entities to export"),
) -> None:
    """Export entities in canonical FollowTheMoney v3.x JSONL format (`.ftm.json`)."""
    db = DatabaseService()
    output = output or get_settings().paths.exports_dir / "aethelburg.ftm.json"
    output.parent.mkdir(parents=True, exist_ok=True)
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


data_app = typer.Typer(help="Data folder, bulk downloads and updates.")
app.add_typer(data_app, name="data")


@data_app.command("location")
def cmd_data_location(
    path: Path | None = typer.Argument(None, help="New data folder (omit to show the current one)"),
    move: bool = typer.Option(False, "--move", help="Copy the database and data sub-folders to the new folder"),
) -> None:
    """Show or change where downloads, the database and exports are kept."""
    if path is None:
        console.print_json(data=describe_location())
        return
    try:
        report = set_location(path, move=move)
    except (ValueError, OSError) as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=report)
    console.print("[bold amber1]Restart Aethelburg to use the new data folder.[/bold amber1]")


@data_app.command("status")
def cmd_data_status(
    check_remote: bool = typer.Option(True, "--check-remote/--offline", help="Ask publishers for their latest release"),
) -> None:
    """Show local and latest available release of every bulk source."""
    table = Table(title="Aethelburg data sources")
    for col in ("Source", "Local version", "Latest available", "Up to date"):
        table.add_column(col)
    for key, info in SOURCES.items():
        local = local_releases(key)
        local_version = local[0]["version"] if local else "-"
        latest = "-"
        if check_remote:
            try:
                latest = latest_release(key).version
            except Exception as exc:  # network or layout change: report, keep going
                latest = f"error: {exc}"
        up_to_date = "yes" if local and local_version == latest else ("?" if not check_remote else "no")
        table.add_row(info.title, local_version, latest, up_to_date)
    console.print(table)


@data_app.command("download")
def cmd_data_download(
    source: list[str] = typer.Option(None, "--source", "-s", help=f"Source key(s): {', '.join(SOURCES)} (default: all)"),
) -> None:
    """Download the latest release of the bulk sources into the data folder (skips releases already on disk)."""
    setup_logging()
    for key in source or list(SOURCES):
        if key not in SOURCES:
            console.print(f"[bold red]Unknown source {key!r}[/bold red]")
            raise typer.Exit(code=1)
        console.print(f"[bold cyan]{SOURCES[key].title}[/bold cyan]")
        last_report = [0.0]

        def report(done: int, total: int | None, _last: list[float] = last_report) -> None:
            if done - _last[0] >= 100 * 1024 * 1024 or (total and done == total):
                _last[0] = done
                pct = f" ({done * 100 // total}%)" if total else ""
                console.print(f"  {done / 1024**2:,.0f} MB{pct}")

        result = download_source(key, progress=report)
        console.print(f"  {result['status']}: {result['data_file']}")


@data_app.command("import")
def cmd_data_import(
    no_score: bool = typer.Option(False, "--no-score", help="Skip FT3 scoring at the end"),
) -> None:
    """Index the whole register, select the subset and import it in full (resumes if interrupted)."""
    setup_logging()

    def report(stage: str, rows: int) -> None:
        console.print(f"  {stage}: {rows:,}")

    summary = refresh_all(progress=report, score=not no_score)
    console.print_json(data=summary)


@data_app.command("watch")
def cmd_data_watch() -> None:
    """Follow the Companies House Streaming API and apply changes until stopped (Ctrl+C)."""
    import asyncio

    setup_logging()
    worker = StreamWorker()

    async def run() -> None:
        worker.start()
        try:
            while True:
                await asyncio.sleep(60)
                streams = worker.status()["streams"]
                console.print(
                    " | ".join(f"{k}: {v['events']} events, timepoint {v['timepoint']}" for k, v in streams.items())
                )
        finally:
            await worker.stop()

    try:
        asyncio.run(run())
    except RuntimeError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(code=1) from exc
    except KeyboardInterrupt:
        console.print("Stopped. The next start resumes from the saved timepoints.")


if __name__ == "__main__":
    app()
