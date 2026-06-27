"""Multiple Hypothesis Testing (MHT) correction for AlphaForge reports.

Provides statistical corrections for multiple hypothesis testing and
data-snooping risk assessment. Used by the empirical report builder.

Critical distinction:
    trial_count is hypotheses tested, NOT oos_trade_count.
    trial_count = grid_search_combinations x thesis_count x feature_set_count

Functions:
    compute_trial_count: Count total trials from grid search, thesis, and feature dimensions.
    bonferroni_correction: Classic Bonferroni correction (alpha / n_trials).
    benjamini_hochberg: FDR control via Benjamini-Hochberg procedure.
    deflated_sharpe: Approximate deflated Sharpe ratio for multiple testing.
    compute_data_snooping_risk: Risk level based on trial count and MHT status.
"""

from __future__ import annotations

import math
from typing import Sequence


# ---------------------------------------------------------------------------
# Trial counting
# ---------------------------------------------------------------------------


def compute_trial_count(
    grid_search_combinations: int,
    thesis_count: int,
    feature_set_count: int,
) -> int:
    """Compute total trial count from all research dimensions.

    trial_count = product of grid_search_combinations x thesis_count x
    feature_set_count. Each dimension is floored at 1 to avoid artificially
    zeroing out the product. Minimum return is 1 to avoid division by zero
    in downstream correction formulas.

    Args:
        grid_search_combinations: Number of hyperparameter combinations
            tested (may be 0 if no grid search was performed).
        thesis_count: Number of alpha theses evaluated.
        feature_set_count: Number of feature sets tested.

    Returns:
        Total trial count, minimum 1.
    """
    g = max(1, grid_search_combinations)
    t = max(1, thesis_count)
    f = max(1, feature_set_count)
    return max(1, g * t * f)


# ---------------------------------------------------------------------------
# Bonferroni correction
# ---------------------------------------------------------------------------


def bonferroni_correction(alpha: float, n_trials: int) -> float:
    """Apply Bonferroni correction to significance threshold.

    adjusted_alpha = alpha / n_trials

    The Bonferroni correction is the most conservative MHT correction.
    It controls the family-wise error rate (FWER) by dividing the
    desired significance level by the number of independent tests.

    Args:
        alpha: Original significance threshold (e.g., 0.05).
        n_trials: Number of independent trials/hypotheses tested.

    Returns:
        Adjusted significance threshold. Returns original alpha when
        n_trials <= 0.
    """
    if n_trials <= 0:
        return alpha
    return alpha / n_trials


# ---------------------------------------------------------------------------
# Benjamini-Hochberg procedure (FDR control)
# ---------------------------------------------------------------------------


def benjamini_hochberg(
    p_values: Sequence[float],
    alpha: float,
) -> list[bool]:
    """Apply Benjamini-Hochberg procedure for false discovery rate control.

    Sorts p-values ascending, finds the largest rank i where
    p_i <= (i / m) * alpha. Rejects (declares significant) all
    hypotheses with p-value at or below that threshold.

    The Benjamini-Hochberg procedure controls the FDR (expected
    proportion of false discoveries among rejected hypotheses)
    at level alpha, under assumptions of independence or positive
    regression dependency.

    Args:
        p_values: Sequence of p-values from multiple hypothesis tests.
        alpha: Desired false discovery rate (e.g., 0.05).

    Returns:
        List of booleans same length as p_values, True where the
        hypothesis is rejected (deemed significant after correction).
    """
    m = len(p_values)
    if m == 0:
        return []

    # Annotate each p-value with its original index
    indexed: list[tuple[int, float]] = list(enumerate(p_values))
    # Sort by p-value ascending
    indexed.sort(key=lambda x: x[1])

    # Find the largest rank i where p_i <= (i / m) * alpha
    max_reject_rank = -1
    for rank, (_, p) in enumerate(indexed, start=1):
        threshold = (rank / m) * alpha
        if p <= threshold:
            max_reject_rank = rank

    # Build result array at original indices
    rejected = [False] * m
    if max_reject_rank >= 0:
        for i in range(max_reject_rank):
            original_idx = indexed[i][0]
            rejected[original_idx] = True

    return rejected


# ---------------------------------------------------------------------------
# Deflated Sharpe ratio
# ---------------------------------------------------------------------------


def deflated_sharpe(
    sharpe: float,
    n_trials: int,
    n_samples: int,
    gamma: float = 0.5,
) -> float:
    """Compute approximate deflated Sharpe ratio.

    Adjusts the observed Sharpe ratio downward to account for the
    inflation caused by multiple testing (data snooping / selection
    bias). When many strategies are tested, the maximum observed
    Sharpe overstates the true Sharpe of the best strategy.

    Formula:
        deflated = sharpe * sqrt((1 - gamma * n_trials / n_samples)
                                 / (1 - gamma))

    When gamma * n_trials / n_samples >= 1, returns 0.0 (edge fully
    deflated by multiple testing — no reliable signal remains).

    NOTE ON METHODOLOGY:
        method: APPROXIMATION
        assumption: gamma=0.5 (moderate positive correlation between trials)
        promotion_eligible: false unless reviewed by a domain expert

    Args:
        sharpe: Observed Sharpe ratio before any correction.
        n_trials: Number of independent trials tested.
        n_samples: Number of independent return observations (e.g., OOS
            trade count or OOS bars).
        gamma: Correlation factor between trials (default 0.5).
            gamma=0 implies independence; gamma close to 1 implies
            near-perfect correlation.

    Returns:
        Deflated Sharpe ratio, floored at 0.0. Returns the original
        Sharpe when n_trials <= 0 or n_samples <= 0 (no adjustment
        possible).
    """
    if n_trials <= 0 or n_samples <= 0:
        return sharpe

    ratio = gamma * n_trials / n_samples
    if ratio >= 1.0:
        return 0.0

    denominator = 1.0 - gamma
    if denominator <= 0.0:
        return 0.0

    numerator = 1.0 - ratio
    return sharpe * math.sqrt(numerator / denominator)


# ---------------------------------------------------------------------------
# Data-snooping risk assessment
# ---------------------------------------------------------------------------


def compute_data_snooping_risk(
    n_trials: int,
    mht_applied: bool,
    fold_count: int,
) -> str:
    """Compute data-snooping risk level.

    Assesses the risk that reported performance is inflated by
    data snooping (multiple testing on the same dataset). Based
    on trial count, whether MHT correction was applied, and the
    number of walk-forward validation folds.

    Args:
        n_trials: Total number of trials/hypotheses tested.
        mht_applied: Whether a valid MHT correction was applied.
        fold_count: Number of walk-forward validation folds.

    Returns:
        Risk level: 'CRITICAL', 'HIGH', 'MEDIUM', or 'LOW'.
    """
    if n_trials > 1000 and not mht_applied:
        return "CRITICAL"
    if n_trials > 100 and not mht_applied:
        return "HIGH"
    if n_trials > 10 or fold_count < 6:
        return "MEDIUM"
    if mht_applied and fold_count >= 6:
        return "LOW"
    # Default: few trials and adequate folds — low risk
    return "LOW"
