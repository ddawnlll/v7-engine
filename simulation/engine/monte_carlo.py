"""
Monte Carlo robustness simulation for the /simulation engine.

Generates N perturbed future paths, runs the simulation engine on each,
and aggregates distributional metrics for diagnostic evidence.

Perturbation methods:
  - PRICE_NOISE: Gaussian noise on each candle close
  - PATH_RESAMPLE: Bootstrapped returns from empirical distribution

Monte Carlo is diagnostic/distributional evidence only.
It does NOT replace realized simulation truth.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationOutput,
)
from simulation.engine.engine import simulate


class PerturbationMethod(str, Enum):
    """Available perturbation methods for Monte Carlo simulation."""

    PRICE_NOISE = "price_noise"
    PATH_RESAMPLE = "path_resample"


@dataclass
class MonteCarloConfig:
    """Configuration for a Monte Carlo simulation run.

    Attributes:
        num_paths: Number of perturbed paths (default 100).
        perturbation_method: Method for perturbing candle paths.
        sigma: Standard deviation for price noise (default 0.002 = 0.2%).
        seed: Random seed for reproducible results.
        max_threads: Max threads for optional parallel execution (reserved).
    """

    num_paths: int = 100
    perturbation_method: PerturbationMethod = PerturbationMethod.PRICE_NOISE
    sigma: float = 0.002
    seed: int = 42
    max_threads: int = 4


@dataclass
class ExpectedRDistribution:
    """Distributional summary of expected R across all perturbed paths."""

    mean: float = 0.0
    std: float = 0.0
    p5: float = 0.0
    p25: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p95: float = 0.0


@dataclass
class MonteCarloResult:
    """Aggregated Monte Carlo simulation result.

    Carries separate lineage (monte_carlo_run_id) distinct from the
    base simulation (base_simulation_run_id). Diagnostic only -- never
    replaces realized simulation truth.
    """

    monte_carlo_run_id: str = ""
    monte_carlo_family_version: str = "mcfam-1.0"
    base_simulation_run_id: str = ""
    perturbation_method: str = "price_noise"
    perturbation_sigma: float = 0.002
    num_paths: int = 100
    expected_r_distribution: ExpectedRDistribution = field(
        default_factory=ExpectedRDistribution
    )
    downside_risk: float = 0.0
    target_before_stop_probability: float = 0.0
    stop_before_target_probability: float = 0.0
    tail_risk: float = 0.0
    confidence_stability: float = 0.0


class MonteCarloDriver:
    """Drives N-path Monte Carlo robustness simulation.

    Usage:
        driver = MonteCarloDriver()
        config = MonteCarloConfig(num_paths=100, sigma=0.002)
        result = driver.run(simulation_input, config)
    """

    _mc_family_version = "mcfam-1.0"

    # -- Public API ----------------------------------------------------------

    def run(
        self,
        input: SimulationInput,
        config: MonteCarloConfig,
    ) -> MonteCarloResult:
        """Run Monte Carlo simulation with N perturbed paths.

        Args:
            input: Base simulation input (unperturbed).
            config: Monte Carlo configuration (num_paths, method, sigma, seed).

        Returns:
            MonteCarloResult with distributional metrics across all paths.
        """
        rng = np.random.default_rng(config.seed)

        # Run baseline simulation to capture base run ID
        baseline_output = simulate(input)

        # Generate perturbed inputs
        if config.perturbation_method == PerturbationMethod.PRICE_NOISE:
            perturbed = self._perturb_price_noise(
                input, config.num_paths, config.sigma, rng,
            )
        elif config.perturbation_method == PerturbationMethod.PATH_RESAMPLE:
            perturbed = self._perturb_path_resample(
                input, config.num_paths, rng,
            )
        else:
            raise ValueError(
                f"Unknown perturbation method: {config.perturbation_method}"
            )

        # Run simulation on each perturbed path
        outputs = self._run_batch(perturbed)

        # Aggregate into result
        result = self._aggregate(outputs, config)
        result.base_simulation_run_id = baseline_output.simulation_run_id

        return result

    # -- Perturbation Methods ------------------------------------------------

    def _perturb_price_noise(
        self,
        input: SimulationInput,
        num_paths: int,
        sigma: float,
        rng: np.random.Generator,
    ) -> list[SimulationInput]:
        """Generate N perturbed copies using Gaussian price noise.

        For each candle:
            perturbed_close = close * (1 + noise), noise ~ N(0, sigma)
            perturbed_high  = max(high, perturbed_close)
            perturbed_low   = min(low, perturbed_close)
        """
        candles = input.future_path.candles
        perturbed: list[SimulationInput] = []

        for _ in range(num_paths):
            new_candles: list[Candle] = []
            for c in candles:
                noise = float(rng.normal(0.0, sigma))
                new_close = c.close * (1.0 + noise)
                new_high = max(c.high, new_close)
                new_low = min(c.low, new_close)

                new_candles.append(
                    Candle(
                        open=c.open,
                        high=new_high,
                        low=new_low,
                        close=new_close,
                        volume=c.volume,
                        close_time_utc=c.close_time_utc,
                    )
                )

            perturbed.append(self._make_input(input, new_candles))

        return perturbed

    def _perturb_path_resample(
        self,
        input: SimulationInput,
        num_paths: int,
        rng: np.random.Generator,
    ) -> list[SimulationInput]:
        """Generate N perturbed copies using bootstrapped returns.

        Computes close-to-close returns from the original future path, then
        samples with replacement to generate new price paths. Falls back to
        price noise if the return distribution is degenerate (all zeros).
        """
        candles = input.future_path.candles
        n_candles = len(candles)

        if n_candles == 0:
            return []

        # Compute close-to-close returns from empirical path
        returns: list[float] = []
        prev = input.entry_price
        for c in candles:
            ret = (c.close - prev) / prev if prev > 0 else 0.0
            returns.append(ret)
            prev = c.close

        returns_arr = np.array(returns)

        # Degenerate case: all returns are zero -- fall back to price noise
        if np.all(returns_arr == 0.0):
            return self._perturb_price_noise(input, num_paths, 0.002, rng)

        perturbed: list[SimulationInput] = []

        for _ in range(num_paths):
            sampled = rng.choice(returns_arr, size=n_candles, replace=True)
            new_candles: list[Candle] = []
            prev_price = input.entry_price

            for i, c in enumerate(candles):
                new_close = prev_price * (1.0 + float(sampled[i]))
                prev_price = new_close

                new_candles.append(
                    Candle(
                        open=c.open,
                        high=max(c.high, new_close),
                        low=min(c.low, new_close),
                        close=new_close,
                        volume=c.volume,
                        close_time_utc=c.close_time_utc,
                    )
                )

            perturbed.append(self._make_input(input, new_candles))

        return perturbed

    # -- Batch Execution -----------------------------------------------------

    def _run_batch(
        self,
        inputs: list[SimulationInput],
    ) -> list[SimulationOutput]:
        """Run the simulation engine on each perturbed input.

        Each output carries a unique monte_carlo_run_id for lineage
        traceability.
        """
        outputs: list[SimulationOutput] = []
        for inp in inputs:
            out = simulate(inp)
            out.monte_carlo_run_id = self._generate_mc_run_id()
            out.monte_carlo_family_version = self._mc_family_version
            outputs.append(out)
        return outputs

    # -- Aggregation ---------------------------------------------------------

    def _aggregate(
        self,
        outputs: list[SimulationOutput],
        config: MonteCarloConfig,
    ) -> MonteCarloResult:
        """Aggregate simulation outputs into a MonteCarloResult.

        Extracts the best action's realized_r_net from each output and
        computes distributional metrics including downside risk (CVaR),
        tail risk, target/stop probabilities, and confidence stability.
        """
        if not outputs:
            return MonteCarloResult(
                monte_carlo_run_id=self._generate_mc_run_id(),
                monte_carlo_family_version=self._mc_family_version,
                perturbation_method=config.perturbation_method.value,
                perturbation_sigma=config.sigma,
                num_paths=0,
            )

        expected_r_values: list[float] = []
        target_count = 0
        stop_count = 0

        for out in outputs:
            if out.best_action == "LONG_NOW":
                r = out.long_outcome.realized_r_net
                if out.long_outcome.exit_reason == "TARGET_HIT":
                    target_count += 1
                elif out.long_outcome.exit_reason == "STOP_HIT":
                    stop_count += 1
            elif out.best_action == "SHORT_NOW":
                r = out.short_outcome.realized_r_net
                if out.short_outcome.exit_reason == "TARGET_HIT":
                    target_count += 1
                elif out.short_outcome.exit_reason == "STOP_HIT":
                    stop_count += 1
            else:  # NO_TRADE
                r = 0.0
            expected_r_values.append(r)

        values = np.array(expected_r_values)
        num_paths = len(outputs)

        # Distributional metrics
        mean = float(np.mean(values))
        std = float(np.std(values, ddof=1)) if num_paths > 1 else 0.0

        percentiles = np.percentile(values, [5.0, 25.0, 50.0, 75.0, 95.0])
        p5, p25, p50, p75, p95 = [float(v) for v in percentiles]

        downside_risk = self._compute_cvar(values, 0.05)
        tail_risk = float(np.min(values))
        confidence_stability = self._compute_stability(values)

        target_prob = target_count / num_paths
        stop_prob = stop_count / num_paths

        return MonteCarloResult(
            monte_carlo_run_id=self._generate_mc_run_id(),
            monte_carlo_family_version=self._mc_family_version,
            base_simulation_run_id="",
            perturbation_method=config.perturbation_method.value,
            perturbation_sigma=config.sigma,
            num_paths=num_paths,
            expected_r_distribution=ExpectedRDistribution(
                mean=round(mean, 6),
                std=round(std, 6),
                p5=round(p5, 6),
                p25=round(p25, 6),
                p50=round(p50, 6),
                p75=round(p75, 6),
                p95=round(p95, 6),
            ),
            downside_risk=round(downside_risk, 6),
            target_before_stop_probability=round(target_prob, 6),
            stop_before_target_probability=round(stop_prob, 6),
            tail_risk=round(tail_risk, 6),
            confidence_stability=round(confidence_stability, 6),
        )

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def _generate_mc_run_id() -> str:
        """Generate a unique Monte Carlo run ID."""
        return "mc_" + str(uuid.uuid4())[:8]

    @staticmethod
    def _compute_cvar(values: np.ndarray, alpha: float) -> float:
        """Compute Conditional Value at Risk (expected shortfall).

        Args:
            values: Array of outcome values.
            alpha: Tail probability (e.g. 0.05 for worst 5%).

        Returns:
            Mean of the worst alpha-fraction of outcomes.
        """
        if len(values) == 0:
            return 0.0
        threshold = np.percentile(values, alpha * 100.0)
        tail = values[values <= threshold]
        if len(tail) == 0:
            return float(threshold)
        return float(np.mean(tail))

    @staticmethod
    def _compute_stability(values: np.ndarray) -> float:
        """Compute confidence stability metric (0-1).

        1.0 = perfectly stable (zero variance across paths).
        0.0 = highly variable relative to the mean.

        Formula: |mean| / (|mean| + std_population)
        """
        if len(values) == 0:
            return 0.0
        m = float(np.mean(values))
        s = float(np.std(values, ddof=0))  # population standard deviation
        if s == 0.0:
            return 1.0
        return min(1.0, abs(m) / (abs(m) + s))

    @staticmethod
    def _make_input(
        base: SimulationInput,
        candles: list[Candle],
    ) -> SimulationInput:
        """Create a SimulationInput with perturbed candles.

        Preserves all non-candle fields from the base input.
        """
        return SimulationInput(
            symbol=base.symbol,
            decision_timestamp=base.decision_timestamp,
            mode=base.mode,
            primary_interval=base.primary_interval,
            entry_price=base.entry_price,
            atr=base.atr,
            future_path=FuturePath(
                candles=candles,
                completeness_status=base.future_path.completeness_status,
                expected_bars=base.future_path.expected_bars,
            ),
            profile=base.profile,
            simulation_family_version=base.simulation_family_version,
            cost_model_version=base.cost_model_version,
        )
