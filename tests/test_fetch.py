"""Tests for fetch pipeline — BlobSource protocol, LocalFetcher, GCSFetcher, checkpointing."""

import json
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from tests.conftest import SCHEMA_PATH

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fetch_db():
    """In-memory DuckDB with all tables (including ingest_checkpoints)."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_PATH.read_text())
    yield conn
    conn.close()


def _make_audit_event(actor_idx, event_idx):
    """Build a minimal valid GCP audit log JSON object."""
    return {
        "protoPayload": {
            "serviceName": "storage.googleapis.com",
            "methodName": "storage.objects.get",
            "authenticationInfo": {
                "principalEmail": f"sa-{actor_idx}@project.iam.gserviceaccount.com"
            },
            "resourceName": f"projects/_/buckets/data-bucket/objects/file-{actor_idx}-{event_idx}.csv",
            "status": {},
        },
        "resource": {"type": "gcs_bucket", "labels": {"project_id": "test-project"}},
        "timestamp": f"2026-03-22T{actor_idx:02d}:{event_idx:02d}:00.000Z",
        "insertId": f"insert-{actor_idx}-{event_idx}",
        "logName": "projects/test-project/logs/cloudaudit.googleapis.com%2Fdata_access",
    }


@pytest.fixture
def audit_log_dir(tmp_path):
    """Temp directory with 3 sample audit log JSONL files, 3 events each."""
    for i, name in enumerate(
        ["2026-03-22_00.json", "2026-03-22_01.json", "2026-03-22_02.json"]
    ):
        events = [_make_audit_event(i, j) for j in range(3)]
        (tmp_path / name).write_text("\n".join(json.dumps(e) for e in events))
    return tmp_path


# ---------------------------------------------------------------------------
# LocalFetcher tests
# ---------------------------------------------------------------------------


class TestLocalFetcher:
    def test_list_blobs_returns_sorted_filenames(self, audit_log_dir):
        from src.ingest.fetch import LocalFetcher

        fetcher = LocalFetcher(str(audit_log_dir))
        blobs = fetcher.list_blobs()
        assert blobs == [
            "2026-03-22_00.json",
            "2026-03-22_01.json",
            "2026-03-22_02.json",
        ]

    def test_list_blobs_empty_directory(self, tmp_path):
        from src.ingest.fetch import LocalFetcher

        fetcher = LocalFetcher(str(tmp_path))
        assert fetcher.list_blobs() == []

    def test_list_blobs_with_prefix_filter(self, audit_log_dir):
        from src.ingest.fetch import LocalFetcher

        fetcher = LocalFetcher(str(audit_log_dir))
        blobs = fetcher.list_blobs(prefix="2026-03-22_01")
        assert blobs == ["2026-03-22_01.json"]

    def test_read_blob_returns_content(self, audit_log_dir):
        from src.ingest.fetch import LocalFetcher

        fetcher = LocalFetcher(str(audit_log_dir))
        content = fetcher.read_blob("2026-03-22_00.json")
        lines = content.strip().split("\n")
        assert len(lines) == 3
        parsed = json.loads(lines[0])
        assert "protoPayload" in parsed

    def test_read_blob_nonexistent_raises(self, audit_log_dir):
        from src.ingest.fetch import LocalFetcher

        fetcher = LocalFetcher(str(audit_log_dir))
        with pytest.raises(FileNotFoundError):
            fetcher.read_blob("nonexistent.json")

    def test_list_blobs_ignores_non_json(self, tmp_path):
        (tmp_path / "readme.txt").write_text("ignore me")
        (tmp_path / "data.json").write_text("{}")

        from src.ingest.fetch import LocalFetcher

        fetcher = LocalFetcher(str(tmp_path))
        assert fetcher.list_blobs() == ["data.json"]

    def test_file_path_raises_valueerror(self, tmp_path):
        file_path = tmp_path / "some_file.json"
        file_path.write_text("{}")

        from src.ingest.fetch import LocalFetcher

        with pytest.raises(ValueError, match="not a directory"):
            LocalFetcher(str(file_path))


# ---------------------------------------------------------------------------
# Checkpoint tests
# ---------------------------------------------------------------------------


class TestCheckpoints:
    def test_get_checkpoint_returns_none_when_empty(self, fetch_db):
        from src.ingest.fetch import get_checkpoint

        assert get_checkpoint(fetch_db, "my-bucket") is None

    def test_set_and_get_checkpoint(self, fetch_db):
        from src.ingest.fetch import get_checkpoint, set_checkpoint

        set_checkpoint(fetch_db, "my-bucket", "file-003.json")
        result = get_checkpoint(fetch_db, "my-bucket")
        assert result == "file-003.json"

    def test_set_checkpoint_updates_existing(self, fetch_db):
        from src.ingest.fetch import get_checkpoint, set_checkpoint

        set_checkpoint(fetch_db, "my-bucket", "file-001.json")
        set_checkpoint(fetch_db, "my-bucket", "file-005.json")
        assert get_checkpoint(fetch_db, "my-bucket") == "file-005.json"

    def test_checkpoints_are_per_source(self, fetch_db):
        from src.ingest.fetch import get_checkpoint, set_checkpoint

        set_checkpoint(fetch_db, "bucket-a", "a-003.json")
        set_checkpoint(fetch_db, "bucket-b", "b-007.json")
        assert get_checkpoint(fetch_db, "bucket-a") == "a-003.json"
        assert get_checkpoint(fetch_db, "bucket-b") == "b-007.json"


# ---------------------------------------------------------------------------
# fetch_and_ingest integration tests
# ---------------------------------------------------------------------------


class TestFetchAndIngest:
    def test_ingests_all_blobs_from_scratch(self, fetch_db, audit_log_dir):
        from src.ingest.fetch import LocalFetcher, fetch_and_ingest

        fetcher = LocalFetcher(str(audit_log_dir))
        stats = fetch_and_ingest(fetch_db, fetcher, source_id="test-local")
        # 3 files x 3 events = 9 events
        assert stats["inserted"] == 9
        assert stats["skipped"] == 0
        assert stats["blobs_processed"] == 3

    def test_checkpoint_skips_already_processed(self, fetch_db, audit_log_dir):
        from src.ingest.fetch import LocalFetcher, fetch_and_ingest, set_checkpoint

        # Pretend we already processed the first file
        set_checkpoint(fetch_db, "test-local", "2026-03-22_00.json")

        fetcher = LocalFetcher(str(audit_log_dir))
        stats = fetch_and_ingest(fetch_db, fetcher, source_id="test-local")
        # Should only process files after the checkpoint (2 files x 3 events)
        assert stats["blobs_processed"] == 2
        assert stats["inserted"] == 6

    def test_checkpoint_updated_after_ingest(self, fetch_db, audit_log_dir):
        from src.ingest.fetch import LocalFetcher, fetch_and_ingest, get_checkpoint

        fetcher = LocalFetcher(str(audit_log_dir))
        fetch_and_ingest(fetch_db, fetcher, source_id="test-local")
        # Should be set to the last blob processed
        assert get_checkpoint(fetch_db, "test-local") == "2026-03-22_02.json"

    def test_idempotent_reingest(self, fetch_db, audit_log_dir):
        from src.ingest.fetch import LocalFetcher, fetch_and_ingest

        fetcher = LocalFetcher(str(audit_log_dir))
        stats1 = fetch_and_ingest(fetch_db, fetcher, source_id="test-local")
        stats2 = fetch_and_ingest(fetch_db, fetcher, source_id="test-local")
        assert stats1["inserted"] == 9
        # Second run: checkpoint means 0 blobs to process
        assert stats2["blobs_processed"] == 0
        assert stats2["inserted"] == 0

    def test_empty_source_returns_zero_stats(self, fetch_db, tmp_path):
        from src.ingest.fetch import LocalFetcher, fetch_and_ingest

        fetcher = LocalFetcher(str(tmp_path))
        stats = fetch_and_ingest(fetch_db, fetcher, source_id="empty")
        assert stats["blobs_processed"] == 0
        assert stats["inserted"] == 0

    def test_parse_errors_counted_not_fatal(self, fetch_db, tmp_path):
        """A blob with invalid JSON lines should count errors but not crash."""
        from src.ingest.fetch import LocalFetcher, fetch_and_ingest

        valid_event = _make_audit_event(0, 0)
        f = tmp_path / "mixed.json"
        f.write_text(json.dumps(valid_event) + "\n" + "NOT VALID JSON\n")

        fetcher = LocalFetcher(str(tmp_path))
        stats = fetch_and_ingest(fetch_db, fetcher, source_id="mixed")
        assert stats["inserted"] == 1
        assert stats["parse_errors"] == 1
        assert stats["blobs_processed"] == 1


# ---------------------------------------------------------------------------
# SingleFileFetcher tests
# ---------------------------------------------------------------------------


class TestSingleFileFetcher:
    def test_list_blobs_returns_filename(self, tmp_path):
        from src.ingest.fetch import SingleFileFetcher

        f = tmp_path / "data.jsonl"
        f.write_text("{}\n")
        fetcher = SingleFileFetcher(str(f))
        assert fetcher.list_blobs() == ["data.jsonl"]

    def test_list_blobs_prefix_filter(self, tmp_path):
        from src.ingest.fetch import SingleFileFetcher

        f = tmp_path / "data.jsonl"
        f.write_text("{}\n")
        fetcher = SingleFileFetcher(str(f))
        assert fetcher.list_blobs(prefix="data") == ["data.jsonl"]
        assert fetcher.list_blobs(prefix="other") == []

    def test_read_blob_returns_content(self, tmp_path):
        from src.ingest.fetch import SingleFileFetcher

        f = tmp_path / "data.jsonl"
        f.write_text('{"key": "value"}\n')
        fetcher = SingleFileFetcher(str(f))
        assert fetcher.read_blob("data.jsonl") == '{"key": "value"}\n'

    def test_read_blob_wrong_name_raises(self, tmp_path):
        from src.ingest.fetch import SingleFileFetcher

        f = tmp_path / "data.jsonl"
        f.write_text("{}\n")
        fetcher = SingleFileFetcher(str(f))
        with pytest.raises(FileNotFoundError):
            fetcher.read_blob("other.jsonl")

    def test_nonexistent_file_raises(self):
        from src.ingest.fetch import SingleFileFetcher

        with pytest.raises(FileNotFoundError):
            SingleFileFetcher("/nonexistent/file.jsonl")


# ---------------------------------------------------------------------------
# GCSFetcher tests (mocked — no real GCS calls)
# ---------------------------------------------------------------------------


class TestGCSFetcher:
    def test_conforms_to_blobsource_protocol(self):
        from src.ingest.fetch import BlobSource, GCSFetcher

        with patch("google.cloud.storage.Client") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            fetcher = GCSFetcher("test-bucket")
            assert isinstance(fetcher, BlobSource)

    def test_list_blobs_returns_sorted_names(self):
        from src.ingest.fetch import GCSFetcher

        with patch("google.cloud.storage.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_bucket = MagicMock()
            mock_client.bucket.return_value = mock_bucket

            # Simulate unsorted blob listing
            blob_c = MagicMock()
            blob_c.name = "c.json"
            blob_a = MagicMock()
            blob_a.name = "a.json"
            blob_b = MagicMock()
            blob_b.name = "b.json"
            mock_bucket.list_blobs.return_value = [blob_c, blob_a, blob_b]

            fetcher = GCSFetcher("test-bucket")
            result = fetcher.list_blobs()
            assert result == ["a.json", "b.json", "c.json"]
            mock_bucket.list_blobs.assert_called_once_with(prefix=None)

    def test_list_blobs_with_prefix(self):
        from src.ingest.fetch import GCSFetcher

        with patch("google.cloud.storage.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_bucket = MagicMock()
            mock_client.bucket.return_value = mock_bucket
            mock_bucket.list_blobs.return_value = []

            fetcher = GCSFetcher("test-bucket")
            fetcher.list_blobs(prefix="2026-03")
            mock_bucket.list_blobs.assert_called_once_with(prefix="2026-03")

    def test_read_blob_returns_text(self):
        from src.ingest.fetch import GCSFetcher

        with patch("google.cloud.storage.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_bucket = MagicMock()
            mock_client.bucket.return_value = mock_bucket
            mock_blob = MagicMock()
            mock_bucket.blob.return_value = mock_blob
            mock_blob.download_as_text.return_value = '{"event": "data"}\n'

            fetcher = GCSFetcher("test-bucket")
            content = fetcher.read_blob("file.json")
            assert content == '{"event": "data"}\n'
            mock_bucket.blob.assert_called_once_with("file.json")

    def test_read_blob_nonexistent_raises_filenotfounderror(self):
        from src.ingest.fetch import GCSFetcher

        with patch("google.cloud.storage.Client") as mock_client_cls:
            from google.cloud.exceptions import NotFound

            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_bucket = MagicMock()
            mock_client.bucket.return_value = mock_bucket
            mock_blob = MagicMock()
            mock_bucket.blob.return_value = mock_blob
            mock_blob.download_as_text.side_effect = NotFound("not found")

            fetcher = GCSFetcher("test-bucket")
            with pytest.raises(FileNotFoundError):
                fetcher.read_blob("nonexistent.json")
