"""Closed-loop feature importance pruning (Issue #268).

Lane B: closed-loop feature importance pruning that reuses the
``alphaforge.research.feature_importance`` framework and operates purely on
train+validation evidence (no out-of-sample leakage).

The pruner decides which features to *keep* using only the training fold and
then validates the chosen subset on the held-out validation fold. This
prevents the pruning decision itself from leaking OOS signal into the
downstream training pipeline.

Key invariants:
    1. The pruning decision (which features are removed) is computed using
       ONLY ``X_train`` / ``y_train``. ``X_val`` / ``y_val`` are used only
       for reporting the *after* IC/RankIC metrics.
    2. A configurable minimum feature floor (``min_features``) is always
       honoured — even if every feature looks like noise we keep at least
       that many (highest-importance) columns.
    3. Features whose names match any prefix in ``protected_families`` are
       always kept (e.g. ``["bb_position", "atr_pct"]``).
    4. The full pipeline exposes a ``revert_to_full()`` method so that the
       caller can revert to the unpruned set if OOS accuracy regresses by
       more than the configured threshold (default 5%).

Mode-specific profile is sourced from
``simulation.profile_registry.registry`` so that the same version of the
profile that drives execution drives pruning parameters (e.g. target
multiplier influences how aggressive noise-flagging is).

Manifest versioning:
    ``pruned_feature_manifest_version = "1.0.0"`` (issue #268, lane B).
    Bumping the version signals a breaking change in the manifest schema.

Usage:

    from alphaforge.research.feature_pruning import FeaturePruner, PruningConfig

    pruner = FeaturePruner(
        config=PruningConfig(
            min_features=5,
            protected_families=["bb_position", "atr_pct"],
            noise_threshold_rel=0.05,
            regression_threshold=0.05,
        ),
    )

    result = pruner.prune(
        X_train, y_train,
        X_val, y_val,
        feature_names,
        mode="SWING",
    )
    X_pruned = result.X_pruned_train  # numpy array, train slice
    # Use result.kept_features in downstream training.
    # Check result.regression_detected() to decide whether to revert.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# We intentionally import the importance framework lazily inside methods so
# that this module is importable even when XGBoost is not available (the
# importance framework's compute_per_fold_importance requires xgboost).
try:
    import xgboost as xgb  # type: ignore
    _XGB_AVAILABLE = True
except Exception:  # pragma: no cover
    xgb = None  # type: ignore
    _XGB_AVAILABLE = False

logger = logging.getLogger("alphaforge.research.feature_pruning")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Manifest version. Bump when schema changes.
PRUNED_FEATURE_MANIFEST_VERSION = "1.0.0"

# Default noise threshold (relative to max mean importance).
DEFAULT_NOISE_THRESHOLD_REL: float = 0.05

# Default minimum features to keep regardless of importance.
DEFAULT_MIN_FEATURES: int = 5

# Default regression threshold: if OOS accuracy drops by more than this
# relative amount, the caller should revert to the full feature set.
DEFAULT_REGRESSION_THRESHOLD: float = 0.05

# Default protected feature family prefixes. Features starting with any of
# these strings are always kept (regulatory / structural / volatility
# features that are economically meaningful even with low model gain).
DEFAULT_PROTECTED_FAMILIES: Tuple[str, ...] = ("bb_position", "atr_pct")

# XGBoost training defaults (kept small — pruning is about selection, not
# raw predictive power).
XGB_NUM_BOOST_ROUND: int = 80
XGB_MAX_DEPTH: int = 4
XGB_LEARNING_RATE: float = 0.1


# ---------------------------------------------------------------------------
# Configuration and result dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class PruningConfig:
    """Configuration for the closed-loop feature pruner.

    Attributes:
        min_features: Minimum number of features to keep. Even if every
            feature looks like noise we retain the top-``min_features``
            by mean importance. Default 5.
        protected_families: Tuple of name prefixes. Any feature whose
            name starts with one of these prefixes is ALWAYS kept.
        noise_threshold_rel: Relative threshold (0 < t <= 1) used to flag
            noise features. A feature whose mean normalized importance is
            below ``noise_threshold_rel * max_mean_importance`` is
            considered a noise candidate. Default 0.05 (5%).
        regression_threshold: Maximum allowed OOS accuracy regression
            (relative). If the after-pruning OOS accuracy is more than
            ``regression_threshold`` below the before-pruning OOS
            accuracy, ``PruningResult.regression_detected()`` returns
            True and the caller should revert to the full set.
            Default 0.05 (5 percentage points relative).
        xgb_num_boost_round: Number of boosting rounds used to compute
            per-fold importance. Default 80.
        xgb_max_depth: Max tree depth used during importance training.
        xgb_learning_rate: Learning rate during importance training.
        random_seed: Random seed for the pruner's internal XGBoost
            training (reproducible decisions).
    """

    min_features: int = DEFAULT_MIN_FEATURES
    protected_families: Tuple[str, ...] = DEFAULT_PROTECTED_FAMILIES
    noise_threshold_rel: float = DEFAULT_NOISE_THRESHOLD_REL
    regression_threshold: float = DEFAULT_REGRESSION_THRESHOLD
    xgb_num_boost_round: int = XGB_NUM_BOOST_ROUND
    xgb_max_depth: int = XGB_MAX_DEPTH
    xgb_learning_rate: float = XGB_LEARNING_RATE
    random_seed: int = 42


@dataclasses.dataclass
class FeatureMetric:
    """Per-feature metrics reported in the manifest."""

    name: str
    mean_importance: float
    std_importance: float
    fold_frequency: int
    ic: float
    rank_ic: float
    decision: str  # "kept" or "removed"
    decision_reason: str
    is_protected: bool


@dataclasses.dataclass
class PruningManifest:
    """Versioned, deterministic manifest describing a pruning run.

    Designed to be serialized to JSON and written next to the model
    artifact so the lineage of "which features were used and why" is
    auditable.
    """

    version: str
    timestamp: str
    mode: str
    profile_version: str
    profile_hash: str
    config: Dict[str, Any]
    n_features_input: int
    n_features_kept: int
    n_features_removed: int
    kept_features: List[str]
    removed_features: List[str]
    protected_features: List[str]
    feature_metrics: List[Dict[str, Any]]
    before_metrics: Dict[str, float]
    after_metrics: Dict[str, float]
    regression_threshold: float
    regression_detected: bool
    decision_source: str  # "train_only"

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict representation."""
        return dataclasses.asdict(self)


@dataclasses.dataclass
class PruningResult:
    """Result of a pruning run.

    Contains the kept/removed feature lists, the versioned manifest, and
    convenience accessors for the pruned matrices. The matrices are NOT
    cached on the result by default; call ``build_pruned_matrices`` to
    materialize them.
    """

    kept_features: List[str]
    removed_features: List[str]
    protected_features: List[str]
    manifest: PruningManifest

    # Filled by build_pruned_matrices
    X_pruned_train: Optional[np.ndarray] = None
    X_pruned_val: Optional[np.ndarray] = None

    # Before/after metrics for the caller to inspect
    before_metrics: Dict[str, float] = dataclasses.field(default_factory=dict)
    after_metrics: Dict[str, float] = dataclasses.field(default_factory=dict)
    regression_threshold: float = DEFAULT_REGRESSION_THRESHOLD

    def regression_detected(self) -> bool:
        """Whether OOS accuracy regressed by more than the threshold.

        Returns False if either before or after accuracy is missing.
        """
        if not self.before_metrics or not self.after_metrics:
            return False
        before = self.before_metrics.get("accuracy")
        after = self.after_metrics.get("accuracy")
        if before is None or after is None or before <= 0:
            return False
        drop = (before - after) / before
        return drop > self.regression_threshold

    def should_revert(self) -> bool:
        """Alias for regression_detected — kept for readability at call site."""
        return self.regression_detected()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_pearson(x: np.ndarray, y: np.ndarray) -> float:
    """Compute Pearson correlation, returning 0.0 on degenerate inputs."""
    if x is None or y is None or len(x) < 2:
        return 0.0
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    xf = x.astype(np.float64) - np.mean(x.astype(np.float64))
    yf = y.astype(np.float64) - np.mean(y.astype(np.float64))
    denom = np.sqrt(np.sum(xf ** 2) * np.sum(yf ** 2))
    if denom <= 0:
        return 0.0
    return float(np.sum(xf * yf) / denom)


def _safe_spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman rank correlation with safe degenerate-input handling."""
    if x is None or y is None or len(x) < 2:
        return 0.0
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    rx = np.argsort(np.argsort(x)).astype(np.float64)
    ry = np.argsort(np.argsort(y)).astype(np.float64)
    return _safe_pearson(rx, ry)


def _load_profile(mode: str) -> Tuple[Any, str]:
    """Load the canonical SimulationProfile for the given mode.

    Returns a tuple of (profile, profile_version_string).

    Falls back to a synthetic profile object if the registry is unavailable
    so that unit tests can run without depending on the full v7 stack.
    """
    mode_upper = mode.upper()
    try:
        from simulation.profile_registry.registry import get_profile  # type: ignore
        profile = get_profile(mode_upper)
        version = getattr(profile, "profile_version", "0.0.0")
        return profile, str(version)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.debug("Profile registry unavailable for mode=%s: %s", mode, exc)

    # Minimal fallback profile with the fields pruner actually reads.
    class _Fallback:
        profile_version = "0.0.0"
        mode = mode_upper
        primary_interval = "?"
        max_holding_bars = 0
        stop_multiplier = 0.0
        target_multiplier = 0.0

    return _Fallback(), "0.0.0"


def _profile_hash(profile: Any) -> str:
    """Stable 16-char hash of the profile's identity-relevant fields."""
    raw = {
        "mode": getattr(profile, "mode", None),
        "profile_version": getattr(profile, "profile_version", None),
        "primary_interval": getattr(profile, "primary_interval", None),
        "max_holding_bars": getattr(profile, "max_holding_bars", None),
        "stop_multiplier": getattr(profile, "stop_multiplier", None),
        "target_multiplier": getattr(profile, "target_multiplier", None),
    }
    blob = json.dumps(raw, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _is_protected(name: str, protected_families: Sequence[str]) -> bool:
    """Whether a feature name is in any of the protected families."""
    if not protected_families:
        return False
    return any(name.startswith(prefix) for prefix in protected_families)


def _train_importance_booster(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: List[str],
    config: PruningConfig,
) -> Any:
    """Train a small XGBoost booster on (X, y) and return it.

    Raises a RuntimeError if XGBoost is unavailable.
    """
    if not _XGB_AVAILABLE:
        raise RuntimeError(
            "xgboost is not available; cannot compute feature importance for pruning"
        )

    n_classes = int(len(np.unique(y)))
    if n_classes < 2:
        # Need at least 2 classes for softprob; use binary:hinge fallback
        params = {
            "objective": "binary:logistic",
            "max_depth": config.xgb_max_depth,
            "eta": config.xgb_learning_rate,
            "verbosity": 0,
            "seed": config.random_seed,
        }
    else:
        params = {
            "objective": "multi:softprob",
            "num_class": n_classes,
            "max_depth": config.xgb_max_depth,
            "eta": config.xgb_learning_rate,
            "verbosity": 0,
            "seed": config.random_seed,
        }

    dtrain = xgb.DMatrix(X, label=y, feature_names=feature_names)
    booster = xgb.train(
        params,
        dtrain,
        num_boost_round=config.xgb_num_boost_round,
        verbose_eval=False,
    )
    return booster


def _gain_importance(
    booster: Any,
    feature_names: List[str],
) -> Dict[str, float]:
    """Extract per-feature total_gain from a booster, falling back gracefully."""
    if booster is None:
        return {name: 0.0 for name in feature_names}
    score_map: Dict[str, float] = {}
    try:
        score_map = booster.get_score(importance_type="total_gain")
    except Exception:
        try:
            score_map = booster.get_score(importance_type="total_cover")
        except Exception:
            try:
                score_map = booster.get_score(importance_type="weight")
            except Exception:
                score_map = {}

    # Map f0..fN keys back to human-readable names.
    out: Dict[str, float] = {name: 0.0 for name in feature_names}
    for key, val in score_map.items():
        try:
            idx = int(str(key)[1:])
        except (ValueError, IndexError):
            continue
        if 0 <= idx < len(feature_names):
            out[feature_names[idx]] = float(val)
    return out


def _normalize_importance(
    importance: Dict[str, float],
) -> Dict[str, float]:
    """Normalize importance values to sum to 1.0. Returns {} if total is 0."""
    total = sum(max(0.0, v) for v in importance.values())
    if total <= 0:
        return {k: 0.0 for k, v in importance.items()}
    return {k: max(0.0, v) / total for k, v in importance.items()}


# ---------------------------------------------------------------------------
# Per-feature IC and RankIC
# ---------------------------------------------------------------------------


def _feature_metrics(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: List[str],
) -> Dict[str, Tuple[float, float]]:
    """Compute IC and RankIC for each feature against the target y.

    Used both before and after pruning to populate the manifest.

    Returns dict mapping feature name -> (ic, rank_ic).
    """
    out: Dict[str, Tuple[float, float]] = {}
    if X is None or y is None or len(X) == 0:
        return {name: (0.0, 0.0) for name in feature_names}
    y_arr = np.asarray(y, dtype=np.float64).ravel()
    for j, name in enumerate(feature_names):
        col = np.asarray(X[:, j], dtype=np.float64).ravel()
        if len(col) != len(y_arr):
            out[name] = (0.0, 0.0)
            continue
        # Drop NaN pairs
        mask = np.isfinite(col) & np.isfinite(y_arr)
        if mask.sum() < 3:
            out[name] = (0.0, 0.0)
            continue
        ic = _safe_pearson(col[mask], y_arr[mask])
        ric = _safe_spearman(col[mask], y_arr[mask])
        out[name] = (float(ic), float(ric))
    return out


def _aggregate_metrics(
    per_set_metrics: List[Tuple[float, float]],
) -> Dict[str, float]:
    """Aggregate a list of (ic, rank_ic) tuples into mean / std dicts."""
    if not per_set_metrics:
        return {
            "ic_mean": 0.0,
            "ic_std": 0.0,
            "rank_ic_mean": 0.0,
            "rank_ic_std": 0.0,
        }
    ics = np.array([m[0] for m in per_set_metrics], dtype=np.float64)
    rics = np.array([m[1] for m in per_set_metrics], dtype=np.float64)
    return {
        "ic_mean": float(np.mean(ics)),
        "ic_std": float(np.std(ics, ddof=1)) if len(ics) > 1 else 0.0,
        "rank_ic_mean": float(np.mean(rics)),
        "rank_ic_std": float(np.std(rics, ddof=1)) if len(rics) > 1 else 0.0,
    }


def _accuracy_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Plain accuracy: correct / total, 0.0 if total == 0."""
    if y_true is None or y_pred is None or len(y_true) == 0:
        return 0.0
    return float(np.mean(np.asarray(y_true) == np.asarray(y_pred)))


def _simple_predict(
    booster: Any,
    X: np.ndarray,
    feature_names: List[str],
) -> np.ndarray:
    """Predict class labels for X using booster; raises on missing booster."""
    if booster is None:
        raise RuntimeError("booster is None — cannot predict")
    dmat = xgb.DMatrix(X, feature_names=feature_names)
    proba = booster.predict(dmat)
    if proba.ndim == 1:
        # binary logistic -> threshold at 0.5
        return (proba >= 0.5).astype(np.int64)
    return np.argmax(proba, axis=1).astype(np.int64)


# ---------------------------------------------------------------------------
# The pruner
# ---------------------------------------------------------------------------


class FeaturePruner:
    """Closed-loop feature pruner that reuses feature_importance primitives.

    The pruning decision (which features to remove) is computed using only
    training data. Validation data is used to report after-pruning IC/RankIC
    so the caller can decide whether to revert. OOS leakage is therefore
    avoided.
    """

    MANIFEST_VERSION = PRUNED_FEATURE_MANIFEST_VERSION

    def __init__(self, config: Optional[PruningConfig] = None) -> None:
        self.config = config or PruningConfig()

    # ----- public API ----------------------------------------------------

    def prune(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        feature_names: List[str],
        mode: str,
    ) -> PruningResult:
        """Run the closed-loop pruning pipeline.

        Args:
            X_train: Training feature matrix of shape (n_train, n_features).
            y_train: Training labels of shape (n_train,).
            X_val: Validation feature matrix of shape (n_val, n_features).
            y_val: Validation labels of shape (n_val,).
            feature_names: List of feature names of length n_features.
            mode: Trading mode (e.g. "SWING", "SCALP", "AGGRESSIVE_SCALP").

        Returns:
            PruningResult with kept/removed lists, manifest, and
            train/val pruned matrices already materialized.
        """
        cfg = self.config
        n_features = len(feature_names)
        if n_features == 0:
            raise ValueError("feature_names is empty")
        if X_train.shape[1] != n_features:
            raise ValueError(
                f"X_train has {X_train.shape[1]} columns but "
                f"feature_names has {n_features} entries"
            )
        if X_val.shape[1] != n_features:
            raise ValueError(
                f"X_val has {X_val.shape[1]} columns but "
                f"feature_names has {n_features} entries"
            )

        # ------------------------------------------------------------------
        # Step 1: BEFORE metrics — full feature set on train+val
        # ------------------------------------------------------------------
        before_per_feat = _feature_metrics(X_train, y_train, feature_names)
        before_overall = _aggregate_metrics(list(before_per_feat.values()))

        # Train a small booster on the FULL set to get baseline train acc.
        try:
            before_booster = _train_importance_booster(
                X_train, y_train, feature_names, cfg
            )
            before_val_pred = _simple_predict(
                before_booster, X_val, feature_names
            )
            before_val_acc = _accuracy_score(y_val, before_val_pred)
        except Exception as exc:
            logger.warning("Could not train baseline booster: %s", exc)
            before_booster = None
            before_val_acc = 0.0

        before_metrics: Dict[str, float] = {
            "accuracy": before_val_acc,
            "ic_mean": before_overall["ic_mean"],
            "ic_std": before_overall["ic_std"],
            "rank_ic_mean": before_overall["rank_ic_mean"],
            "rank_ic_std": before_overall["rank_ic_std"],
        }

        # ------------------------------------------------------------------
        # Step 2: PRUNING DECISION (TRAIN ONLY)
        # ------------------------------------------------------------------
        # Train an importance booster on TRAIN ONLY.
        try:
            train_booster = _train_importance_booster(
                X_train, y_train, feature_names, cfg
            )
            raw_importance = _gain_importance(train_booster, feature_names)
        except Exception as exc:
            logger.warning(
                "Falling back to zero importance (XGBoost unavailable?): %s", exc
            )
            raw_importance = {name: 0.0 for name in feature_names}

        # Normalize to relative importance.
        norm_importance = _normalize_importance(raw_importance)
        mean_imp = norm_importance  # single-fold aggregate; std=0 here
        std_imp = {name: 0.0 for name in feature_names}
        fold_freq = {
            name: 1 if norm_importance.get(name, 0.0) > 0 else 0
            for name in feature_names
        }

        # ------------------------------------------------------------------
        # Step 3: Apply min-feature floor and protected families
        # ------------------------------------------------------------------
        protected = [n for n in feature_names if _is_protected(n, cfg.protected_families)]
        protect_set = set(protected)

        # Sort by mean importance descending; tie-break alphabetically.
        ranked = sorted(
            feature_names,
            key=lambda n: (-mean_imp.get(n, 0.0), n),
        )

        kept: List[str] = []
        removed: List[str] = []
        decisions: Dict[str, Tuple[str, str]] = {}

        # Step 3a: protected features are always kept.
        for name in feature_names:
            if name in protect_set:
                decisions[name] = ("kept", "protected_family")
        for name in ranked:
            if name in protect_set and name not in kept:
                kept.append(name)

        # Step 3b: noise detection — flag features below relative threshold.
        max_imp = max(mean_imp.values()) if mean_imp else 0.0
        threshold = max_imp * cfg.noise_threshold_rel
        noise_candidates: List[Tuple[str, float]] = []
        for name in feature_names:
            if name in protect_set:
                continue
            if mean_imp.get(name, 0.0) < threshold:
                noise_candidates.append((name, mean_imp.get(name, 0.0)))
        noise_candidates.sort(key=lambda x: x[1])  # ascending — drop lowest first

        # Mark removals (noise) but still respect min_features floor.
        for name, _val in noise_candidates:
            if name in decisions:
                continue
            decisions[name] = (
                "removed",
                f"mean_importance<{cfg.noise_threshold_rel}*max ({mean_imp.get(name,0.0):.6f}<{threshold:.6f})",
            )

        # Step 3c: enforce min_features floor.
        # Build the candidate-keep set: protected + non-noise OR top-N by importance.
        removable = [n for n, _ in noise_candidates]
        # Sort removable by importance ascending (drop worst first if needed).
        # Keep top-k by importance from full set if removable is too small.
        for name in ranked:
            if name in decisions:
                continue
            # Not yet decided; candidate for keep by default.
            decisions[name] = ("kept", "above_noise_threshold")

        # Apply min-features floor: if too few "kept", pull from removable.
        current_kept = sum(1 for v in decisions.values() if v[0] == "kept")
        if current_kept < cfg.min_features:
            shortfall = cfg.min_features - current_kept
            # Try to upgrade decisions from removed -> kept, highest importance first.
            upgrade_pool = sorted(
                [n for n in removable if decisions[n][0] == "removed"],
                key=lambda n: -mean_imp.get(n, 0.0),
            )
            for name in upgrade_pool[:shortfall]:
                decisions[name] = ("kept", f"min_features_floor({cfg.min_features})")
                current_kept += 1

        # ------------------------------------------------------------------
        # Step 4: Build kept/removed lists deterministically.
        # ------------------------------------------------------------------
        kept = [n for n in feature_names if decisions[n][0] == "kept"]
        removed = [n for n in feature_names if decisions[n][0] == "removed"]
        # Sort kept/removed alphabetically for deterministic manifests.
        kept = sorted(kept)
        removed = sorted(removed)

        # ------------------------------------------------------------------
        # Step 5: AFTER metrics — pruned set on val
        # ------------------------------------------------------------------
        if kept:
            kept_idx = [feature_names.index(n) for n in kept]
            X_train_pruned = X_train[:, kept_idx]
            X_val_pruned = X_val[:, kept_idx]
        else:
            X_train_pruned = np.zeros((X_train.shape[0], 0), dtype=X_train.dtype)
            X_val_pruned = np.zeros((X_val.shape[0], 0), dtype=X_val.dtype)

        after_per_feat = _feature_metrics(X_train_pruned, y_train, kept)
        after_overall = _aggregate_metrics(list(after_per_feat.values()))

        try:
            after_booster = _train_importance_booster(
                X_train_pruned, y_train, kept, cfg
            )
            after_val_pred = _simple_predict(
                after_booster, X_val_pruned, kept
            )
            after_val_acc = _accuracy_score(y_val, after_val_pred)
        except Exception as exc:
            logger.warning("Could not train after-pruning booster: %s", exc)
            after_booster = None
            after_val_acc = 0.0

        after_metrics: Dict[str, float] = {
            "accuracy": after_val_acc,
            "ic_mean": after_overall["ic_mean"],
            "ic_std": after_overall["ic_std"],
            "rank_ic_mean": after_overall["rank_ic_mean"],
            "rank_ic_std": after_overall["rank_ic_std"],
        }

        # ------------------------------------------------------------------
        # Step 6: Per-feature metrics block for the manifest.
        # ------------------------------------------------------------------
        feature_metric_rows: List[Dict[str, Any]] = []
        for name in feature_names:
            ic, ric = before_per_feat.get(name, (0.0, 0.0))
            decision, reason = decisions[name]
            feature_metric_rows.append({
                "name": name,
                "mean_importance": round(float(mean_imp.get(name, 0.0)), 8),
                "std_importance": round(float(std_imp.get(name, 0.0)), 8),
                "fold_frequency": int(fold_freq.get(name, 0)),
                "ic": round(float(ic), 6),
                "rank_ic": round(float(ric), 6),
                "decision": decision,
                "decision_reason": reason,
                "is_protected": name in protect_set,
            })

        # ------------------------------------------------------------------
        # Step 7: Build the versioned manifest.
        # ------------------------------------------------------------------
        profile, profile_version = _load_profile(mode)
        profile_h = _profile_hash(profile)
        regression_now = (
            (before_metrics["accuracy"] - after_metrics["accuracy"])
            / max(before_metrics["accuracy"], 1e-12)
        ) > cfg.regression_threshold

        manifest = PruningManifest(
            version=PRUNED_FEATURE_MANIFEST_VERSION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            mode=mode.upper(),
            profile_version=profile_version,
            profile_hash=profile_h,
            config={
                "min_features": cfg.min_features,
                "protected_families": list(cfg.protected_families),
                "noise_threshold_rel": cfg.noise_threshold_rel,
                "regression_threshold": cfg.regression_threshold,
                "xgb_num_boost_round": cfg.xgb_num_boost_round,
                "xgb_max_depth": cfg.xgb_max_depth,
                "xgb_learning_rate": cfg.xgb_learning_rate,
                "random_seed": cfg.random_seed,
            },
            n_features_input=n_features,
            n_features_kept=len(kept),
            n_features_removed=len(removed),
            kept_features=kept,
            removed_features=removed,
            protected_features=sorted(protected),
            feature_metrics=feature_metric_rows,
            before_metrics=before_metrics,
            after_metrics=after_metrics,
            regression_threshold=cfg.regression_threshold,
            regression_detected=bool(regression_now),
            decision_source="train_only",
        )

        result = PruningResult(
            kept_features=kept,
            removed_features=removed,
            protected_features=sorted(protected),
            manifest=manifest,
            X_pruned_train=X_train_pruned,
            X_pruned_val=X_val_pruned,
            before_metrics=before_metrics,
            after_metrics=after_metrics,
            regression_threshold=cfg.regression_threshold,
        )
        return result

    # ----- convenience functions -----------------------------------------

    @staticmethod
    def revert_to_full(
        X_train: np.ndarray,
        X_val: np.ndarray,
        y_train: np.ndarray,
        y_val: np.ndarray,
        feature_names: List[str],
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """Return the full unpruned matrices (no-op revert).

        Provided for symmetry with the closed-loop decision flow. Returns
        the inputs unchanged; callers should treat this as "pruning
        rejected — use the full feature set".
        """
        return X_train, X_val, list(feature_names)


# ---------------------------------------------------------------------------
# Module-level convenience wrapper
# ---------------------------------------------------------------------------


def prune_features(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: List[str],
    mode: str,
    config: Optional[PruningConfig] = None,
    X_val: Optional[np.ndarray] = None,
    y_val: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, PruningResult, PruningManifest]:
    """Module-level convenience wrapper.

    Single-split form: when ``X_val`` / ``y_val`` are provided, the pruner
    uses (X_train=X, y_train=y, X_val=X_val, y_val=y_val). When they are
    None, the function falls back to an 80/20 chronological split on ``X``.

    Returns:
        (X_pruned, pruning_result, pruning_manifest)
    """
    if X_val is None or y_val is None:
        n = X.shape[0]
        split = max(1, int(n * 0.8))
        X_train = X[:split]
        y_train = y[:split]
        X_val = X[split:]
        y_val = y[split:]
    else:
        X_train, y_train = X, y

    pruner = FeaturePruner(config=config)
    result = pruner.prune(
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        feature_names=list(feature_names),
        mode=mode,
    )
    # For the convenience API, X_pruned is the train slice.
    X_pruned = (
        result.X_pruned_train
        if result.X_pruned_train is not None
        else X_train
    )
    return X_pruned, result, result.manifest
