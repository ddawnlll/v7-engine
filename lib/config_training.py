"""
Training configuration — single source of truth for training parameters.

Provides a frozen TrainingConfig dataclass that combines:
- Canonical simulation profile parameters (from simulation.profile_registry)
- Training-specific config (from configs/training.yaml)

Usage:
    from lib.config_training import load_training_config

    config = load_training_config("SCALP")
    print(config.stop_multiplier)   # 1.75 (canonical simulation value)
    print(config.label_horizon)     # computed from max_holding_bars
    print(config.confidence_threshold)  # 0.50 (matching old behavior, overridable in training.yaml)

Design: mirrors the pattern in v7/gates/config.py
Domain: lib/ is NOT the ideal home for this (it crosses into simulation/), but
the simulation registry IS the canonical authority for stop/target/horizon
parameters.  The alternative (alphaforge/ or a new domain) would create a
circular authority dependency or duplicate the registry lookup.  This loader
is kept minimal — it reads, validates, and returns; it does NOT re-define
simulation parameters.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Label parameter defaults (per mode) ──────────────────────────────
# label_horizon: number of bars to look forward for forward-return label.
# label_threshold: return threshold to classify as LONG/SHORT vs NO_TRADE.
# These are NOT simulation parameters — they are alphaforge research choices
# that depend on the mode's timeframe.  The defaults below match the values
# that were previously hardcoded in MODE_CONFIG in train.py / real_training.py.
MODE_LABEL_DEFAULTS: dict[str, dict[str, float | int]] = {
    "SWING": {
        "label_horizon": 24,
        "label_threshold": 0.005,
    },
    "SCALP": {
        "label_horizon": 12,
        "label_threshold": 0.003,
    },
    "AGGRESSIVE_SCALP": {
        "label_horizon": 8,
        "label_threshold": 0.002,
    },
}


# ── TrainingConfig dataclass ─────────────────────────────────────────


@dataclass(frozen=True)
class TrainingConfig:
    """Single source of truth for training configuration.

    Combines the canonical simulation profile with training-specific
    configuration from ``configs/training.yaml``.

    Attributes:
        mode:                Trading mode (SWING, SCALP, AGGRESSIVE_SCALP).
        primary_interval:    Primary trading interval (from simulation profile).
        max_holding_bars:    Maximum bars to hold a position (from simulation).
        stop_multiplier:     Stop distance as ATR multiple (from simulation).
        target_multiplier:   Target distance as ATR multiple (from simulation).
        ambiguity_margin_r:  Ambiguity margin in R-multiples (from simulation).
        min_action_edge_r:   Minimum edge threshold (from simulation).
        stop_method:         ATR method for stops (from simulation).
        target_method:       ATR method for targets (from simulation).
        no_trade_default:    Whether NO_TRADE is the default (from simulation).
        label_horizon:       Horizon in bars for forward-return labels.
        label_threshold:     Return threshold for label classification.
        wfv_folds:           Walk-forward validation folds (from training.yaml).
        algorithm:           ML algorithm (xgboost / lightgbm).
        confidence_threshold:Confidence threshold for trade filtering.
        features:            Feature groups to use ("all" or list).
        xgboost_params:      XGBoost hyperparameters (from training.yaml).
        lightgbm_params:     LightGBM hyperparameters (from training.yaml).
        gates:               Gate safety settings (from training.yaml).
        profile_version:     Simulation profile version string.
        profile_hash:        16-char sim profile hash for lineage tracking.
    """

    mode: str
    # ── Simulation profile (authoritative) ─────────────────────────
    primary_interval: str
    max_holding_bars: int
    stop_multiplier: float
    target_multiplier: float
    ambiguity_margin_r: float
    min_action_edge_r: float
    stop_method: str
    target_method: str
    no_trade_default: bool
    # ── Label parameters (research choice) ─────────────────────────
    label_horizon: int
    label_threshold: float
    # ── Training config (from training.yaml) ───────────────────────
    wfv_folds: int
    algorithm: str
    confidence_threshold: float
    features: str | list[str]
    xgboost_params: dict[str, Any] = field(default_factory=dict)
    lightgbm_params: dict[str, Any] = field(default_factory=dict)
    gates: dict[str, bool] = field(default_factory=dict)
    # ── Profile tracking ───────────────────────────────────────────
    profile_version: str = ""
    profile_hash: str = ""


def _compute_label_horizon_from_profile(profile: Any) -> int:
    """Derive label horizon from MODE_LABEL_DEFAULTS (per-mode research choices).

    For triple-barrier (stop/target) labels, label_horizon = max_holding_bars
    is correct in principle, but AGGRESSIVE_SCALP research chose 8 bars
    (vs max_holding_bars=5) to ensure enough forward price context.
    MODE_LABEL_DEFAULTS preserves these per-mode research choices.
    """
    mode_key = profile.mode.value if hasattr(profile.mode, "value") else str(profile.mode)
    defaults = MODE_LABEL_DEFAULTS.get(mode_key)
    if defaults is not None:
        return int(defaults["label_horizon"])
    return profile.max_holding_bars


def _compute_label_threshold_from_profile(profile: Any) -> float:
    """Derive a label threshold from the simulation profile.

    Uses the target_multiplier as a heuristic: a threshold that captures
    economically meaningful moves is ~0.5 * atr * target_mult / entry_price.
    Since we don't know entry price here, use the convention from MODE_LABEL_DEFAULTS.
    """
    mode_key = profile.mode.value if hasattr(profile.mode, "value") else str(profile.mode)
    defaults = MODE_LABEL_DEFAULTS.get(mode_key, MODE_LABEL_DEFAULTS["SWING"])
    return float(defaults["label_threshold"])


# ── Public API ───────────────────────────────────────────────────────


def load_training_config(
    mode: str,
    config_path: str | Path = "configs/training.yaml",
    profile_hash: str | None = None,
) -> TrainingConfig:
    """Load training configuration for the given mode.

    Merges canonical simulation registry parameters with training
    config from ``configs/training.yaml``.  Simulation profile values
    are authoritative (LOCKED) and override training.yaml where they
    overlap.

    Args:
        mode:         Trading mode (SWING, SCALP, AGGRESSIVE_SCALP).
        config_path:  Path to training.yaml config file (default: ``configs/training.yaml``).
        profile_hash: Optional specific profile version hash.  When None,
                      uses the latest registered version.

    Returns:
        A frozen ``TrainingConfig`` with merged values.

    Raises:
        ValueError:      If mode is unknown or config is malformed.
        FileNotFoundError: If ``config_path`` does not exist.
    """
    import yaml

    mode_upper = mode.upper()

    # ── 1. Load simulation profile (canonical authority) ───────────
    from simulation.profile_registry.registry import get_profile, _compute_profile_hash

    profile = get_profile(mode_upper, version=profile_hash)
    actual_hash = _compute_profile_hash(profile)
    profile_version = profile.profile_version

    # ── 2. Load training.yaml ──────────────────────────────────────
    config_path = Path(config_path)
    if config_path.exists():
        with open(config_path) as f:
            yaml_data = yaml.safe_load(f) or {}
    else:
        logger.warning("Training config %s not found, using defaults", config_path)
        yaml_data = {}

    training_cfg = yaml_data.get("training", {}) if isinstance(yaml_data, dict) else {}

    # ── 3. Resolve label parameters ────────────────────────────────
    # Use simulation profile -> max_holding_bars as label_horizon.
    # Use per-mode defaults for threshold.
    label_horizon = _compute_label_horizon_from_profile(profile)
    label_defaults = MODE_LABEL_DEFAULTS.get(mode_upper, MODE_LABEL_DEFAULTS["SWING"])
    label_threshold = training_cfg.get("label_threshold") or float(
        label_defaults["label_threshold"]
    )

    # ── 4. Algorithm params ────────────────────────────────────────
    xgb_params = dict(training_cfg.get("xgboost", {}))
    lgb_params = dict(training_cfg.get("lightgbm", {}))
    xgb_params.setdefault("max_depth", 4)
    xgb_params.setdefault("learning_rate", 0.05)
    xgb_params.setdefault("n_estimators", 200)
    xgb_params.setdefault("subsample", 0.8)
    xgb_params.setdefault("colsample_bytree", 0.8)
    xgb_params.setdefault("early_stopping_rounds", 20)
    xgb_params.setdefault("tree_method", "hist")
    xgb_params.setdefault("n_jobs", -1)
    lgb_params.setdefault("max_depth", 6)
    lgb_params.setdefault("learning_rate", 0.05)
    lgb_params.setdefault("n_estimators", 500)
    lgb_params.setdefault("subsample", 0.8)
    lgb_params.setdefault("colsample_bytree", 0.8)
    lgb_params.setdefault("early_stopping_rounds", 50)

    # ── 5. Gate safety ─────────────────────────────────────────────
    gates_cfg: dict[str, bool] = {}
    gates_raw = yaml_data.get("gates", {}) if isinstance(yaml_data, dict) else {}
    for gate_key in ("training_authorized", "wfv_authorized"):
        gates_cfg[gate_key] = bool(gates_raw.get(gate_key, False))

    return TrainingConfig(
        mode=mode_upper,
        primary_interval=profile.primary_interval,
        max_holding_bars=profile.max_holding_bars,
        stop_multiplier=profile.stop_multiplier,
        target_multiplier=profile.target_multiplier,
        ambiguity_margin_r=profile.ambiguity_margin_r,
        min_action_edge_r=profile.min_action_edge_r,
        stop_method=profile.stop_method,
        target_method=profile.target_method,
        no_trade_default=profile.no_trade_default,
        label_horizon=label_horizon,
        label_threshold=label_threshold,
        wfv_folds=int(training_cfg.get("wfv_folds", 6)),
        algorithm=str(training_cfg.get("algorithm", "xgboost")),
        confidence_threshold=float(training_cfg.get("confidence_threshold", 0.50)),
        features=training_cfg.get("features", "all"),
        xgboost_params=xgb_params,
        lightgbm_params=lgb_params,
        gates=gates_cfg,
        profile_version=profile_version,
        profile_hash=actual_hash,
    )


def resolve_training_scope(
    mode: str,
    scope_type: str = "research",
    config_path: str | Path = "configs/training.yaml",
) -> dict[str, Any]:
    """Resolve training scope (research or full) from config.

    Args:
        mode:       Trading mode.
        scope_type: ``"research"`` or ``"full"``.
        config_path: Path to training.yaml.

    Returns:
        Dict with ``symbols``, ``intervals``, ``primary_interval``,
        and ``time_range`` keys.
    """
    import yaml

    config_path = Path(config_path)
    if not config_path.exists():
        config = load_training_config(mode, config_path)
        return {
            "symbols": {
                "min": 8,
                "max": 20,
            } if scope_type == "research" else {
                "min": 60,
            },
            "intervals": [config.primary_interval],
            "primary_interval": config.primary_interval,
            "time_range": {},
        }

    with open(config_path) as f:
        yaml_data = yaml.safe_load(f) or {}

    scope = yaml_data.get(scope_type, {})
    config = load_training_config(mode, config_path)

    # If intervals not specified in scope, use primary from simulation profile
    intervals = scope.get("intervals", [config.primary_interval])

    return {
        "symbols": scope.get("symbols", {}),
        "intervals": intervals,
        "primary_interval": config.primary_interval,
        "time_range": scope.get("time_range_months", {}),
    }
