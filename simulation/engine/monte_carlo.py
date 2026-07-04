"""
Monte Carlo robustness simulation.

Generates N perturbed future paths, runs the simulation engine on each,
and aggregates into distributional evidence.

Perturbation Method 1 (price_noise): Gaussian noise on OHLC candles.
"""

from __future__ import annotations

import copy
import math
import random
import uuid
from typing import Any

from simulation.contracts.models import Candle, MonteCarloConfig, MonteCarloOutput, SimulationInput
from simulation.engine.engine import simulate


def _perturb_candle(bar: Candle, sigma: float, rng: random.Random) -> Candle:
    """Add Gaussian noise to a candle's OHLC values."""
    noise = 1.0 + rng.gauss(0.0, sigma)
    new_close = bar.close * noise
    new_high = max(bar.high, new_close)
    new_low = min(bar.low, new_close)
    return Candle(
        open=bar.open,
        high=new_high,
        low=new_low,
        close=new_close,
        volume=bar.volume,
        close_time_utc=bar.close_time_utc,
    )


def _perturb_path(candles: list[Candle], sigma: float, rng: random.Random) -> list[Candle]:
    """Generate one perturbed copy of a candle path."""
    return [_perturb_candle(c, sigma, rng) for c in candles]


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear interpolation percentile."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    rank = (n - 1) * (pct / 100.0)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return sorted_values[lower]
    weight = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight


def _aggregate_mc(results: list[dict[str, Any]], config: MonteCarloConfig, base_run_id: str) -> MonteCarloOutput:
    """Aggregate per-path simulation results into MonteCarloOutput."""
    n = len(results)
    long_r = []
    short_r = []
    target_before_stop = 0
    stop_before_target = 0
    best_action_long = 0
    best_action_short = 0
    best_action_no_trade = 0
    all_best_r: list[float] = []

    for r in results:
        long_r.append(r["long_r_net"])
        short_r.append(r["short_r_net"])
        all_best_r.append(r["best_r"])
        if r["best_action"] == "LONG_NOW":
            best_action_long += 1
        elif r["best_action"] == "SHORT_NOW":
            best_action_short += 1
        else:
            best_action_no_trade += 1
        # Track exit outcomes for the best action only
        if r["best_action_exit"] == "TARGET_HIT":
            target_before_stop += 1
        elif r["best_action_exit"] == "STOP_HIT":
            stop_before_target += 1

    sorted_long = sorted(long_r)
    sorted_short = sorted(short_r)
    sorted_best = sorted(all_best_r)

    # Expected R distribution for the best action
    mean_r = sum(all_best_r) / n if n else 0.0
    variance = sum((x - mean_r) ** 2 for x in all_best_r) / n if n else 0.0
    std_r = math.sqrt(variance)

    # CVaR: average of worst 5%
    tail_count = max(1, n // 20)
    worst_5pct = sorted_best[:tail_count]
    cvar = sum(worst_5pct) / len(worst_5pct)

    # Tail risk: max drawdown from sorted equity
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r_val in sorted_best:
        equity += r_val
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)

    # Confidence stability: ratio of paths where best action matches majority
    majority_action = max(
        [(best_action_long, "LONG"), (best_action_short, "SHORT"), (best_action_no_trade, "NO_TRADE")],
        key=lambda x: x[0],
    )
    stability = majority_action[0] / n if n else 0.0

    return MonteCarloOutput(
        monte_carlo_run_id=f"mc_{uuid.uuid4().hex[:12]}",
        monte_carlo_family_version=config.monte_carlo_family_version,
        perturbation_method=config.perturbation_method,
        perturbation_sigma=config.perturbation_sigma,
        num_paths=n,
        base_simulation_run_id=base_run_id,
        best_action_long_runs=best_action_long / n if n else 0.0,
        best_action_short_runs=best_action_short / n if n else 0.0,
        best_action_no_trade_runs=best_action_no_trade / n if n else 0.0,
        expected_r_distribution={
            "mean": round(mean_r, 4),
            "std": round(std_r, 4),
            "p5": round(_percentile(sorted_best, 5), 4),
            "p25": round(_percentile(sorted_best, 25), 4),
            "p50": round(_percentile(sorted_best, 50), 4),
            "p75": round(_percentile(sorted_best, 75), 4),
            "p95": round(_percentile(sorted_best, 95), 4),
        },
        downside_risk=round(cvar, 4),
        target_before_stop_probability=round(target_before_stop / n, 4) if n else 0.0,
        stop_before_target_probability=round(stop_before_target / n, 4) if n else 0.0,
        tail_risk=round(abs(max_dd), 4),
        confidence_stability=round(stability, 4),
    )


def run_monte_carlo(
    input: SimulationInput,
    config: MonteCarloConfig | None = None,
) -> MonteCarloOutput:
    """Run N perturbed simulations and return distributional evidence.

    Args:
        input: Base SimulationInput with original future path.
        config: Monte Carlo configuration (num_paths, sigma, seed).

    Returns:
        MonteCarloOutput with aggregated distributional evidence.
    """
    cfg = config or MonteCarloConfig()
    rng = random.Random(cfg.perturbation_seed)
    base_run_id = input.simulation_family_version or "sim-unknown"

    results: list[dict[str, Any]] = []
    for _ in range(cfg.num_paths):
        perturbed_candles = _perturb_path(input.future_path.candles, cfg.perturbation_sigma, rng)
        perturbed_input = copy.deepcopy(input)
        perturbed_input.future_path.candles = perturbed_candles
        output = simulate(perturbed_input)

        best_action_str = output.best_action
        if best_action_str == "LONG_NOW":
            best_exit = output.long_outcome.exit_reason
        elif best_action_str == "SHORT_NOW":
            best_exit = output.short_outcome.exit_reason
        else:
            best_exit = "NO_TRADE"
        results.append({
            "long_r_net": output.long_outcome.realized_r_net,
            "short_r_net": output.short_outcome.realized_r_net,
            "best_r": max(
                output.long_outcome.realized_r_net,
                output.short_outcome.realized_r_net,
                0.0,
            ),
            "best_action": best_action_str,
            "best_action_exit": best_exit,
        })

    return _aggregate_mc(results, cfg, base_run_id)
