"""
AlphaForge label builder — converts SimulationOutput to AlphaForgeLabel.

Produces classification labels (LONG_NOW / SHORT_NOW / NO_TRADE / AMBIGUOUS_STATE)
and regression targets (R-multiples, path quality) for XGBoost training.

Supports ATR-adaptive stop/target multipliers for dynamic position sizing
based on rolling ATR percentile rank.

Domain rule: AlphaForge consumes SimulationOutput through side-effect-free
adapters. This builder does NOT import simulation internals.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from alphaforge.errors import AlphaForgeError


# Canonical mode thresholds (from simulation/docs/profiles.md)
_MODE_DEFAULTS: dict[str, dict[str, float]] = {
    "SWING": {
        "min_action_edge_r": 0.35,
        "ambiguity_margin_r": 0.20,
        "stop_multiplier": 2.0,
        "target_multiplier": 2.0,
    },
    "SCALP": {
        "min_action_edge_r": 0.15,
        "ambiguity_margin_r": 0.10,
        "stop_multiplier": 1.5,
        "target_multiplier": 1.5,
    },
    "AGGRESSIVE_SCALP": {
        "min_action_edge_r": 0.08,
        "ambiguity_margin_r": 0.05,
        "stop_multiplier": 1.0,
        "target_multiplier": 1.0,
    },
}

LABEL_INTERPRETATION_VERSION = "labelint-1.0.0"


def _resolve_thresholds(mode: str, **overrides) -> dict[str, float]:
    """Resolve mode thresholds, with optional overrides."""
    defaults = _MODE_DEFAULTS.get(mode)
    if defaults is None:
        defaults = {
            "min_action_edge_r": 0.15,
            "ambiguity_margin_r": 0.10,
            "stop_multiplier": 2.0,
            "target_multiplier": 2.0,
        }
    result = dict(defaults)
    for key in ("min_action_edge_r", "ambiguity_margin_r", "stop_multiplier", "target_multiplier"):
        if overrides.get(key) is not None:
            result[key] = float(overrides[key])
    return result


def _get_nested(obj: dict, path: str, default: Any = None) -> Any:
    """Get a nested dict value by dot-separated path."""
    parts = path.split(".")
    current = obj
    for part in parts:
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def build_label(simulation_output: dict[str, Any], **kwargs) -> dict[str, Any]:
    """Build an AlphaForgeLabel row from a SimulationOutput dict.

    Args:
        simulation_output: Dict matching the SimulationOutput schema.
        **kwargs: Optional overrides:
            min_action_edge_r: Override for the mode's min action edge.
            ambiguity_margin_r: Override for the mode's ambiguity gap.
            adaptive_stop: Enable ATR-adaptive stop/target multipliers (default True).
            atr_percentile_window: Rolling window for ATR percentile rank (default 20).
            atr_percentile_rank: Pre-computed ATR percentile rank [0, 1].
                If adaptive_stop is True and no rank is provided, the builder
                attempts to extract ATR values from simulation_output to compute
                a rolling percentile rank. If insufficient data, rank defaults to 0.5.

    Returns:
        Dict matching the AlphaForgeLabel schema.

    Raises:
        AlphaForgeError: If required fields are missing from simulation_output.
    """
    mode = simulation_output.get("mode", "")
    thresholds = _resolve_thresholds(mode, **kwargs)

    adaptive_stop = kwargs.get("adaptive_stop", True)
    atr_percentile_window = kwargs.get("atr_percentile_window", 20)

    # Resolve base stop/target multipliers from simulation profile
    profile = simulation_output.get("profile", {})
    base_stop_mult = profile.get("stop_multiplier") or thresholds.get("stop_multiplier", 2.0)
    base_target_mult = profile.get("target_multiplier") or thresholds.get("target_multiplier", 2.0)

    # Resolve ATR percentile rank for adaptive stop/target
    atr_percentile_rank = kwargs.get("atr_percentile_rank")
    if adaptive_stop and atr_percentile_rank is None:
        # Attempt to compute percentile rank from ATR list in simulation_output
        atr_values = simulation_output.get("atr_list", simulation_output.get("atr_values"))
        if atr_values is not None and len(atr_values) > 0:
            current_atr = simulation_output.get("atr")
            if current_atr is not None:
                atr_arr = np.array(atr_values[-atr_percentile_window:], dtype=np.float64)
                valid = atr_arr[~np.isnan(atr_arr)]
                if len(valid) > 0:
                    rank = np.mean(valid < current_atr)
                    atr_percentile_rank = float(rank)
                else:
                    atr_percentile_rank = 0.5
            else:
                atr_percentile_rank = 0.5
        else:
            atr_percentile_rank = 0.5

    # Compute effective stop/target multipliers
    if adaptive_stop and atr_percentile_rank is not None and not np.isnan(atr_percentile_rank):
        effective_stop_mult = base_stop_mult * (1.0 + atr_percentile_rank)
        effective_target_mult = base_target_mult * (1.0 + atr_percentile_rank)
    else:
        effective_stop_mult = base_stop_mult
        effective_target_mult = base_target_mult
        atr_percentile_rank = None

    # Extract required fields
    long_r_net = _get_nested(simulation_output, "long_outcome.realized_r_net")
    short_r_net = _get_nested(simulation_output, "short_outcome.realized_r_net")
    resolution_status = simulation_output.get("resolution_status", "COMPLETE")
    is_ambiguous = bool(simulation_output.get("is_ambiguous", False))

    if long_r_net is None or short_r_net is None:
        raise AlphaForgeError(
            f"Cannot build label: missing realized_r_net. "
            f"long={long_r_net}, short={short_r_net}"
        )

    # Determine label validity
    if resolution_status in ("UNRESOLVED", "INVALIDATED"):
        label_validity = "INVALID"
        best_action_label = "INVALID_OR_UNRESOLVED"
    elif is_ambiguous:
        label_validity = "AMBIGUOUS"
        best_action_label = "AMBIGUOUS_STATE"
    else:
        label_validity = "VALID"
        # Apply classification rules
        best_r = max(long_r_net, short_r_net)
        gap_r = abs(long_r_net - short_r_net)

        if gap_r < thresholds["ambiguity_margin_r"]:
            best_action_label = "AMBIGUOUS_STATE"
            label_validity = "AMBIGUOUS"
        elif best_r < thresholds["min_action_edge_r"]:
            best_action_label = "NO_TRADE"
        elif long_r_net > short_r_net:
            best_action_label = "LONG_NOW"
        else:
            best_action_label = "SHORT_NOW"

    # Build label row
    label = {
        "symbol": simulation_output.get("symbol", ""),
        "timestamp": simulation_output.get("decision_timestamp", ""),
        "mode": mode,
        "simulation_family_version": _get_nested(
            simulation_output, "lineage.simulation_family_version", "unknown"
        ),
        "label_interpretation_version": LABEL_INTERPRETATION_VERSION,
        "long_R_net": long_r_net,
        "short_R_net": short_r_net,
        "best_action_label": best_action_label,
        "label_validity": label_validity,
    }

    # ATR-adaptive stop/target fields
    if adaptive_stop and atr_percentile_rank is not None:
        label["atr_percentile_rank"] = atr_percentile_rank
        label["effective_stop_multiplier"] = effective_stop_mult
        label["effective_target_multiplier"] = effective_target_mult

    # Optional fields from path metrics
    for field, source_path in [
        ("long_mae_R", "long_outcome.path_metrics.mae_r"),
        ("short_mae_R", "short_outcome.path_metrics.mae_r"),
        ("long_mfe_R", "long_outcome.path_metrics.mfe_r"),
        ("short_mfe_R", "short_outcome.path_metrics.mfe_r"),
    ]:
        value = _get_nested(simulation_output, source_path)
        if value is not None:
            label[field] = value

    # Optional fields from no-trade outcome
    for field, source_path in [
        ("saved_loss_score", "no_trade_outcome.saved_loss_score"),
        ("missed_opportunity_score", "no_trade_outcome.missed_opportunity_score"),
    ]:
        value = _get_nested(simulation_output, source_path)
        if value is not None:
            label[field] = value

    # Optional: action gap and regret
    action_gap = simulation_output.get("action_gap_r")
    if action_gap is not None:
        label["action_gap_R"] = action_gap

    regret = simulation_output.get("regret_r", 0.0)
    if regret is not None:
        label["regret_R"] = regret

    # Path quality for best action
    if best_action_label in ("LONG_NOW",):
        pq = _get_nested(simulation_output, "long_outcome.path_metrics.path_quality_score")
    elif best_action_label in ("SHORT_NOW",):
        pq = _get_nested(simulation_output, "short_outcome.path_metrics.path_quality_score")
    else:
        pq = None
    if pq is not None:
        label["path_quality_score"] = pq

    return label


def build_labels(
    simulation_outputs: list[dict[str, Any]],
    **kwargs,
) -> list[dict[str, Any]]:
    """Build multiple labels from a list of SimulationOutput dicts.

    When adaptive_stop=True and no atr_percentile_rank is provided per-row,
    this function computes rolling percentile ranks across the batch using
    each output's 'atr' field and a sliding window.

    Args:
        simulation_outputs: List of SimulationOutput dicts.
        **kwargs: Passed through to build_label, except for batch-aware
            adaptive_stop which computes rolling percentiles across all rows.

    Returns:
        List of AlphaForgeLabel dicts.
    """
    adaptive_stop = kwargs.get("adaptive_stop", True)
    atr_percentile_window = kwargs.get("atr_percentile_window", 20)

    # Batch-compute rolling ATR percentile ranks if adaptive_stop is enabled
    # and no per-row atr_percentile_rank was explicitly provided.
    if adaptive_stop and "atr_percentile_rank" not in kwargs:
        atr_values = []
        for so in simulation_outputs:
            atr_val = so.get("atr")
            atr_values.append(atr_val if atr_val is not None else float("nan"))

        percentile_ranks = _compute_rolling_percentile_rank(
            np.array(atr_values, dtype=np.float64),
            window=atr_percentile_window,
        )

        labels = []
        for so, rank in zip(simulation_outputs, percentile_ranks):
            row_kwargs = dict(kwargs)
            row_kwargs["atr_percentile_rank"] = rank
            labels.append(build_label(so, **row_kwargs))
        return labels

    return [build_label(so, **kwargs) for so in simulation_outputs]


def _compute_rolling_percentile_rank(
    values: np.ndarray,
    window: int = 20,
) -> np.ndarray:
    """Compute rolling percentile rank of current value within trailing window.

    For each position t, computes the fraction of values in the window
    [t-window+1 .. t-1] that are less than the current value at t.
    Returns NaN for t < window (insufficient lookback).

    Args:
        values: 1D numpy array of ATR values (or any comparable series).
        window: Rolling window size.

    Returns:
        1D numpy array of percentile ranks in [0, 1], NaN at start.
    """
    n = len(values)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window or window < 2:
        return result

    for i in range(window, n):
        window_vals = values[i - window:i]
        current = values[i]
        if np.isnan(current):
            continue
        valid = window_vals[~np.isnan(window_vals)]
        if len(valid) < 2:
            result[i] = 0.5
        else:
            result[i] = float(np.mean(valid < current))

    return result
