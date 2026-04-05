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
        assert len(tables) == 11
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
        # 6 normal_scheduled + 6 key_secret_attack + 1 quiet_window + 6 multi_format/audit = 19
        assert count == 19

    def test_idempotent_reingest(self, runner, tmp_db):
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        runner.invoke(cli, ["ingest", "--sample", "--db-path", tmp_db])
        runner.invoke(cli, ["ingest", "--sample", "--db-path", tmp_db])

        import duckdb
        conn = duckdb.connect(tmp_db)
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        assert count == 19  # duplicates rejected


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


class TestIngestLocalDir:
    def test_ingests_from_directory(self, runner, tmp_db, tmp_path):
        """--local-dir ingests all JSON files from a directory."""
        import json

        import duckdb

        # Create a JSON file with 2 valid audit log events
        events = [
            {
                "protoPayload": {
                    "serviceName": "storage.googleapis.com",
                    "methodName": "storage.objects.get",
                    "authenticationInfo": {"principalEmail": "sa@project.iam.gserviceaccount.com"},
                    "resourceName": f"projects/_/buckets/b/objects/f{i}.csv",
                    "status": {},
                },
                "resource": {"type": "gcs_bucket", "labels": {"project_id": "test"}},
                "timestamp": f"2026-03-22T00:0{i}:00.000Z",
                "insertId": f"i-{i}",
                "logName": "projects/test/logs/cloudaudit.googleapis.com%2Fdata_access",
            }
            for i in range(2)
        ]
        # Multi-format pipeline expects prefix subdirectories (per sub-prefix)
        audit_dir = tmp_path / "cloudaudit.googleapis.com" / "data_access"
        audit_dir.mkdir(parents=True)
        (audit_dir / "batch.json").write_text("\n".join(json.dumps(e) for e in events))

        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        result = runner.invoke(cli, ["ingest", "--local-dir", str(tmp_path), "--db-path", tmp_db])
        assert result.exit_code == 0
        assert "2 inserted" in result.output

        conn = duckdb.connect(tmp_db)
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        assert count == 2

    def test_idempotent_local_dir(self, runner, tmp_db, tmp_path):
        """Second --local-dir run processes 0 blobs due to checkpointing."""
        import json

        event = {
            "protoPayload": {
                "serviceName": "storage.googleapis.com",
                "methodName": "storage.objects.get",
                "authenticationInfo": {"principalEmail": "sa@project.iam.gserviceaccount.com"},
                "resourceName": "projects/_/buckets/b/objects/f.csv",
                "status": {},
            },
            "resource": {"type": "gcs_bucket", "labels": {"project_id": "test"}},
            "timestamp": "2026-03-22T00:00:00.000Z",
            "insertId": "i-1",
            "logName": "projects/test/logs/cloudaudit.googleapis.com%2Fdata_access",
        }
        audit_dir = tmp_path / "cloudaudit.googleapis.com"
        audit_dir.mkdir()
        (audit_dir / "data.json").write_text(json.dumps(event))

        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        runner.invoke(cli, ["ingest", "--local-dir", str(tmp_path), "--db-path", tmp_db])
        result = runner.invoke(cli, ["ingest", "--local-dir", str(tmp_path), "--db-path", tmp_db])
        assert result.exit_code == 0
        assert "0 blobs" in result.output


class TestInspect:
    def test_inspect_runs_on_fixtures(self, runner):
        """murmur inspect on fixtures directory produces a report."""
        result = runner.invoke(cli, ["inspect", str(FIXTURES_DIR)])
        assert result.exit_code == 0
        assert "LOG INSPECTION REPORT" in result.output
        assert "Total entries:" in result.output

    def test_inspect_with_empty_dir(self, runner, tmp_path):
        """murmur inspect on an empty directory produces an empty report."""
        result = runner.invoke(cli, ["inspect", str(tmp_path)])
        assert result.exit_code == 0
        assert "Total entries: 0" in result.output

    def test_inspect_nonexistent_dir(self, runner):
        """murmur inspect on a nonexistent directory fails."""
        result = runner.invoke(cli, ["inspect", "/nonexistent/path"])
        assert result.exit_code != 0


class TestIngestMutualExclusivity:
    def test_multiple_sources_rejected(self, runner, tmp_db, tmp_path):
        """Passing more than one source option should fail."""
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        result = runner.invoke(
            cli, ["ingest", "--sample", "--local-dir", str(tmp_path), "--db-path", tmp_db]
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower() or "mutually exclusive" in (result.stderr or "").lower()

    def test_no_source_shows_usage(self, runner, tmp_db):
        """No source option should show usage help."""
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        result = runner.invoke(cli, ["ingest", "--db-path", tmp_db])
        assert result.exit_code != 0


class TestIngestGcsBucket:
    def test_gcs_bucket_calls_fetch_and_ingest_multi(self, runner, tmp_db):
        """--gcs-bucket wires GCSFetcher into fetch_and_ingest_multi."""
        from unittest.mock import MagicMock, patch

        runner.invoke(cli, ["init-db", "--db-path", tmp_db])

        mock_fetcher = MagicMock()
        mock_stats = {
            "blobs_processed": 2, "inserted": 5, "skipped": 0, "parse_errors": 0,
            "correlated": 3, "audit_parsed": 5, "scheduler_parsed": 2, "cloudrun_parsed": 2,
        }

        with patch("src.cli.GCSFetcher", return_value=mock_fetcher) as mock_cls, \
             patch("src.cli.fetch_and_ingest_multi", return_value=mock_stats) as mock_fai:
            result = runner.invoke(
                cli, ["ingest", "--gcs-bucket", "my-bucket", "--db-path", tmp_db]
            )
            assert result.exit_code == 0
            mock_cls.assert_called_once_with("my-bucket")
            mock_fai.assert_called_once()
            assert "5 inserted" in result.output


class TestIngestFileValidation:
    def test_file_rejects_directory(self, runner, tmp_db, tmp_path):
        """--file with a directory path should fail (dir_okay=False)."""
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        result = runner.invoke(cli, ["ingest", "--file", str(tmp_path), "--db-path", tmp_db])
        assert result.exit_code != 0

    def test_local_dir_rejects_file(self, runner, tmp_db, tmp_path):
        """--local-dir with a file path should fail (file_okay=False)."""
        f = tmp_path / "data.json"
        f.write_text("{}")
        runner.invoke(cli, ["init-db", "--db-path", tmp_db])
        result = runner.invoke(cli, ["ingest", "--local-dir", str(f), "--db-path", tmp_db])
        assert result.exit_code != 0
