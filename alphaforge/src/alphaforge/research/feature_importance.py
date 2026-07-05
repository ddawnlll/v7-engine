"""Feature importance analysis using XGBoost gain importance.

P0.10 (Issue #140): SHAP-style feature importance computed per walk-forward
fold. Uses XGBoost built-in total_gain importance as a SHAP-like measure
(the SHAP package is not installed in this environment). Gain importance
measures the total reduction in loss contributed by each feature across
all trees — conceptually similar to SHAP's aggregate feature attribution.

SHAP replacement note:
  In production, install the `shap` package and replace
  `booster.get_score(importance_type="total_gain")` with
  `shap.TreeExplainer(booster).shap_values(X)` for per-sample attribution.
  The total_gain importance used here is an aggregate proxy that matches
  the XGBoost native feature_importance field already used in model artifacts.

Usage:
    from alphaforge.research.feature_importance import (
        compute_per_fold_importance,
        aggregate_fold_importance,
        extract_top_features,
        flag_noise_features,
        compute_feature_importance_analysis,
    )

    # Per-fold analysis
    boosters: list[xgb.Booster] = [...]  # one per walk-forward fold
    analysis = compute_feature_importance_analysis(
        boosters, feature_names=["feat_1", "feat_2", ...]
    )
    top_5 = analysis["top_features"]
    noise = analysis["noise_features"]
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import xgboost as xgb

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default relative threshold for noise features:
#   mean_importance < DEFAULT_NOISE_THRESHOLD_REL * max_mean_importance
DEFAULT_NOISE_THRESHOLD_REL: float = 0.05

# Default number of top features to extract
DEFAULT_TOP_K: int = 5


# ---------------------------------------------------------------------------
# Per-fold importance
# ---------------------------------------------------------------------------


def compute_per_fold_importance(
    booster: xgb.Booster,
    feature_names: Optional[List[str]] = None,
) -> Dict[str, float]:
    """Compute feature importance for a single trained booster.

    Uses total_gain importance type (sum of gain from all splits that use
    the feature), falling back to total_cover then weight.

    Args:
        booster: Trained XGBoost Booster object.
        feature_names: Optional list of feature names. When provided, dict
            keys are human-readable names instead of 'f0', 'f1', etc.

    Returns:
        Dict mapping feature name to raw gain importance score.
        Empty dict if the booster has no importance data.

    Raises:
        TypeError: If booster is not an xgb.Booster.
    """
    if not isinstance(booster, xgb.Booster):
        raise TypeError(
            f"booster must be xgboost.Booster, got {type(booster).__name__}"
        )

    try:
        score_map = booster.get_score(importance_type="total_gain")
    except Exception:
        try:
            score_map = booster.get_score(importance_type="total_cover")
        except Exception:
            score_map = booster.get_score(importance_type="weight")

    if not score_map:
        return {}

    if feature_names:
        return _map_score_keys(score_map, feature_names)

    return {k: float(v) for k, v in score_map.items()}


def _map_score_keys(
    score_map: Dict[str, float],
    feature_names: List[str],
) -> Dict[str, float]:
    """Map XGBoost internal keys (f0, f1, ...) to human-readable names."""
    result: Dict[str, float] = {}
    for key, value in score_map.items():
        try:
            idx = int(key[1:])  # f0 -> 0, f12 -> 12
        except (ValueError, IndexError):
            result[key] = float(value)
            continue
        if 0 <= idx < len(feature_names):
            result[feature_names[idx]] = float(value)
        else:
            result[key] = float(value)
    return result


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _normalize_importance(
    importance: Dict[str, float],
) -> Dict[str, float]:
    """Normalize importance values to sum to 1.0.

    Returns a copy; does not mutate the input.
    """
    if not importance:
        return {}
    total = sum(importance.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in importance.items()}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate_fold_importance(
    per_fold_importance: List[Dict[str, float]],
    normalize: bool = True,
) -> Dict[str, Any]:
    """Aggregate feature importance across walk-forward folds.

    For each feature, computes:
      - Mean normalized importance across folds
      - Standard deviation of normalized importance
      - Fold frequency (number of folds where feature has non-zero importance)

    Normalization ensures each fold contributes equally to the aggregate
    regardless of overall gain magnitude differences between folds.

    Args:
        per_fold_importance: List of dicts, one per fold, mapping
            feature name -> raw gain importance score.
        normalize: If True (default), normalizes each fold's importance
            to sum to 1.0 before aggregating.

    Returns:
        Dict with keys:
            mean (Dict[str, float]): Mean normalized importance per feature.
            std (Dict[str, float]): Standard deviation of normalized
                importance per feature.
            fold_frequency (Dict[str, int]): Count of folds where feature
                had non-zero importance.
            n_folds (int): Number of folds.
            n_features (int): Number of unique features seen.
    """
    if not per_fold_importance:
        return {
            "mean": {},
            "std": {},
            "fold_frequency": {},
            "n_folds": 0,
            "n_features": 0,
        }

    # Collect all feature names seen across any fold
    all_features: set = set()
    for imp in per_fold_importance:
        all_features.update(imp.keys())

    # Normalize each fold's importance
    normalized_maps: List[Dict[str, float]] = []
    for imp in per_fold_importance:
        nm = _normalize_importance(imp) if normalize else _normalize_importance(imp)
        normalized_maps.append(nm)

    # Build per-feature arrays and fold frequency
    import_arrays: Dict[str, List[float]] = {feat: [] for feat in all_features}
    fold_freq: Dict[str, int] = {feat: 0 for feat in all_features}

    for nm in normalized_maps:
        for feat in all_features:
            val = nm.get(feat, 0.0)
            import_arrays[feat].append(val)
            if val > 0:
                fold_freq[feat] += 1

    # Compute mean and std
    mean_imp: Dict[str, float] = {}
    std_imp: Dict[str, float] = {}
    for feat in all_features:
        arr = np.array(import_arrays[feat])
        mean_imp[feat] = float(np.mean(arr))
        std_imp[feat] = (
            float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
        )

    return {
        "mean": mean_imp,
        "std": std_imp,
        "fold_frequency": fold_freq,
        "n_folds": len(per_fold_importance),
        "n_features": len(all_features),
    }


# ---------------------------------------------------------------------------
# Top-k extraction
# ---------------------------------------------------------------------------


def extract_top_features(
    aggregated: Dict[str, Any],
    k: int = DEFAULT_TOP_K,
) -> List[Dict[str, Any]]:
    """Extract the top-k features by mean normalized importance.

    Args:
        aggregated: Dict from aggregate_fold_importance().
        k: Number of top features to return (default 5).

    Returns:
        List of dicts sorted by mean importance descending, each with:
            name (str): Feature name.
            mean_importance (float): Mean normalized importance.
            std_importance (float): Standard deviation across folds.
            fold_frequency (int): Number of folds with non-zero importance.
        Empty list if aggregation is empty.
    """
    mean_imp = aggregated.get("mean", {})
    if not mean_imp:
        return []

    std_imp = aggregated.get("std", {})
    fold_freq = aggregated.get("fold_frequency", {})

    sorted_features = sorted(
        mean_imp.items(), key=lambda x: x[1], reverse=True
    )

    result: List[Dict[str, Any]] = []
    for name, mean_val in sorted_features[:k]:
        result.append({
            "name": name,
            "mean_importance": round(float(mean_val), 6),
            "std_importance": round(float(std_imp.get(name, 0.0)), 6),
            "fold_frequency": fold_freq.get(name, 0),
        })

    return result


# ---------------------------------------------------------------------------
# Noise detection
# ---------------------------------------------------------------------------


def flag_noise_features(
    aggregated: Dict[str, Any],
    threshold_rel: float = DEFAULT_NOISE_THRESHOLD_REL,
) -> List[Dict[str, Any]]:
    """Flag features whose mean importance is below a relative threshold.

    A feature is flagged as a "noise candidate" if its mean normalized
    importance is less than `threshold_rel * max_mean_importance`. This
    identifies features that contribute little predictive signal compared
    to the most important feature.

    Args:
        aggregated: Dict from aggregate_fold_importance().
        threshold_rel: Relative threshold. Default 0.05 means a feature
            must have at least 5% of the top feature's importance to avoid
            being flagged.

    Returns:
        List of dicts sorted by mean importance descending, each with:
            name (str): Feature name.
            mean_importance (float): Mean normalized importance.
            max_importance (float): Maximum mean importance across features.
            threshold_used (float): Actual threshold value applied.
            reason (str): Explanation of why flagged.
        Empty list if no features fall below threshold.
    """
    mean_imp = aggregated.get("mean", {})
    if not mean_imp:
        return []

    max_val = max(mean_imp.values()) if mean_imp else 0.0
    if max_val <= 0:
        return []

    threshold = max_val * threshold_rel

    candidates = [
        (name, val)
        for name, val in mean_imp.items()
        if val < threshold
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)

    result: List[Dict[str, Any]] = []
    for name, mean_val in candidates:
        result.append({
            "name": name,
            "mean_importance": round(float(mean_val), 6),
            "max_importance": round(float(max_val), 6),
            "threshold_used": round(float(threshold), 6),
            "reason": (
                f"Mean importance ({mean_val:.6f}) below "
                f"{threshold_rel * 100:.0f}% relative threshold "
                f"({threshold:.6f}) of max feature importance "
                f"({max_val:.6f})"
            ),
        })

    return result


# ---------------------------------------------------------------------------
# Complete analysis
# ---------------------------------------------------------------------------


def compute_feature_importance_analysis(
    boosters: List[xgb.Booster],
    feature_names: Optional[List[str]] = None,
    top_k: int = DEFAULT_TOP_K,
    noise_threshold_rel: float = DEFAULT_NOISE_THRESHOLD_REL,
) -> Dict[str, Any]:
    """Run a complete feature importance analysis from fold boosters.

    Combines fold-level importance computation, cross-fold aggregation,
    top-k extraction, and noise detection into a single call.

    Args:
        boosters: List of trained XGBoost Boosters (one per fold).
        feature_names: Optional list of feature names for human-readable
            importance keys.
        top_k: Number of top features to extract (default 5).
        noise_threshold_rel: Relative threshold for noise flagging
            (default 0.05 = 5% of max).

    Returns:
        Dict with keys:
            per_fold: List[Dict[str, float]] — raw importance per fold.
            aggregated: Dict — aggregated mean/std/frequency.
            top_features: List[Dict] — top-k features with metadata.
            noise_features: List[Dict] — flagged noise feature candidates.
            method: str — importance type used ("xgboost_total_gain").

    Raises:
        ValueError: If boosters list is empty.
        TypeError: If any element is not an xgb.Booster.
    """
    if not boosters:
        raise ValueError("boosters list cannot be empty")

    per_fold: List[Dict[str, float]] = []
    for booster in boosters:
        imp = compute_per_fold_importance(booster, feature_names)
        per_fold.append(imp)

    aggregated = aggregate_fold_importance(per_fold, normalize=True)
    top_features = extract_top_features(aggregated, k=top_k)
    noise_features = flag_noise_features(
        aggregated, threshold_rel=noise_threshold_rel
    )

    return {
        "per_fold": per_fold,
        "aggregated": aggregated,
        "top_features": top_features,
        "noise_features": noise_features,
        "method": "xgboost_total_gain",
    }
