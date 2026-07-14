"""Factor selection module for AlphaForge — IC-based feature selection + dynamic weighting.

Implements the AlphaForge paper's findings:
- Static IC: 2.43% → Dynamic IC: 4.40%
- Optimal feature pool: ~10 features
- 100+ features perform WORSE than 10 (non-monotonic)

This module provides:
1. Per-feature IC/RankIC/ICIR computation (wraps ic_metrics.py)
2. Correlation-based greedy feature selection
3. Dynamic fold-wise weighting (leakage-free)
4. A/B comparison harness for walk_forward_validate

All functions are pure-numpy, deterministic, and stateless.
No profitability claims, no real market data, no state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from alphaforge.reports.ic_metrics import (
    compute_dynamic_weights,
    compute_feature_correlation_matrix,
    compute_ic,
    compute_per_feature_ic,
    rankdata,
    select_features_greedy_ic,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FactorSelectionConfig:
    """Configuration for factor selection A/B comparison.
    
    Attributes:
        max_features: Maximum number of features to select (default 20).
        corr_threshold: Correlation threshold for redundancy removal (default 0.5).
        min_ic: Minimum |IC| to consider a feature (default 0.005).
        enable_dynamic_weighting: Whether to apply fold-wise dynamic weighting
            to the selected feature set (Config B).
    """
    max_features: int = 20
    corr_threshold: float = 0.5
    min_ic: float = 0.005
    enable_dynamic_weighting: bool = True


@dataclass
class FactorSelectionResult:
    """Result of factor selection analysis.
    
    Attributes:
        selected_features: List of selected feature names (ordered by |IC| desc).
        ic_table: Per-feature IC/RankIC table from compute_per_feature_ic.
        n_total_features: Total number of features before selection.
        n_selected_features: Number of features after selection.
        config: The FactorSelectionConfig used.
    """
    selected_features: List[str] = field(default_factory=list)
    ic_table: List[dict] = field(default_factory=list)
    n_total_features: int = 0
    n_selected_features: int = 0
    config: Optional[FactorSelectionConfig] = None


def run_factor_selection(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: List[str],
    config: Optional[FactorSelectionConfig] = None,
) -> FactorSelectionResult:
    """Run factor selection on a feature matrix.
    
    Computes per-feature IC, builds correlation matrix, and selects
    features using greedy IC-based selection with redundancy removal.
    
    Args:
        X: (N, F) feature matrix.
        y: (N,) target array.
        feature_names: List of F feature names.
        config: FactorSelectionConfig (defaults applied if None).
    
    Returns:
        FactorSelectionResult with selected features and IC table.
    """
    if config is None:
        config = FactorSelectionConfig()
    
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    
    n_total = X.shape[1] if X.ndim == 2 else 0
    logger.info(
        "Factor selection: N=%d, F=%d, max=%d, corr_thr=%.2f, min_ic=%.4f",
        len(y), n_total, config.max_features, config.corr_threshold, config.min_ic,
    )
    
    # Step 1: Per-feature IC computation
    ic_table = compute_per_feature_ic(X, y, feature_names)
    
    # Step 2: Correlation matrix
    corr_matrix, _ = compute_feature_correlation_matrix(X, feature_names)
    
    # Step 3: Greedy selection
    selected = select_features_greedy_ic(
        ic_table, corr_matrix, feature_names,
        max_features=config.max_features,
        corr_threshold=config.corr_threshold,
        min_ic=config.min_ic,
    )
    
    logger.info(
        "Factor selection: %d/%d features selected (top IC: %.4f)",
        len(selected), n_total,
        ic_table[0]["abs_ic"] if ic_table else 0.0,
    )
    
    return FactorSelectionResult(
        selected_features=selected,
        ic_table=ic_table,
        n_total_features=n_total,
        n_selected_features=len(selected),
        config=config,
    )


def apply_feature_mask(
    X: np.ndarray,
    feature_names: List[str],
    selected_features: List[str],
) -> tuple[np.ndarray, List[str]]:
    """Apply feature mask: select only the specified feature columns.
    
    Args:
        X: (N, F) feature matrix.
        feature_names: List of F feature names.
        selected_features: List of selected feature names to keep.
    
    Returns:
        (X_selected, selected_names) — masked matrix and its names.
    """
    X = np.asarray(X, dtype=np.float64)
    name_to_idx = {name: idx for idx, name in enumerate(feature_names)}
    
    indices = [name_to_idx[n] for n in selected_features if n in name_to_idx]
    if not indices:
        logger.warning("No matching features found — returning empty matrix")
        return np.empty((len(X), 0)), []
    
    return X[:, indices], [feature_names[i] for i in indices]


def apply_dynamic_weighting_to_fold(
    X_train: np.ndarray,
    X_val: np.ndarray,
    y_train: np.ndarray,
    feature_names: List[str],
    selected_features: List[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Compute fold-wise dynamic weights and apply them to train/val.
    
    Weights are computed from the TRAINING fold only (leakage-free),
    then applied to both train and validation feature matrices.
    
    Weight formula: w_j = |IC_j| / sum(|IC_j|) for selected features.
    X_weighted[:, j] = X[:, j] * w_j
    
    Args:
        X_train: (N_train, F) training feature matrix.
        X_val: (N_val, F) validation feature matrix.
        y_train: (N_train,) training target values.
        feature_names: Full feature name list.
        selected_features: List of selected feature names.
    
    Returns:
        (X_train_weighted, X_val_weighted) — weighted feature matrices.
    """
    weights = compute_dynamic_weights(X_train, y_train, feature_names, selected_features)
    
    X_train_w = X_train * weights[np.newaxis, :]
    X_val_w = X_val * weights[np.newaxis, :]
    
    return X_train_w, X_val_w


def format_ic_table_for_logging(
    ic_table: List[dict],
    top_n: int = 15,
) -> str:
    """Format IC table as a human-readable string for logging.
    
    Args:
        ic_table: Output of compute_per_feature_ic.
        top_n: Number of top features to show (default 15).
    
    Returns:
        Formatted string with IC table.
    """
    lines = [
        f"{'Feature':<40} {'IC':>8} {'RankIC':>8} {'|IC|':>8} {'N_valid':>8}",
        "-" * 76,
    ]
    for r in ic_table[:top_n]:
        lines.append(
            f"{r['name']:<40} {r['ic']:>8.4f} {r['rank_ic']:>8.4f} "
            f"{r['abs_ic']:>8.4f} {r['n_valid']:>8d}"
        )
    if len(ic_table) > top_n:
        lines.append(f"  ... ({len(ic_table) - top_n} more features)")
    return "\n".join(lines)
