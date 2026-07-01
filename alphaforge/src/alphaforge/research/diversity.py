"""Symbol Diversity Analysis — post-hoc research tool.

Evaluates how evenly a model's feature importance or predictions are
distributed across symbols. High diversity = model uses signals from
multiple symbols; low diversity = model overfits to one symbol.

This module is NOT part of the core feature pipeline. It is a post-hoc
research tool that consumes already-computed features and model outputs.

Usage:
    from alphaforge.research.diversity import compute_symbol_diversity_analysis

    # After compute_features returns a FeatureMatrix:
    diversity = compute_symbol_diversity_analysis(
        feature_matrix=np.column_stack([...]),
        symbol_indices={"BTCUSDT": [0, 1, 2], "ETHUSDT": [3, 4, 5]},
    )
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DIVERSITY_CORRELATION_WEIGHT: float = 0.4
DEFAULT_DIVERSITY_DIVERGENCE_WEIGHT: float = 0.3
DEFAULT_DIVERSITY_RETURN_WEIGHT: float = 0.3
DEFAULT_MAX_SYMBOLS_DIVERSITY: int = 10
DEFAULT_DIVERSITY_TOP_K: int = 5


# ===========================================================================
# Per-symbol correlation matrix
# ===========================================================================


def _symbol_correlation_matrix(
    feature_matrix: np.ndarray,
    symbol_indices: Dict[str, List[int]],
) -> Dict[str, Dict[str, float]]:
    """Compute pairwise feature correlation between symbols.

    For each pair of symbols, computes the mean absolute Pearson correlation
    across all features. Lower values indicate more diverse (complementary)
    features between symbols.

    Args:
        feature_matrix: (n_samples, n_features) numpy array.
        symbol_indices: Dict mapping symbol -> list of row indices.

    Returns:
        Nested dict: symbol_corr[sym_a][sym_b] = mean_abs_correlation.
    """
    symbols = sorted(symbol_indices.keys())
    n_symbols = len(symbols)

    if n_symbols < 2:
        return {}

    corr_matrix: Dict[str, Dict[str, float]] = {
        sym: {} for sym in symbols
    }

    for i in range(n_symbols):
        sym_a = symbols[i]
        idx_a = symbol_indices[sym_a]
        if len(idx_a) < 5:
            continue
        data_a = feature_matrix[idx_a]
        # Drop constant columns
        std_a = np.std(data_a, axis=0)
        valid_cols = std_a > 1e-12
        if not np.any(valid_cols):
            continue
        data_a = data_a[:, valid_cols]

        corr_matrix[sym_a][sym_a] = 1.0

        for j in range(i + 1, n_symbols):
            sym_b = symbols[j]
            idx_b = symbol_indices[sym_b]
            if len(idx_b) < 5:
                corr_matrix[sym_a][sym_b] = 0.0
                corr_matrix[sym_b][sym_a] = 0.0
                continue
            data_b = feature_matrix[idx_b]

            # Ensure same feature columns
            min_cols = min(data_a.shape[1], data_b.shape[1])
            if min_cols < 1:
                corr_matrix[sym_a][sym_b] = 0.0
                corr_matrix[sym_b][sym_a] = 0.0
                continue

            x = data_a[:, :min_cols]
            y = data_b[:, :min_cols]

            # Compute pairwise correlation per feature
            with np.errstate(divide="ignore", invalid="ignore"):
                corr_vals = np.array([
                    np.corrcoef(x[:, k], y[:, k])[0, 1]
                    if np.std(x[:, k]) > 1e-12 and np.std(y[:, k]) > 1e-12
                    else 0.0
                    for k in range(min_cols)
                ])
            mean_abs_corr = float(np.nanmean(np.abs(corr_vals)))
            corr_matrix[sym_a][sym_b] = mean_abs_corr
            corr_matrix[sym_b][sym_a] = mean_abs_corr

    return corr_matrix


# ===========================================================================
# Jensen-Shannon divergence across symbol feature distributions
# ===========================================================================


def _js_divergence(p: np.ndarray, q: np.ndarray) -> float:
    """Jensen-Shannon divergence between two discrete probability distributions.

    JS divergence is symmetric and bounded in [0, 1] (when using log base 2).
    Higher values = more divergent distributions.

    Args:
        p: First probability distribution (1D array, must sum to 1).
        q: Second probability distribution (1D array, must sum to 1).

    Returns:
        JS divergence in [0, 1].
    """
    p = np.asarray(p, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)
    p = p / np.sum(p) if np.sum(p) > 0 else p
    q = q / np.sum(q) if np.sum(q) > 0 else q
    m = 0.5 * (p + q)

    def _kl(a: np.ndarray, b: np.ndarray) -> float:
        mask = (a > 0) & (b > 0)
        if not np.any(mask):
            return 0.0
        return float(np.sum(a[mask] * np.log2(a[mask] / b[mask])))

    return float(0.5 * _kl(p, m) + 0.5 * _kl(q, m))


def _symbol_js_divergence(
    feature_matrix: np.ndarray,
    symbol_indices: Dict[str, List[int]],
    n_bins: int = 20,
) -> Dict[str, Dict[str, float]]:
    """Compute Jensen-Shannon divergence between symbol feature distributions.

    For each pair of symbols, discretizes the feature values into histograms
    and computes the mean JS divergence across all features.

    Args:
        feature_matrix: (n_samples, n_features) numpy array.
        symbol_indices: Dict mapping symbol -> list of row indices.
        n_bins: Number of histogram bins for distribution estimation.

    Returns:
        Nested dict: js_div[sym_a][sym_b] = mean_js_divergence.
    """
    symbols = sorted(symbol_indices.keys())
    n_symbols = len(symbols)

    if n_symbols < 2:
        return {}

    n_features = feature_matrix.shape[1]
    js_matrix: Dict[str, Dict[str, float]] = {sym: {} for sym in symbols}

    for i in range(n_symbols):
        sym_a = symbols[i]
        idx_a = symbol_indices[sym_a]
        if len(idx_a) < 5:
            continue
        js_matrix[sym_a][sym_a] = 0.0

        for j in range(i + 1, n_symbols):
            sym_b = symbols[j]
            idx_b = symbol_indices[sym_b]
            if len(idx_b) < 5:
                js_matrix[sym_a][sym_b] = 0.0
                js_matrix[sym_b][sym_a] = 0.0
                continue

            divergences: List[float] = []
            for k in range(n_features):
                f_a = feature_matrix[idx_a, k]
                f_b = feature_matrix[idx_b, k]
                valid = ~np.isnan(f_a) & ~np.isnan(f_b)
                if np.sum(valid) < 5:
                    continue
                hist_a, _ = np.histogram(f_a[valid], bins=n_bins, density=True)
                hist_b, _ = np.histogram(f_b[valid], bins=n_bins, density=True)
                js_val = _js_divergence(hist_a, hist_b)
                divergences.append(js_val)

            mean_js = float(np.mean(divergences)) if divergences else 0.0
            js_matrix[sym_a][sym_b] = mean_js
            js_matrix[sym_b][sym_a] = mean_js

    return js_matrix


# ===========================================================================
# Return correlation
# ===========================================================================


def _return_correlation(
    returns_by_symbol: Dict[str, np.ndarray],
) -> Dict[str, Dict[str, float]]:
    """Compute pairwise return correlation between symbols.

    Args:
        returns_by_symbol: Dict mapping symbol -> 1D array of log returns.

    Returns:
        Nested dict: ret_corr[sym_a][sym_b] = correlation.
    """
    symbols = sorted(returns_by_symbol.keys())
    n_symbols = len(symbols)
    if n_symbols < 2:
        return {}

    corr_matrix: Dict[str, Dict[str, float]] = {sym: {} for sym in symbols}
    for i in range(n_symbols):
        sym_a = symbols[i]
        r_a = returns_by_symbol.get(sym_a, np.array([]))
        corr_matrix[sym_a][sym_a] = 1.0
        for j in range(i + 1, n_symbols):
            sym_b = symbols[j]
            r_b = returns_by_symbol.get(sym_b, np.array([]))
            if len(r_a) < 5 or len(r_b) < 5:
                corr_matrix[sym_a][sym_b] = 0.0
                corr_matrix[sym_b][sym_a] = 0.0
                continue
            min_len = min(len(r_a), len(r_b))
            with np.errstate(divide="ignore", invalid="ignore"):
                corr_val = float(np.corrcoef(r_a[:min_len], r_b[:min_len])[0, 1])
            corr_matrix[sym_a][sym_b] = corr_val if not np.isnan(corr_val) else 0.0
            corr_matrix[sym_b][sym_a] = corr_matrix[sym_a][sym_b]

    return corr_matrix


# ===========================================================================
# Composite diversity score
# ===========================================================================


def compute_symbol_diversity_analysis(
    feature_matrix: np.ndarray,
    symbol_indices: Dict[str, List[int]],
    returns_by_symbol: Optional[Dict[str, np.ndarray]] = None,
    correlation_weight: float = DEFAULT_DIVERSITY_CORRELATION_WEIGHT,
    divergence_weight: float = DEFAULT_DIVERSITY_DIVERGENCE_WEIGHT,
    return_weight: float = DEFAULT_DIVERSITY_RETURN_WEIGHT,
    max_symbols: int = DEFAULT_MAX_SYMBOLS_DIVERSITY,
    top_k: int = DEFAULT_DIVERSITY_TOP_K,
) -> Dict[str, Any]:
    """Compute composite symbol diversity analysis.

    Combines three diversity signals:
      1. Feature correlation: lower cross-symbol feature correlation = higher diversity.
      2. Distribution divergence: higher JS divergence = more independent symbols.
      3. Return correlation: lower return correlation = more independent price action.

    The composite score for each symbol pair is:
      diversity_score = w_corr * (1 - feature_corr)
                      + w_div * js_divergence
                      + w_ret * (1 - abs(return_corr))

    Overall portfolio diversity = mean of all pairwise scores.
    Range: [0, 1]. Higher = more diverse.

    Args:
        feature_matrix: (n_samples, n_features) numpy array of all features.
        symbol_indices: Dict mapping symbol name -> list of row indices.
        returns_by_symbol: Optional dict mapping symbol -> 1D log return array.
        correlation_weight: Weight for feature correlation component.
        divergence_weight: Weight for JS divergence component.
        return_weight: Weight for return correlation component.
        max_symbols: Max symbols to include (capped for performance).
        top_k: Number of most/least diverse pairs to report.

    Returns:
        Dict with keys:
            mean_diversity: float — overall portfolio diversity [0, 1].
            symbol_count: int — number of symbols analyzed.
            pairwise_scores: Dict[str, float] — diversity per symbol pair.
            most_diverse_pairs: list — top-k most diverse pairs.
            least_diverse_pairs: list — top-k least diverse pairs.
            components: Dict with correlation, divergence, return matrices.
    """
    symbols = sorted(symbol_indices.keys())
    if len(symbols) > max_symbols:
        symbols = symbols[:max_symbols]

    if len(symbols) < 2:
        return {
            "mean_diversity": 1.0,
            "symbol_count": len(symbols),
            "pairwise_scores": {},
            "most_diverse_pairs": [],
            "least_diverse_pairs": [],
            "components": {},
        }

    # Compute component matrices
    feat_corr = _symbol_correlation_matrix(feature_matrix, symbol_indices)
    js_div = _symbol_js_divergence(feature_matrix, symbol_indices)

    ret_corr: Dict[str, Dict[str, float]] = {}
    if returns_by_symbol is not None:
        ret_corr = _return_correlation(returns_by_symbol)

    # Combine into composite score
    pairwise_scores: Dict[str, float] = {}
    pair_list: List[tuple] = []

    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            sym_a = symbols[i]
            sym_b = symbols[j]

            feat_c = feat_corr.get(sym_a, {}).get(sym_b, 0.5)
            js_d = js_div.get(sym_a, {}).get(sym_b, 0.5)
            ret_c = ret_corr.get(sym_a, {}).get(sym_b, 0.5) if ret_corr else 0.5

            score = (
                correlation_weight * (1.0 - min(feat_c, 1.0))
                + divergence_weight * min(js_d, 1.0)
                + return_weight * (1.0 - min(abs(ret_c), 1.0))
            )
            key = f"{sym_a}-{sym_b}"
            pairwise_scores[key] = round(score, 4)
            pair_list.append((key, score))

    # Sort by diversity
    pair_list.sort(key=lambda x: x[1], reverse=True)
    most_diverse = [{"pair": p, "score": round(s, 4)} for p, s in pair_list[:top_k]]
    least_diverse = [{"pair": p, "score": round(s, 4)} for p, s in pair_list[-top_k:]]
    least_diverse.reverse()

    mean_diversity = float(np.mean([s for _, s in pair_list])) if pair_list else 0.0

    return {
        "mean_diversity": round(mean_diversity, 4),
        "symbol_count": len(symbols),
        "pairwise_scores": pairwise_scores,
        "most_diverse_pairs": most_diverse,
        "least_diverse_pairs": least_diverse,
        "components": {
            "feature_correlation": feat_corr,
            "js_divergence": js_div,
            "return_correlation": ret_corr,
        },
    }
