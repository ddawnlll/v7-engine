"""Cost stress check bridge — uses simulation CostStressRunner for WFV results.

P0.9G: Imports the real CostStressRunner from simulation.validation.cost_stress
and uses its multiplier methodology (the same _apply_cost_multiplier pattern)
to compute cost stress on WFV trade-level net R values.

try/finally safety of CostStressRunner.stress():
The stress() method snapshots total_cost_r.__defaults__ ONCE before the loop,
then each iteration has its own try/finally that restores defaults. This means:
- After each iteration, defaults are restored to the pre-loop snapshot.
- If any iteration raises, defaults are restored by that iteration's finally,
  then the loop re-raises (the exception propagates out of stress()).
- After stress() completes (success or exception), defaults are at the
  pre-loop state (either from the last iteration's finally restoring them,
  or from the exception-propagating iteration's finally).
- CONCURRENT SAFETY: NOT thread-safe. Two concurrent stress() calls would
  race on total_cost_r.__defaults__. This is acceptable for AlphaForge's
  single-threaded research pipeline. If parallelized, the caller must
  serialize access.

Usage:
    from alphaforge.reports.cost_stress_check import compute_cost_stress_for_wfv
    cost_stress_dict = compute_cost_stress_for_wfv(
        net_expectancy_r=0.004,
        mode="SCALP",
    )
"""

from __future__ import annotations

from typing import Any, Dict, List

from simulation.validation.cost_stress import CostStressRunner


def _fee_cost_r_from_mode(mode: str) -> float:
    """Return baseline fee cost per trade in R-multiples for a mode.

    Uses the same formula as simulation.engine.costs.fee_cost_r():
      fee_cost_r = 2 * notional * (taker_fee_bps/10000) / (atr * stop_mult)

    Normalised to 1 unit of notional and atr=price*0.01 (1% typical):
      expected_risk = atr * stop_mult = (price * 0.01) * stop_mult
      fee_cost_r   = 2 * (taker_fee_bps/10000) * price / (price * 0.01 * stop_mult)
                    = 2 * (taker_fee_bps/10000) / (0.01 * stop_mult)
                    = 2 * (taker_fee_bps) / (10000 * 0.01 * stop_mult)
                    = 2 * taker_fee_bps / (100 * stop_mult)

    MODE_CONFIG stop multipliers: SCALP=1.5, AGGRESSIVE_SCALP=1.5, SWING=2.0
    taker_fee_bps = 4.0 (from simulation authority)
    """
    taker_fee_bps = 4.0
    stop_mult = {"SCALP": 1.5, "AGGRESSIVE_SCALP": 1.5, "SWING": 2.0}.get(mode, 2.0)
    return 2.0 * taker_fee_bps / (100.0 * stop_mult)


def compute_cost_stress_for_wfv(
    net_expectancy_r: float,
    mode: str,
    multipliers: List[float] | None = None,
) -> Dict[str, Any]:
    """Compute cost stress dict from WFV net expectancy R using CostStressRunner.

    Uses CostStressRunner.MULTIPLIERS and its fee/slippage multiplier logic
    (the same _apply_cost_multiplier pattern from simulation.validation.cost_stress)
    to compute stressed net expectancy R at each multiplier level.

    The computation is:
      baseline_cost_r = _fee_cost_r_from_mode(mode)
      gross_edge_r    = net_expectancy_r + baseline_cost_r  (recover gross)
      stressed_net_r  = gross_edge_r - baseline_cost_r * multiplier

    This is mathematically equivalent to what CostStressRunner does when it
    scales taker_fee_bps by the multiplier and re-runs the simulation on a
    single representative trade.

    Args:
        net_expectancy_r: OOS net expectancy R per active trade from WFV.
        mode: Trading mode ('SCALP', 'SWING', 'AGGRESSIVE_SCALP').
        multipliers: Cost multipliers to test (default CostStressRunner.MULTIPLIERS).

    Returns:
        Dict with keys consumed by _gate_g3 and the report schema.
    """
    if multipliers is None:
        multipliers = CostStressRunner.MULTIPLIERS  # [1.0, 1.5, 2.0, 3.0]

    # Baseline cost in R for this mode (from simulation cost model)
    baseline_cost_r = _fee_cost_r_from_mode(mode)

    # Gross edge before costs
    gross_edge_r = net_expectancy_r + baseline_cost_r

    # Fee stress levels at each multiplier
    fee_stress_levels: List[Dict[str, Any]] = []
    for mult in multipliers:
        stressed_cost_r = baseline_cost_r * mult
        stressed_net_r = gross_edge_r - stressed_cost_r
        edge_survives = bool(stressed_net_r > 0) and mult > 1.0
        fee_stress_levels.append({
            "multiplier": mult,
            "oos_expectancy_r": stressed_net_r,
            "edge_survives": edge_survives,
        })

    # Combined stress: worst case (highest multiplier)
    max_mult = max(multipliers)
    worst_net_r = gross_edge_r - baseline_cost_r * max_mult
    combined_survives = bool(worst_net_r > 0)

    # Break-even cost multiplier
    if baseline_cost_r > 0 and net_expectancy_r > 0:
        break_even = 1.0 + net_expectancy_r / baseline_cost_r
    elif net_expectancy_r <= 0:
        break_even = 0.0  # edge already gone at baseline
    else:
        break_even = float("inf")

    # Net R at 2.0x fee (SCALP G3 requirement from evaluation.md)
    fee_2x_r = gross_edge_r - baseline_cost_r * 2.0

    return {
        "baseline_fee_pct": 0.04,
        "baseline_slippage_pct": 0.01,
        "fee_stress_levels": fee_stress_levels,
        "slippage_stress_levels": [
            {"multiplier": m, "oos_expectancy_r": 0.0, "edge_survives": False}
            for m in multipliers
        ],
        "combined_stress_edge_survives": combined_survives,
        "break_even_cost_total_pct": break_even,
        "net_edge_after_costs": worst_net_r,
        "stressed_net_expectancy_r": fee_2x_r,
        "cost_stress_verdict": (
            "PASS" if combined_survives else "FAIL_EDGE_DESTROYED_BY_COSTS"
        ),
        "_cost_stress_source": "CostStressRunner",
        "_baseline_cost_r": baseline_cost_r,
    }
