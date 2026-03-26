"""Tests for provenance enrichment pipeline step."""

from src.ingest.provenance_ingest import enrich_provenance, enrich_provenance_batch
from src.schema import ProvenanceLevel, ProvenanceSource
from tests.conftest import make_event

SCHEDULER_SA = "service-123456@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
BUILD_SA = "123456@cloudbuild.gserviceaccount.com"
KNOWN = {SCHEDULER_SA, BUILD_SA}


class TestEnrichProvenance:
    def test_trigger_ref_with_known_scheduler_sa(self):
        event = make_event(
            trigger_ref="sched-exec-001",
            actor_id=SCHEDULER_SA,
        )
        result = enrich_provenance(event, KNOWN)
        assert result.provenance_level == ProvenanceLevel.WEAK
        assert result.provenance_source == ProvenanceSource.CLOUD_SCHEDULER

    def test_trigger_ref_with_known_build_sa(self):
        event = make_event(
            trigger_ref="build-exec-001",
            actor_id=BUILD_SA,
        )
        result = enrich_provenance(event, KNOWN)
        assert result.provenance_level == ProvenanceLevel.WEAK
        assert result.provenance_source == ProvenanceSource.CLOUD_BUILD

    def test_trigger_ref_with_unknown_actor(self):
        """trigger_ref present but actor not in known_initiators — still WEAK."""
        event = make_event(
            trigger_ref="some-ref",
            actor_id="random-sa@project.iam.gserviceaccount.com",
        )
        result = enrich_provenance(event, KNOWN)
        assert result.provenance_level == ProvenanceLevel.WEAK
        assert result.provenance_source == ProvenanceSource.UNKNOWN

    def test_no_trigger_ref_known_actor(self):
        """Known SA acting without trigger_ref — no proof, stays NONE."""
        event = make_event(
            trigger_ref=None,
            actor_id=SCHEDULER_SA,
        )
        result = enrich_provenance(event, KNOWN)
        assert result.provenance_level == ProvenanceLevel.NONE
        assert result.provenance_source == ProvenanceSource.UNKNOWN

    def test_no_trigger_ref_unknown_actor(self):
        event = make_event(trigger_ref=None, actor_id="attacker@evil.com")
        result = enrich_provenance(event, KNOWN)
        assert result.provenance_level == ProvenanceLevel.NONE
        assert result.provenance_source == ProvenanceSource.UNKNOWN

    def test_empty_known_initiators(self):
        """With empty known set, trigger_ref still grants WEAK but source is UNKNOWN."""
        event = make_event(trigger_ref="ref-001", actor_id=SCHEDULER_SA)
        result = enrich_provenance(event, set())
        assert result.provenance_level == ProvenanceLevel.WEAK
        assert result.provenance_source == ProvenanceSource.UNKNOWN

    def test_does_not_mutate_original(self):
        event = make_event(trigger_ref="ref-001", actor_id=SCHEDULER_SA)
        result = enrich_provenance(event, KNOWN)
        assert event.provenance_level == ProvenanceLevel.NONE
        assert result.provenance_level == ProvenanceLevel.WEAK
        assert event is not result

    def test_preserves_non_provenance_fields(self):
        event = make_event(
            event_id="preserve-001",
            trigger_ref="ref-001",
            actor_id=SCHEDULER_SA,
            target_zone="DATA",
        )
        result = enrich_provenance(event, KNOWN)
        assert result.event_id == "preserve-001"
        assert result.actor_id == SCHEDULER_SA
        assert result.target_zone == event.target_zone


class TestEnrichProvenanceBatch:
    def test_batch_preserves_count(self):
        events = [
            make_event(event_id="b1", trigger_ref="ref-001", actor_id=SCHEDULER_SA),
            make_event(event_id="b2", trigger_ref=None, actor_id="user@example.com"),
            make_event(event_id="b3", trigger_ref="ref-002", actor_id=BUILD_SA),
        ]
        results = enrich_provenance_batch(events, KNOWN)
        assert len(results) == 3

    def test_batch_enriches_each_event(self):
        events = [
            make_event(event_id="b1", trigger_ref="ref-001", actor_id=SCHEDULER_SA),
            make_event(event_id="b2", trigger_ref=None, actor_id="user@example.com"),
        ]
        results = enrich_provenance_batch(events, KNOWN)
        assert results[0].provenance_level == ProvenanceLevel.WEAK
        assert results[0].provenance_source == ProvenanceSource.CLOUD_SCHEDULER
        assert results[1].provenance_level == ProvenanceLevel.NONE
        assert results[1].provenance_source == ProvenanceSource.UNKNOWN


class TestLoadKnownInitiators:
    def test_resolves_project_number_placeholder(self, tmp_path, monkeypatch):
        """PROJECT_NUMBER placeholder in known_initiators.json is resolved from env."""
        config_file = tmp_path / "known_initiators.json"
        config_file.write_text(
            '["service-PROJECT_NUMBER@gcp-sa-cloudscheduler.iam.gserviceaccount.com"]'
        )
        monkeypatch.setenv("GCP_PROJECT_NUMBER", "9876543210")

        from config.settings import MurmurSettings

        settings = MurmurSettings(known_initiators_path=str(config_file))
        result = settings.load_known_initiators()
        assert "service-9876543210@gcp-sa-cloudscheduler.iam.gserviceaccount.com" in result

    def test_placeholder_unresolved_when_env_missing(self, tmp_path, monkeypatch):
        """Without GCP_PROJECT_NUMBER env var, placeholder stays as-is."""
        config_file = tmp_path / "known_initiators.json"
        config_file.write_text(
            '["service-PROJECT_NUMBER@gcp-sa-cloudscheduler.iam.gserviceaccount.com"]'
        )
        monkeypatch.delenv("GCP_PROJECT_NUMBER", raising=False)

        from config.settings import MurmurSettings

        settings = MurmurSettings(known_initiators_path=str(config_file))
        result = settings.load_known_initiators()
        assert "service-PROJECT_NUMBER@gcp-sa-cloudscheduler.iam.gserviceaccount.com" in result

    def test_non_placeholder_entries_unchanged(self, tmp_path, monkeypatch):
        """Entries without PROJECT_NUMBER are returned as-is."""
        config_file = tmp_path / "known_initiators.json"
        config_file.write_text('["service-123456@gcp-sa-cloudscheduler.iam.gserviceaccount.com"]')
        monkeypatch.setenv("GCP_PROJECT_NUMBER", "9876543210")

        from config.settings import MurmurSettings

        settings = MurmurSettings(known_initiators_path=str(config_file))
        result = settings.load_known_initiators()
        assert "service-123456@gcp-sa-cloudscheduler.iam.gserviceaccount.com" in result
