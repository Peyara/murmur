"""Tests for Murmur CLI commands."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from src.cli import cli

FIXTURES_DIR = Path(__file__).parent.parent / "data" / "fixtures"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a temporary DB path and clean up."""
    db_path = str(tmp_path / "test.duckdb")
    yield db_path


class TestInitDb:
    def test_creates_database(self, runner, tmp_db):
        result = runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        assert result.exit_code == 0
        assert Path(tmp_db).exists()

    def test_creates_all_tables(self, runner, tmp_db):
        import duckdb

        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        conn = duckdb.connect(tmp_db)
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        ]
        conn.close()
        assert len(tables) == 10
        assert "events" in tables

    def test_idempotent(self, runner, tmp_db):
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        result = runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        assert result.exit_code == 0


class TestIngestSample:
    def test_populates_events(self, runner, tmp_db):
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        result = runner.invoke(cli, ["ingest", "--sample", "--db-path", tmp_db])
        assert result.exit_code == 0

        import duckdb
        conn = duckdb.connect(tmp_db)
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        # 6 normal_scheduled + 6 key_secret_attack + 1 quiet_window = 13
        assert count == 13

    def test_idempotent_reingest(self, runner, tmp_db):
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        runner.invoke(cli, ["ingest", "--sample", "--db-path", tmp_db])
        runner.invoke(cli, ["ingest", "--sample", "--db-path", tmp_db])

        import duckdb
        conn = duckdb.connect(tmp_db)
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        assert count == 13  # duplicates rejected


class TestIngestFile:
    def test_ingest_single_file(self, runner, tmp_db):
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        fixture = str(FIXTURES_DIR / "key_secret_attack.jsonl")
        result = runner.invoke(cli, ["ingest", "--file", fixture, "--db-path", tmp_db])
        assert result.exit_code == 0

        import duckdb
        conn = duckdb.connect(tmp_db)
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        assert count == 6

    def test_ingest_file_correct_zones(self, runner, tmp_db):
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        fixture = str(FIXTURES_DIR / "key_secret_attack.jsonl")
        runner.invoke(cli, ["ingest", "--file", fixture, "--db-path", tmp_db])

        import duckdb
        conn = duckdb.connect(tmp_db)
        zones = set(
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT target_zone FROM events"
            ).fetchall()
        )
        conn.close()
        assert "IDENTITY" in zones
        assert "SECRET" in zones

    def test_scheduled_events_have_weak_provenance(self, runner, tmp_db):
        """normal_scheduled.jsonl events have trigger_ref -> provenance_level=WEAK."""
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        fixture = str(FIXTURES_DIR / "normal_scheduled.jsonl")
        runner.invoke(cli, ["ingest", "--file", fixture, "--db-path", tmp_db])

        import duckdb
        conn = duckdb.connect(tmp_db)
        rows = conn.execute(
            "SELECT provenance_level, provenance_source FROM events "
            "WHERE trigger_ref IS NOT NULL"
        ).fetchall()
        conn.close()
        assert len(rows) == 6
        for level, source in rows:
            assert level == "WEAK"
        # At least one event should be the scheduler SA itself (in known_initiators)
        assert any(source == "CLOUD_SCHEDULER" for _, source in rows)

    def test_attack_events_have_none_provenance(self, runner, tmp_db):
        """key_secret_attack.jsonl events have no trigger_ref -> provenance_level=NONE."""
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        fixture = str(FIXTURES_DIR / "key_secret_attack.jsonl")
        runner.invoke(cli, ["ingest", "--file", fixture, "--db-path", tmp_db])

        import duckdb
        conn = duckdb.connect(tmp_db)
        rows = conn.execute(
            "SELECT DISTINCT provenance_level FROM events"
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "NONE"

    def test_nonexistent_file(self, runner, tmp_db):
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        result = runner.invoke(cli, ["ingest", "--file", "/nonexistent.jsonl", "--db-path", tmp_db])
        assert result.exit_code != 0
