"""Regime Filter — boolean trade_allowed mask from regime features.

Takes CUSUM change point signals, HMM volatility states, and volatility
regime classifications and produces a per-bar trade_allowed boolean mask.

Rules:
  1. Skip bars with HIGH volatility regime (regime == 2.0)
  2. Skip bars with high HMM vol state (state == 1)
  3. Skip bars at CUSUM change points (signal == 1)
  4. Mode-specific tolerance windows for lenient filtering

Design constraints:
  - numpy-only
  - causal: trade_allowed[t] uses data at t only
  - deterministic: same input always produces identical output
  - PBO guard validation hooks available for auditing

Authority: AlphaForge owns regime filter.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Default thresholds (SWING baseline)
# ---------------------------------------------------------------------------

# CUSUM: skip bars where signal == 1 (change point detected)
SWING_CUSUM_BLOCK: bool = True
SCALP_CUSUM_BLOCK: bool = True
AGGRESSIVE_SCALP_CUSUM_BLOCK: bool = True

# HMM vol state: block when state == 1 (high volatility regime)
SWING_HMM_VOL_STATE_BLOCK: float = 1.0  # block state values >= this
SCALP_HMM_VOL_STATE_BLOCK: float = 1.0
AGGRESSIVE_SCALP_HMM_VOL_STATE_BLOCK: float = 1.0

# Volatility regime: block when regime >= this value
# regime values: 0=LOW, 1=MEDIUM, 2=HIGH
SWING_VOL_REGIME_BLOCK: float = 2.0  # block HIGH only
SCALP_VOL_REGIME_BLOCK: float = 1.5  # block MEDIUM+ for SCALP (tighter)
AGGRESSIVE_SCALP_VOL_REGIME_BLOCK: float = 1.0  # block MEDIUM+ for aggressive

# HMM vol probability threshold (0..1) — optional probability-based filtering
SWING_HMM_VOL_PROB_THRESHOLD: float = 0.8  # block when prob > threshold
SCALP_HMM_VOL_PROB_THRESHOLD: float = 0.6
AGGRESSIVE_SCALP_HMM_VOL_PROB_THRESHOLD: float = 0.5

# ---------------------------------------------------------------------------
# Mode-specific threshold map
# ---------------------------------------------------------------------------

_MODE_FILTER_DEFAULTS: dict[str, dict[str, float]] = {
    "SWING": {
        "cusum_block": float(SWING_CUSUM_BLOCK),
        "hmm_vol_state_block": SWING_HMM_VOL_STATE_BLOCK,
        "vol_regime_block": SWING_VOL_REGIME_BLOCK,
        "hmm_vol_prob_threshold": SWING_HMM_VOL_PROB_THRESHOLD,
    },
    "SCALP": {
        "cusum_block": float(SCALP_CUSUM_BLOCK),
        "hmm_vol_state_block": SCALP_HMM_VOL_STATE_BLOCK,
        "vol_regime_block": SCALP_VOL_REGIME_BLOCK,
        "hmm_vol_prob_threshold": SCALP_HMM_VOL_PROB_THRESHOLD,
    },
    "AGGRESSIVE_SCALP": {
        "cusum_block": float(AGGRESSIVE_SCALP_CUSUM_BLOCK),
        "hmm_vol_state_block": AGGRESSIVE_SCALP_HMM_VOL_STATE_BLOCK,
        "vol_regime_block": AGGRESSIVE_SCALP_VOL_REGIME_BLOCK,
        "hmm_vol_prob_threshold": AGGRESSIVE_SCALP_HMM_VOL_PROB_THRESHOLD,
    },
}


# ===========================================================================
# Core filter function
# ===========================================================================


def compute_regime_filter(
    cusum_signal: np.ndarray,
    hmm_vol_state: np.ndarray,
    volatility_regime: np.ndarray,
    hmm_vol_probability: Optional[np.ndarray] = None,
    mode: str = "SWING",
    **overrides,
) -> np.ndarray:
    """Compute trade_allowed boolean mask from regime features.

    Rules per bar:
      - trade_allowed[t] = True by default
      - False if cusum_signal[t] == 1 (change point detected, when cusum_block=True)
      - False if hmm_vol_state[t] >= hmm_vol_state_block (high vol state)
      - False if volatility_regime[t] >= vol_regime_block (e.g. HIGH vol)
      - False if hmm_vol_probability[t] > hmm_vol_prob_threshold (probability filter)

    Args:
        cusum_signal: CUSUM change point signal (0 or 1). NaN-safe.
        hmm_vol_state: HMM volatility state (0=low, 1=high). NaN-safe.
        volatility_regime: Volatility regime (0=LOW, 1=MEDIUM, 2=HIGH). NaN-safe.
        hmm_vol_probability: Optional HMM high-vol probability [0,1] for
            probability-based filtering. If None, this rule is skipped.
        mode: Trading mode string ("SWING", "SCALP", "AGGRESSIVE_SCALP").
        **overrides: Override any mode-specific threshold by name.

    Returns:
        Boolean numpy array of same length as inputs. True = trade allowed.

    Raises:
        ValueError: If input arrays have different lengths.
        ValueError: If mode is unknown.

    Causality: trade_allowed[t] uses regime features at t only. Purely
    per-bar decision — no lookahead, no future data access.
    """
    # Validate lengths match
    n = len(cusum_signal)
    if len(hmm_vol_state) != n or len(volatility_regime) != n:
        raise ValueError(
            f"Length mismatch: cusum_signal={n}, hmm_vol_state={len(hmm_vol_state)}, "
            f"volatility_regime={len(volatility_regime)}"
        )
    if hmm_vol_probability is not None and len(hmm_vol_probability) != n:
        raise ValueError(
            f"hmm_vol_probability length {len(hmm_vol_probability)} != {n}"
        )

    # Resolve thresholds
    mode_key = mode.upper()
    if mode_key not in _MODE_FILTER_DEFAULTS:
        raise ValueError(f"Unknown mode '{mode}'. Supported: {sorted(_MODE_FILTER_DEFAULTS)}")

    thresholds = dict(_MODE_FILTER_DEFAULTS[mode_key])
    thresholds.update(overrides)

    cusum_block = bool(thresholds["cusum_block"])
    hmm_vol_state_block = thresholds["hmm_vol_state_block"]
    vol_regime_block = thresholds["vol_regime_block"]
    hmm_vol_prob_threshold = thresholds["hmm_vol_prob_threshold"]

    # Start with all allowed
    allowed = np.ones(n, dtype=bool)

    # Rule 1: Block CUSUM change points
    if cusum_block:
        mask = ~np.isnan(cusum_signal) & (cusum_signal >= 0.5)
        allowed[mask] = False

    # Rule 2: Block high HMM vol state
    mask = ~np.isnan(hmm_vol_state) & (hmm_vol_state >= hmm_vol_state_block)
    allowed[mask] = False

    # Rule 3: Block high volatility regime
    mask = ~np.isnan(volatility_regime) & (volatility_regime >= vol_regime_block)
    allowed[mask] = False

    # Rule 4: Block high HMM vol probability (optional)
    if hmm_vol_probability is not None:
        mask = ~np.isnan(hmm_vol_probability) & (hmm_vol_probability > hmm_vol_prob_threshold)
        allowed[mask] = False

    return allowed


# ===========================================================================
# Filter breakdown (diagnostic)
# ===========================================================================


def compute_filter_breakdown(
    cusum_signal: np.ndarray,
    hmm_vol_state: np.ndarray,
    volatility_regime: np.ndarray,
    hmm_vol_probability: Optional[np.ndarray] = None,
    mode: str = "SWING",
) -> Dict[str, np.ndarray]:
    """Compute per-rule breakdown of why bars are blocked.

    Returns dict with boolean arrays for each blocking rule:
      - blocked_by_cusum: CUSUM change point blocked
      - blocked_by_hmm_state: HMM high vol state blocked
      - blocked_by_vol_regime: volatility regime blocked
      - blocked_by_hmm_prob: HMM vol probability blocked (if applicable)
      - trade_allowed: combined result

    All arrays are same length as inputs.
    """
    thresholds = _MODE_FILTER_DEFAULTS.get(mode.upper(), _MODE_FILTER_DEFAULTS["SWING"])
    n = len(cusum_signal)

    blocked_cusum = np.zeros(n, dtype=bool)
    blocked_hmm = np.zeros(n, dtype=bool)
    blocked_vol = np.zeros(n, dtype=bool)
    blocked_prob = np.zeros(n, dtype=bool)

    mask = ~np.isnan(cusum_signal) & (cusum_signal >= 0.5)
    blocked_cusum[mask] = True

    mask = ~np.isnan(hmm_vol_state) & (hmm_vol_state >= thresholds["hmm_vol_state_block"])
    blocked_hmm[mask] = True

    mask = ~np.isnan(volatility_regime) & (volatility_regime >= thresholds["vol_regime_block"])
    blocked_vol[mask] = True

    if hmm_vol_probability is not None:
        mask = ~np.isnan(hmm_vol_probability) & (hmm_vol_probability > thresholds["hmm_vol_prob_threshold"])
        blocked_prob[mask] = True

    combined = ~(blocked_cusum | blocked_hmm | blocked_vol | blocked_prob)

    return {
        "blocked_by_cusum": blocked_cusum,
        "blocked_by_hmm_state": blocked_hmm,
        "blocked_by_vol_regime": blocked_vol,
        "blocked_by_hmm_prob": blocked_prob,
        "trade_allowed": combined,
    }


# ===========================================================================
# PBO guard validation hooks
# ===========================================================================


def validate_regime_filter_conditions(
    trade_allowed: np.ndarray,
    min_allowed_frac: float = 0.1,
) -> Dict[str, object]:
    """Validate that regime filter does not block excessive bars.

    PBO guard: if the filter blocks more than (1 - min_allowed_frac)
    of bars, a warning condition is raised. This prevents catastrophic
    feature collapse from overly aggressive filtering.

    Args:
        trade_allowed: Boolean array from compute_regime_filter.
        min_allowed_frac: Minimum fraction of bars that must remain
            tradeable. Default 0.1 (10%).

    Returns:
        Dict with keys:
          - allowed_frac: fraction of bars where trade_allowed is True
          - blocked_frac: fraction blocked
          - within_bounds: True if allowed_frac >= min_allowed_frac
          - n_allowed: count of allowed bars
          - n_total: total bars
          - pbo_warning: warning message if blocked too many, else empty string
    """
    n_total = len(trade_allowed)
    if n_total == 0:
        return {
            "allowed_frac": 0.0,
            "blocked_frac": 0.0,
            "within_bounds": False,
            "n_allowed": 0,
            "n_total": 0,
            "pbo_warning": "Empty trade_allowed array — no bars to validate",
        }

    n_allowed = int(np.sum(trade_allowed))
    allowed_frac = n_allowed / n_total
    blocked_frac = 1.0 - allowed_frac
    within_bounds = allowed_frac >= min_allowed_frac

    pbo_warning = ""
    if not within_bounds:
        pbo_warning = (
            f"PBO GUARD: regime filter blocks {blocked_frac:.1%} of bars "
            f"(allowed: {allowed_frac:.1%}, min: {min_allowed_frac:.1%}). "
            f"Review filter thresholds for potential feature collapse."
        )

    return {
        "allowed_frac": allowed_frac,
        "blocked_frac": blocked_frac,
        "within_bounds": within_bounds,
        "n_allowed": n_allowed,
        "n_total": n_total,
        "pbo_warning": pbo_warning,
    }
