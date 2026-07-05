"""
Gate configuration — per-gate thresholds, enabled/disabled, stop-on-fail.

Provides GateConfig dataclass, a DEFAULT_GATE_CONFIG list with canonical
G0-G10 defaults, and a YAML loader for custom configurations.

Usage:
    from v7.gates.config import DEFAULT_GATE_CONFIG, load_gate_config

    # Use defaults
    config = DEFAULT_GATE_CONFIG

    # Load from YAML
    config = load_gate_config("configs/gates.yaml")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GateConfig:
    """Per-gate configuration entry.

    Attributes:
        gate_id:    Canonical gate ID, e.g. "G0", "G1", "G10".
        enabled:    If False, the gate is skipped during evaluation.
        threshold:  Override threshold for the gate (if applicable).
                    Uses the gate's internal threshold when None.
        stop_on_fail: If True, evaluation stops immediately on failure.
    """

    gate_id: str
    enabled: bool = True
    threshold: float | None = None
    stop_on_fail: bool = False


# ── Default Gate Configurations ──────────────────────────────────────────
# These match the canonical G0-G10 gate definitions from evaluator.py.
# Threshold overrides left as None to use gate-internal defaults.
# G7-G10 are disabled by default (infrastructure not yet built).

DEFAULT_GATE_CONFIG: list[GateConfig] = [
    GateConfig("G0", enabled=True,  stop_on_fail=True),   # DOC_READY (structural)
    GateConfig("G1", enabled=True,  stop_on_fail=False),  # RESEARCH_BACKTEST
    GateConfig("G2", enabled=True,  stop_on_fail=False),  # WALK_FORWARD_OOS
    GateConfig("G3", enabled=True,  stop_on_fail=False),  # COST_STRESS
    GateConfig("G4", enabled=True,  stop_on_fail=False),  # REGIME_BREAKDOWN
    GateConfig("G5", enabled=True,  stop_on_fail=False),  # SYMBOL_STABILITY
    GateConfig("G6", enabled=True,  stop_on_fail=False),  # CALIBRATION_RELIABILITY
    GateConfig("G7", enabled=True,  stop_on_fail=False),  # SHADOW
    GateConfig("G8", enabled=True,  stop_on_fail=False),  # PAPER
    GateConfig("G9", enabled=True,  stop_on_fail=False),  # TINY_LIVE
    GateConfig("G10", enabled=True, stop_on_fail=False),  # LIVE
]


def _config_to_dict(config: GateConfig) -> dict[str, Any]:
    """Serialize a single GateConfig to a dict for YAML export."""
    return {
        "gate_id": config.gate_id,
        "enabled": config.enabled,
        "threshold": config.threshold,
        "stop_on_fail": config.stop_on_fail,
    }


def _dict_to_config(d: dict[str, Any]) -> GateConfig:
    """Deserialize a dict to a GateConfig, validating required fields."""
    gate_id = d.get("gate_id", "")
    if not gate_id or not gate_id.startswith("G"):
        raise ValueError(f"Invalid gate_id in config: '{gate_id}'")
    return GateConfig(
        gate_id=gate_id,
        enabled=d.get("enabled", True),
        threshold=d.get("threshold"),
        stop_on_fail=d.get("stop_on_fail", False),
    )


def load_gate_config(path: str) -> list[GateConfig]:
    """Load gate configuration from a YAML file.

    The YAML file should contain a top-level 'gates' key with a list of
    gate config dicts. Each dict must have a 'gate_id' field; all other
    fields are optional and default to GateConfig defaults.

    Args:
        path: Filesystem path to the YAML config file.

    Returns:
        A list of GateConfig objects. Missing gates use DEFAULT_GATE_CONFIG
        values as fallback.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the YAML is malformed or contains invalid gate IDs.
    """
    import yaml

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "gates" not in data:
        raise ValueError("YAML config must contain a top-level 'gates' list")

    gates_data = data["gates"]
    if not isinstance(gates_data, list):
        raise ValueError("'gates' must be a list")

    # Build a lookup from gate_id -> GateConfig
    loaded: dict[str, GateConfig] = {}
    for entry in gates_data:
        if not isinstance(entry, dict):
            raise ValueError(f"Each gate config entry must be a dict, got {type(entry).__name__}")
        cfg = _dict_to_config(entry)
        loaded[cfg.gate_id] = cfg

    # Merge with defaults: loaded entries override defaults for missing fields
    result: list[GateConfig] = []
    for default in DEFAULT_GATE_CONFIG:
        if default.gate_id in loaded:
            loaded_cfg = loaded[default.gate_id]
            # Merge: override fields that are explicitly set in YAML
            # (non-None threshold, explicit enabled/stop_on_fail)
            threshold = loaded_cfg.threshold if loaded_cfg.threshold is not None else default.threshold
            # enabled and stop_on_fail come from the loaded config entirely
            # since YAML explicit False means "disabled", not "use default"
            result.append(GateConfig(
                gate_id=default.gate_id,
                enabled=loaded_cfg.enabled,
                threshold=threshold,
                stop_on_fail=loaded_cfg.stop_on_fail,
            ))
        else:
            result.append(default)

    return result


def resolve_gate_configs(
    custom_config: list[GateConfig] | None = None,
) -> list[GateConfig]:
    """Resolve a custom config against defaults.

    Args:
        custom_config: Optional override config list. If None,
                       DEFAULT_GATE_CONFIG is returned.

    Returns:
        A list of GateConfig objects. Missing gates in the custom config
        are filled from DEFAULT_GATE_CONFIG.
    """
    if custom_config is None:
        return list(DEFAULT_GATE_CONFIG)

    lookup = {cfg.gate_id: cfg for cfg in DEFAULT_GATE_CONFIG}
    for cfg in custom_config:
        lookup[cfg.gate_id] = cfg

    # Preserve canonical G0-G10 order
    return [lookup[g.gate_id] for g in DEFAULT_GATE_CONFIG]
