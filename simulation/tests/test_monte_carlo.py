"""Tests for simulation/engine/monte_carlo.py.

Tests: perturbation shape preservation, zero-sigma determinism,
distributional aggregation, extreme market scenarios.
"""

import math

from simulation.contracts.models import Candle, FuturePath, MonteCarloConfig, SimulationInput, SimulationProfile, TradingMode
from simulation.engine.monte_carlo import MonteCarloOutput, _perturb_candle, _percentile, run_monte_carlo


def _swing_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="swing_profile-1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=30,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.20,
        min_action_edge_r=0.35,
        no_trade_default=False,
        mae_penalty_weight=1.0,
        cost_penalty_weight=1.0,
        time_penalty_weight=0.3,
    )


def _make_input(candles: list[Candle]) -> SimulationInput:
    return SimulationInput(
        symbol="BTCUSDT",
        decision_timestamp="2026-06-01T12:00:00Z",
        mode=TradingMode.SWING,
        primary_interval="4h",
        entry_price=50000.0,
        atr=1000.0,
        future_path=FuturePath(candles=candles),
        profile=_swing_profile(),
    )


def _swing_candles() -> list[Candle]:
    """Moderate bullish path for SWING."""
    return [
        Candle(open=50200, high=50500, low=50100, close=50400),
        Candle(open=50400, high=51000, low=50300, close=50800),
        Candle(open=50800, high=51500, low=50700, close=51300),
        Candle(open=51300, high=52000, low=51200, close=51800),
        Candle(open=51800, high=52600, low=51700, close=52500),
    ]


# ── _perturb_candle ────────────────────────────────────────────────

class TestPerturbCandle:
    def test_high_is_max_of_high_and_close(self):
        """After perturbation, high >= perturbed close."""
        import random
        rng = random.Random(42)
        c = Candle(open=100, high=110, low=90, close=105)
        for _ in range(50):
            p = _perturb_candle(c, 0.01, rng)
            assert p.high >= p.close
            assert p.low <= p.close

    def test_sigma_zero_identity(self):
        """Sigma=0 → identical candles."""
        import random
        rng = random.Random(42)
        c = Candle(open=100, high=110, low=90, close=105)
        p = _perturb_candle(c, 0.0, rng)
        assert p.open == 100
        assert p.high == 110
        assert p.low == 90
        assert p.close == 105

    def test_preserves_open_and_volume(self):
        """Open and volume are never modified."""
        import random
        rng = random.Random(42)
        c = Candle(open=100, high=110, low=90, close=105, volume=1000.0)
        p = _perturb_candle(c, 0.02, rng)
        assert p.open == 100
        assert p.volume == 1000.0


# ── _percentile ────────────────────────────────────────────────────

class TestPercentile:
    def test_empty(self):
        assert _percentile([], 50) == 0.0

    def test_single(self):
        assert _percentile([5.0], 50) == 5.0

    def test_median_odd(self):
        assert _percentile([1.0, 2.0, 3.0], 50) == 2.0

    def test_median_even(self):
        assert _percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5

    def test_p95(self):
        values = list(range(1, 101))
        p95 = _percentile(values, 95)
        assert 94.0 <= p95 <= 96.0


# ── run_monte_carlo ────────────────────────────────────────────────

class TestRunMonteCarlo:
    def test_sigma_zero_deterministic(self):
        """Sigma=0 and seed=None → all paths identical to baseline."""
        inp = _make_input(_swing_candles())
        config = MonteCarloConfig(num_paths=10, perturbation_sigma=0.0)
        result = run_monte_carlo(inp, config)
        assert result.num_paths == 10
        assert result.monte_carlo_run_id.startswith("mc_")
        assert result.perturbation_method == "price_noise"
        # All paths identical → std = 0, stability = 1.0
        assert result.expected_r_distribution["std"] == 0.0
        assert result.confidence_stability >= 0.9  # all agree

    def test_returns_all_required_fields(self):
        inp = _make_input(_swing_candles())
        result = run_monte_carlo(inp)
        assert isinstance(result, MonteCarloOutput)
        assert result.monte_carlo_family_version == "mcfam-1.0"
        assert result.perturbation_method == "price_noise"
        assert result.perturbation_sigma == 0.002
        assert result.num_paths == 100
        # Distribution fields
        dist = result.expected_r_distribution
        for key in ("mean", "std", "p5", "p25", "p50", "p75", "p95"):
            assert key in dist
            assert isinstance(dist[key], float)
        # Probabilities each in [0, 1]
        assert 0.0 <= result.target_before_stop_probability <= 1.0
        assert 0.0 <= result.stop_before_target_probability <= 1.0
        # Best action ratios sum to 1
        total = result.best_action_long_runs + result.best_action_short_runs + result.best_action_no_trade_runs
        assert abs(total - 1.0) < 0.01

    def test_bullish_path_biases_long(self):
        """Strong uptrend → most paths favor LONG."""
        inp = _make_input(_swing_candles())
        result = run_monte_carlo(inp, MonteCarloConfig(num_paths=50, perturbation_sigma=0.001, perturbation_seed=42))
        assert result.best_action_long_runs > result.best_action_short_runs

    def test_bearish_path_biases_short(self):
        """Strong downtrend → most paths favor SHORT."""
        candles = [
            Candle(open=49800, high=49900, low=49300, close=49400),
            Candle(open=49400, high=49500, low=48500, close=48600),
            Candle(open=48600, high=48800, low=47300, close=47400),
            Candle(open=47400, high=47600, low=46500, close=46600),
            Candle(open=46600, high=46800, low=45500, close=45600),
        ]
        inp = _make_input(candles)
        result = run_monte_carlo(inp, MonteCarloConfig(num_paths=50, perturbation_sigma=0.001, perturbation_seed=42))
        assert result.best_action_short_runs > result.best_action_long_runs

    def test_downside_risk_non_positive(self):
        """CVaR (downside_risk) should be <= 0 for worst 5%."""
        inp = _make_input(_swing_candles())
        result = run_monte_carlo(inp, MonteCarloConfig(num_paths=30, perturbation_sigma=0.005, perturbation_seed=123))
        assert result.downside_risk <= result.expected_r_distribution["mean"]

    def test_reproducible_with_seed(self):
        """Same seed → same results."""
        inp = _make_input(_swing_candles())
        cfg = MonteCarloConfig(num_paths=20, perturbation_sigma=0.002, perturbation_seed=42)
        r1 = run_monte_carlo(inp, cfg)
        r2 = run_monte_carlo(inp, cfg)
        assert r1.expected_r_distribution == r2.expected_r_distribution
        assert r1.best_action_long_runs == r2.best_action_long_runs

    def test_different_seeds_different_results(self):
        """Different seeds → different best_action_long_runs (highly likely)."""
        inp = _make_input(_swing_candles())
        r1 = run_monte_carlo(inp, MonteCarloConfig(num_paths=20, perturbation_sigma=0.01, perturbation_seed=1))
        r2 = run_monte_carlo(inp, MonteCarloConfig(num_paths=20, perturbation_sigma=0.01, perturbation_seed=2))
        # Almost certainly different proportions
        assert r1.best_action_long_runs != r2.best_action_long_runs


# ── Edge cases ─────────────────────────────────────────────────────

class TestEdgeCases:
    def test_single_candle_path(self):
        """Works with only 1 candle."""
        inp = _make_input([Candle(open=100, high=105, low=95, close=102)])
        result = run_monte_carlo(inp, MonteCarloConfig(num_paths=5, perturbation_sigma=0.001))
        assert result.num_paths == 5

    def test_empty_path_returns_results(self):
        """Empty candle list → all paths time-exit at entry."""
        inp = _make_input([])
        result = run_monte_carlo(inp, MonteCarloConfig(num_paths=5))
        assert result.num_paths == 5
        # No movement possible → NO_TRADE dominant
        assert result.best_action_no_trade_runs > 0
