"""Tests for scoring physics layer (delta_F, EMA)."""

import json
from datetime import datetime, timedelta

from src.score.physics import compute_delta_f


W1 = datetime(2026, 3, 28, 10, 0, 0)


def _insert_flux_window(db, window_start, sigma):
    """Insert a zone_flux_windows row with given sigma_coarse."""
    db.execute(
        "INSERT INTO zone_flux_windows (window_start, flux_matrix, net_currents, "
        "sigma_coarse, bridge_count) VALUES (?, ?, ?, ?, ?)",
        [window_start, "[]", "{}", sigma, 0],
    )


class TestDeltaF:
    def test_no_history_returns_zero(self, db):
        """First window with no prior data -> delta_F = 0."""
        result = compute_delta_f(db, W1, current_sigma=5.0)
        assert result == 0.0

    def test_increasing_sigma(self, db):
        """Sigma rises above EMA -> positive delta_F."""
        # Insert 3 prior windows with sigma=2.0
        for i in range(3):
            w = W1 - timedelta(minutes=15 * (3 - i))
            _insert_flux_window(db, w, 2.0)
        result = compute_delta_f(db, W1, current_sigma=5.0)
        assert result > 0

    def test_decreasing_sigma(self, db):
        """Sigma drops below EMA -> negative delta_F."""
        for i in range(3):
            w = W1 - timedelta(minutes=15 * (3 - i))
            _insert_flux_window(db, w, 8.0)
        result = compute_delta_f(db, W1, current_sigma=2.0)
        assert result < 0

    def test_stable_sigma_near_zero(self, db):
        """Constant sigma -> delta_F converges to ~0."""
        for i in range(20):
            w = W1 - timedelta(minutes=15 * (20 - i))
            _insert_flux_window(db, w, 3.0)
        result = compute_delta_f(db, W1, current_sigma=3.0)
        assert abs(result) < 0.5  # close to zero after convergence


class TestEMA:
    def test_alpha_smoothing(self, db):
        """Verify EMA formula: new = alpha*current + (1-alpha)*prev."""
        # Single prior window with sigma=10.0
        w0 = W1 - timedelta(minutes=15)
        _insert_flux_window(db, w0, 10.0)
        # Current sigma=20.0, alpha=0.1
        # EMA after 1 window: 10.0 (first value = first sigma)
        # delta_F = 20.0 - 10.0 = 10.0
        result = compute_delta_f(db, W1, current_sigma=20.0, alpha=0.1)
        assert abs(result - 10.0) < 1e-9

    def test_two_windows_ema(self, db):
        """EMA with 2 prior windows."""
        w0 = W1 - timedelta(minutes=30)
        w1 = W1 - timedelta(minutes=15)
        _insert_flux_window(db, w0, 10.0)
        _insert_flux_window(db, w1, 20.0)
        # EMA: start=10.0, then 0.1*20 + 0.9*10 = 11.0
        # delta_F = current - 11.0
        result = compute_delta_f(db, W1, current_sigma=15.0, alpha=0.1)
        assert abs(result - (15.0 - 11.0)) < 1e-9
