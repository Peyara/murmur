"""Shared test fixtures for Murmur."""

from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from src.schema import (
    ActionType,
    ActorType,
    CanonicalEvent,
    EventResult,
    ProvenanceLevel,
    ProvenanceSource,
    TargetType,
    TargetZone,
)

SCHEMA_PATH = Path(__file__).parent.parent / "sql" / "schema.sql"


@pytest.fixture
def db():
    """In-memory DuckDB with all tables created from schema.sql."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_PATH.read_text())
    yield conn
    conn.close()


def make_event(**overrides) -> CanonicalEvent:
    """Factory for CanonicalEvent with sensible defaults. Override any field via kwargs."""
    defaults = dict(
        event_id="evt-test-001",
        ts=datetime(2026, 3, 22, 10, 5, 0),
        window_start=datetime(2026, 3, 22, 10, 0, 0),
        actor_id="test-sa@project.iam.gserviceaccount.com",
        actor_type=ActorType.SERVICE_ACCOUNT,
        action_type=ActionType.OTHER,
        target_id="projects/test-project/some-resource",
        target_type=TargetType.OTHER,
        target_zone=TargetZone.DATA,
        result=EventResult.SUCCESS,
        provenance_level=ProvenanceLevel.NONE,
        provenance_source=ProvenanceSource.UNKNOWN,
        correlation_confidence=0.0,
        env="sandbox",
        is_deploy=False,
        is_incident=False,
        is_infrastructure=False,
        risk_tags="[]",
        coverage_flag=True,
    )
    defaults.update(overrides)
    return CanonicalEvent(**defaults)
