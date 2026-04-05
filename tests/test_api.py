"""API endpoint tests — validates all 5 endpoints with seeded DuckDB data."""

import json
from datetime import datetime

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.report.api import _THRESHOLDS, _router
from src.report.db import get_db
from src.report.models import ZONE_ORDER

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SCHEMA_PATH = "sql/schema.sql"
W1 = datetime(2026, 4, 3, 20, 0, 0)  # calm window
W2 = datetime(2026, 4, 3, 20, 15, 0)  # calm window
W3 = datetime(2026, 4, 3, 21, 15, 0)  # attack window


@pytest.fixture
def seeded_db():
    """In-memory DuckDB seeded with events, windows, and risk scores."""
    conn = duckdb.connect(":memory:")
    with open(SCHEMA_PATH) as f:
        conn.execute(f.read())

    # Zone flux windows
    calm_flux = json.dumps([[0.0] * 6 for _ in range(6)])
    attack_flux = [[0.0] * 6 for _ in range(6)]
    attack_flux[1][2] = 5.0  # IDENTITY -> SECRET flow
    attack_flux_json = json.dumps(attack_flux)

    for w, sigma, flux, bridges in [
        (W1, 0.18, calm_flux, 0),
        (W2, 0.20, calm_flux, 0),
        (W3, 3.01, attack_flux_json, 2),
    ]:
        conn.execute(
            "INSERT INTO zone_flux_windows (window_start, flux_matrix, sigma_coarse, bridge_count) "
            "VALUES (?, ?, ?, ?)",
            [w, flux, sigma, bridges],
        )

    # Actor windows + risk scores — normal actor
    for w in [W1, W2, W3]:
        conn.execute(
            "INSERT INTO actor_windows (window_start, actor_id, event_count, "
            "zone_sequence, provenance_level, pattern_match_score) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [w, "normal-sa@proj.iam", 4, '["DATA"]', "WEAK", 0.85],
        )
        conn.execute(
            "INSERT INTO risk_scores (window_start, actor_id, inv_score, inv_count, sigma_coarse, "
            "novelty_score, bridge_new, delta_f, fusion_raw, residual_risk, fired_invariants, explanation) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [w, "normal-sa@proj.iam", 0.0, 0, 0.18, 0.0, 0, 0.0, 0.05, 0.05, "[]", "no invariants fired"],
        )

    # Actor windows + risk scores — attacker (only in W3)
    conn.execute(
        "INSERT INTO actor_windows (window_start, actor_id, event_count, "
        "zone_sequence, provenance_level, pattern_match_score) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [W3, "attacker-sa@proj.iam", 7, '["IDENTITY", "SECRET", "EXFIL_RISK"]', "NONE", 0.0],
    )
    conn.execute(
        "INSERT INTO risk_scores (window_start, actor_id, inv_score, inv_count, sigma_coarse, "
        "novelty_score, bridge_new, delta_f, fusion_raw, residual_risk, fired_invariants, explanation) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [W3, "attacker-sa@proj.iam", 5.0, 3, 3.01, 8.5, 2, 2.8, 0.87, 0.87,
         '["INV_002", "INV_006", "INV_010"]', "Key created; Novel secret access; New sensitive edge"],
    )

    # Edges — attacker in W3
    conn.execute(
        "INSERT INTO edges_window (window_start, actor_id, source_zone, "
        "target_zone, target_id, edge_count, is_new_30d) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [W3, "attacker-sa@proj.iam", "IDENTITY", "SECRET", "secret_high", 3, True],
    )
    conn.execute(
        "INSERT INTO edges_window (window_start, actor_id, source_zone, "
        "target_zone, target_id, edge_count, is_new_30d) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [W3, "normal-sa@proj.iam", "DATA", "DATA", "some-bucket", 4, False],
    )

    # Events — minimal for zone counts
    for i, (zone, actor) in enumerate([
        ("IDENTITY", "attacker-sa@proj.iam"),
        ("SECRET", "attacker-sa@proj.iam"),
        ("SECRET", "attacker-sa@proj.iam"),
        ("DATA", "normal-sa@proj.iam"),
        ("DATA", "normal-sa@proj.iam"),
    ]):
        conn.execute(
            "INSERT INTO events (event_id, ts, window_start, actor_id, actor_type, action_type, "
            "target_id, target_type, target_zone, result) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [f"evt-{i}", W3, W3, actor, "SERVICE_ACCOUNT", "OTHER",
             f"resource-{i}", "OTHER", zone, "SUCCESS"],
        )

    yield conn
    conn.close()


@pytest.fixture
def client(seeded_db):
    """FastAPI test client with injected DuckDB connection."""
    app = FastAPI()
    app.include_router(_router)

    # Override the db dependency to return our seeded connection
    app.dependency_overrides[get_db] = lambda: seeded_db

    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPulse:
    def test_returns_200(self, client):
        r = client.get("/api/pulse")
        assert r.status_code == 200

    def test_response_shape(self, client):
        data = client.get("/api/pulse").json()
        assert data["status"] in ("NORMAL", "WATCH", "MEDIUM", "HIGH")
        assert len(data["flux_matrix"]) == 6
        assert all(len(row) == 6 for row in data["flux_matrix"])
        assert set(data["tier_counts"].keys()) == {"HIGH", "MEDIUM", "WATCH", "NORMAL"}
        assert data["zone_names"] == ZONE_ORDER

    def test_latest_window_selected(self, client):
        data = client.get("/api/pulse").json()
        # W3 is the latest window and has the attacker
        assert data["sigma_coarse"] == pytest.approx(3.01)
        assert data["bridge_count"] == 2

    def test_tier_counts_sum(self, client):
        data = client.get("/api/pulse").json()
        total = sum(data["tier_counts"].values())
        assert total == len(data["top_actors"])

    def test_top_actors_ordered_by_risk(self, client):
        data = client.get("/api/pulse").json()
        risks = [a["residual_risk"] for a in data["top_actors"]]
        assert risks == sorted(risks, reverse=True)

    def test_trend_has_multiple_windows(self, client):
        data = client.get("/api/pulse").json()
        assert len(data["trend"]) >= 2


class TestZones:
    def test_returns_200(self, client):
        r = client.get("/api/zones")
        assert r.status_code == 200

    def test_all_zones_present(self, client):
        data = client.get("/api/zones").json()
        zone_ids = [n["id"] for n in data["nodes"]]
        assert zone_ids == ZONE_ORDER

    def test_flux_matrix_6x6(self, client):
        data = client.get("/api/zones").json()
        assert len(data["flux_matrix"]) == 6
        assert all(len(row) == 6 for row in data["flux_matrix"])

    def test_connections_have_actors(self, client):
        data = client.get("/api/zones").json()
        for conn in data["connections"]:
            assert len(conn["actors"]) > 0

    def test_new_edge_flag(self, client):
        data = client.get("/api/zones").json()
        identity_secret = [
            c for c in data["connections"]
            if c["source"] == "IDENTITY" and c["target"] == "SECRET"
        ]
        assert len(identity_secret) == 1
        assert identity_secret[0]["has_new_edge"] is True

    def test_explicit_window_param(self, client):
        data = client.get("/api/zones", params={"window": W1.isoformat()}).json()
        # W1 has no edges, no events in our seed data
        assert data["sigma_coarse"] == pytest.approx(0.18)


class TestActors:
    def test_returns_200(self, client):
        r = client.get("/api/actors")
        assert r.status_code == 200

    def test_default_latest_window(self, client):
        data = client.get("/api/actors").json()
        # Latest window (W3) has 2 actors
        assert len(data["actors"]) == 2

    def test_actors_have_alert_tier(self, client):
        data = client.get("/api/actors").json()
        for actor in data["actors"]:
            assert actor["alert_tier"] in ("NORMAL", "WATCH", "MEDIUM", "HIGH")

    def test_zone_filter(self, client):
        data = client.get("/api/actors", params={"zone": "SECRET"}).json()
        # Only attacker has SECRET in zone_sequence
        assert len(data["actors"]) == 1
        assert data["actors"][0]["actor_id"] == "attacker-sa@proj.iam"

    def test_attacker_has_fired_invariants(self, client):
        data = client.get("/api/actors").json()
        attacker = [a for a in data["actors"] if "attacker" in a["actor_id"]][0]
        assert len(attacker["fired_invariants"]) == 3
        assert "INV_002" in attacker["fired_invariants"]


class TestAlerts:
    def test_returns_200(self, client):
        r = client.get("/api/alerts")
        assert r.status_code == 200

    def test_only_above_threshold(self, client):
        data = client.get("/api/alerts").json()
        for alert in data["alerts"]:
            assert alert["residual_risk"] >= _THRESHOLDS["WATCH"]

    def test_total_matches_list(self, client):
        data = client.get("/api/alerts").json()
        assert data["total"] == len(data["alerts"])


class TestTimeline:
    def test_returns_200(self, client):
        r = client.get("/api/timeline", params={"hours": 720})
        assert r.status_code == 200

    def test_ordered_by_window(self, client):
        data = client.get("/api/timeline", params={"hours": 720}).json()
        windows = [p["window_start"] for p in data["points"]]
        assert windows == sorted(windows)

    def test_actor_filter(self, client):
        data = client.get("/api/timeline", params={"hours": 720, "actor": "attacker-sa@proj.iam"}).json()
        actors = {p["actor_id"] for p in data["points"]}
        assert actors == {"attacker-sa@proj.iam"}

    def test_hours_returned(self, client):
        data = client.get("/api/timeline", params={"hours": 48}).json()
        assert data["hours"] == 48


class TestEmptyDB:
    """Endpoints should handle an empty database gracefully."""

    @pytest.fixture
    def empty_client(self):
        conn = duckdb.connect(":memory:")
        with open(SCHEMA_PATH) as f:
            conn.execute(f.read())

        app = FastAPI()
        app.include_router(_router)
        app.dependency_overrides[get_db] = lambda: conn

        yield TestClient(app)
        conn.close()

    def test_pulse_empty(self, empty_client):
        r = empty_client.get("/api/pulse")
        assert r.status_code == 200
        assert r.json()["status"] == "NORMAL"
        assert r.json()["window_start"] is None

    def test_zones_empty(self, empty_client):
        r = empty_client.get("/api/zones")
        assert r.status_code == 200
        assert r.json()["nodes"] == []

    def test_actors_empty(self, empty_client):
        r = empty_client.get("/api/actors")
        assert r.status_code == 200
        assert r.json()["actors"] == []

    def test_alerts_empty(self, empty_client):
        r = empty_client.get("/api/alerts")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_timeline_empty(self, empty_client):
        r = empty_client.get("/api/timeline")
        assert r.status_code == 200
        assert r.json()["points"] == []
