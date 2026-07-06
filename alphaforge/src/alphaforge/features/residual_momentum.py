"""Residual Momentum / Clustering Feature Group — beta-adjusted cross-sectional momentum.

Computes beta-adjusted residual momentum, k-means clustering of symbols,
and cross-sectional rank momentum from multi-symbol OHLCV data.

Design constraints (consistent with pipeline.py):
  - numpy only (no pandas, scipy, ta-lib)
  - no network calls
  - all features are causal (no future leakage)
  - NaN fill for insufficient lookback

Cross-sectional contract:
  Every function accepts multi-symbol OHLCV data as a Dict mapping symbol
  identifier to a Dict[str, np.ndarray] of OHLCV arrays.
  All symbols must have the same number of bars.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from numba import njit
except ImportError:
    njit = lambda x: x

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FEATURE_GROUP_NAME: str = "residual_momentum"

# Default beta estimation window (bars)
DEFAULT_BETA_WINDOW: int = 20

# Default number of clusters for k-means
DEFAULT_N_CLUSTERS: int = 3

# Default k-means max iterations
DEFAULT_KMEANS_MAX_ITER: int = 100

# Default momentum windows for cross-sectional momentum
DEFAULT_CS_MOM_WINDOW_1: int = 5
DEFAULT_CS_MOM_WINDOW_2: int = 10
DEFAULT_CS_MOM_WINDOW_3: int = 20

# Minimum valid observations for regression
MIN_VALID: int = 5

# Default random seed for k-means initialization
KMEANS_RANDOM_SEED: int = 42


# ===========================================================================
# Helpers
# ===========================================================================


def _validate_multi_symbol_ohlcv(
    multi_ohlcv: Dict[str, Dict[str, np.ndarray]],
) -> int:
    """Validate multi-symbol OHLCV data and return uniform bar count.

    Args:
        multi_ohlcv: Dict mapping symbol -> {'close': ..., ...}.

    Returns:
        Common number of bars across all symbols.

    Raises:
        ValueError: if fewer than 2 symbols, missing columns, or mismatched lengths.
    """
    if not isinstance(multi_ohlcv, dict) or len(multi_ohlcv) < 2:
        raise ValueError(
            f"Residual momentum features require at least 2 symbols, "
            f"got {len(multi_ohlcv) if isinstance(multi_ohlcv, dict) else 0}"
        )

    required = {"close"}
    bar_counts: List[int] = []

    for symbol, ohlcv in multi_ohlcv.items():
        missing = required - set(ohlcv.keys())
        if missing:
            raise ValueError(f"Symbol '{symbol}' missing required columns: {missing}")

        for col in required:
            arr = ohlcv[col]
            if not isinstance(arr, np.ndarray) or arr.ndim != 1:
                raise TypeError(
                    f"Symbol '{symbol}' column '{col}' must be 1D numpy.ndarray"
                )

        bar_counts.append(len(ohlcv["close"]))

    if len(set(bar_counts)) != 1:
        raise ValueError(
            f"All symbols must have the same number of bars. Got lengths: "
            f"{dict(zip(multi_ohlcv.keys(), bar_counts))}"
        )

    n_bars = bar_counts[0]
    if n_bars < 2:
        raise ValueError(
            f"Need at least 2 bars for residual momentum, got {n_bars}"
        )

    return n_bars


def _compute_log_returns(close: np.ndarray) -> np.ndarray:
    """Compute 1-bar log returns (causal). NaN at t=0."""
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < 2:
        return result
    with np.errstate(divide="ignore", invalid="ignore"):
        result[1:] = np.log(close[1:] / close[:-1])
    return result


@njit
def _rolling_ols_beta(
    y: np.ndarray,
    x: np.ndarray,
    window: int,
    min_valid: int = MIN_VALID,
) -> np.ndarray:
    """Compute rolling OLS beta of y vs x over a causal window.

    beta[t] = cov(y_window, x_window) / var(x_window).
    Returns NaN for t < window-1 or when insufficient valid data.

    Args:
        y: Dependent variable series (e.g., symbol returns).
        x: Independent variable series (e.g., BTC returns).
        window: Rolling window size.
        min_valid: Minimum valid paired observations.

    Returns:
        Array of beta coefficients, same length as inputs.
    """
    n = len(y)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window or window < 2:
        return result

    for i in range(window - 1, n):
        y_seg = y[i - window + 1 : i + 1]
        x_seg = x[i - window + 1 : i + 1]

        valid = ~np.isnan(y_seg) & ~np.isnan(x_seg)
        n_valid = int(np.sum(valid))
        if n_valid < min_valid:
            continue

        xv = x_seg[valid]
        yv = y_seg[valid]

        x_mean = np.mean(xv)
        y_mean = np.mean(yv)

        dx = xv - x_mean
        dy = yv - y_mean

        cov = np.sum(dx * dy) / n_valid
        var_x = np.sum(dx * dx) / n_valid

        if var_x < 1e-14:
            continue

        result[i] = cov / var_x

    return result


def _kmeans_plusplus_init(
    data: np.ndarray,
    n_clusters: int,
    random_seed: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """K-means++ initialization.

    Args:
        data: 2D array of shape (n_samples, n_features).
        n_clusters: Number of clusters.
        random_seed: Random seed for reproducibility.

    Returns:
        (centroids, labels) where centroids have shape (n_clusters, n_features).
    """
    rng = np.random.RandomState(random_seed)
    n = data.shape[0]
    if n == 0:
        return np.empty((0, data.shape[1])), np.empty(0, dtype=np.int64)

    # Choose first centroid uniformly at random
    first_idx = rng.randint(0, n)
    centroids = np.empty((n_clusters, data.shape[1]), dtype=np.float64)
    centroids[0] = data[first_idx]

    for c in range(1, n_clusters):
        # Compute squared distances to nearest centroid
        min_dists = np.full(n, np.inf, dtype=np.float64)
        for i in range(n):
            for j in range(c):
                d = data[i] - centroids[j]
                dist_sq = d[0] * d[0] + d[1] * d[1] if data.shape[1] == 2 else np.sum(d * d)
                if dist_sq < min_dists[i]:
                    min_dists[i] = dist_sq

        # Choose next centroid with probability proportional to distance^2
        probs = min_dists / np.sum(min_dists)
        cumsum = 0.0
        r = rng.random()
        next_idx = n - 1
        for i in range(n):
            cumsum += probs[i]
            if r < cumsum:
                next_idx = i
                break
        centroids[c] = data[next_idx]

    # Initial labels by nearest centroid
    labels = np.empty(n, dtype=np.int64)
    for i in range(n):
        best_dist = np.inf
        best_c = 0
        for c in range(n_clusters):
            d = data[i] - centroids[c]
            dist_sq = d[0] * d[0] + d[1] * d[1] if data.shape[1] == 2 else np.sum(d * d)
            if dist_sq < best_dist:
                best_dist = dist_sq
                best_c = c
        labels[i] = best_c

    return centroids, labels


def _kmeans_iteration(
    data: np.ndarray,
    centroids: np.ndarray,
    n_clusters: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Single k-means iteration: assign labels, update centroids.

    Returns (centroids, labels).
    """
    n = data.shape[0]
    n_features = data.shape[1]
    labels = np.empty(n, dtype=np.int64)

    # Assignment step
    for i in range(n):
        best_dist = np.inf
        best_c = 0
        for c in range(n_clusters):
            d = data[i] - centroids[c]
            dist_sq = 0.0
            for f in range(n_features):
                dist_sq += d[f] * d[f]
            if dist_sq < best_dist:
                best_dist = dist_sq
                best_c = c
        labels[i] = best_c

    # Update step
    new_centroids = np.zeros_like(centroids)
    counts = np.zeros(n_clusters, dtype=np.int64)
    for i in range(n):
        c = labels[i]
        for f in range(n_features):
            new_centroids[c, f] += data[i, f]
        counts[c] += 1
    for c in range(n_clusters):
        if counts[c] > 0:
            for f in range(n_features):
                new_centroids[c, f] /= counts[c]
        else:
            # Keep old centroid if cluster is empty
            for f in range(n_features):
                new_centroids[c, f] = centroids[c, f]

    return new_centroids, labels


def _kmeans_cluster(
    data: np.ndarray,
    n_clusters: int,
    max_iter: int,
    random_seed: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """K-means clustering with k-means++ initialization.

    Args:
        data: 2D array of shape (n_samples, n_features).
        n_clusters: Number of clusters.
        max_iter: Maximum iterations.
        random_seed: Random seed.

    Returns:
        (centroids, labels)
    """
    centroids, labels = _kmeans_plusplus_init(data, n_clusters, random_seed)

    for _ in range(max_iter):
        new_centroids, new_labels = _kmeans_iteration(data, centroids, n_clusters)

        # Check convergence: labels unchanged
        changed = False
        for i in range(len(labels)):
            if labels[i] != new_labels[i]:
                changed = True
                break
        if not changed:
            break

        centroids = new_centroids
        labels = new_labels

    return centroids, labels


# ===========================================================================
# Public API
# ===========================================================================


def compute_beta(
    symbol_returns: np.ndarray,
    btc_returns: np.ndarray,
    window: int = DEFAULT_BETA_WINDOW,
) -> np.ndarray:
    """Compute rolling OLS beta of symbol returns vs BTC returns.

    beta[t] measures the symbol's systematic exposure to BTC at bar t.

    Args:
        symbol_returns: Symbol log returns, shape (n_bars,).
        btc_returns: BTC log returns, shape (n_bars,).
        window: Rolling window in bars (default 20).

    Returns:
        Array of beta coefficients, same length as inputs.
        NaN for t < window-1.
    """
    return _rolling_ols_beta(symbol_returns, btc_returns, window)


def compute_residual_momentum(
    symbol_returns: np.ndarray,
    btc_returns: np.ndarray,
    beta: np.ndarray,
) -> np.ndarray:
    """Compute residual returns after removing BTC beta exposure.

    residual_return[t] = symbol_return[t] - beta[t] * btc_return[t]

    This isolates the symbol's idiosyncratic (alpha) momentum,
    removing the systematic BTC-driven component.

    Args:
        symbol_returns: Symbol log returns, shape (n_bars,).
        btc_returns: BTC log returns, shape (n_bars,).
        beta: Rolling beta from compute_beta(), shape (n_bars,).

    Returns:
        Residual returns array, same length as inputs.
        NaN where beta is NaN.
    """
    result = np.full_like(symbol_returns, np.nan, dtype=np.float64)
    valid = ~np.isnan(beta) & ~np.isnan(symbol_returns) & ~np.isnan(btc_returns)
    result[valid] = symbol_returns[valid] - beta[valid] * btc_returns[valid]
    return result


def cluster_symbols(
    symbol_profiles: np.ndarray,
    n_clusters: int = DEFAULT_N_CLUSTERS,
    max_iter: int = DEFAULT_KMEANS_MAX_ITER,
    random_seed: int = KMEANS_RANDOM_SEED,
) -> Tuple[np.ndarray, np.ndarray]:
    """Cluster symbols by their feature profiles using k-means.

    Args:
        symbol_profiles: 2D array of shape (n_symbols, n_features).
            Each row is a symbol's feature vector (e.g., [beta, volatility, momentum]).
        n_clusters: Number of clusters (default 3).
        max_iter: Maximum k-means iterations (default 100).
        random_seed: Random seed for reproducibility (default 42).

    Returns:
        (centroids, labels) where:
          centroids: (n_clusters, n_features) array of cluster centers.
          labels: (n_symbols,) integer cluster assignment for each symbol.
    """
    return _kmeans_cluster(symbol_profiles, n_clusters, max_iter, random_seed)


def compute_cross_sectional_momentum(
    returns_matrix: np.ndarray,
    windows: Tuple[int, ...] = (
        DEFAULT_CS_MOM_WINDOW_1,
        DEFAULT_CS_MOM_WINDOW_2,
        DEFAULT_CS_MOM_WINDOW_3,
    ),
) -> Dict[str, np.ndarray]:
    """Compute rank-based cross-sectional momentum from a returns matrix.

    For each bar, ranks symbols by their cumulative return over each window,
    producing a rank-normalized momentum signal.

    Args:
        returns_matrix: 2D array of shape (n_symbols, n_bars).
            Each row is a symbol's return series (log returns preferred).
        windows: Tuple of cumulative return windows in bars.

    Returns:
        Dict mapping f"cs_momentum_{w}" to 2D array of shape (n_symbols, n_bars).
        Each array contains cross-sectional ranks in [0, 1] for that window.
    """
    n_symbols, n_bars = returns_matrix.shape
    result: Dict[str, np.ndarray] = {}

    for window in windows:
        rank_matrix = np.full((n_symbols, n_bars), np.nan, dtype=np.float64)

        for t in range(window - 1, n_bars):
            # Cumulative return over window for each symbol
            cum_ret = np.full(n_symbols, np.nan, dtype=np.float64)
            for s in range(n_symbols):
                seg = returns_matrix[s, max(0, t - window + 1) : t + 1]
                seg_clean = seg[~np.isnan(seg)]
                if len(seg_clean) >= 2:
                    cum_ret[s] = np.sum(seg_clean)

            # Rank cross-sectionally
            valid = ~np.isnan(cum_ret)
            n_valid = int(np.sum(valid))
            if n_valid >= 2:
                valid_indices = np.where(valid)[0]
                valid_vals = cum_ret[valid]
                order = np.argsort(valid_vals)
                ranks = np.empty(n_valid, dtype=np.float64)
                ranks[order] = np.arange(n_valid, dtype=np.float64)
                ranks /= max(n_valid - 1, 1)
                for idx, rank_val in zip(valid_indices, ranks):
                    rank_matrix[idx, t] = rank_val
            elif n_valid == 1:
                valid_idx = np.where(valid)[0][0]
                rank_matrix[valid_idx, t] = 0.5

        result[f"cs_momentum_{window}"] = rank_matrix

    return result


def compute_residual_momentum_group(
    multi_ohlcv: Dict[str, Dict[str, np.ndarray]],
    btc_symbol: str = "BTCUSDT",
    beta_window: int = DEFAULT_BETA_WINDOW,
    n_clusters: int = DEFAULT_N_CLUSTERS,
    cs_windows: Tuple[int, ...] = (
        DEFAULT_CS_MOM_WINDOW_1,
        DEFAULT_CS_MOM_WINDOW_2,
        DEFAULT_CS_MOM_WINDOW_3,
    ),
) -> Dict[str, np.ndarray]:
    """Compute all residual momentum features for a multi-symbol universe.

    For each symbol (excluding the BTC reference), computes:
      - beta: rolling OLS beta vs BTC
      - residual_momentum: beta-adjusted returns
      - cluster_id: k-means cluster label (based on recent beta/vol/momentum)

    Also computes cross-sectional rank momentum across all non-BTC symbols.

    Args:
        multi_ohlcv: Dict mapping symbol -> {'close': ndarray, ...}.
        btc_symbol: Symbol identifier for BTC reference (default "BTCUSDT").
        beta_window: Rolling beta window in bars (default 20).
        n_clusters: Number of k-means clusters (default 3).
        cs_windows: Cumulative return windows for cross-sectional momentum.

    Returns:
        Dict mapping feature name to 2D array of shape (n_symbols - 1, n_bars).
        BTC/USDT itself is excluded from the output features.
        Keys:
          residual_beta         — beta vs BTC
          residual_momentum     — beta-adjusted residual return
          cluster_id            — k-means cluster assignment (per bar)
          cs_momentum_{w}       — cross-sectional rank momentum at each window
    """
    n_bars = _validate_multi_symbol_ohlcv(multi_ohlcv)
    symbols = list(multi_ohlcv.keys())

    if btc_symbol not in multi_ohlcv:
        raise ValueError(
            f"btc_symbol='{btc_symbol}' not found in multi_ohlcv keys: {symbols}"
        )

    # BTC returns (reference)
    btc_close = multi_ohlcv[btc_symbol]["close"].astype(np.float64)
    btc_returns = _compute_log_returns(btc_close)

    # Separate BTC from other symbols
    other_symbols = [s for s in symbols if s != btc_symbol]
    n_others = len(other_symbols)

    if n_others < 1:
        raise ValueError(
            f"Need at least 1 non-BTC symbol for residual momentum, got {n_others}"
        )

    # Storage: (n_others, n_bars)
    beta_matrix = np.full((n_others, n_bars), np.nan, dtype=np.float64)
    residual_matrix = np.full((n_others, n_bars), np.nan, dtype=np.float64)
    returns_matrix = np.full((n_others, n_bars), np.nan, dtype=np.float64)

    for idx, sym in enumerate(other_symbols):
        close = multi_ohlcv[sym]["close"].astype(np.float64)
        sym_returns = _compute_log_returns(close)
        returns_matrix[idx, :] = sym_returns

        # Rolling beta vs BTC
        beta = compute_beta(sym_returns, btc_returns, beta_window)
        beta_matrix[idx, :] = beta

        # Residual momentum
        residual = compute_residual_momentum(sym_returns, btc_returns, beta)
        residual_matrix[idx, :] = residual

    # ------------------------------------------------------------------
    # Cluster symbols based on their latest beta, volatility, and momentum
    # Use the most recent valid values as the symbol profile
    # ------------------------------------------------------------------
    profile_features: List[float] = []
    for idx in range(n_others):
        beta_series = beta_matrix[idx, :]
        res_series = residual_matrix[idx, :]
        ret_series = returns_matrix[idx, :]

        # Most recent valid values
        valid_beta = beta_series[~np.isnan(beta_series)]
        valid_res = res_series[~np.isnan(res_series)]
        valid_ret = ret_series[~np.isnan(ret_series)]

        beta_latest = float(valid_beta[-1]) if len(valid_beta) > 0 else 0.0
        vol_latest = float(np.std(valid_ret[-beta_window:], ddof=1)) if len(valid_ret) >= 2 else 0.0
        mom_latest = float(np.sum(valid_res[-5:])) if len(valid_res) >= 5 else 0.0  # 5-bar residual momentum

        profile_features.extend([beta_latest, vol_latest, mom_latest])

    symbol_profiles = np.array(profile_features, dtype=np.float64).reshape(n_others, 3)
    centroids, labels = cluster_symbols(symbol_profiles, n_clusters=n_clusters)

    # Per-bar cluster labels: propagate the stable cluster assignment
    cluster_id_matrix = np.full((n_others, n_bars), np.nan, dtype=np.float64)
    for idx in range(n_others):
        cluster_id_matrix[idx, :] = float(labels[idx])

    # ------------------------------------------------------------------
    # Cross-sectional rank momentum across non-BTC symbols
    # ------------------------------------------------------------------
    cs_result = compute_cross_sectional_momentum(returns_matrix, windows=cs_windows)

    # ------------------------------------------------------------------
    # Assemble result dict
    # ------------------------------------------------------------------
    result: Dict[str, np.ndarray] = {
        "residual_beta": beta_matrix,
        "residual_momentum": residual_matrix,
        "cluster_id": cluster_id_matrix,
    }
    result.update(cs_result)

    logger.info(
        "Residual momentum group: %d symbols, %d bars, %d clusters",
        n_others, n_bars, n_clusters,
    )

    return result
