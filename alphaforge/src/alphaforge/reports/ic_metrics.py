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

    if probs.shape[0] == 0:
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
) -> np.ndarray:
    """Compute expected R-multiple from 3-class probability distribution.

    Element-wise dot product over the three classes:

        ``expected_R[i] = sum_c probs_3class[i, c] * r_per_class[i, c]``

    for class index *c* in {0, 1, 2}.

    Args:
        probs_3class:
            2-D array of shape ``(N, 3)`` — predicted probabilities for the
            three classes (e.g. down / neutral / up).
        r_per_class:
            2-D array of shape ``(N, 3)`` — per-class expected R-multiple
            for each sample.

    Returns:
        1-D array of shape ``(N,)`` — element-wise expected R-multiple.
    """
    probs = np.asarray(probs_3class, dtype=np.float64)
    rvals = np.asarray(r_per_class, dtype=np.float64)
    return np.sum(probs * rvals, axis=1)
