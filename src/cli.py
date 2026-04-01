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
    fetch_and_ingest_multi,
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
            stats = fetch_and_ingest_multi(conn, fetcher, source_id_prefix=f"gcs:{gcs_bucket}")
        elif local_dir:
            fetcher = LocalFetcher(local_dir)
            stats = fetch_and_ingest_multi(conn, fetcher, source_id_prefix=f"local:{local_dir}")
        elif file_path:
            fetcher = SingleFileFetcher(file_path)
            mtime = int(Path(file_path).stat().st_mtime)
            stats = fetch_and_ingest(conn, fetcher, source_id=f"file:{file_path}:{mtime}")
        else:
            fetcher = LocalFetcher(str(Path(SETTINGS.fixtures_dir)))
            stats = fetch_and_ingest(conn, fetcher, source_id="sample:fixtures")

        click.echo(
            f"Ingest complete: {stats['blobs_processed']} blobs, "
            f"{stats['inserted']} inserted, {stats['skipped']} duplicates, "
            f"{stats['parse_errors']} errors"
        )
        if "correlated" in stats:
            click.echo(
                f"  Correlation: {stats.get('correlated', 0)} events correlated, "
                f"{stats.get('audit_parsed', 0)} audit, "
                f"{stats.get('scheduler_parsed', 0)} scheduler, "
                f"{stats.get('cloudrun_parsed', 0)} cloudrun"
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

    from src.provenance.patterns import list_patterns
    from src.provenance.residual import compute_residual_risk
    from src.score.fusion import compute_fusion

    db_path = db_path or SETTINGS.db_path
    conn = duckdb.connect(db_path)
    try:
        known = SETTINGS.load_known_initiators()
        cached_patterns = list_patterns(conn, include_inactive=False)

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
            compute_residual_risk(conn, ws, actor_id, fusion_raw, known, SETTINGS,
                                  cached_patterns=cached_patterns)
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


@cli.command("register-pattern")
@click.option("--db-path", default=None, help="Path to DuckDB file.")
@click.option("--name", required=True, help="Pattern name.")
@click.option("--description", default="", help="Pattern description.")
@click.option("--initiator-type", default="SCHEDULED", help="SCHEDULED | HUMAN_TRIGGERED | API_TRIGGERED")
@click.option("--actors", required=True, help="Comma-separated expected actor SA emails.")
@click.option("--zones", required=True, help="Comma-separated expected zone sequence.")
@click.option("--rate-min", type=float, default=0, help="Min events per window.")
@click.option("--rate-max", type=float, default=100, help="Max events per window.")
@click.option("--duration", type=int, default=15, help="Expected duration in minutes.")
def register_pattern_cmd(db_path, name, description, initiator_type, actors, zones, rate_min, rate_max, duration):
    """Register a sanctioned pattern."""
    from src.provenance.patterns import register_pattern

    db_path = db_path or SETTINGS.db_path
    conn = duckdb.connect(db_path)
    try:
        actor_list = [a.strip() for a in actors.split(",")]
        zone_list = [z.strip() for z in zones.split(",")]
        pid = register_pattern(
            conn, name, description, initiator_type,
            actor_list, zone_list, None, rate_min, rate_max, duration,
        )
        click.echo(f"Pattern registered: {pid} ({name})")
    finally:
        conn.close()


@cli.command("list-patterns")
@click.option("--db-path", default=None, help="Path to DuckDB file.")
@click.option("--all", "include_inactive", is_flag=True, help="Include inactive patterns.")
def list_patterns_cmd(db_path, include_inactive):
    """List sanctioned patterns."""
    from src.provenance.patterns import list_patterns

    db_path = db_path or SETTINGS.db_path
    conn = duckdb.connect(db_path)
    try:
        patterns = list_patterns(conn, include_inactive=include_inactive)
        if not patterns:
            click.echo("No patterns registered.")
            return
        for p in patterns:
            status = "active" if p["active"] else "inactive"
            matches = p.get("match_count", 0) or 0
            click.echo(f"  {p['pattern_id']}  {p['name']:30s}  [{status}]  {matches} matches")
    finally:
        conn.close()


@cli.command("deactivate-pattern")
@click.argument("pattern_id")
@click.option("--db-path", default=None, help="Path to DuckDB file.")
def deactivate_pattern_cmd(pattern_id, db_path):
    """Deactivate a sanctioned pattern."""
    from src.provenance.patterns import deactivate_pattern

    db_path = db_path or SETTINGS.db_path
    conn = duckdb.connect(db_path)
    try:
        if deactivate_pattern(conn, pattern_id):
            click.echo(f"Pattern {pattern_id} deactivated.")
        else:
            click.echo(f"Pattern {pattern_id} not found.", err=True)
            sys.exit(1)
    finally:
        conn.close()


@cli.command("show-trigger-chain")
@click.argument("event_id")
@click.option("--db-path", default=None, help="Path to DuckDB file.")
def show_trigger_chain_cmd(event_id, db_path):
    """Show trigger chain for an event."""
    from src.provenance.trigger_chain import resolve_trigger_chain

    db_path = db_path or SETTINGS.db_path
    conn = duckdb.connect(db_path)
    try:
        known = SETTINGS.load_known_initiators()
        row = conn.execute(
            "SELECT trigger_ref FROM events WHERE event_id = ?", [event_id]
        ).fetchone()
        if not row:
            click.echo(f"Event {event_id} not found.", err=True)
            sys.exit(1)

        chain = resolve_trigger_chain(conn, row[0], known)
        click.echo(f"Resolved: {chain.resolved}")
        click.echo(f"Depth: {chain.depth}")
        click.echo(f"Chain: {' -> '.join(chain.chain) if chain.chain else '(empty)'}")
        if chain.terminal_initiator:
            click.echo(f"Terminal initiator: {chain.terminal_initiator}")
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
