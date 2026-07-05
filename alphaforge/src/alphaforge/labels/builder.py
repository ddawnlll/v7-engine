"""
AlphaForge label builder — converts SimulationOutput to AlphaForgeLabel.

Produces classification labels (LONG_NOW / SHORT_NOW / NO_TRADE / AMBIGUOUS_STATE)
and regression targets (R-multiples, path quality) for XGBoost training.

Domain rule: AlphaForge consumes SimulationOutput through side-effect-free
adapters. This builder does NOT import simulation internals.
"""

from __future__ import annotations

from typing import Any

from alphaforge.errors import AlphaForgeError


# Canonical mode thresholds (from simulation/docs/profiles.md)
_MODE_DEFAULTS: dict[str, dict[str, float]] = {
    "SWING": {
        "min_action_edge_r": 0.35,
        "ambiguity_margin_r": 0.20,
    },
    "SCALP": {
        "min_action_edge_r": 0.15,
        "ambiguity_margin_r": 0.10,
    },
    "AGGRESSIVE_SCALP": {
        "min_action_edge_r": 0.08,
        "ambiguity_margin_r": 0.05,
    },
}

LABEL_INTERPRETATION_VERSION = "labelint-1.0.0"


def _resolve_thresholds(mode: str, **overrides) -> dict[str, float]:
    """Resolve mode thresholds, with optional overrides."""
    defaults = _MODE_DEFAULTS.get(mode)
    if defaults is None:
        defaults = {"min_action_edge_r": 0.15, "ambiguity_margin_r": 0.10}
    result = dict(defaults)
    for key in ("min_action_edge_r", "ambiguity_margin_r"):
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

    Returns:
        Dict matching the AlphaForgeLabel schema.

    Raises:
        AlphaForgeError: If required fields are missing from simulation_output.
    """
    mode = simulation_output.get("mode", "")
    thresholds = _resolve_thresholds(mode, **kwargs)

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

    Args:
        simulation_outputs: List of SimulationOutput dicts.
        **kwargs: Passed through to build_label.

    Returns:
        List of AlphaForgeLabel dicts.
    """
    return [build_label(so, **kwargs) for so in simulation_outputs]
