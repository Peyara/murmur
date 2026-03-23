"""Provenance enrichment — resolves trigger_ref to provenance_level and source.

Pipeline step between parser and dedup:
  raw JSON -> parse_audit_log() -> enrich_provenance() -> insert_event()

The parser extracts trigger_ref from metadata. This module classifies the
provenance source by matching the actor against known initiators (Cloud
Scheduler SAs, Cloud Build SAs) and assigns the appropriate provenance_level.
"""

from dataclasses import replace

from src.schema import CanonicalEvent, ProvenanceLevel, ProvenanceSource

# SA email suffixes used to classify provenance source
_SCHEDULER_SUFFIX = "@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
_BUILD_SUFFIX = "@cloudbuild.gserviceaccount.com"


def _classify_source(actor_id: str, known_initiators: set[str]) -> ProvenanceSource:
    """Classify provenance source from actor identity and known initiators."""
    if actor_id not in known_initiators:
        return ProvenanceSource.UNKNOWN
    if actor_id.endswith(_SCHEDULER_SUFFIX):
        return ProvenanceSource.CLOUD_SCHEDULER
    if actor_id.endswith(_BUILD_SUFFIX):
        return ProvenanceSource.CLOUD_BUILD
    return ProvenanceSource.UNKNOWN


def enrich_provenance(
    event: CanonicalEvent, known_initiators: set[str]
) -> CanonicalEvent:
    """Enrich a parsed event with provenance classification.

    Rules:
    - trigger_ref present: provenance_level=WEAK, source classified by actor
    - trigger_ref absent: provenance_level=NONE, source=UNKNOWN
    """
    if event.trigger_ref is not None:
        source = _classify_source(event.actor_id, known_initiators)
        return replace(
            event,
            provenance_level=ProvenanceLevel.WEAK,
            provenance_source=source,
        )

    return replace(
        event,
        provenance_level=ProvenanceLevel.NONE,
        provenance_source=ProvenanceSource.UNKNOWN,
    )


def enrich_provenance_batch(
    events: list[CanonicalEvent], known_initiators: set[str]
) -> list[CanonicalEvent]:
    """Enrich a batch of events. Convenience wrapper over enrich_provenance."""
    return [enrich_provenance(e, known_initiators) for e in events]
