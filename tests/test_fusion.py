"""Tests for scoring fusion layer."""

from datetime import datetime, timedelta

from src.ingest.dedup import insert_event
from src.schema import ActionType, TargetZone
from src.score.fusion import FUSION_WEIGHTS, compute_fusion, normalize, sigmoid_normalize
from tests.conftest import make_event

W1 = datetime(2026, 3, 28, 10, 0, 0)
KNOWN = {"known-sa@proj"}


def _setup_minimal(db, actor_id="sa@proj"):
    """Insert minimal data for fusion: 1 event, actor_window, edges, flux."""
    insert_event(db, make_event(
        event_id="e1", ts=W1 + timedelta(minutes=1),
        window_start=W1, actor_id=actor_id,
    ))
    db.execute(
        "INSERT INTO actor_windows (window_start, actor_id, event_count, action_types, "
        "zone_sequence, target_ids, burst_per_min, breadth_entropy, provenance_level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [W1, actor_id, 1, '["GCS_READ"]', '["DATA"]', '["t1"]', 1.0, 0.0, "NONE"],
    )
    db.execute(
        "INSERT INTO zone_flux_windows (window_start, flux_matrix, net_currents, "
        "sigma_coarse, bridge_count) VALUES (?, ?, ?, ?, ?)",
        [W1, "[]", "{}", 0.0, 0],
    )


class TestNormalize:
    def test_zero(self):
        assert normalize(0.0, 10.0) == 0.0

    def test_max(self):
        assert normalize(10.0, 10.0) == 1.0

    def test_mid(self):
        assert normalize(5.0, 10.0) == 0.5

    def test_exceeds_max(self):
        """Clips to 1.0."""
        assert normalize(20.0, 10.0) == 1.0

    def test_zero_bound(self):
        """Zero max_bound -> 0.0 (no div by zero)."""
        assert normalize(5.0, 0.0) == 0.0

    def test_negative(self):
        """Negative values clamp to 0.0."""
        assert normalize(-5.0, 10.0) == 0.0


class TestFusion:
    def test_all_zeros(self, db):
        """All signals near zero -> fusion_raw very low (sigma sigmoid has baseline ~0.047)."""
        _setup_minimal(db)
        result = compute_fusion(db, W1, "sa@proj", KNOWN)
        # sigma_coarse sigmoid floor ~0.047 * weight 0.05 = ~0.002, plus small burst
        assert result < 0.02

        row = db.execute(
            "SELECT fusion_raw FROM risk_scores WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert row is not None
        assert row[0] < 0.01

    def test_inv_score_dominant(self, db):
        """High inv_score with other signals zero -> fusion dominated by inv weight."""
        _setup_minimal(db)
        # Insert an IAM_CREATE_KEY event to trigger INV_002 (sev 5)
        insert_event(db, make_event(
            event_id="e2", ts=W1 + timedelta(minutes=2),
            window_start=W1, actor_id="sa@proj",
            action_type=ActionType.IAM_CREATE_KEY,
            target_zone=TargetZone.IDENTITY,
        ))
        result = compute_fusion(db, W1, "sa@proj", KNOWN)
        # inv_score=5 -> normalized 1.0, weight=0.20; inv_count=1 -> normalized 0.1, weight=0.15
        inv_floor = FUSION_WEIGHTS["inv_score"] + FUSION_WEIGHTS["inv_count"] * 0.1
        assert result >= inv_floor * 0.9

    def test_writes_risk_scores_row(self, db):
        """Fusion writes a complete row to risk_scores."""
        _setup_minimal(db)
        compute_fusion(db, W1, "sa@proj", KNOWN)
        row = db.execute(
            "SELECT inv_score, sigma_coarse, novelty_score, bridge_new, "
            "delta_f, burst_per_min, breadth_entropy, fusion_raw, "
            "residual_risk, fired_invariants "
            "FROM risk_scores WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert row is not None
        # residual_risk == fusion_raw (no provenance discount yet)
        assert row[7] == row[8]  # fusion_raw == residual_risk
        assert row[9] is not None  # fired_invariants JSON exists

    def test_weights_sum_to_one(self):
        total = sum(FUSION_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_inv_count_differentiates(self, db):
        """More invariants -> higher fusion score via inv_count signal."""
        from src.score.invariants import InvariantResult, compute_inv_score

        few = [
            InvariantResult("INV_002", True, 5, "a"),
            InvariantResult("INV_003", True, 5, "b"),
        ]
        many = [
            InvariantResult("INV_001", True, 5, "a"),
            InvariantResult("INV_002", True, 5, "b"),
            InvariantResult("INV_003", True, 5, "c"),
            InvariantResult("INV_004", True, 4, "d"),
            InvariantResult("INV_005", True, 5, "e"),
            InvariantResult("INV_006", True, 5, "f"),
            InvariantResult("INV_008", True, 5, "g"),
            InvariantResult("INV_010", True, 5, "h"),
        ]
        score_few, count_few, _ = compute_inv_score(few)
        score_many, count_many, _ = compute_inv_score(many)

        # MAX severity is the same (both have sev=5)
        assert score_few == score_many == 5.0
        # But count differs — this is what inv_count captures
        assert count_few == 2
        assert count_many == 8

        # inv_count contribution: (8-2)/10 * weight
        from src.score.fusion import NORM_BOUNDS
        delta = FUSION_WEIGHTS["inv_count"] * (
            count_many / NORM_BOUNDS["inv_count"] - count_few / NORM_BOUNDS["inv_count"]
        )
        assert delta > 0.05  # meaningful separation (threshold adjusted for Sprint 3 weight rebalance)


class TestSigmoidNormalize:
    def test_floor_at_zero(self):
        """sigma=0 -> ~0.047 (never truly zero)."""
        result = sigmoid_normalize(0.0)
        assert 0.04 < result < 0.06

    def test_midpoint(self):
        """sigma=x0 -> exactly 0.5."""
        result = sigmoid_normalize(3.0)
        assert abs(result - 0.5) < 1e-9

    def test_saturation(self):
        """sigma=10 -> close to 1.0."""
        result = sigmoid_normalize(10.0)
        assert result > 0.99

    def test_monotonic(self):
        """Higher sigma -> higher output."""
        vals = [sigmoid_normalize(x) for x in [0, 1, 2, 3, 5, 10]]
        assert vals == sorted(vals)

    def test_no_overflow_large_negative(self):
        """Extreme negative input doesn't raise OverflowError."""
        result = sigmoid_normalize(-1000.0)
        assert result >= 0.0
        assert result < 0.001

    def test_no_overflow_large_positive(self):
        """Extreme positive input doesn't raise OverflowError."""
        result = sigmoid_normalize(1000.0)
        assert result > 0.999
