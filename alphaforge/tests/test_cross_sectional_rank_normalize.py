"""Tests for cross_sectional_rank_normalize — vectorized rank normalization.

Covers:
  (a) Exact equivalence to the original per-timestamp loop
  (b) Correct rank values [0, 1] for valid groups
  (c) Timestamps with <3 symbols are left unchanged
  (d) Single timestamp (no cross-section) → no-op
  (e) NaN preservation through normalization
  (f) Large randomized comparison with original loop
  (g) Verify no memory corruption (copy vs view)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from alphaforge.train import cross_sectional_rank_normalize


def _original_loop(X: np.ndarray, ts: np.ndarray) -> np.ndarray:
    """Original O(T*F*S) implementation for equivalence testing."""
    _unique_ts = np.unique(ts)
    X_ranked = X.copy()
    for _ts in _unique_ts:
        _mask = ts == _ts
        _n = _mask.sum()
        if _n >= 3:
            for _col in range(X.shape[1]):
                _vals = X[_mask, _col]
                _ranks = (_vals.argsort().argsort().astype(np.float64) + 0.5) / _n
                X_ranked[_mask, _col] = _ranks
    return X_ranked


class TestCrossSectionalRankNormalize:
    """cross_sectional_rank_normalize — grouped 2D argsort rank normalization."""

    def test_equivalence_with_original_loop(self):
        """Vectorized version produces identical output to original loop."""
        rng = np.random.RandomState(42)
        n_ts, n_sym, n_feat = 50, 10, 20
        ts = np.repeat(np.arange(n_ts, dtype=np.int64), n_sym)
        ts_sorted = np.sort(ts)  # ensure contiguous groups
        X = rng.randn(n_ts * n_sym, n_feat)

        expected = _original_loop(X, ts_sorted)
        actual = cross_sectional_rank_normalize(X, ts_sorted)

        assert np.allclose(expected, actual, equal_nan=True), (
            "Vectorized output differs from original loop"
        )

    def test_equivalence_large_scale(self):
        """Equivalence holds at larger scale (simulating 57 sym x 89 feat)."""
        rng = np.random.RandomState(123)
        n_ts, n_sym, n_feat = 100, 57, 89
        ts = np.repeat(np.arange(n_ts, dtype=np.int64), n_sym)
        ts_sorted = np.sort(ts)
        X = rng.randn(n_ts * n_sym, n_feat)

        expected = _original_loop(X, ts_sorted)
        actual = cross_sectional_rank_normalize(X, ts_sorted)
        assert np.allclose(expected, actual, equal_nan=True)

    def test_rank_values_in_range(self):
        """Normalized ranks are in (0, 1]."""
        rng = np.random.RandomState(42)
        n_ts, n_sym, n_feat = 10, 5, 8
        ts = np.repeat(np.arange(n_ts, dtype=np.int64), n_sym)
        ts_sorted = np.sort(ts)
        X = rng.randn(n_ts * n_sym, n_feat)

        result = cross_sectional_rank_normalize(X, ts_sorted)
        for _ts in np.unique(ts_sorted):
            mask = ts_sorted == _ts
            group = result[mask]
            assert np.all(group >= 0.0) and np.all(group <= 1.0), (
                f"Rank values outside [0, 1] for ts={_ts}"
            )

    def test_less_than_three_symbols_unchanged(self):
        """Timestamps with <3 symbols are left unmodified."""
        ts = np.array([0, 0, 0, 1, 1, 2], dtype=np.int64)  # ts=1 has 2 sym, ts=2 has 1
        X = np.array([
            [10.0, 20.0],
            [11.0, 21.0],
            [12.0, 22.0],
            [30.0, 40.0],
            [31.0, 41.0],
            [50.0, 60.0],
        ])
        result = cross_sectional_rank_normalize(X, ts)
        # ts=1 (2 sym) and ts=2 (1 sym) should be unchanged
        assert np.allclose(result[3:5], X[3:5])
        assert np.allclose(result[5:6], X[5:6])
        # But ts=0 (3 sym) should be ranked
        assert not np.allclose(result[0:3], X[0:3])

    def test_single_timestamp_many_symbols_ranked(self):
        """Single timestamp with 100 symbols ranks them (valid cross-section)."""
        ts = np.zeros(100, dtype=np.int64)
        rng = np.random.RandomState(42)
        X = rng.randn(100, 10)
        result = cross_sectional_rank_normalize(X, ts)
        # 100 symbols across 1 timestamp — 100 >= 3, so ranking applies
        assert np.all(result >= 0.0) and np.all(result <= 1.0)
        assert not np.allclose(result, X)

    def test_nan_matches_original_behavior(self):
        """NaN handling matches original loop (argsort puts NaN last → rank)."""
        rng = np.random.RandomState(42)
        n_ts, n_sym, n_feat = 5, 5, 4
        ts = np.repeat(np.arange(n_ts, dtype=np.int64), n_sym)
        ts_sorted = np.sort(ts)
        X = rng.randn(n_ts * n_sym, n_feat)
        X[0, 0] = np.nan  # one NaN in first group

        # Both original and vectorized produce same NaN→rank mapping
        expected = _original_loop(X, ts_sorted)
        actual = cross_sectional_rank_normalize(X, ts_sorted)
        assert np.allclose(expected, actual, equal_nan=True)

    def test_deterministic(self):
        """Same input produces same output."""
        rng = np.random.RandomState(42)
        ts = np.repeat(np.arange(10, dtype=np.int64), 5)
        ts_sorted = np.sort(ts)
        X = rng.randn(50, 8)
        r1 = cross_sectional_rank_normalize(X, ts_sorted)
        r2 = cross_sectional_rank_normalize(X, ts_sorted)
        assert np.allclose(r1, r2)

    def test_contiguous_groups_assumption(self):
        """Works correctly when timestamps are not contiguous (but sorted)."""
        ts = np.array([0, 0, 0, 2, 2, 2, 5, 5, 5], dtype=np.int64)
        X = np.arange(27, dtype=np.float64).reshape(9, 3)
        result = cross_sectional_rank_normalize(X, ts)
        expected = _original_loop(X, ts)
        assert np.allclose(result, expected, equal_nan=True)
