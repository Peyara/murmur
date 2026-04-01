"""Tests for world model zone flux graph layer."""

import json
import math
from datetime import datetime, timedelta

from src.world.graph import (
    compute_zone_flux,
    schnakenberg_entropy,
    build_flux_matrix,
    ZONE_COUNT,
)


W1 = datetime(2026, 3, 28, 10, 0, 0)


def _zeros():
    """6x6 zero matrix."""
    return [[0.0] * ZONE_COUNT for _ in range(ZONE_COUNT)]


def _insert_edge(db, window_start, actor_id, src, tgt, target_id, count, is_new=False):
    """Insert an edge directly into edges_window."""
    db.execute(
        "INSERT INTO edges_window (window_start, actor_id, source_zone, target_zone, "
        "target_id, edge_count, first_seen, is_new_30d) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [window_start, actor_id, src, tgt, target_id, count, window_start, is_new],
    )


# --- schnakenberg_entropy (pure function) ---


class TestSchnakenbergEntropy:
    def test_symmetric_zero(self):
        """Equal forward/reverse flows -> sigma = 0 (equilibrium)."""
        m = _zeros()
        m[0][1] = 5.0
        m[1][0] = 5.0
        assert schnakenberg_entropy(m, {}) == 0.0

    def test_hand_calculated(self):
        """Known asymmetric case: J_01=10, J_10=2."""
        m = _zeros()
        m[0][1] = 10.0
        m[1][0] = 2.0
        # sigma = (10-2) * ln(10/2) = 8 * ln(5) = 8 * 1.6094...
        expected = 8.0 * math.log(10.0 / 2.0)
        assert abs(schnakenberg_entropy(m, {}) - expected) < 1e-9

    def test_zero_flux_skipped(self):
        """Pair with zero in one direction -> no crash, contribution = 0."""
        m = _zeros()
        m[0][1] = 5.0  # one direction only
        m[1][0] = 0.0
        assert schnakenberg_entropy(m, {}) == 0.0

    def test_all_zeros(self):
        assert schnakenberg_entropy(_zeros(), {}) == 0.0

    def test_multiple_pairs(self):
        """Two active pairs: (0,1) and (2,3)."""
        m = _zeros()
        m[0][1] = 10.0
        m[1][0] = 2.0
        m[2][3] = 8.0
        m[3][2] = 4.0
        s01 = (10.0 - 2.0) * math.log(10.0 / 2.0)
        s23 = (8.0 - 4.0) * math.log(8.0 / 4.0)
        assert abs(schnakenberg_entropy(m, {}) - (s01 + s23)) < 1e-9


class TestTieredConfidence:
    def test_cold_pair_zero_contribution(self):
        """<5 observations -> contribution = 0."""
        m = _zeros()
        m[0][1] = 10.0
        m[1][0] = 2.0
        obs = {(0, 1): 3}  # Cold
        assert schnakenberg_entropy(m, obs) == 0.0

    def test_warm_pair_half_weight(self):
        """5-50 observations -> contribution * 0.5."""
        m = _zeros()
        m[0][1] = 10.0
        m[1][0] = 2.0
        obs = {(0, 1): 25}  # Warm
        full = (10.0 - 2.0) * math.log(10.0 / 2.0)
        assert abs(schnakenberg_entropy(m, obs) - full * 0.5) < 1e-9

    def test_calibrated_pair_full_weight(self):
        """>50 observations -> full contribution."""
        m = _zeros()
        m[0][1] = 10.0
        m[1][0] = 2.0
        obs = {(0, 1): 100}  # Calibrated
        full = (10.0 - 2.0) * math.log(10.0 / 2.0)
        assert abs(schnakenberg_entropy(m, obs) - full) < 1e-9

    def test_no_obs_counts_means_calibrated(self):
        """When obs_counts is empty dict, all pairs treated as calibrated (no tier data)."""
        m = _zeros()
        m[0][1] = 10.0
        m[1][0] = 2.0
        full = (10.0 - 2.0) * math.log(10.0 / 2.0)
        assert abs(schnakenberg_entropy(m, {}) - full) < 1e-9

    def test_mixed_tiers(self):
        """Cold pair ignored, calibrated pair contributes fully."""
        m = _zeros()
        m[0][1] = 10.0  # Cold
        m[1][0] = 2.0
        m[2][3] = 8.0  # Calibrated
        m[3][2] = 4.0
        obs = {(0, 1): 3, (2, 3): 100}
        s23 = (8.0 - 4.0) * math.log(8.0 / 4.0)
        assert abs(schnakenberg_entropy(m, obs) - s23) < 1e-9


# --- build_flux_matrix ---


class TestBuildFluxMatrix:
    def test_empty_edges(self, db):
        matrix = build_flux_matrix(db, W1)
        assert matrix == _zeros()

    def test_single_edge(self, db):
        # SECRET=2, DATA=3 in ZONE_ORDER (CONTROL=0, IDENTITY=1, SECRET=2, DATA=3, COMPUTE=4, EXFIL_RISK=5)
        _insert_edge(db, W1, "sa@proj", "SECRET", "DATA", "t1", 5)
        matrix = build_flux_matrix(db, W1)
        assert matrix[2][3] == 5.0

    def test_multiple_actors_summed(self, db):
        _insert_edge(db, W1, "alice@proj", "SECRET", "DATA", "t1", 3)
        _insert_edge(db, W1, "bob@proj", "SECRET", "DATA", "t2", 7)
        matrix = build_flux_matrix(db, W1)
        assert matrix[2][3] == 10.0

    def test_self_loop_on_diagonal(self, db):
        _insert_edge(db, W1, "sa@proj", "DATA", "DATA", "t1", 4)
        matrix = build_flux_matrix(db, W1)
        assert matrix[3][3] == 4.0


# --- compute_zone_flux (integration) ---


class TestComputeZoneFlux:
    def test_inserts_row(self, db):
        _insert_edge(db, W1, "sa@proj", "SECRET", "DATA", "t1", 5)
        _insert_edge(db, W1, "sa@proj", "DATA", "SECRET", "t2", 3)
        result = compute_zone_flux(db, W1)
        assert result is not None

        row = db.execute(
            "SELECT flux_matrix, sigma_coarse, bridge_count FROM zone_flux_windows "
            "WHERE window_start = ?",
            [W1],
        ).fetchone()
        assert row is not None
        matrix = json.loads(row[0])
        assert matrix[2][3] == 5.0  # SECRET->DATA
        assert matrix[3][2] == 3.0  # DATA->SECRET
        # sigma > 0 for asymmetric flow
        assert row[1] > 0

    def test_bridge_count_new_cross_zone(self, db):
        _insert_edge(db, W1, "sa@proj", "SECRET", "DATA", "t1", 1, is_new=True)
        _insert_edge(db, W1, "sa@proj", "DATA", "DATA", "t2", 1, is_new=True)  # self-loop, not a bridge
        compute_zone_flux(db, W1)
        row = db.execute(
            "SELECT bridge_count FROM zone_flux_windows WHERE window_start = ?", [W1]
        ).fetchone()
        assert row[0] == 1  # only the cross-zone edge

    def test_bridge_count_old_edges_excluded(self, db):
        _insert_edge(db, W1, "sa@proj", "SECRET", "DATA", "t1", 1, is_new=False)
        compute_zone_flux(db, W1)
        row = db.execute(
            "SELECT bridge_count FROM zone_flux_windows WHERE window_start = ?", [W1]
        ).fetchone()
        assert row[0] == 0

    def test_net_currents(self, db):
        _insert_edge(db, W1, "sa@proj", "SECRET", "DATA", "t1", 10)
        _insert_edge(db, W1, "sa@proj", "DATA", "SECRET", "t2", 3)
        compute_zone_flux(db, W1)
        row = db.execute(
            "SELECT net_currents FROM zone_flux_windows WHERE window_start = ?", [W1]
        ).fetchone()
        nets = json.loads(row[0])
        # SECRET(2) < DATA(3), so pair key is "2_3", net = flux[2][3] - flux[3][2] = 10 - 3 = 7
        assert nets["2_3"] == 7.0

    def test_empty_edges_zero_sigma(self, db):
        compute_zone_flux(db, W1)
        row = db.execute(
            "SELECT sigma_coarse FROM zone_flux_windows WHERE window_start = ?", [W1]
        ).fetchone()
        assert row[0] == 0.0
