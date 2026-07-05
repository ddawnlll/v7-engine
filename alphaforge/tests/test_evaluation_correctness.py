"""Measurement correctness tests for factor evaluation.

These tests use deterministic toy panels where the expected outcome is known.
If any test fails, the evaluator has a bug — not a data problem.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alphaforge.factors.evaluation import (
    compute_cross_sectional_ic,
    compute_forward_returns,
    compute_top_bottom_spread,
    compute_turnover,
    evaluate_factor,
)
from alphaforge.factors.factors import FACTOR_REGISTRY


# ── HELPERS ────────────────────────────────────────────────────────

def _make_toy_panel(data: dict[str, list[float]], symbols: list[str]) -> pd.DataFrame:
    """Create a small DataFrame from dict of lists."""
    idx = pd.date_range("2024-01-01", periods=len(data[symbols[0]]), freq="1h")
    return pd.DataFrame(data, index=idx, columns=symbols)


# ── TEST 1: FORWARD RETURNS ───────────────────────────────────────

class TestForwardReturns:
    def test_basic(self):
        close = _make_toy_panel(
            {"A": [100, 110, 121, 133.1], "B": [200, 190, 180.5, 171.475]},
            ["A", "B"],
        )
        fwd = compute_forward_returns(close, horizons=[1])

        # fwd_ret[t] = close[t+1] / close[t] - 1
        expected_A = [0.10, 0.10, 0.10, np.nan]
        expected_B = [-0.05, -0.05, -0.05, np.nan]

        result = fwd[1]
        np.testing.assert_allclose(result["A"].values, expected_A, rtol=1e-10)
        np.testing.assert_allclose(result["B"].values, expected_B, rtol=1e-10)

    def test_no_lookahead(self):
        """Forward return at t should NOT use data beyond t+horizon."""
        close = _make_toy_panel(
            {"A": [100, 100, 100, 200, 100]},
            ["A"],
        )
        fwd = compute_forward_returns(close, horizons=[2])
        # At t=2: close[4]/close[2] - 1 = 100/100 - 1 = 0
        # At t=3: NaN (no close[5])
        assert fwd[2]["A"].iloc[2] == pytest.approx(0.0)
        assert np.isnan(fwd[2]["A"].iloc[3])


# ── TEST 2: RANK IC = +1 (perfect positive) ──────────────────────

class TestRankIC:
    def test_perfect_positive_ic(self):
        """If factor ranks perfectly predict forward return ranks, IC should be +1."""
        # 3 symbols, factor perfectly predicts return order
        factor = _make_toy_panel(
            {"A": [1.0, 1.0], "B": [2.0, 2.0], "C": [3.0, 3.0]},
            ["A", "B", "C"],
        )
        # Returns: C > B > A (same order as factor)
        fwd = _make_toy_panel(
            {"A": [0.01, 0.01], "B": [0.02, 0.02], "C": [0.03, 0.03]},
            ["A", "B", "C"],
        )
        ic = compute_cross_sectional_ic(factor, fwd)
        # With perfect rank correlation, IC should be +1.0
        assert ic.mean() == pytest.approx(1.0, abs=1e-10)

    def test_perfect_negative_ic(self):
        """If factor ranks perfectly inversely predict return, IC should be -1."""
        factor = _make_toy_panel(
            {"A": [1.0, 1.0], "B": [2.0, 2.0], "C": [3.0, 3.0]},
            ["A", "B", "C"],
        )
        # Returns: A > B > C (opposite order)
        fwd = _make_toy_panel(
            {"A": [0.03, 0.03], "B": [0.02, 0.02], "C": [0.01, 0.01]},
            ["A", "B", "C"],
        )
        ic = compute_cross_sectional_ic(factor, fwd)
        assert ic.mean() == pytest.approx(-1.0, abs=1e-10)

    def test_zero_ic_random(self):
        """Random factor should produce IC near 0."""
        np.random.seed(42)
        n_sym = 50
        factor_data = np.random.randn(100, n_sym)
        fwd_data = np.random.randn(100, n_sym)
        factor = pd.DataFrame(factor_data)
        fwd = pd.DataFrame(fwd_data)
        ic = compute_cross_sectional_ic(factor, fwd)
        assert abs(ic.mean()) < 0.15  # should be near 0


# ── TEST 3: TOP-BOTTOM SPREAD ─────────────────────────────────────

class TestTopBottomSpread:
    def test_spread_positive_when_top_outperforms(self):
        """If top factor scores predict higher returns, spread should be positive."""
        # 10 symbols, top 2 (D, E) have highest factor scores AND highest returns
        factor = _make_toy_panel(
            {"A": [1], "B": [2], "C": [3], "D": [9], "E": [10],
             "F": [4], "G": [5], "H": [6], "I": [7], "J": [8]},
            ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        )
        fwd = _make_toy_panel(
            {"A": [0.01], "B": [0.01], "C": [0.01], "D": [0.10], "E": [0.10],
             "F": [0.01], "G": [0.01], "H": [0.01], "I": [0.01], "J": [0.01]},
            ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        )
        spread = compute_top_bottom_spread(factor, fwd)
        assert spread.iloc[0] > 0, f"Expected positive spread, got {spread.iloc[0]}"

    def test_spread_negative_when_bottom_outperforms(self):
        """If bottom factor scores predict higher returns, spread should be negative."""
        factor = _make_toy_panel(
            {"A": [10], "B": [9], "C": [8], "D": [1], "E": [2],
             "F": [7], "G": [6], "H": [5], "I": [4], "J": [3]},
            ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        )
        fwd = _make_toy_panel(
            {"A": [0.01], "B": [0.01], "C": [0.01], "D": [0.10], "E": [0.10],
             "F": [0.01], "G": [0.01], "H": [0.01], "I": [0.01], "J": [0.01]},
            ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        )
        spread = compute_top_bottom_spread(factor, fwd)
        assert spread.iloc[0] < 0, f"Expected negative spread, got {spread.iloc[0]}"


# ── TEST 4: TURNOVER ──────────────────────────────────────────────

class TestTurnover:
    def test_turnover_never_negative(self):
        """Turnover must be in [0, 1] range — never negative."""
        factor = _make_toy_panel(
            {"A": [1, 2, 3, 4, 5], "B": [5, 4, 3, 2, 1],
             "C": [3, 3, 3, 3, 3], "D": [2, 4, 2, 4, 2],
             "E": [4, 2, 4, 2, 4]},
            ["A", "B", "C", "D", "E"],
        )
        turnover = compute_turnover(factor)
        valid = turnover.dropna()
        assert (valid >= 0).all(), f"Negative turnover found: {valid[valid < 0]}"
        assert (valid <= 1).all(), f"Turnover > 1 found: {valid[valid > 1]}"

    def test_turnover_zero_when_stable(self):
        """If top group never changes, turnover should be 0."""
        # Same top 2 symbols every timestamp
        factor = _make_toy_panel(
            {"A": [10, 10, 10, 10], "B": [9, 9, 9, 9],
             "C": [1, 1, 1, 1], "D": [2, 2, 2, 2], "E": [3, 3, 3, 3]},
            ["A", "B", "C", "D", "E"],
        )
        turnover = compute_turnover(factor)
        valid = turnover.dropna()
        assert valid.mean() == pytest.approx(0.0, abs=1e-10)

    def test_turnover_one_when_complete_flip(self):
        """If top group completely flips each timestamp, turnover should be ~1."""
        # 5 symbols, top 2 flips between {A,B} and {C,D}
        factor = _make_toy_panel(
            {"A": [10, 1, 10, 1], "B": [9, 2, 9, 2],
             "C": [1, 10, 1, 10], "D": [2, 9, 2, 9], "E": [5, 5, 5, 5]},
            ["A", "B", "C", "D", "E"],
        )
        turnover = compute_turnover(factor)
        valid = turnover.dropna()
        assert valid.mean() == pytest.approx(1.0, abs=1e-10)


# ── TEST 5: DIRECTION HANDLING ────────────────────────────────────

class TestDirectionHandling:
    def _make_direction_data(self, n_sym=10):
        """Create realistic 20-row panels for direction testing.
        Factor S5-S9 have higher scores AND higher close prices → positive IC."""
        cols = [f"S{i}" for i in range(n_sym)]
        np.random.seed(123)
        rows = 20
        # Factor scores: S5-S9 are systematically higher
        factor_data = {}
        close_data = {}
        for i, c in enumerate(cols):
            base = float(i) * 0.5  # S0=0, S1=0.5, ..., S9=4.5
            factor_data[c] = [base + np.random.randn() * 0.1 for _ in range(rows)]
            # Close prices that correlate with factor (higher factor → higher return)
            drift = 0.002 if i >= 5 else -0.002
            prices = [100.0]
            for _ in range(rows - 1):
                prices.append(prices[-1] * (1 + drift + np.random.randn() * 0.005))
            close_data[c] = prices

        factor = _make_toy_panel(factor_data, cols)
        close = _make_toy_panel(close_data, cols)
        fwd_returns = compute_forward_returns(close, horizons=[1])
        return factor, fwd_returns

    def test_short_direction_flips_spread_sign(self):
        """For 'short' direction, net_return should flip the raw spread sign.
        But 'gross_return' should remain raw (unsigned)."""
        factor, fwd_returns = self._make_direction_data()

        results = evaluate_factor("test_factor", factor, fwd_returns, "short")
        r = results[0]

        gross = r["top_bottom_gross_return"]
        net = r["top_bottom_net_return"]

        # Gross should be the raw spread (positive in this case)
        assert gross > 0, f"Raw spread should be positive, got {gross}"
        # Net should be the direction-adjusted spread
        # For "short" direction, net = raw * (-1) = negative
        assert net < 0, f"Short-direction net should be negative, got {net}"
        # The magnitude should be the same (no cost model yet)
        assert abs(abs(gross) - abs(net)) < 1e-10, \
            f"|gross|={abs(gross)} != |net|={abs(net)}"
        # IC should also be direction-adjusted: for "short", positive raw IC
        # becomes negative adjusted IC (bad for short direction)
        assert r["mean_rank_ic"] < 0, \
            f"Short factor with positive raw IC should have negative adjusted IC, got {r['mean_rank_ic']}"

    def test_long_direction_preserves_spread_sign(self):
        """For 'long' direction, net_return should equal raw spread."""
        factor, fwd_returns = self._make_direction_data()

        results = evaluate_factor("test_factor", factor, fwd_returns, "long")
        r = results[0]

        gross = r["top_bottom_gross_return"]
        net = r["top_bottom_net_return"]

        # Both should be positive and equal (long direction, no cost)
        assert gross > 0
        assert net > 0
        assert abs(gross - net) < 1e-10, \
            f"Long: gross={gross} should equal net={net}"


# ── TEST 6: IC_IR SIGN CONSISTENCY ────────────────────────────────

class TestICIRConsistency:
    def test_ic_ir_matches_notes_for_long(self):
        """ic_ir column should match the IC_IR printed in notes for long factors."""
        n_sym = 20
        cols = [f"S{i}" for i in range(n_sym)]
        np.random.seed(42)
        # Create a weak but consistent factor (need 5+ rows for valid IC)
        rows = 10
        factor_data = {c: [np.random.randn() + i * 0.1 for _ in range(rows)] for i, c in enumerate(cols)}
        fwd_data = {c: [np.random.randn() + i * 0.1 for _ in range(rows)] for i, c in enumerate(cols)}

        factor = _make_toy_panel(factor_data, cols)
        fwd_panel = _make_toy_panel(fwd_data, cols)
        fwd_returns = compute_forward_returns(fwd_panel, horizons=[1])

        results = evaluate_factor("test_factor", factor, fwd_returns, "long")
        r = results[0]

        ic_ir_value = r["ic_ir"]
        # Extract IC_IR from notes
        notes = r["notes"]
        if "IC_IR=" in notes:
            ic_ir_from_notes = float(notes.split("IC_IR=")[1].rstrip(")"))
            assert abs(ic_ir_value - ic_ir_from_notes) < 0.01, \
                f"ic_ir={ic_ir_value} != notes IC_IR={ic_ir_from_notes}"


# ── TEST 7: SYNTHETIC PERFECT SIGNAL (THE SMOKE TEST) ────────────

class TestSyntheticPerfectSignal:
    def test_perfect_signal_passes(self):
        """Inject perfect future return as factor → should get IC=1.0 and PASS.

        This is the ultimate smoke test: if a perfect signal can't produce
        a PASS, the evaluator is broken.
        """
        n_sym = 20
        cols = [f"S{i}" for i in range(n_sym)]

        # Create close prices with known returns
        np.random.seed(42)
        returns = np.random.randn(200, n_sym) * 0.01
        close_data = {}
        for j, c in enumerate(cols):
            prices = [100.0]
            for i in range(1, 200):
                prices.append(prices[-1] * (1 + returns[i, j]))
            close_data[c] = prices

        close = _make_toy_panel(close_data, cols)
        fwd_returns = compute_forward_returns(close, horizons=[1])

        # PERFECT SIGNAL: factor scores = forward returns (no lookahead for test purposes)
        # This simulates "if we knew the future, would the evaluator detect it?"
        perfect_factor = fwd_returns[1].copy()

        results = evaluate_factor("perfect_signal", perfect_factor, fwd_returns, "long")
        r = results[0]

        print(f"  Perfect signal IC: {r['mean_rank_ic']:.4f}")
        print(f"  Perfect signal IC_IR: {r['ic_ir']:.4f}")
        print(f"  Perfect signal pass_fail: {r['pass_fail']}")

        # IC should be exactly 1.0 (factor IS the forward return)
        assert r["mean_rank_ic"] > 0.99, \
            f"Perfect signal IC should be ~1.0, got {r['mean_rank_ic']}"
        assert r["pass_fail"] == "PASS", \
            f"Perfect signal should PASS, got {r['pass_fail']}"


# ── TEST 8: COST MODEL (currently missing) ────────────────────────

class TestCostModel:
    def _make_cost_data(self, n_sym=10):
        """Create realistic 20-row panels for cost model testing."""
        cols = [f"S{i}" for i in range(n_sym)]
        np.random.seed(456)
        rows = 20
        factor_data = {}
        close_data = {}
        for i, c in enumerate(cols):
            base = float(i) * 0.5
            factor_data[c] = [base + np.random.randn() * 0.1 for _ in range(rows)]
            drift = 0.002 if i >= 5 else -0.002
            prices = [100.0]
            for _ in range(rows - 1):
                prices.append(prices[-1] * (1 + drift + np.random.randn() * 0.005))
            close_data[c] = prices

        factor = _make_toy_panel(factor_data, cols)
        close = _make_toy_panel(close_data, cols)
        fwd_returns = compute_forward_returns(close, horizons=[1])
        return factor, fwd_returns

    @pytest.mark.xfail(strict=True, reason="Cost model not yet implemented")
    def test_net_equals_gross_when_no_cost(self):
        """INTENT: This test asserts net == gross for long trades, which is only
        true when there is NO cost model. Once a cost model is implemented,
        net will be less than gross and this test MUST FAIL — the xfail marker
        documents that the test's assertion describes the pre-cost-model world
        and will break (correctly) when costs are introduced."""
        factor, fwd_returns = self._make_cost_data()

        results = evaluate_factor("test_factor", factor, fwd_returns, "long")
        r = results[0]

        # For long direction: net = gross (no cost model yet)
        gross = r["top_bottom_gross_return"]
        net = r["top_bottom_net_return"]
        assert abs(gross - net) < 1e-10, \
            f"Long: gross={gross} should equal net={net} (no cost model yet)"

    def test_short_net_is_negative_of_gross(self):
        """For short direction without cost model, net = -gross."""
        factor, fwd_returns = self._make_cost_data()

        results = evaluate_factor("test_factor", factor, fwd_returns, "short")
        r = results[0]

        gross = r["top_bottom_gross_return"]
        net = r["top_bottom_net_return"]
        # For short: net = -gross (no cost model)
        assert abs(gross + net) < 1e-10, \
            f"Short: net={net} should equal -gross={-gross}"
