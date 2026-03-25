"""Murmur CLI — entry point for all commands."""

import sys
from pathlib import Path

import click
import duckdb

from config.settings import SETTINGS
from src.ingest.fetch import (
    GCSFetcher,
    LocalFetcher,
    SingleFileFetcher,
    fetch_and_ingest,
)


@click.group()
def cli():
    """Murmur — Trajectory Risk Engine."""
    pass


@cli.command("init-db")
@click.option("--db-path", default=None, help="Path to DuckDB file.")
def init_db(db_path: str | None):
    """Create DuckDB database and initialize all tables."""
    db_path = db_path or SETTINGS.db_path
    schema_path = Path(SETTINGS.schema_path)

    if not schema_path.exists():
        click.echo(f"Schema file not found: {schema_path}", err=True)
        sys.exit(1)

    conn = duckdb.connect(db_path)
    try:
        conn.execute(schema_path.read_text())
    finally:
        conn.close()
    click.echo(f"Database initialized at {db_path}")


@cli.command("ingest")
@click.option("--sample", is_flag=True, help="Ingest all fixture files from data/fixtures/.")
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False), help="Ingest a single JSONL file.")
@click.option(
    "--local-dir", type=click.Path(exists=True, file_okay=False), help="Ingest all JSON files from a local directory."
)
@click.option("--gcs-bucket", default=None, help="Ingest audit logs from a GCS bucket.")
@click.option("--db-path", default=None, help="Path to DuckDB file.")
def ingest(
    sample: bool,
    file_path: str | None,
    local_dir: str | None,
    gcs_bucket: str | None,
    db_path: str | None,
):
    """Ingest GCP audit log events into DuckDB."""
    sources = sum(bool(s) for s in [sample, file_path, local_dir, gcs_bucket])
    if sources > 1:
        raise click.UsageError("Options --sample, --file, --local-dir, and --gcs-bucket are mutually exclusive.")
    if sources == 0:
        raise click.UsageError("Specify --sample, --file PATH, --local-dir DIR, or --gcs-bucket BUCKET.")

    db_path = db_path or SETTINGS.db_path
    conn = duckdb.connect(db_path)
    try:
        if gcs_bucket:
            fetcher = GCSFetcher(gcs_bucket)
            source_id = f"gcs:{gcs_bucket}"
        elif local_dir:
            fetcher = LocalFetcher(local_dir)
            source_id = f"local:{local_dir}"
        elif file_path:
            fetcher = SingleFileFetcher(file_path)
            mtime = int(Path(file_path).stat().st_mtime)
            source_id = f"file:{file_path}:{mtime}"
        else:
            fetcher = LocalFetcher(str(Path(SETTINGS.fixtures_dir)))
            source_id = "sample:fixtures"

        stats = fetch_and_ingest(conn, fetcher, source_id=source_id)
        click.echo(
            f"Ingest complete: {stats['blobs_processed']} blobs, "
            f"{stats['inserted']} inserted, {stats['skipped']} duplicates, "
            f"{stats['parse_errors']} errors"
        )
    finally:
        conn.close()


@cli.command("inspect")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--cluster-window",
    default=30.0,
    help="Temporal clustering window in seconds (default: 30).",
)
def inspect(directory: str, cluster_window: float):
    """Inspect raw log files — discover structure, patterns, and correlations."""
    from src.ingest.inspector import format_report, inspect_logs

    click.echo(f"Inspecting logs in {directory} ...")
    report = inspect_logs(directory, cluster_window_seconds=cluster_window)
    click.echo(format_report(report))
