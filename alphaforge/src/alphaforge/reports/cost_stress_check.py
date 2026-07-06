"""Cost stress check bridge — wires alphaforge WFV results to simulation CostStressRunner.

P0.9G: Uses the existing compute_cost_stress() from alphaforge.validation.cost_stress
(which models linear R costs from baseline fee/slippage/spread at configurable
multipliers) and converts its output into the dict format expected by
_build_empirical_cost_stress() and _gate_g3().

Domain boundary: alphaforge.reports imports from alphaforge.validation, NOT from
simulation directly. The simulation cost model constants are accessed through
the validation layer's defaults, which can be overridden per mode.

Usage:
    from alphaforge.reports.cost_stress_check import compute_cost_stress_for_wfv
    cost_stress_dict = compute_cost_stress_for_wfv(
        net_expectancy_r=0.004,
        mode="SCALP",
    )
    wfv_results["cost_stress"] = cost_stress_dict
"""

from __future__ import annotations

from typing import Any, Dict

from alphaforge.validation.cost_stress import (
    compute_cost_stress,
    cost_stress_to_stress_levels,
)

# Baseline cost percentages per side (matching simulation authority).
# taker_fee_bps=4.0 → 0.04%, slippage_bps=1.0 → 0.01%
_DEFAULT_FEE_PCT: float = 0.04
_DEFAULT_SLIPPAGE_PCT: float = 0.01

# Mode-specific stop multipliers for entry risk estimation.
# entry_risk_pct = stop_mult * 0.01 (approximate ATR = 1% of price).
_MODE_STOP_MULT: dict[str, float] = {
    "SCALP": 1.5,
    "AGGRESSIVE_SCALP": 1.5,
    "SWING": 2.0,
}


def _entry_risk_for_mode(mode: str) -> float:
    """Estimate entry risk percentage for a mode from its stop multiplier.

    The default entry_risk_pct in compute_cost_stress is 0.02 (2%),
    which assumes SWING's 2.0 stop_mult with ~1% ATR.
    For SCALP's 1.5 stop_mult: 1.5 * 0.01 = 0.015 (1.5%).
    """
    stop_mult = _MODE_STOP_MULT.get(mode, 2.0)
    return stop_mult * 0.01


def compute_cost_stress_for_wfv(
    net_expectancy_r: float,
    mode: str,
    fee_pct: float = _DEFAULT_FEE_PCT,
    slippage_pct: float = _DEFAULT_SLIPPAGE_PCT,
) -> Dict[str, Any]:
    """Compute cost stress dict for a WFV result.

    This is the bridge function called by the empirical report builder.
    It wraps compute_cost_stress() with mode-appropriate defaults and
    converts the structured result into the dict format expected by
    the report schema and _gate_g3().

    Args:
        net_expectancy_r: OOS net expectancy R per active trade from WFV.
        mode: Trading mode ('SCALP', 'SWING', 'AGGRESSIVE_SCALP').
        fee_pct: Baseline fee percentage (default 0.04 = 4 bps).
        slippage_pct: Baseline slippage percentage (default 0.01 = 1 bp).

    Returns:
        Dict with keys:
            combined_stress_edge_survives: bool
            break_even_cost_total_pct: float
            stressed_net_expectancy_r: float (net R at 2.0x fee stress)
            baseline_fee_pct: float
            baseline_slippage_pct: float
            fee_stress_levels: list
            slippage_stress_levels: list
            cost_stress_verdict: str
    """
    entry_risk_pct = _entry_risk_for_mode(mode)

    result = compute_cost_stress(
        oos_expectancy_r=net_expectancy_r,
        baseline_fee_pct=fee_pct,
        baseline_slippage_pct=slippage_pct,
        entry_risk_pct=entry_risk_pct,
    )

    stress_dict = cost_stress_to_stress_levels(
        result,
        baseline_fee_pct=fee_pct,
        baseline_slippage_pct=slippage_pct,
    )

    # Add the stressed net expectancy at 2.0x fee (SCALP G3 requirement)
    fee_2x = next(
        (lv.get("oos_expectancy_r", 0.0) for lv in stress_dict.get("fee_stress_levels", [])
         if lv.get("multiplier") == 2.0),
        0.0,
    )
    stress_dict["stressed_net_expectancy_r"] = fee_2x

    return stress_dict
