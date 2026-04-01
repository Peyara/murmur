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


@cli.command("window")
@click.option("--db-path", default=None, help="Path to DuckDB file.")
@click.option("--window-start", default=None, help="ISO timestamp. If omitted, process all windows.")
def window(db_path: str | None, window_start: str | None):
    """Compute world model: actor_windows, edges_window, zone_flux_windows."""
    from datetime import datetime

    from src.world.graph import compute_zone_flux
    from src.world.window import compute_actor_windows, compute_edges

    db_path = db_path or SETTINGS.db_path
    conn = duckdb.connect(db_path)
    try:
        if window_start:
            windows = [(datetime.fromisoformat(window_start),)]
        else:
            windows = conn.execute(
                "SELECT DISTINCT window_start FROM events ORDER BY window_start"
            ).fetchall()

        total_actors = 0
        total_edges = 0
        for (ws,) in windows:
            actors = compute_actor_windows(conn, ws)
            edges = compute_edges(conn, ws)
            compute_zone_flux(conn, ws)
            total_actors += actors
            total_edges += edges

        click.echo(
            f"Window complete: {len(windows)} windows, "
            f"{total_actors} actor-window rows, {total_edges} edge rows"
        )
    finally:
        conn.close()


@cli.command("score")
@click.option("--db-path", default=None, help="Path to DuckDB file.")
@click.option("--window-start", default=None, help="ISO timestamp. If omitted, score all windows.")
def score(db_path: str | None, window_start: str | None):
    """Compute risk scores for all (window, actor) pairs."""
    from datetime import datetime

    from src.score.fusion import compute_fusion

    db_path = db_path or SETTINGS.db_path
    conn = duckdb.connect(db_path)
    try:
        known = SETTINGS.load_known_initiators()

        if window_start:
            pairs = conn.execute(
                "SELECT window_start, actor_id FROM actor_windows WHERE window_start = ?",
                [datetime.fromisoformat(window_start)],
            ).fetchall()
        else:
            pairs = conn.execute(
                "SELECT window_start, actor_id FROM actor_windows ORDER BY window_start"
            ).fetchall()

        scores = []
        for ws, actor_id in pairs:
            fusion_raw = compute_fusion(conn, ws, actor_id, known)
            scores.append(fusion_raw)

        # fusion_raw is [0, 1]; settings thresholds are on [0, 10] scale.
        # Normalize thresholds to fusion scale for comparison.
        high_t = SETTINGS.alert_high_threshold / 10.0
        med_t = SETTINGS.alert_med_threshold / 10.0
        high = sum(1 for s in scores if s >= high_t)
        med = sum(1 for s in scores if med_t <= s < high_t)
        click.echo(
            f"Score complete: {len(scores)} (window, actor) pairs scored. "
            f"High: {high}, Medium: {med}"
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
