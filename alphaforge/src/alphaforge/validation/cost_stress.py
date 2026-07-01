"""Cost stress computation — independent fee, slippage, spread dimensions.

Computes whether an edge survives under independent cost stress scenarios:
  - Fee stress at 1.5x, 2x, 3x of baseline fee
  - Slippage stress at 1.5x, 2x, 3x of baseline slippage
  - Spread sensitivity at 1.5x, 2x of baseline spread
  - Combined worst-case (all costs at highest multiplier)
  - Break-even total cost multiplier

Uses a linear cost model:
  cost_r = 2 * cost_pct / 100 / entry_risk_pct

where cost_pct is the per-side cost as a percentage of notional,
and entry_risk_pct is the stop distance as a fraction of price
(default 0.02 = 2% for SWING; SCALP modes have tighter stops).

Domain boundary: AlphaForge owns validation design and execution.
The function is in alphaforge.validation because it feeds thesis
validator evidence and validation reports.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from alphaforge.validation.contracts import (
    CostStressResult,
    NOT_EVALUATED,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default entry risk as fraction of price (stop distance / price).
# SWING mode: ~2% (ATR * 2.0 stop_mult / price, typical).
# SCALP modes might be 0.5-1.0%, but callers can override.
_DEFAULT_ENTRY_RISK_PCT: float = 0.02

# Default baseline costs as percentages of notional (per side).
_DEFAULT_FEE_PCT: float = 0.04       # 4 bps taker fee
_DEFAULT_SLIPPAGE_PCT: float = 0.02  # 2 bps slippage
_DEFAULT_SPREAD_PCT: float = 0.01    # 1 bp spread

# Default stress multiplier sets.
_FEE_MULTIPLIERS: Tuple[float, ...] = (1.5, 2.0, 3.0)
_SLIPPAGE_MULTIPLIERS: Tuple[float, ...] = (1.5, 2.0, 3.0)
_SPREAD_MULTIPLIERS: Tuple[float, ...] = (1.5, 2.0)


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def _cost_component_r(
    cost_pct: float,
    entry_risk_pct: float,
) -> float:
    """Convert a per-side cost percentage to R-multiple.

    Models round-trip cost (entry + exit), so the factor is 2.
    cost_pct is a percentage (e.g., 0.04 = 4 bps).
    entry_risk_pct is a decimal fraction (e.g., 0.02 = 2%).
    """
    if entry_risk_pct <= 0:
        return 0.0
    return 2.0 * (cost_pct / 100.0) / entry_risk_pct


def _extra_cost_r(
    baseline_pct: float,
    multiplier: float,
    entry_risk_pct: float,
) -> float:
    """Extra cost in R beyond baseline for a given cost component.

    When multiplier = 1.0, extra cost is 0.
    """
    if multiplier <= 1.0:
        return 0.0
    baseline_r = _cost_component_r(baseline_pct, entry_risk_pct)
    return baseline_r * (multiplier - 1.0)


def compute_cost_stress(
    oos_expectancy_r: float,
    baseline_fee_pct: float = _DEFAULT_FEE_PCT,
    baseline_slippage_pct: float = _DEFAULT_SLIPPAGE_PCT,
    baseline_spread_pct: float = _DEFAULT_SPREAD_PCT,
    entry_risk_pct: float = _DEFAULT_ENTRY_RISK_PCT,
    fee_multipliers: Tuple[float, ...] = _FEE_MULTIPLIERS,
    slippage_multipliers: Tuple[float, ...] = _SLIPPAGE_MULTIPLIERS,
    spread_multipliers: Tuple[float, ...] = _SPREAD_MULTIPLIERS,
) -> CostStressResult:
    """Compute independent cost stress dimensions from OOS expectancy.

    Args:
        oos_expectancy_r: Net OOS expectancy in R-multiples (after baseline
            costs). This is the primary signal the edge survives on.
        baseline_fee_pct: Baseline taker fee as a percentage of notional
            (e.g., 0.04 = 4 bps). Default 0.04.
        baseline_slippage_pct: Baseline slippage as a percentage of notional.
            Default 0.02.
        baseline_spread_pct: Baseline spread cost as a percentage of notional.
            Default 0.01.
        entry_risk_pct: Entry risk (stop distance) as a fraction of price.
            Default 0.02 (2%) for SWING.
        fee_multipliers: Fee stress multipliers to test. Default (1.5, 2.0, 3.0).
        slippage_multipliers: Slippage stress multipliers. Default (1.5, 2.0, 3.0).
        spread_multipliers: Spread stress multipliers. Default (1.5, 2.0).

    Returns:
        CostStressResult with all fields populated (NOT_EVALUATED sentinel
        is never returned from this function; every field has a float or bool).
    """
    if entry_risk_pct <= 0:
        entry_risk_pct = _DEFAULT_ENTRY_RISK_PCT

    # Baseline costs in R
    fee_baseline_r = _cost_component_r(baseline_fee_pct, entry_risk_pct)
    slip_baseline_r = _cost_component_r(baseline_slippage_pct, entry_risk_pct)
    spread_baseline_r = _cost_component_r(baseline_spread_pct, entry_risk_pct)
    total_baseline_cost_r = fee_baseline_r + slip_baseline_r + spread_baseline_r

    # Gross edge before costs
    gross_expectancy_r = oos_expectancy_r + total_baseline_cost_r

    # ------------------------------------------------------------------
    # 1. Fee stress scenarios
    # ------------------------------------------------------------------
    fee_results: Dict[float, float] = {}
    for mult in fee_multipliers:
        extra = _extra_cost_r(baseline_fee_pct, mult, entry_risk_pct)
        fee_results[mult] = gross_expectancy_r - total_baseline_cost_r - extra

    # Map to named fields (1.5x -> field name)
    fee_1_5x = fee_results.get(1.5, gross_expectancy_r - total_baseline_cost_r)
    fee_2x = fee_results.get(2.0, gross_expectancy_r - total_baseline_cost_r)
    fee_3x = fee_results.get(3.0, gross_expectancy_r - total_baseline_cost_r)

    fee_survives = (
        oos_expectancy_r > 0  # must have positive baseline edge
        and all(v > 0 for v in fee_results.values())
    )

    # ------------------------------------------------------------------
    # 2. Slippage stress scenarios
    # ------------------------------------------------------------------
    slip_results: Dict[float, float] = {}
    for mult in slippage_multipliers:
        extra = _extra_cost_r(baseline_slippage_pct, mult, entry_risk_pct)
        slip_results[mult] = gross_expectancy_r - total_baseline_cost_r - extra

    slip_1_5x = slip_results.get(1.5, gross_expectancy_r - total_baseline_cost_r)
    slip_2x = slip_results.get(2.0, gross_expectancy_r - total_baseline_cost_r)
    slip_3x = slip_results.get(3.0, gross_expectancy_r - total_baseline_cost_r)

    slip_survives = (
        oos_expectancy_r > 0
        and all(v > 0 for v in slip_results.values())
    )

    # ------------------------------------------------------------------
    # 3. Spread sensitivity scenarios
    # ------------------------------------------------------------------
    spread_results: Dict[float, float] = {}
    for mult in spread_multipliers:
        extra = _extra_cost_r(baseline_spread_pct, mult, entry_risk_pct)
        spread_results[mult] = gross_expectancy_r - total_baseline_cost_r - extra

    spread_1_5x = spread_results.get(1.5, gross_expectancy_r - total_baseline_cost_r)
    spread_2x = spread_results.get(2.0, gross_expectancy_r - total_baseline_cost_r)

    # ------------------------------------------------------------------
    # 4. Combined worst-case stress
    #    Apply the highest multiplier from each set simultaneously.
    # ------------------------------------------------------------------
    max_fee_mult = max(fee_multipliers)
    max_slip_mult = max(slippage_multipliers)
    max_spread_mult = max(spread_multipliers)

    extra_fee = _extra_cost_r(baseline_fee_pct, max_fee_mult, entry_risk_pct)
    extra_slip = _extra_cost_r(baseline_slippage_pct, max_slip_mult, entry_risk_pct)
    extra_spread = _extra_cost_r(baseline_spread_pct, max_spread_mult, entry_risk_pct)
    combined_extra_r = extra_fee + extra_slip + extra_spread
    combined_r = gross_expectancy_r - total_baseline_cost_r - combined_extra_r
    combined_survives = combined_r > 0

    # ------------------------------------------------------------------
    # 5. Break-even cost calculation
    #    Total multiplier that would bring net edge to zero.
    #    If total_baseline_cost_r is zero, break-even is infinite.
    # ------------------------------------------------------------------
    if total_baseline_cost_r > 0 and oos_expectancy_r > 0:
        break_even_mult = 1.0 + oos_expectancy_r / total_baseline_cost_r
    elif oos_expectancy_r <= 0:
        break_even_mult = 0.0  # edge already destroyed at baseline
    else:
        break_even_mult = float("inf")  # zero-cost edge

    return CostStressResult(
        fee_baseline=fee_baseline_r,
        fee_stress_1_5x=fee_1_5x,
        fee_stress_2x=fee_2x,
        fee_stress_3x=fee_3x,
        slippage_baseline=slip_baseline_r,
        slippage_stress_1_5x=slip_1_5x,
        slippage_stress_2x=slip_2x,
        slippage_stress_3x=slip_3x,
        spread_baseline=spread_baseline_r,
        spread_stress_1_5x=spread_1_5x,
        spread_stress_2x=spread_2x,
        combined_stress=combined_r,
        break_even_cost=break_even_mult,
        fee_stress_edge_survives=fee_survives,
        slippage_stress_edge_survives=slip_survives,
        combined_stress_edge_survives=combined_survives,
        # funding_deferred_block is preserved from the default
    )


# ---------------------------------------------------------------------------
# Converter to report dict format
# ---------------------------------------------------------------------------


def cost_stress_to_stress_levels(
    result: CostStressResult,
    baseline_fee_pct: float,
    baseline_slippage_pct: float,
) -> Dict[str, Any]:
    """Convert a CostStressResult to the dict format used by empirical reports.

    Produces the structure expected by _build_empirical_cost_stress and
    the ModeResearchReport schema.

    Args:
        result: Populated CostStressResult from compute_cost_stress().
        baseline_fee_pct: Baseline fee percentage (e.g., 0.04).
        baseline_slippage_pct: Baseline slippage percentage (e.g., 0.02).

    Returns:
        Dict with keys:
            baseline_fee_pct, baseline_slippage_pct,
            fee_stress_levels (list of {multiplier, oos_expectancy_r, edge_survives}),
            slippage_stress_levels (list of {...}),
            combined_stress_edge_survives,
            break_even_cost_total_pct,
            net_edge_after_costs,
            cost_stress_verdict.
    """
    fee_levels: List[Dict[str, Any]] = []
    field_map = {
        1.5: ("fee_stress_1_5x", "fee_stress_edge_survives"),
        2.0: ("fee_stress_2x", "fee_stress_edge_survives"),
        3.0: ("fee_stress_3x", "fee_stress_edge_survives"),
    }
    for mult, (expect_attr, survive_attr) in field_map.items():
        expect_val = getattr(result, expect_attr, 0.0)
        survive_val = getattr(result, survive_attr, False)
        # For fee-specific stress, check that the edge under this exact
        # multiplier is positive
        edge_survives = bool(expect_val > 0) if isinstance(expect_val, (int, float)) else False
        fee_levels.append({
            "multiplier": mult,
            "oos_expectancy_r": expect_val if isinstance(expect_val, (int, float)) else 0.0,
            "edge_survives": edge_survives,
        })

    slip_levels: List[Dict[str, Any]] = []
    slip_field_map = {
        1.5: ("slippage_stress_1_5x", "slippage_stress_edge_survives"),
        2.0: ("slippage_stress_2x", "slippage_stress_edge_survives"),
        3.0: ("slippage_stress_3x", "slippage_stress_edge_survives"),
    }
    for mult, (expect_attr, survive_attr) in slip_field_map.items():
        expect_val = getattr(result, expect_attr, 0.0)
        edge_survives = bool(expect_val > 0) if isinstance(expect_val, (int, float)) else False
        slip_levels.append({
            "multiplier": mult,
            "oos_expectancy_r": expect_val if isinstance(expect_val, (int, float)) else 0.0,
            "edge_survives": edge_survives,
        })

    combined = bool(result.combined_stress_edge_survives)
    break_even = (
        float(result.break_even_cost)
        if isinstance(result.break_even_cost, (int, float))
        else 0.0
    )

    # net_edge_after_costs is combined_stress in this model
    net_edge = float(result.combined_stress) if isinstance(result.combined_stress, (int, float)) else 0.0

    return {
        "baseline_fee_pct": baseline_fee_pct,
        "baseline_slippage_pct": baseline_slippage_pct,
        "fee_stress_levels": fee_levels,
        "slippage_stress_levels": slip_levels,
        "combined_stress_edge_survives": combined,
        "break_even_cost_total_pct": break_even,
        "net_edge_after_costs": net_edge,
        "cost_stress_verdict": (
            "PASS" if combined
            else "FAIL_EDGE_DESTROYED_BY_COSTS"
        ),
    }
