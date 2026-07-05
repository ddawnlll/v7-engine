"""
MonteCarloAdapter -- side-effect-free Monte Carlo robustness simulation.

Takes a single SimulationInput, generates N perturbed future paths by
adding Gaussian noise to candle prices, runs the simulation on each
perturbed path, and aggregates results into MonteCarloOutput.

This is diagnostic/distributional evidence -- it does NOT replace
realized simulation truth. Outputs carry separate monte_carlo_run_id
lineage so they are distinguishable from realized simulation outputs.

No network I/O, no exchange APIs. Pure deterministic computation
(seeded random noise for reproducibility).
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import replace
from typing import Any

from simulation.contracts.models import (
    Candle,
    FuturePath,
    MonteCarloOutput,
    SimulationInput,
    SimulationOutput,
)
from simulation.engine.engine import simulate
from simulation.adapters._validation import (
    validate_monte_carlo_output,
    validate_simulation_input,
)

# ---------------------------------------------------------------------------
# Seeded Gaussian noise generator (pure, no global state)
# ---------------------------------------------------------------------------


class _SeededNoise:
    """Deterministic Gaussian noise generator.

    Uses Python's ``random.Random`` -- a pure-PRNG with no global state, no
    system entropy calls, and no I/O. Identical seed always produces
    identical noise sequences.
    """

    __slots__ = ("_rng",)

    def __init__(self, seed: int) -> None:
        self._rng = __import__("random").Random(seed)

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        return self._rng.gauss(mu, sigma)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class MonteCarloAdapter:
    """Side-effect-free Monte Carlo robustness simulation.

    Generates N perturbed versions of a SimulationInput, runs simulation
    on each, and aggregates into MonteCarloOutput with distributional
    statistics.

    All randomness is seeded for full reproducibility.
    """

    KIND: str = "MONTE_CARLO"

    def __init__(
        self,
        n_perturbations: int = 100,
        noise_std: float = 0.01,
        seed: int = 42,
    ):
        """Initialize Monte Carlo adapter.

        Args:
            n_perturbations: Number of perturbed paths to generate.
            noise_std: Standard deviation of Gaussian noise applied to
                candle prices, as a fraction of price (e.g. 0.01 = 1%).
            seed: PRNG seed for deterministic reproducibility.
        """
        if n_perturbations < 1:
            raise ValueError(
                f"n_perturbations must be >= 1, got {n_perturbations}"
            )
        if noise_std <= 0:
            raise ValueError(
                f"noise_std must be positive, got {noise_std}"
            )

        self._n = n_perturbations
        self._noise_std = noise_std
        self._seed = seed

    # ── Public API ────────────────────────────────────────────────────────

    def get_adapter_kind(self) -> str:
        """Return 'MONTE_CARLO'."""
        return self.KIND

    def run(self, input: SimulationInput) -> MonteCarloOutput:
        """Run Monte Carlo perturbation simulation.

        Args:
            input: Baseline SimulationInput.

        Returns:
            MonteCarloOutput with baseline result, perturbed results,
            and aggregate statistics.

        Raises:
            ValueError: If input validation fails.
        """
        errors = self.validate_input(input)
        if errors:
            raise ValueError(
                f"MonteCarloAdapter input validation failed: "
                f"{'; '.join(errors)}"
            )

        mc_run_id = str(uuid.uuid4())

        # Baseline (unperturbed) run
        baseline_output = simulate(input)
        baseline_lineage = replace(baseline_output.lineage, adapter_kind=self.KIND)
        baseline_output = replace(
            baseline_output,
            lineage=baseline_lineage,
            monte_carlo_run_id=mc_run_id,
        )

        # Perturbed runs
        noise_gen = _SeededNoise(self._seed)
        perturbed_outputs: list[SimulationOutput] = []

        for _ in range(self._n):
            perturbed = self._perturb_input(input, noise_gen)
            p_output = simulate(perturbed)
            p_lineage = replace(p_output.lineage, adapter_kind=self.KIND)
            p_output = replace(
                p_output,
                lineage=p_lineage,
                monte_carlo_run_id=mc_run_id,
            )
            perturbed_outputs.append(p_output)

        # Aggregate statistics
        agg = self._compute_aggregate_stats(perturbed_outputs)

        result = MonteCarloOutput(
            baseline_output=baseline_output,
            perturbed_outputs=perturbed_outputs,
            monte_carlo_run_id=mc_run_id,
            perturbation_params={
                "n_perturbations": self._n,
                "noise_std": self._noise_std,
                "seed": self._seed,
            },
            aggregate_stats=agg,
        )

        out_errors = validate_monte_carlo_output(result)
        if out_errors:
            raise ValueError(
                f"MonteCarloAdapter output validation failed: "
                f"{'; '.join(out_errors)}"
            )

        return result

    def validate_input(self, input: SimulationInput) -> list[str]:
        """Validate input for Monte Carlo simulation.

        Delegates to the shared input validator; Monte Carlo has no
        additional input constraints beyond the standard ones.
        """
        return validate_simulation_input(input)

    def validate_output(self, output: MonteCarloOutput) -> list[str]:
        """Validate a MonteCarloOutput."""
        return validate_monte_carlo_output(output)

    @staticmethod
    def is_side_effect_free() -> bool:
        """Return True: MonteCarloAdapter has no side effects."""
        return True

    # ── Internal: perturbation ────────────────────────────────────────────

    @staticmethod
    def _perturb_input(
        input: SimulationInput,
        noise_gen: _SeededNoise,
    ) -> SimulationInput:
        """Create a perturbed copy of *input* with noisy future path candles.

        Each candle's open, high, low, close receives independent
        multiplicative Gaussian noise. Volume and timestamp are preserved.
        """
        noisy_candles: list[Candle] = []
        for candle in input.future_path.candles:
            factor = 1.0 + noise_gen.gauss(0.0, 0.01)  # base noise on prices
            # Each OHLC value gets its own noise factor
            noisy_candles.append(
                Candle(
                    open=candle.open * (1.0 + noise_gen.gauss(0.0, 0.01)),
                    high=candle.high * (1.0 + noise_gen.gauss(0.0, 0.01)),
                    low=candle.low * (1.0 + noise_gen.gauss(0.0, 0.01)),
                    close=candle.close * (1.0 + noise_gen.gauss(0.0, 0.01)),
                    volume=candle.volume,
                    close_time_utc=candle.close_time_utc,
                )
            )

        noisy_path = FuturePath(
            candles=noisy_candles,
            completeness_status=input.future_path.completeness_status,
            expected_bars=input.future_path.expected_bars,
        )

        return replace(input, future_path=noisy_path)

    # ── Internal: aggregation ─────────────────────────────────────────────

    @staticmethod
    def _compute_aggregate_stats(
        outputs: list[SimulationOutput],
    ) -> dict[str, Any]:
        """Compute distributional statistics across perturbed outputs.

        Returns a dict with:
          - long_realized_r_net: {mean, std, min, max, p5, p25, p50, p75, p95}
          - short_realized_r_net: {mean, std, min, max, p5, p25, p50, p75, p95}
          - best_action_distribution: map of action -> count
          - action_gap_r: {mean, std}
        """
        long_r = [o.long_outcome.realized_r_net for o in outputs]
        short_r = [o.short_outcome.realized_r_net for o in outputs]
        gap_r = [o.action_gap_r for o in outputs]

        # Best action counts
        action_counts: dict[str, int] = {}
        for o in outputs:
            action_counts[o.best_action] = action_counts.get(o.best_action, 0) + 1

        return {
            "long_realized_r_net": _describe(long_r),
            "short_realized_r_net": _describe(short_r),
            "best_action_distribution": dict(
                sorted(action_counts.items(), key=lambda x: -x[1])
            ),
            "action_gap_r": {
                "mean": _mean(gap_r),
                "std": _stdev(gap_r),
            },
        }


# ---------------------------------------------------------------------------
# Descriptive statistics helpers
# ---------------------------------------------------------------------------


def _describe(values: list[float]) -> dict[str, float]:
    """Compute descriptive statistics for a list of floats."""
    if not values:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0,
                "p5": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0}
    sorted_vals = sorted(values)
    return {
        "mean": _mean(values),
        "std": _stdev(values),
        "min": sorted_vals[0],
        "max": sorted_vals[-1],
        "p5": sorted_vals[max(0, round(len(sorted_vals) * 0.05) - 1)],
        "p25": sorted_vals[max(0, round(len(sorted_vals) * 0.25) - 1)],
        "p50": sorted_vals[max(0, round(len(sorted_vals) * 0.50) - 1)],
        "p75": sorted_vals[max(0, round(len(sorted_vals) * 0.75) - 1)],
        "p95": sorted_vals[max(0, round(len(sorted_vals) * 0.95) - 1)],
    }


def _mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) >= 2 else 0.0
