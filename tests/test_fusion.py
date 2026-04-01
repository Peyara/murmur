"""Tests for scoring fusion layer."""

from datetime import datetime, timedelta

from src.ingest.dedup import insert_event
from src.schema import ActionType, TargetZone
from src.score.fusion import FUSION_WEIGHTS, compute_fusion, normalize
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
        """All signals zero -> fusion_raw = 0."""
        _setup_minimal(db)
        result = compute_fusion(db, W1, "sa@proj", KNOWN)
        # burst_per_min=1.0 -> normalized to 1/20=0.05, weight=0.08 -> 0.004
        assert result < 0.01  # near-zero, dominated by small burst signal

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
        # inv_score=5 -> normalized to 5/5=1.0, weight=0.35
        # Other signals may be small but nonzero
        assert result >= FUSION_WEIGHTS["inv_score"] * 0.9  # at least ~0.35

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
