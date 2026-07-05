"""Tests for Monte Carlo robustness simulation.

Covers:
  - Perturbation methods (price noise, path resample) structural integrity
  - MonteCarloDriver full-pipeline output completeness
  - Aggregation correctness (mean, std, percentiles, CVaR, stability)
  - Determinism and reproducibility
  - Edge cases (N=1, N=1000, small candles, sigma=0, empty candles)
"""

from __future__ import annotations

import numpy as np
import pytest

from simulation.contracts.models import (
    ActionOutcome,
    Candle,
    FuturePath,
    NoTradeOutcome,
    SimulationInput,
    SimulationLineage,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.monte_carlo import (
    ExpectedRDistribution,
    MonteCarloConfig,
    MonteCarloDriver,
    MonteCarloResult,
    PerturbationMethod,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def swing_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="test-1.0",
        mode=TradingMode.SWING,
        primary_interval="1h",
        max_holding_bars=20,
        stop_multiplier=2.0,
        target_multiplier=3.0,
        ambiguity_margin_r=0.1,
        min_action_edge_r=0.5,
        no_trade_default=False,
    )


@pytest.fixture
def trending_up_input(swing_profile: SimulationProfile) -> SimulationInput:
    """20 candles trending upward from 100, creating a LONG-favorable path."""
    candles: list[Candle] = []
    price = 100.0
    for i in range(20):
        c_open = price
        # Gentle upward drift with small noise
        drift = 0.003 if i % 2 == 0 else -0.001
        c_close = c_open * (1.0 + drift)
        c_high = max(c_open, c_close) * 1.005
        c_low = min(c_open, c_close) * 0.995
        candles.append(
            Candle(open=c_open, high=c_high, low=c_low, close=c_close)
        )
        price = c_close

    return SimulationInput(
        symbol="TEST",
        decision_timestamp="2026-07-01T00:00:00Z",
        mode=TradingMode.SWING,
        primary_interval="1h",
        entry_price=100.0,
        atr=2.0,
        future_path=FuturePath(candles=candles),
        profile=swing_profile,
    )


@pytest.fixture
def flat_input(swing_profile: SimulationProfile) -> SimulationInput:
    """5 candles with unchanged close (no trend, no volatility)."""
    candles = [
        Candle(open=100.0, high=101.0, low=99.0, close=100.0)
        for _ in range(5)
    ]
    return SimulationInput(
        symbol="TEST",
        decision_timestamp="2026-07-01T00:00:00Z",
        mode=TradingMode.SWING,
        primary_interval="1h",
        entry_price=100.0,
        atr=2.0,
        future_path=FuturePath(candles=candles),
        profile=swing_profile,
    )


# ---------------------------------------------------------------------------
# MonteCarloConfig & Enum Tests
# ---------------------------------------------------------------------------


class TestPerturbationMethod:
    def test_members(self) -> None:
        assert PerturbationMethod.PRICE_NOISE.value == "price_noise"
        assert PerturbationMethod.PATH_RESAMPLE.value == "path_resample"

    def test_is_enum_str(self) -> None:
        assert issubclass(PerturbationMethod, str)


class TestMonteCarloConfig:
    def test_defaults(self) -> None:
        cfg = MonteCarloConfig()
        assert cfg.num_paths == 100
        assert cfg.perturbation_method == PerturbationMethod.PRICE_NOISE
        assert cfg.sigma == 0.002
        assert cfg.seed == 42
        assert cfg.max_threads == 4


# ---------------------------------------------------------------------------
# Perturbation: Price Noise
# ---------------------------------------------------------------------------


class TestPriceNoisePerturbation:
    """Structural integrity of price-noise perturbed candles."""

    def test_perturbed_candles_maintain_structure(
        self, trending_up_input: SimulationInput,
    ) -> None:
        driver = MonteCarloDriver()
        rng = np.random.default_rng(42)
        perturbed = driver._perturb_price_noise(trending_up_input, 10, 0.002, rng)

        for pi in perturbed:
            for c in pi.future_path.candles:
                assert c.high >= c.close >= c.low, (
                    f"Candle violates high >= close >= low: "
                    f"high={c.high}, close={c.close}, low={c.low}"
                )

    def test_correct_number_of_paths(
        self, trending_up_input: SimulationInput,
    ) -> None:
        driver = MonteCarloDriver()
        rng = np.random.default_rng(42)
        perturbed = driver._perturb_price_noise(trending_up_input, 50, 0.002, rng)
        assert len(perturbed) == 50

    def test_retains_candle_count(
        self, trending_up_input: SimulationInput,
    ) -> None:
        driver = MonteCarloDriver()
        rng = np.random.default_rng(42)
        perturbed = driver._perturb_price_noise(trending_up_input, 5, 0.002, rng)
        orig_n = len(trending_up_input.future_path.candles)
        for pi in perturbed:
            assert len(pi.future_path.candles) == orig_n

    def test_sigma_zero_identical_candles(
        self, trending_up_input: SimulationInput,
    ) -> None:
        """sigma=0 means no noise -- candles match the original exactly."""
        driver = MonteCarloDriver()
        rng = np.random.default_rng(42)
        perturbed = driver._perturb_price_noise(trending_up_input, 5, 0.0, rng)

        for pi in perturbed:
            for orig_c, pert_c in zip(
                trending_up_input.future_path.candles, pi.future_path.candles
            ):
                assert pert_c.close == pytest.approx(orig_c.close, abs=1e-10)
                assert pert_c.high == pytest.approx(orig_c.high, abs=1e-10)
                assert pert_c.low == pytest.approx(orig_c.low, abs=1e-10)

    def test_sigma_zero_yields_identical_expected_r(
        self, trending_up_input: SimulationInput,
    ) -> None:
        """With sigma=0, all paths produce the same expected R."""
        from simulation.engine.engine import simulate

        base_out = simulate(trending_up_input)
        if base_out.best_action == "LONG_NOW":
            base_r = base_out.long_outcome.realized_r_net
        elif base_out.best_action == "SHORT_NOW":
            base_r = base_out.short_outcome.realized_r_net
        else:
            base_r = 0.0

        driver = MonteCarloDriver()
        config = MonteCarloConfig(num_paths=10, sigma=0.0, seed=42)
        result = driver.run(trending_up_input, config)

        assert result.expected_r_distribution.mean == pytest.approx(
            base_r, abs=1e-10
        )
        assert result.expected_r_distribution.std == 0.0

    def test_empty_candles(
        self, swing_profile: SimulationProfile,
    ) -> None:
        """Empty candle list produces no perturbed paths."""
        inp = SimulationInput(
            symbol="TEST",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SWING,
            primary_interval="1h",
            entry_price=100.0,
            atr=2.0,
            future_path=FuturePath(candles=[]),
            profile=swing_profile,
        )
        driver = MonteCarloDriver()
        rng = np.random.default_rng(42)
        perturbed = driver._perturb_price_noise(inp, 10, 0.002, rng)
        assert len(perturbed) == 10
        for pi in perturbed:
            assert len(pi.future_path.candles) == 0


# ---------------------------------------------------------------------------
# Perturbation: Path Resample (Bootstrap)
# ---------------------------------------------------------------------------


class TestPathResamplePerturbation:
    """Structural integrity of bootstrapped candles."""

    def test_resampled_candles_maintain_structure(
        self, trending_up_input: SimulationInput,
    ) -> None:
        driver = MonteCarloDriver()
        rng = np.random.default_rng(42)
        perturbed = driver._perturb_path_resample(trending_up_input, 10, rng)

        for pi in perturbed:
            for c in pi.future_path.candles:
                assert c.high >= c.close >= c.low, (
                    f"Candle violates high >= close >= low: "
                    f"high={c.high}, close={c.close}, low={c.low}"
                )

    def test_correct_number_of_paths(
        self, trending_up_input: SimulationInput,
    ) -> None:
        driver = MonteCarloDriver()
        rng = np.random.default_rng(42)
        perturbed = driver._perturb_path_resample(trending_up_input, 30, rng)
        assert len(perturbed) == 30

    def test_retains_candle_count(
        self, trending_up_input: SimulationInput,
    ) -> None:
        driver = MonteCarloDriver()
        rng = np.random.default_rng(42)
        perturbed = driver._perturb_path_resample(trending_up_input, 5, rng)
        orig_n = len(trending_up_input.future_path.candles)
        for pi in perturbed:
            assert len(pi.future_path.candles) == orig_n

    def test_fallback_on_flat_data(
        self, flat_input: SimulationInput,
    ) -> None:
        """Flat candles (all returns=0) trigger fallback to price noise."""
        driver = MonteCarloDriver()
        rng = np.random.default_rng(42)
        # Should not raise and should produce the correct number of outputs
        perturbed = driver._perturb_path_resample(flat_input, 10, rng)
        assert len(perturbed) == 10
        for pi in perturbed:
            assert len(pi.future_path.candles) == 5

    def test_empty_candles(
        self, swing_profile: SimulationProfile,
    ) -> None:
        """Empty candle list returns empty list (no paths)."""
        inp = SimulationInput(
            symbol="TEST",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SWING,
            primary_interval="1h",
            entry_price=100.0,
            atr=2.0,
            future_path=FuturePath(candles=[]),
            profile=swing_profile,
        )
        driver = MonteCarloDriver()
        rng = np.random.default_rng(42)
        perturbed = driver._perturb_path_resample(inp, 10, rng)
        assert len(perturbed) == 0


# ---------------------------------------------------------------------------
# MonteCarloDriver Full Pipeline
# ---------------------------------------------------------------------------


class TestMonteCarloDriver:
    """End-to-end pipeline tests for MonteCarloDriver.run()."""

    def test_produces_all_expected_fields(
        self, trending_up_input: SimulationInput,
    ) -> None:
        driver = MonteCarloDriver()
        config = MonteCarloConfig(num_paths=10, seed=42)
        result = driver.run(trending_up_input, config)

        # Lineage
        assert result.monte_carlo_run_id.startswith("mc_")
        assert result.monte_carlo_family_version == "mcfam-1.0"
        assert len(result.base_simulation_run_id) > 0

        # Perturbation metadata
        assert result.perturbation_method == "price_noise"
        assert result.perturbation_sigma == 0.002
        assert result.num_paths == 10

        # Distribution fields
        dist = result.expected_r_distribution
        for field_name in ("mean", "std", "p5", "p25", "p50", "p75", "p95"):
            assert isinstance(getattr(dist, field_name), float)

        # Risk fields
        assert isinstance(result.downside_risk, float)
        assert isinstance(result.tail_risk, float)
        assert isinstance(result.confidence_stability, float)

        # Probability fields
        assert 0.0 <= result.target_before_stop_probability <= 1.0
        assert 0.0 <= result.stop_before_target_probability <= 1.0

    def test_target_stop_probabilities_sum_le_one(
        self, trending_up_input: SimulationInput,
    ) -> None:
        """Verification: target_p + stop_p <= 1.0 per spec validation rule."""
        driver = MonteCarloDriver()
        config = MonteCarloConfig(num_paths=50, seed=42)
        result = driver.run(trending_up_input, config)

        total = (
            result.target_before_stop_probability
            + result.stop_before_target_probability
        )
        assert total <= 1.0 + 1e-10  # float tolerance

    def test_path_resample_pipeline(
        self, trending_up_input: SimulationInput,
    ) -> None:
        """PATH_RESAMPLE runs end-to-end without error."""
        driver = MonteCarloDriver()
        config = MonteCarloConfig(
            num_paths=10,
            perturbation_method=PerturbationMethod.PATH_RESAMPLE,
            seed=42,
        )
        result = driver.run(trending_up_input, config)

        assert result.num_paths == 10
        assert result.perturbation_method == "path_resample"
        assert result.monte_carlo_run_id.startswith("mc_")
        assert isinstance(result.expected_r_distribution.mean, float)

    def test_invalid_perturbation_method_raises(
        self, trending_up_input: SimulationInput,
    ) -> None:
        driver = MonteCarloDriver()
        config = MonteCarloConfig(
            num_paths=10,
            perturbation_method="bogus_method",  # type: ignore[arg-type]
            seed=42,
        )
        with pytest.raises(ValueError, match="Unknown perturbation method"):
            driver.run(trending_up_input, config)


# ---------------------------------------------------------------------------
# Determinism & Reproducibility
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_identical_results(
        self, trending_up_input: SimulationInput,
    ) -> None:
        driver = MonteCarloDriver()
        config_a = MonteCarloConfig(num_paths=20, seed=123)
        config_b = MonteCarloConfig(num_paths=20, seed=123)

        result_a = driver.run(trending_up_input, config_a)
        result_b = driver.run(trending_up_input, config_b)

        dist_a = result_a.expected_r_distribution
        dist_b = result_b.expected_r_distribution

        assert dist_a.mean == pytest.approx(dist_b.mean, abs=1e-10)
        assert dist_a.std == pytest.approx(dist_b.std, abs=1e-10)
        assert dist_a.p50 == pytest.approx(dist_b.p50, abs=1e-10)

    def test_different_seed_different_run_ids(
        self, trending_up_input: SimulationInput,
    ) -> None:
        """Run IDs are unique across invocations."""
        driver = MonteCarloDriver()
        config_a = MonteCarloConfig(num_paths=5, seed=1)
        config_b = MonteCarloConfig(num_paths=5, seed=999)

        result_a = driver.run(trending_up_input, config_a)
        result_b = driver.run(trending_up_input, config_b)

        assert result_a.monte_carlo_run_id != result_b.monte_carlo_run_id


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_n_1(self, trending_up_input: SimulationInput) -> None:
        """N=1: single path produces std=0 and equal percentiles."""
        driver = MonteCarloDriver()
        config = MonteCarloConfig(num_paths=1, seed=42)
        result = driver.run(trending_up_input, config)

        assert result.num_paths == 1
        assert result.expected_r_distribution.std == 0.0

        dist = result.expected_r_distribution
        assert dist.p5 == dist.p50 == dist.p95

    def test_n_1000(self, trending_up_input: SimulationInput) -> None:
        """N=1000: stress test for large path count."""
        driver = MonteCarloDriver()
        config = MonteCarloConfig(num_paths=1000, seed=42)
        result = driver.run(trending_up_input, config)

        assert result.num_paths == 1000
        assert result.monte_carlo_run_id.startswith("mc_")
        assert isinstance(result.expected_r_distribution.mean, float)

    def test_very_small_candle_data(
        self, swing_profile: SimulationProfile,
    ) -> None:
        """1-2 candles still produce valid results."""
        driver = MonteCarloDriver()
        config = MonteCarloConfig(num_paths=10, seed=42)

        # 1 candle
        inp_1 = SimulationInput(
            symbol="TEST",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SWING,
            primary_interval="1h",
            entry_price=100.0,
            atr=2.0,
            future_path=FuturePath(
                candles=[Candle(open=100.0, high=102.0, low=98.0, close=101.0)]
            ),
            profile=swing_profile,
        )
        result_1 = driver.run(inp_1, config)
        assert result_1.num_paths == 10
        assert isinstance(result_1.expected_r_distribution.mean, float)

        # 2 candles
        inp_2 = SimulationInput(
            symbol="TEST",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SWING,
            primary_interval="1h",
            entry_price=100.0,
            atr=2.0,
            future_path=FuturePath(
                candles=[
                    Candle(open=100.0, high=102.0, low=98.0, close=101.0),
                    Candle(open=101.0, high=103.0, low=99.0, close=102.0),
                ]
            ),
            profile=swing_profile,
        )
        result_2 = driver.run(inp_2, config)
        assert result_2.num_paths == 10

    def test_flat_price_produces_result(
        self, flat_input: SimulationInput,
    ) -> None:
        """Flat price (no movement) still runs without error."""
        driver = MonteCarloDriver()
        config = MonteCarloConfig(num_paths=10, seed=42)
        result = driver.run(flat_input, config)

        assert result.num_paths == 10
        assert isinstance(result.expected_r_distribution.mean, float)


# ---------------------------------------------------------------------------
# CVaR Computation
# ---------------------------------------------------------------------------


class TestCVaR:
    """Unit tests for Conditional Value at Risk (_compute_cvar)."""

    def test_uniform_distribution(self) -> None:
        """CVaR(0.05) of uniform[0,1] ≈ 0.025."""
        values = np.linspace(0.0, 1.0, 10000)
        cvar = MonteCarloDriver._compute_cvar(values, 0.05)
        assert cvar == pytest.approx(0.025, abs=0.01)

    def test_single_value(self) -> None:
        values = np.array([42.0])
        cvar = MonteCarloDriver._compute_cvar(values, 0.05)
        assert cvar == 42.0

    def test_all_identical(self) -> None:
        values = np.array([3.0, 3.0, 3.0, 3.0, 3.0])
        cvar = MonteCarloDriver._compute_cvar(values, 0.05)
        assert cvar == 3.0

    def test_empty_input(self) -> None:
        cvar = MonteCarloDriver._compute_cvar(np.array([]), 0.05)
        assert cvar == 0.0

    def test_negative_values(self) -> None:
        """CVaR handles negative outcomes correctly."""
        values = np.array([-5.0, -4.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0])
        cvar = MonteCarloDriver._compute_cvar(values, 0.20)
        # Worst 20% = -5.0 and -4.0 → mean = -4.5
        assert cvar == pytest.approx(-4.5, abs=0.01)

    def test_alpha_boundary(self) -> None:
        """CVaR at alpha=1.0 equals the global mean."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        cvar = MonteCarloDriver._compute_cvar(values, 1.0)
        assert cvar == pytest.approx(3.0, abs=1e-10)


# ---------------------------------------------------------------------------
# Confidence Stability
# ---------------------------------------------------------------------------


class TestConfidenceStability:
    """Unit tests for confidence stability (_compute_stability)."""

    def test_zero_variance_perfect_stability(self) -> None:
        values = np.array([1.0, 1.0, 1.0])
        s = MonteCarloDriver._compute_stability(values)
        assert s == 1.0

    def test_high_noise_low_stability(self) -> None:
        values = np.array([-100.0, 100.0, -50.0, 50.0, -25.0, 25.0])
        s = MonteCarloDriver._compute_stability(values)
        assert 0.0 <= s < 0.5  # low stability

    def test_low_noise_high_stability(self) -> None:
        values = np.array([9.9, 10.0, 10.1, 9.8, 10.2])
        s = MonteCarloDriver._compute_stability(values)
        assert s > 0.9  # high stability

    def test_range_bounds(self) -> None:
        """Stability is always in [0, 1] for random inputs."""
        rng = np.random.default_rng(42)
        for _ in range(50):
            values = rng.normal(0.0, 1.0, 100)
            s = MonteCarloDriver._compute_stability(values)
            assert 0.0 <= s <= 1.0 + 1e-10

    def test_empty_input(self) -> None:
        s = MonteCarloDriver._compute_stability(np.array([]))
        assert s == 0.0

    def test_zero_mean_nonzero_std(self) -> None:
        """Zero mean with nonzero std => stability = 0."""
        values = np.array([-1.0, 0.0, 1.0])
        s = MonteCarloDriver._compute_stability(values)
        assert s == 0.0


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


class TestAggregation:
    """Verifies _aggregate produces correct values from known outputs."""

    def test_aggregate_known_distribution(self) -> None:
        """Aggregation of known expected_r values produces correct stats."""
        driver = MonteCarloDriver()

        outputs: list[SimulationOutput] = []
        for r in [0.5, 1.0, 1.5, 2.0, 2.5]:
            # All LONG_NOW so we can set exit_reason predictably
            exit_reason = "TARGET_HIT" if r >= 1.5 else "STOP_HIT"
            outputs.append(
                _make_output(best_action="LONG_NOW", r=r, exit_reason=exit_reason)
            )

        config = MonteCarloConfig(num_paths=5, seed=42)
        result = driver._aggregate(outputs, config)

        assert result.num_paths == 5
        assert result.expected_r_distribution.mean == pytest.approx(1.5, abs=1e-6)
        assert result.expected_r_distribution.p50 == pytest.approx(1.5, abs=1e-6)
        # numpy default linear interpolation for 5 values:
        # p5 at position 4*0.05=0.2 -> 0.5+0.2*0.5=0.6
        # p95 at position 4*0.95=3.8 -> 2.0+0.8*0.5=2.4
        assert result.expected_r_distribution.p5 == pytest.approx(0.6, abs=1e-6)
        assert result.expected_r_distribution.p95 == pytest.approx(2.4, abs=1e-6)
        # 3 out of 5 hit target (>= 1.5)
        assert result.target_before_stop_probability == pytest.approx(0.6, abs=1e-6)
        assert result.stop_before_target_probability == pytest.approx(0.4, abs=1e-6)

    def test_aggregate_no_trade_paths(self) -> None:
        """NO_TRADE paths contribute r=0 to the distribution."""
        driver = MonteCarloDriver()

        outputs: list[SimulationOutput] = []
        for r in [0.5, 1.0]:
            outputs.append(
                _make_output(best_action="LONG_NOW", r=r, exit_reason="TARGET_HIT")
            )
        # NO_TRADE → r = 0.0
        outputs.append(
            _make_output(best_action="NO_TRADE", r=0.0, exit_reason="")
        )

        config = MonteCarloConfig(num_paths=3, seed=42)
        result = driver._aggregate(outputs, config)

        # Mean of [0.5, 1.0, 0.0] = 0.5
        assert result.expected_r_distribution.mean == pytest.approx(0.5, abs=1e-6)
        # Only 2 paths had LONG_NOW with TARGET_HIT
        assert result.target_before_stop_probability == pytest.approx(2.0 / 3.0, abs=1e-6)

    def test_aggregate_empty(self) -> None:
        driver = MonteCarloDriver()
        config = MonteCarloConfig(num_paths=0, seed=42)
        result = driver._aggregate([], config)
        assert result.num_paths == 0
        assert result.downside_risk == 0.0
        assert result.confidence_stability == 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_output(
    best_action: str,
    r: float,
    exit_reason: str,
    action: str = "",
) -> SimulationOutput:
    """Build a minimal SimulationOutput for aggregation testing."""
    if not action:
        action = best_action if best_action != "NO_TRADE" else "LONG_NOW"

    ao = ActionOutcome(
        action=action,
        realized_r_net=r,
        realized_r_gross=r,
        exit_reason=exit_reason,
        exit_price=100.0,
        total_cost_r=0.0,
        hold_duration_bars=1,
    )
    nto = NoTradeOutcome()

    return SimulationOutput(
        simulation_run_id="test",
        symbol="TEST",
        decision_timestamp="2026-07-01T00:00:00Z",
        mode="SWING",
        primary_interval="1h",
        resolution_status="COMPLETE",
        long_outcome=ao if action == "LONG_NOW" else ActionOutcome(action="LONG_NOW"),
        short_outcome=ao if action == "SHORT_NOW" else ActionOutcome(action="SHORT_NOW"),
        no_trade_outcome=nto,
        best_action=best_action,
        second_best_action="NO_TRADE" if best_action != "NO_TRADE" else "LONG_NOW",
        action_gap_r=0.5,
        regret_r=0.0,
        is_ambiguous=False,
    )
