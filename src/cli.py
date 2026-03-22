"""Murmur CLI — entry point for all commands."""

import json
import sys
from pathlib import Path

import click
import duckdb

from config.settings import SETTINGS
from src.ingest.parser import parse_audit_log
from src.ingest.dedup import insert_event


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
    conn.execute(schema_path.read_text())
    conn.close()
    click.echo(f"Database initialized at {db_path}")


@cli.command("ingest")
@click.option("--sample", is_flag=True, help="Ingest all fixture files from data/fixtures/.")
@click.option("--file", "file_path", type=click.Path(exists=True), help="Ingest a single JSONL file.")
@click.option("--db-path", default=None, help="Path to DuckDB file.")
def ingest(sample: bool, file_path: str | None, db_path: str | None):
    """Ingest GCP audit log events into DuckDB."""
    db_path = db_path or SETTINGS.db_path
    conn = duckdb.connect(db_path)

    if sample:
        fixtures_dir = Path(SETTINGS.fixtures_dir)
        files = sorted(fixtures_dir.glob("*.jsonl"))
        if not files:
            click.echo(f"No JSONL files found in {fixtures_dir}", err=True)
            conn.close()
            sys.exit(1)
        total_inserted = 0
        total_skipped = 0
        for f in files:
            inserted, skipped = _ingest_file(conn, f)
            total_inserted += inserted
            total_skipped += skipped
        click.echo(f"Sample ingest complete: {total_inserted} inserted, {total_skipped} duplicates skipped")

    elif file_path:
        inserted, skipped = _ingest_file(conn, Path(file_path))
        click.echo(f"Ingest complete: {inserted} inserted, {skipped} duplicates skipped")

    else:
        click.echo("Specify --sample or --file PATH", err=True)
        conn.close()
        sys.exit(1)

    conn.close()


def _ingest_file(conn: duckdb.DuckDBPyConnection, path: Path) -> tuple[int, int]:
    """Parse and ingest a single JSONL file. Returns (inserted, skipped)."""
    inserted = 0
    skipped = 0
    parse_errors = 0

    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                event = parse_audit_log(raw)
                if insert_event(conn, event):
                    inserted += 1
                else:
                    skipped += 1
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                parse_errors += 1
                click.echo(f"  Warning: {path.name}:{line_num} parse error: {e}", err=True)

    if parse_errors:
        click.echo(f"  {path.name}: {parse_errors} parse errors", err=True)

    return inserted, skipped
