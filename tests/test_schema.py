"""Tests for DuckDB schema creation and CanonicalEvent dataclass."""

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

EXPECTED_TABLES = [
    "events",
    "sanctioned_patterns",
    "actor_windows",
    "zone_flux_windows",
    "edges_window",
    "risk_scores",
    "closure_state",
    "opening_closing_pairs",
    "policy_suggestions",
    "candidate_patterns",
]


@pytest.fixture
def db():
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_PATH.read_text())
    yield conn
    conn.close()


class TestSchemaCreation:
    def test_schema_executes_without_error(self, db):
        # If we get here, schema.sql ran successfully
        result = db.execute("SELECT 1").fetchone()
        assert result == (1,)

    @pytest.mark.parametrize("table_name", EXPECTED_TABLES)
    def test_table_exists(self, db, table_name):
        tables = [
            row[0]
            for row in db.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        ]
        assert table_name in tables

    def test_all_10_tables_created(self, db):
        tables = db.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main'"
        ).fetchall()
        assert len(tables) == 10

    def test_events_table_has_primary_key(self, db):
        # Inserting duplicate event_id should fail
        db.execute(
            "INSERT INTO events (event_id, ts, window_start, actor_id, "
            "actor_type, action_type, target_id, target_type, target_zone) "
            "VALUES ('e1', '2026-01-01', '2026-01-01', 'a1', 'HUMAN', "
            "'OTHER', 't1', 'OTHER', 'DATA')"
        )
        with pytest.raises(duckdb.ConstraintException):
            db.execute(
                "INSERT INTO events (event_id, ts, window_start, actor_id, "
                "actor_type, action_type, target_id, target_type, target_zone) "
                "VALUES ('e1', '2026-01-01', '2026-01-01', 'a1', 'HUMAN', "
                "'OTHER', 't1', 'OTHER', 'DATA')"
            )


class TestCanonicalEvent:
    def test_create_with_required_fields(self):
        event = CanonicalEvent(
            event_id="test-001",
            ts=datetime(2026, 3, 22, 10, 0, 0),
            window_start=datetime(2026, 3, 22, 10, 0, 0),
            actor_id="user@example.com",
            actor_type=ActorType.HUMAN,
            action_type=ActionType.SECRET_ACCESS,
            target_id="projects/p1/secrets/secret_high",
            target_type=TargetType.SECRET,
            target_zone=TargetZone.SECRET,
        )
        assert event.event_id == "test-001"
        assert event.action_type == ActionType.SECRET_ACCESS
        assert event.target_zone == TargetZone.SECRET

    def test_defaults(self):
        event = CanonicalEvent(
            event_id="test-002",
            ts=datetime(2026, 1, 1),
            window_start=datetime(2026, 1, 1),
            actor_id="sa@proj.iam.gserviceaccount.com",
            actor_type=ActorType.SERVICE_ACCOUNT,
            action_type=ActionType.OTHER,
            target_id="some-resource",
            target_type=TargetType.OTHER,
            target_zone=TargetZone.DATA,
        )
        assert event.result == EventResult.SUCCESS
        assert event.provenance_level == ProvenanceLevel.NONE
        assert event.provenance_source == ProvenanceSource.UNKNOWN
        assert event.is_deploy is False
        assert event.is_incident is False
        assert event.coverage_flag is True
        assert event.trigger_ref is None
        assert event.actor_subtype is None
        assert event.env == "sandbox"

    def test_optional_fields(self):
        event = CanonicalEvent(
            event_id="test-003",
            ts=datetime(2026, 1, 1),
            window_start=datetime(2026, 1, 1),
            actor_id="actor",
            actor_type=ActorType.HUMAN,
            action_type=ActionType.IAM_SET_POLICY,
            target_id="target",
            target_type=TargetType.IAM_POLICY,
            target_zone=TargetZone.CONTROL,
            trigger_ref="sched-exec-123",
            provenance_level=ProvenanceLevel.WEAK,
            provenance_source=ProvenanceSource.CLOUD_SCHEDULER,
            actor_subtype=None,
            tool_name=None,
            model_id=None,
        )
        assert event.provenance_level == ProvenanceLevel.WEAK
        assert event.trigger_ref == "sched-exec-123"


class TestEnums:
    def test_action_type_has_13_members(self):
        assert len(ActionType) == 13

    def test_target_zone_has_6_members(self):
        assert len(TargetZone) == 6

    def test_provenance_level_has_3_members(self):
        assert len(ProvenanceLevel) == 3

    def test_str_enum_values(self):
        # str Enum members should be usable as strings (for DuckDB storage)
        assert ActionType.IAM_SET_POLICY == "IAM_SET_POLICY"
        assert TargetZone.EXFIL_RISK == "EXFIL_RISK"
        assert ProvenanceLevel.WEAK == "WEAK"
