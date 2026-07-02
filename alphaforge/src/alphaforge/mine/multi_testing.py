"""Multiple testing correction for alpha rule mining.

Provides statistical corrections to control false positives when testing
many alpha rules simultaneously. Implements Bonferroni (FWER control),
Benjamini-Hochberg (FDR control), and Harvey-Liu-Zhu deflated Sharpe ratio.

Classes:
    MultiTestingCorrector: Static methods for multiple testing correction.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np
from scipy.stats import norm


class MultiTestingCorrector:
    """Statistical corrections for multiple hypothesis testing in alpha mining.

    Provides static methods for:
    - Bonferroni correction (FWER control)
    - Benjamini-Hochberg procedure (FDR control)
    - Harvey-Liu-Zhu deflated Sharpe ratio
    - High-level correct() method operating on rule dicts

    All methods are stateless and operate on numpy arrays for performance.
    """

    # ------------------------------------------------------------------
    # Bonferroni correction
    # ------------------------------------------------------------------

    @staticmethod
    def bonferroni(p_values: np.ndarray, alpha: float = 0.05) -> np.ndarray:
        """Apply Bonferroni correction for multiple comparisons.

        Adjusts the significance threshold to alpha' = alpha / m where m is
        the number of tests. Returns a boolean mask indicating which p-values
        survive the correction.

        The Bonferroni correction controls the family-wise error rate (FWER)
        by being maximally conservative: it divides the desired alpha equally
        among all tests, bounding the probability of *any* false positive
        at <= alpha.

        Args:
            p_values: Array of p-values from m hypothesis tests.
            alpha: Desired family-wise error rate (default 0.05).

        Returns:
            Boolean array same length as p_values, True where the p-value
            is <= alpha / m (survives Bonferroni correction).
        """
        m = len(p_values)
        if m == 0:
            return np.array([], dtype=bool)
        adjusted_threshold = alpha / m
        return p_values <= adjusted_threshold

    # ------------------------------------------------------------------
    # Benjamini-Hochberg procedure (FDR control)
    # ------------------------------------------------------------------

    @staticmethod
    def benjamini_hochberg(p_values: np.ndarray, q: float = 0.05) -> np.ndarray:
        """Apply Benjamini-Hochberg procedure for false discovery rate control.

        Sorts p-values ascending, then finds the largest rank i where
        p_i <= (i / m) * q. All hypotheses with rank <= i are rejected
        (declared significant).

        The BH procedure controls the expected proportion of false discoveries
        among rejected hypotheses at level q, under assumptions of independence
        or positive regression dependency.

        Args:
            p_values: Array of p-values from m hypothesis tests.
            q: Desired false discovery rate (default 0.05).

        Returns:
            Boolean array same length as p_values, True where the hypothesis
            is rejected (deemed significant after FDR control).
        """
        m = len(p_values)
        if m == 0:
            return np.array([], dtype=bool)

        # Sort p-values and track original indices
        sorted_indices = np.argsort(p_values, kind="stable")
        sorted_p = p_values[sorted_indices]

        # Find the largest rank where p_i <= (i / m) * q
        ranks = np.arange(1, m + 1, dtype=float)
        thresholds = (ranks / m) * q
        below_threshold = sorted_p <= thresholds

        if not np.any(below_threshold):
            return np.zeros(m, dtype=bool)

        # Max rank (0-indexed) that satisfies the condition
        max_rank = int(np.max(np.where(below_threshold)[0]))

        # Build boolean mask at original indices
        rejected = np.zeros(m, dtype=bool)
        rejected[sorted_indices[: max_rank + 1]] = True

        return rejected

    # ------------------------------------------------------------------
    # Harvey-Liu-Zhu deflated Sharpe ratio
    # ------------------------------------------------------------------

    @staticmethod
    def deflated_sharpe(sharpe_values: np.ndarray, N: int, m: int) -> np.ndarray:
        """Apply Harvey-Liu-Zhu deflated Sharpe ratio correction.

        Adjusts observed Sharpe ratios to account for the inflation caused
        by multiple testing (data snooping / selection bias). Uses the
        Harvey, Liu & Zhu (2016) multiple testing adjustment framework.

        Formula:
            DSR = Sharpe * sqrt((N-1) / N) * norm.ppf(1 - 0.5/m)

        Where:
            Sharpe: original Sharpe ratio(s)
            N: number of independent return observations
            m: number of trials / hypotheses tested

        A larger m produces a larger multiple-testing correction factor
        (more trials tested means the best observed Sharpe is more likely
        inflated by chance). The small-sample correction sqrt((N-1)/N)
        adjusts for bias in the Sharpe estimator.

        Args:
            sharpe_values: Array of observed Sharpe ratios to correct.
            N: Number of independent observations (e.g., OOS trade count).
                Must be > 1.
            m: Number of trials/hypotheses tested. Must be > 0.

        Returns:
            Array of deflated Sharpe ratios, same shape as sharpe_values.
            Returns NaN when N <= 1 or m <= 0 (invalid inputs).
        """
        if N <= 1 or m <= 0:
            return np.full_like(sharpe_values, np.nan, dtype=float)

        small_sample_correction = math.sqrt((N - 1) / N)
        multiple_testing_factor = norm.ppf(1 - 0.5 / m)

        return sharpe_values * small_sample_correction * multiple_testing_factor

    # ------------------------------------------------------------------
    # High-level correct() — enriches rule dicts
    # ------------------------------------------------------------------

    @staticmethod
    def correct(
        rules: List[Dict[str, Any]],
        method: str = "fdr",
        q: float = 0.05,
        alpha: float = 0.05,
        N: int | None = None,
        m: int | None = None,
    ) -> List[Dict[str, Any]]:
        """Apply multiple testing correction to a list of alpha rule dicts.

        Enriches each rule dict with:
            adjusted_p_value (float | None): P-value or DSR after correction.
            passes_correction (bool): Whether the rule survives the correction.

        Supported methods:

        ``'bonferroni'``
            Uses the ``p_value`` key from each rule. Adjusted p-value =
            min(p * len(rules), 1.0). Rejects when adjusted p-value <= alpha.

        ``'fdr'`` (default) / ``'benjamini_hochberg'``
            Uses the ``p_value`` key from each rule. Adjusted p-value =
            min(p * len(rules) / rank, 1.0). Rejects when the BH procedure
            flags the hypothesis at level q.

        ``'deflated_sharpe'``
            Uses the ``sharpe_ratio`` key from each rule. Requires N and m
            as keyword arguments. adjusted_p_value is set to the DSR value.
            A rule passes if DSR > 0.

        Args:
            rules: List of dicts, each representing an alpha rule. Must
                contain ``p_value`` for Bonferroni/BH methods, or
                ``sharpe_ratio`` for ``deflated_sharpe`` method.
            method: Correction method. One of ``'bonferroni'``, ``'fdr'``
                (default), ``'benjamini_hochberg'``, or ``'deflated_sharpe'``.
            q: Desired FDR for BH procedure (default 0.05). Ignored for
                other methods.
            alpha: Desired FWER for Bonferroni (default 0.05). Ignored for
                other methods.
            N: Number of independent observations. Required for
                ``deflated_sharpe``.
            m: Number of trials. Required for ``deflated_sharpe``.

        Returns:
            List of rule dicts enriched with ``adjusted_p_value`` and
            ``passes_correction``.

        Raises:
            ValueError: If required fields are missing from rules, or if
                N/m are missing for ``deflated_sharpe``.
        """
        if not rules:
            return rules

        results: List[Dict[str, Any]] = [dict(r) for r in rules]  # shallow copy

        method_key = method.lower().replace("_", "").replace("-", "")

        if method_key in ("fdr", "benjaminihochberg"):
            p_values = np.array(
                [_get_rule_pvalue(r, results, i) for i, r in enumerate(results)],
                dtype=float,
            )
            rejected = MultiTestingCorrector.benjamini_hochberg(p_values, q=q)

            # Compute adjusted p-values: min(p * m / rank, 1.0)
            m_count = len(p_values)
            sorted_indices = np.argsort(p_values, kind="stable")
            sorted_p = p_values[sorted_indices]
            adjusted_p = np.full(m_count, 1.0, dtype=float)
            for rank_idx, orig_idx in enumerate(sorted_indices):
                rank = rank_idx + 1
                adj = sorted_p[rank_idx] * m_count / rank
                adjusted_p[orig_idx] = min(adj, 1.0)

            for idx, rule in enumerate(results):
                rule["adjusted_p_value"] = float(adjusted_p[idx])
                rule["passes_correction"] = bool(rejected[idx])

        elif method_key == "bonferroni":
            p_values = np.array(
                [_get_rule_pvalue(r, results, i) for i, r in enumerate(results)],
                dtype=float,
            )
            rejected = MultiTestingCorrector.bonferroni(p_values, alpha=alpha)

            # Adjusted p-values: min(p * m, 1.0)
            m_count = len(p_values)
            adjusted_p = np.clip(p_values * m_count, None, 1.0)

            for idx, rule in enumerate(results):
                rule["adjusted_p_value"] = float(adjusted_p[idx])
                rule["passes_correction"] = bool(rejected[idx])

        elif method_key == "deflatedsharpe":
            if N is None or m is None:
                raise ValueError(
                    "N (observations) and m (trials) are required "
                    "for 'deflated_sharpe' correction"
                )

            sharpe_values = np.array(
                [
                    _get_rule_sharpe(r, results, i)
                    for i, r in enumerate(results)
                ],
                dtype=float,
            )
            dsr = MultiTestingCorrector.deflated_sharpe(sharpe_values, N=N, m=m)

            for idx, rule in enumerate(results):
                dsr_val = dsr[idx]
                rule["adjusted_p_value"] = (
                    float(dsr_val) if not np.isnan(dsr_val) else None
                )
                rule["passes_correction"] = bool(
                    not np.isnan(dsr_val) and dsr_val > 0
                )

        else:
            raise ValueError(
                f"Unknown correction method: '{method}'. "
                f"Expected 'bonferroni', 'fdr', 'benjamini_hochberg', "
                f"or 'deflated_sharpe'."
            )

        return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_rule_pvalue(
    rule: Dict[str, Any],
    rules: List[Dict[str, Any]],
    idx: int,
) -> float:
    """Extract p_value from a rule dict, raising on missing key."""
    val = rule.get("p_value")
    if val is None:
        raise ValueError(
            f"Rule at index {idx} missing required 'p_value' field "
            f"for {rules[idx].get('rule_id', 'unknown')}"
        )
    return float(val)


def _get_rule_sharpe(
    rule: Dict[str, Any],
    rules: List[Dict[str, Any]],
    idx: int,
) -> float:
    """Extract sharpe_ratio from a rule dict, raising on missing key."""
    val = rule.get("sharpe_ratio")
    if val is None:
        raise ValueError(
            f"Rule at index {idx} missing required 'sharpe_ratio' field "
            f"for deflated_sharpe correction"
        )
    return float(val)
