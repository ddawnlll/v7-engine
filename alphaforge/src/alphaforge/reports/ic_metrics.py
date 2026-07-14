"""IC / Rank IC infrastructure for AlphaForge research reports.

Provides pure-numpy functions for computing Information Coefficient (Pearson),
Rank IC (Spearman), IC Information Ratio, calibration error (ECE / MCE), and
expected-R-from-probabilities aggregation.

All functions operate on numpy arrays and return deterministic scalar or array
values.  No profitability claims, no real market data, no state.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import rankdata


def compute_ic(
    predicted_R: np.ndarray,
    realized_R: np.ndarray,
) -> float:
    """Pearson correlation (Information Coefficient) between predicted and
    realized R-multiples.

    NaN values are filtered pairwise.  Returns 0.0 when fewer than 3 valid
    samples remain after filtering, or when either series has effectively zero
    standard deviation (< 1e-10).

    Args:
        predicted_R:
            1-D array of predicted R values.
        realized_R:
            1-D array of realized R values, same length as *predicted_R*.

    Returns:
        Pearson correlation coefficient, or 0.0 under degenerate conditions.
    """
    predicted_R = np.asarray(predicted_R, dtype=np.float64)
    realized_R = np.asarray(realized_R, dtype=np.float64)

    # Pairwise NaN filter.
    valid = ~(np.isnan(predicted_R) | np.isnan(realized_R))
    p = predicted_R[valid]
    r = realized_R[valid]

    if p.shape[0] < 3:
        return 0.0

    # Degenerate-variance guard.
    if np.std(p) < 1e-10 or np.std(r) < 1e-10:
        return 0.0

    corr = np.corrcoef(p, r)[0, 1]
    return float(corr)


def compute_rank_ic(
    predicted_R: np.ndarray,
    realized_R: np.ndarray,
) -> float:
    """Spearman rank correlation (Rank IC) between predicted and realized
    R-multiples.

    Ranks are computed via :func:`scipy.stats.rankdata`.  NaN values are
    filtered pairwise.  Returns 0.0 under the same degenerate conditions as
    :func:`compute_ic`.

    Args:
        predicted_R:
            1-D array of predicted R values.
        realized_R:
            1-D array of realized R values, same length as *predicted_R*.

    Returns:
        Spearman rank correlation coefficient, or 0.0 under degenerate
        conditions.
    """
    predicted_R = np.asarray(predicted_R, dtype=np.float64)
    realized_R = np.asarray(realized_R, dtype=np.float64)

    # Pairwise NaN filter.
    valid = ~(np.isnan(predicted_R) | np.isnan(realized_R))
    p = predicted_R[valid]
    r = realized_R[valid]

    if p.shape[0] < 3:
        return 0.0

    # Rank transform — ties resolved by average rank.
    p_ranked = rankdata(p)
    r_ranked = rankdata(r)

    # Degenerate-variance guard on ranks.
    if np.std(p_ranked) < 1e-10 or np.std(r_ranked) < 1e-10:
        return 0.0

    corr = np.corrcoef(p_ranked, r_ranked)[0, 1]
    return float(corr)


def compute_ic_ir(
    per_fold_ics: np.ndarray,
) -> float:
    """IC Information Ratio — mean(IC) / std(IC) with numerical stability.

    The Information Ratio measures the consistency of IC across folds or
    time windows.  A higher ratio indicates more stable predictive
    performance.

    Args:
        per_fold_ics:
            1-D array of IC values, one per fold or evaluation window.

    Returns:
        IC Information Ratio (float).  Returns 0.0 when fewer than 2 folds
        are provided.
    """
    ics = np.asarray(per_fold_ics, dtype=np.float64)

    if ics.shape[0] < 2:
        return 0.0

    # Filter NaN folds — a single NaN fold should not collapse the IR.
    valid = ~np.isnan(ics)
    if np.sum(valid) < 2:
        return 0.0

    mean_ic = np.mean(ics[valid])
    std_ic = np.std(ics[valid], ddof=1)  # sample std

    return float(mean_ic / (std_ic + 1e-10))


def compute_calibration_error(
    probabilities: np.ndarray,
    outcomes: np.ndarray,
    n_bins: int = 10,
) -> tuple[float, float]:
    """Expected Calibration Error (ECE) and Maximum Calibration Error (MCE).

    Both probabilities and outcomes are assumed to be for a binary event
    (e.g. ``probability[price goes up]`` and ``outcome = 1.0`` if the event
    occurred, 0.0 otherwise).  Probabilities are binned into *n_bins*
    equally-spaced intervals over [0, 1].

    NaN values in either array are filtered pairwise before binning.

    For each bin *b*:
        ``confidence[b] = mean(probability in bin)``
        ``accuracy[b] = mean(outcome in bin)``

    ECE is the weighted average of ``|accuracy - confidence|`` across bins.
    MCE is the maximum absolute gap across bins.

    Args:
        probabilities:
            1-D array of predicted probabilities in [0, 1].
        outcomes:
            1-D array of binary outcomes (0.0 or 1.0), same length as
            *probabilities*.
        n_bins:
            Number of equal-width bins (default 10).

    Returns:
        ``(ece, mce)`` tuple — both floats, 0.0 when no data is available.
    """
    probs = np.asarray(probabilities, dtype=np.float64)
    outc = np.asarray(outcomes, dtype=np.float64)

    # Pairwise NaN filter.
    valid = ~(np.isnan(probs) | np.isnan(outc))
    probs = probs[valid]
    outc = outc[valid]

    if probs.shape[0] < 2:
        return 0.0, 0.0

    # Clamp probabilities to [0, 1] to avoid edge bin artefacts.
    probs = np.clip(probs, 0.0, 1.0)

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(probs, bins=bin_edges, right=False)

    # Bin index n_bins+1 catches exactly 1.0; remap to the last bin.
    bin_indices = np.clip(bin_indices, 1, n_bins) - 1

    total_samples = probs.shape[0]
    ece = 0.0
    mce = 0.0

    for b in range(n_bins):
        mask = bin_indices == b
        bin_count = np.sum(mask)

        if bin_count == 0:
            continue

        bin_conf = np.mean(probs[mask])
        bin_acc = np.mean(outc[mask])
        gap = abs(bin_acc - bin_conf)

        ece += gap * bin_count / total_samples
        mce = max(mce, gap)

    return float(ece), float(mce)


def compute_expected_r_from_probabilities(
    probs_3class: np.ndarray,
    r_per_class: np.ndarray,
) -> float:
    """Compute expected R-multiple from 3-class probability distribution.

    Element-wise dot product over the three classes, then averaged across
    all samples to produce a single scalar.

    NaN values in the per-sample dot product are excluded from the final
    average.  Returns 0.0 when zero valid samples remain.

    Args:
        probs_3class:
            2-D array of shape ``(N, 3)`` — predicted probabilities for the
            three classes (e.g. down / neutral / up).
        r_per_class:
            2-D array of shape ``(N, 3)`` — per-class expected R-multiple
            for each sample.

    Returns:
        Scalar expected R-multiple averaged across valid samples.
    """
    probs = np.asarray(probs_3class, dtype=np.float64)
    rvals = np.asarray(r_per_class, dtype=np.float64)

    # Element-wise expected R per sample.
    per_sample = np.sum(probs * rvals, axis=1)

    # Filter NaN.
    valid = ~np.isnan(per_sample)
    if np.sum(valid) == 0:
        return 0.0

    return float(np.mean(per_sample[valid]))


# ---------------------------------------------------------------------------
# Per-feature IC / Rank IC / ICIR for factor selection (Faz 3)
# ---------------------------------------------------------------------------

def compute_per_feature_ic(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list[str],
) -> list[dict]:
    """Compute IC, Rank IC, and absolute correlation for every feature column.

    For each feature column ``j`` in X, computes:
    - IC (Pearson correlation between feature_j and y)
    - Rank IC (Spearman correlation between feature_j and y)
    - Abs IC (|IC|, used for feature ranking)

    NaN rows are filtered pairwise per feature.

    Args:
        X: (N, F) feature matrix.
        y: (N,) target array (e.g. net_r_values or integer labels).
        feature_names: List of F feature names.

    Returns:
        List of dicts, one per feature, sorted by |IC| descending:
        ``[{name, ic, rank_ic, abs_ic, n_valid}, ...]``
    """
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n_features = X.shape[1] if X.ndim == 2 else 0

    if n_features == 0 or len(y) == 0:
        return []

    results = []
    for j in range(n_features):
        col = X[:, j]
        valid = ~(np.isnan(col) | np.isnan(y))
        p = col[valid]
        r = y[valid]
        n_valid = int(np.sum(valid))

        if n_valid < 10:
            results.append({
                "name": feature_names[j] if j < len(feature_names) else f"f{j}",
                "ic": 0.0,
                "rank_ic": 0.0,
                "abs_ic": 0.0,
                "n_valid": n_valid,
            })
            continue

        # Pearson IC
        if np.std(p) < 1e-10 or np.std(r) < 1e-10:
            ic = 0.0
        else:
            ic = float(np.corrcoef(p, r)[0, 1])

        # Spearman Rank IC
        p_ranked = rankdata(p)
        r_ranked = rankdata(r)
        if np.std(p_ranked) < 1e-10 or np.std(r_ranked) < 1e-10:
            rank_ic = 0.0
        else:
            rank_ic = float(np.corrcoef(p_ranked, r_ranked)[0, 1])

        results.append({
            "name": feature_names[j] if j < len(feature_names) else f"f{j}",
            "ic": round(ic, 6),
            "rank_ic": round(rank_ic, 6),
            "abs_ic": round(abs(ic), 6),
            "n_valid": n_valid,
        })

    # Sort by absolute IC descending
    results.sort(key=lambda x: x["abs_ic"], reverse=True)
    return results


def compute_feature_correlation_matrix(
    X: np.ndarray,
    feature_names: list[str],
) -> tuple[np.ndarray, list[str]]:
    """Compute pairwise Pearson correlation matrix for all feature columns.

    NaN values are replaced with 0.0 before correlation (standard practice
    for feature selection — NaN-fill columns are decorrelated by design).

    Args:
        X: (N, F) feature matrix.
        feature_names: List of F feature names.

    Returns:
        (corr_matrix, feature_names) — corr_matrix is (F, F) ndarray.
    """
    X = np.asarray(X, dtype=np.float64)
    n_features = X.shape[1] if X.ndim == 2 else 0

    if n_features == 0:
        return np.empty((0, 0)), feature_names

    # Replace NaN with 0.0 for correlation computation
    X_clean = np.where(np.isnan(X), 0.0, X)

    # Degenerate-variance guard: replace constant columns with zeros
    for j in range(n_features):
        if np.std(X_clean[:, j]) < 1e-10:
            X_clean[:, j] = 0.0

    corr_matrix = np.corrcoef(X_clean, rowvar=False)
    # Clamp numerical noise
    corr_matrix = np.clip(corr_matrix, -1.0, 1.0)
    # Diagonal to exactly 1.0
    np.fill_diagonal(corr_matrix, 1.0)

    return corr_matrix, feature_names


def select_features_greedy_ic(
    ic_results: list[dict],
    corr_matrix: np.ndarray,
    feature_names: list[str],
    max_features: int = 20,
    corr_threshold: float = 0.5,
    min_ic: float = 0.005,
) -> list[str]:
    """Greedy feature selection: pick highest-IC features, drop correlated.

    Algorithm (standard from finance factor selection literature):
    1. Start with the feature having the highest |IC|.
    2. Add it to the selected set.
    3. Remove all features with |correlation| > corr_threshold to the selected one.
    4. Repeat until max_features reached or no features remain above min_ic.

    This ensures selected features are both individually predictive AND
    minimally redundant (low mutual correlation).

    Args:
        ic_results: Output of compute_per_feature_ic (sorted by |IC| desc).
        corr_matrix: Output of compute_feature_correlation_matrix.
        feature_names: Canonical feature name list (same order as corr_matrix).
        max_features: Maximum number of features to select (default 20).
        corr_threshold: Correlation threshold for redundancy removal (default 0.5).
        min_ic: Minimum |IC| to consider a feature (default 0.005).

    Returns:
        List of selected feature names, ordered by |IC| (highest first).
    """
    # Build name -> index mapping
    name_to_idx = {name: idx for idx, name in enumerate(feature_names)}

    # Filter to features above min_ic
    eligible = [r for r in ic_results if r["abs_ic"] >= min_ic]

    selected_names = []
    selected_indices = set()

    for candidate in eligible:
        if len(selected_names) >= max_features:
            break

        name = candidate["name"]
        if name not in name_to_idx:
            continue

        idx = name_to_idx[name]
        if idx in selected_indices:
            continue

        # Check correlation with already-selected features
        too_correlated = False
        for sel_idx in selected_indices:
            if abs(corr_matrix[idx, sel_idx]) > corr_threshold:
                too_correlated = True
                break

        if not too_correlated:
            selected_names.append(name)
            selected_indices.add(idx)

    return selected_names


def compute_dynamic_weights(
    X_train: np.ndarray,
    y_train: np.ndarray,
    feature_names: list[str],
    selected_features: list[str],
) -> np.ndarray:
    """Compute per-feature dynamic weights using trailing IC.

    Uses the training fold's own IC values as weights, normalized to sum to 1.
    This is leakage-free because weights are computed from the TRAINING fold only,
    then applied to both training and validation within the same fold.

    Weight formula: w_j = |IC_j| / sum(|IC_j|) for selected features only.
    Features not in selected_features get weight 0.

    Args:
        X_train: (N_train, F) feature matrix for the training fold.
        y_train: (N_train,) target values for the training fold.
        feature_names: Full feature name list (same order as X_train columns).
        selected_features: List of selected feature names.

    Returns:
        (F,) weight array — 0.0 for non-selected features, positive for selected.
    """
    X_train = np.asarray(X_train, dtype=np.float64)
    y_train = np.asarray(y_train, dtype=np.float64)
    n_features = X_train.shape[1] if X_train.ndim == 2 else 0

    weights = np.zeros(n_features, dtype=np.float64)
    name_to_idx = {name: idx for idx, name in enumerate(feature_names)}

    total_abs_ic = 0.0
    for name in selected_features:
        if name not in name_to_idx:
            continue
        idx = name_to_idx[name]
        col = X_train[:, idx]
        valid = ~(np.isnan(col) | np.isnan(y_train))
        p = col[valid]
        r = y_train[valid]
        if len(p) < 10 or np.std(p) < 1e-10 or np.std(r) < 1e-10:
            weights[idx] = 0.001  # small epsilon to avoid zero-weight
            total_abs_ic += 0.001
        else:
            ic = abs(float(np.corrcoef(p, r)[0, 1]))
            weights[idx] = max(ic, 0.001)  # floor to avoid zero-weight
            total_abs_ic += weights[idx]

    # Normalize to sum to 1
    if total_abs_ic > 0:
        weights /= total_abs_ic

    return weights
