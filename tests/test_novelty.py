"""Tests for scoring novelty layer."""

import json
from datetime import datetime

from src.score.novelty import compute_novelty_score, get_bridge_new


W1 = datetime(2026, 3, 28, 10, 0, 0)


def _insert_edge(db, actor_id, src, tgt, target_id, is_new, count=1):
    db.execute(
        "INSERT INTO edges_window VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [W1, actor_id, src, tgt, target_id, count, W1, is_new],
    )


def _insert_flux(db, bridge_count):
    db.execute(
        "INSERT INTO zone_flux_windows VALUES (?, ?, ?, ?, ?)",
        [W1, "[]", "{}", 0.0, bridge_count],
    )


class TestNoveltyScore:
    def test_no_new_edges(self, db):
        _insert_edge(db, "sa@proj", "SECRET", "DATA", "t1", False)
        assert compute_novelty_score(db, W1, "sa@proj") == 0.0

    def test_new_data_edge(self, db):
        """DATA zone weight = 1.0."""
        _insert_edge(db, "sa@proj", "SECRET", "DATA", "t1", True)
        assert compute_novelty_score(db, W1, "sa@proj") == 1.0

    def test_new_secret_edge(self, db):
        """SECRET zone weight = 2.0."""
        _insert_edge(db, "sa@proj", "DATA", "SECRET", "s1", True)
        assert compute_novelty_score(db, W1, "sa@proj") == 2.0

    def test_new_exfil_edge(self, db):
        """EXFIL_RISK zone weight = 2.0."""
        _insert_edge(db, "sa@proj", "DATA", "EXFIL_RISK", "x1", True)
        assert compute_novelty_score(db, W1, "sa@proj") == 2.0

    def test_new_identity_edge(self, db):
        """IDENTITY zone weight = 1.5."""
        _insert_edge(db, "sa@proj", "DATA", "IDENTITY", "i1", True)
        assert compute_novelty_score(db, W1, "sa@proj") == 1.5

    def test_new_control_edge(self, db):
        """CONTROL zone weight = 1.5."""
        _insert_edge(db, "sa@proj", "DATA", "CONTROL", "c1", True)
        assert compute_novelty_score(db, W1, "sa@proj") == 1.5

    def test_mixed_edges(self, db):
        """New SECRET (2.0) + new DATA (1.0) + old COMPUTE (0) = 3.0."""
        _insert_edge(db, "sa@proj", "DATA", "SECRET", "s1", True)
        _insert_edge(db, "sa@proj", "SECRET", "DATA", "d1", True)
        _insert_edge(db, "sa@proj", "DATA", "COMPUTE", "c1", False)
        assert compute_novelty_score(db, W1, "sa@proj") == 3.0

    def test_other_actor_excluded(self, db):
        """Only counts edges for the specified actor."""
        _insert_edge(db, "other@proj", "DATA", "SECRET", "s1", True)
        assert compute_novelty_score(db, W1, "sa@proj") == 0.0


class TestBridgeNew:
    def test_returns_bridge_count(self, db):
        _insert_flux(db, 3)
        assert get_bridge_new(db, W1) == 3

    def test_no_flux_row(self, db):
        assert get_bridge_new(db, W1) == 0
