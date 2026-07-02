"""Tests for MultiTestingCorrector — multiple testing correction for alpha mining.

Tests every method in alphaforge.mine.multi_testing:
- bonferroni: FWER control via alpha/m threshold
- benjamini_hochberg: FDR control via BH procedure
- deflated_sharpe: Harvey-Liu-Zhu corrected Sharpe ratio
- correct: high-level enrichment of rule dicts
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np
import pytest
from scipy.stats import norm

from alphaforge.mine.multi_testing import MultiTestingCorrector


# ===========================================================================
# Bonferroni correction
# ===========================================================================


class TestBonferroni:
    """Tests for MultiTestingCorrector.bonferroni()."""

    def test_100_tests_5_significant_becomes_0(self):
        """Bonferroni: 100 tests, 5 with p=0.01, 95 with p=0.5.

        alpha' = 0.05 / 100 = 0.0005.
        p=0.01 > 0.0005, so none survive.
        After correction: 0 significant.
        """
        p_values = np.array([0.01] * 5 + [0.5] * 95, dtype=float)
        result = MultiTestingCorrector.bonferroni(p_values, alpha=0.05)
        assert result.sum() == 0, (
            f"Expected 0 rejections, got {result.sum()}"
        )
        assert len(result) == 100

    def test_some_survive(self):
        """Bonferroni: 10 tests, 3 with very small p-values."""
        p_values = np.array(
            [0.001, 0.0005, 0.0001, 0.5, 0.3, 0.2, 0.1, 0.05, 0.01, 0.02],
            dtype=float,
        )
        # alpha' = 0.05 / 10 = 0.005
        # p=0.001 <= 0.005 -> reject
        # p=0.0005 <= 0.005 -> reject
        # p=0.0001 <= 0.005 -> reject
        # All others > 0.005 -> accept
        result = MultiTestingCorrector.bonferroni(p_values, alpha=0.05)
        expected = np.array(
            [True, True, True, False, False, False, False, False, False, False],
        )
        assert np.array_equal(result, expected)

    def test_empty_array(self):
        """Bonferroni: empty array returns empty array."""
        result = MultiTestingCorrector.bonferroni(np.array([], dtype=float))
        assert len(result) == 0
        assert result.dtype == bool

    def test_all_false_with_no_true_hits(self):
        """Bonferroni: no p-values survive correction."""
        p_values = np.array([0.5, 0.6, 0.7, 0.8], dtype=float)
        result = MultiTestingCorrector.bonferroni(p_values, alpha=0.05)
        assert not result.any()

    def test_all_true_with_extreme_pvalues(self):
        """Bonferroni: extremely small p-values all survive."""
        p_values = np.array([1e-6, 1e-7, 1e-8], dtype=float)
        result = MultiTestingCorrector.bonferroni(p_values, alpha=0.05)
        # alpha' = 0.05/3 ~ 0.0167
        assert result.all()


# ===========================================================================
# Benjamini-Hochberg procedure
# ===========================================================================


class TestBenjaminiHochberg:
    """Tests for MultiTestingCorrector.benjamini_hochberg()."""

    def test_fdr_control_correct(self):
        """BH: correctly identifies significant tests.

        p_values = [0.01, 0.02, 0.03, 0.04, 0.9], q=0.05

        Sorted: 0.01(0), 0.02(1), 0.03(2), 0.04(3), 0.9(4)
        Rank 1: threshold=0.01,  p=0.01 <= 0.01  -> reject
        Rank 2: threshold=0.02,  p=0.02 <= 0.02  -> reject
        Rank 3: threshold=0.03,  p=0.03 <= 0.03  -> reject
        Rank 4: threshold=0.04,  p=0.04 <= 0.04  -> reject
        Rank 5: threshold=0.05,  p=0.9  > 0.05   -> stop
        """
        p_values = np.array([0.01, 0.02, 0.03, 0.04, 0.9], dtype=float)
        result = MultiTestingCorrector.benjamini_hochberg(p_values, q=0.05)
        expected = np.array([True, True, True, True, False])
        assert np.array_equal(result, expected)

    def test_no_rejections(self):
        """BH: no p-values below their rank threshold."""
        p_values = np.array([0.02, 0.1, 0.3], dtype=float)
        # Rank 1: threshold=0.0167, p=0.02 > 0.0167 -> stop immediately
        result = MultiTestingCorrector.benjamini_hochberg(p_values, q=0.05)
        assert not result.any()

    def test_empty_array(self):
        """BH: empty array returns empty array."""
        result = MultiTestingCorrector.benjamini_hochberg(
            np.array([], dtype=float), q=0.05,
        )
        assert len(result) == 0
        assert result.dtype == bool

    def test_maintains_original_order(self):
        """BH: result order matches input p-value order."""
        p_values = np.array([0.9, 0.01, 0.5, 0.02], dtype=float)
        # Sorted: (1, 0.01), (3, 0.02), (2, 0.5), (0, 0.9)
        # m=4, q=0.05
        # Rank 1: threshold=0.0125, p=0.01 <= 0.0125 -> reject
        # Rank 2: threshold=0.025,  p=0.02 <= 0.025  -> reject
        # Rank 3: threshold=0.0375, p=0.5  > 0.0375  -> stop
        # max_reject_rank = 1 (0-indexed), so indices 1 and 3 are True
        result = MultiTestingCorrector.benjamini_hochberg(p_values, q=0.05)
        expected = np.array([False, True, False, True])
        assert np.array_equal(result, expected)

    def test_all_rejected(self):
        """BH: all p-values small enough to be rejected."""
        p_values = np.array([0.001, 0.002, 0.003], dtype=float)
        # m=3, q=0.05
        # Rank 1: threshold=0.0167, 0.001 <= 0.0167
        # Rank 2: threshold=0.0333, 0.002 <= 0.0333
        # Rank 3: threshold=0.05,   0.003 <= 0.05
        result = MultiTestingCorrector.benjamini_hochberg(p_values, q=0.05)
        assert result.all()

    def test_single_element(self):
        """BH: single p-value, rejected if p <= q."""
        assert (
            MultiTestingCorrector.benjamini_hochberg(
                np.array([0.01]), q=0.05,
            )[0]
        )
        assert not (
            MultiTestingCorrector.benjamini_hochberg(
                np.array([0.1]), q=0.05,
            )[0]
        )


# ===========================================================================
# Deflated Sharpe ratio (Harvey-Liu-Zhu)
# ===========================================================================


class TestDeflatedSharpe:
    """Tests for MultiTestingCorrector.deflated_sharpe()."""

    def test_known_input_expected_output(self):
        """DSR: known input produces expected output.

        Sharpe=1.0, N=100, m=10

        DSR = 1.0 * sqrt(99/100) * norm.ppf(1 - 0.5/10)
            = sqrt(0.99) * norm.ppf(0.95)
            = 0.994987... * 1.644853...
            = 1.6366...
        """
        sharpe = np.array([1.0], dtype=float)
        result = MultiTestingCorrector.deflated_sharpe(sharpe, N=100, m=10)
        expected = math.sqrt(99 / 100) * norm.ppf(1 - 0.5 / 10)
        assert result[0] == pytest.approx(expected, abs=1e-10)

    def test_vector_input(self):
        """DSR: handles multiple Sharpe values."""
        sharpe = np.array([0.5, 1.0, 2.0], dtype=float)
        result = MultiTestingCorrector.deflated_sharpe(sharpe, N=250, m=20)
        assert len(result) == 3
        # Ratio between outputs should match ratio between inputs
        assert result[1] / result[0] == pytest.approx(2.0, abs=1e-10)
        assert result[2] / result[1] == pytest.approx(2.0, abs=1e-10)

    def test_invalid_N_returns_nan(self):
        """DSR: N <= 1 returns NaN."""
        sharpe = np.array([1.0], dtype=float)
        result = MultiTestingCorrector.deflated_sharpe(sharpe, N=1, m=10)
        assert np.isnan(result[0])

        result2 = MultiTestingCorrector.deflated_sharpe(sharpe, N=0, m=10)
        assert np.isnan(result2[0])

    def test_invalid_m_returns_nan(self):
        """DSR: m <= 0 returns NaN."""
        sharpe = np.array([1.0], dtype=float)
        result = MultiTestingCorrector.deflated_sharpe(sharpe, N=100, m=0)
        assert np.isnan(result[0])

        result2 = MultiTestingCorrector.deflated_sharpe(sharpe, N=100, m=-1)
        assert np.isnan(result2[0])

    def test_large_m_small_N(self):
        """DSR: handles extreme parameters without error."""
        sharpe = np.array([2.0], dtype=float)
        # Large m, small N
        result = MultiTestingCorrector.deflated_sharpe(sharpe, N=30, m=1000)
        # Should produce a finite result (large correction factor)
        assert np.isfinite(result[0])
        assert result[0] > 0

    def test_empty_array(self):
        """DSR: empty array returns empty array."""
        result = MultiTestingCorrector.deflated_sharpe(
            np.array([], dtype=float), N=100, m=10,
        )
        assert len(result) == 0


# ===========================================================================
# High-level correct() method
# ===========================================================================


class TestCorrect:
    """Tests for MultiTestingCorrector.correct()."""

    def make_rules_with_pvalues(
        self, p_values: List[float],
    ) -> List[Dict[str, Any]]:
        """Helper: build rule dicts with p_value field."""
        return [
            {"rule_id": f"rule_{i}", "p_value": p}
            for i, p in enumerate(p_values)
        ]

    def make_rules_with_sharpes(
        self, sharpe_values: List[float],
    ) -> List[Dict[str, Any]]:
        """Helper: build rule dicts with sharpe_ratio field."""
        return [
            {"rule_id": f"rule_{i}", "sharpe_ratio": s}
            for i, s in enumerate(sharpe_values)
        ]

    # --- Bonferroni via correct() ---

    def test_correct_bonferroni(self):
        """correct(method='bonferroni') applies Bonferroni and enriches dicts."""
        rules = self.make_rules_with_pvalues([0.001, 0.01, 0.5])
        result = MultiTestingCorrector.correct(rules, method="bonferroni")
        assert len(result) == 3
        for r in result:
            assert "adjusted_p_value" in r
            assert "passes_correction" in r

        # adj_p = min(p * 3, 1.0)
        assert result[0]["adjusted_p_value"] == pytest.approx(0.003, abs=1e-10)
        assert result[1]["adjusted_p_value"] == pytest.approx(0.03, abs=1e-10)
        assert result[2]["adjusted_p_value"] == 1.0

        # alpha' = 0.05/3 = 0.0167
        # p=0.001 passes, p=0.01 passes (barely), p=0.5 fails
        assert result[0]["passes_correction"] is True
        assert result[1]["passes_correction"] is True
        assert result[2]["passes_correction"] is False

    def test_correct_bonferroni_custom_alpha(self):
        """correct(method='bonferroni', alpha=0.01) uses custom FWER."""
        rules = self.make_rules_with_pvalues([0.001, 0.005])
        result = MultiTestingCorrector.correct(
            rules, method="bonferroni", alpha=0.01,
        )
        # alpha' = 0.01/2 = 0.005
        # p=0.001 passes, p=0.005 passes
        assert result[0]["passes_correction"] is True
        assert result[1]["passes_correction"] is True

    # --- FDR via correct() ---

    def test_correct_fdr(self):
        """correct(method='fdr') applies BH and enriches dicts."""
        p_values = [0.01, 0.02, 0.03, 0.04, 0.9]
        rules = self.make_rules_with_pvalues(p_values)
        result = MultiTestingCorrector.correct(rules, method="fdr")
        assert len(result) == 5
        assert result[0]["passes_correction"] is True
        assert result[1]["passes_correction"] is True
        assert result[2]["passes_correction"] is True
        assert result[3]["passes_correction"] is True
        assert result[4]["passes_correction"] is False

        # Adjusted p-values: min(p * m / rank, 1.0)
        # Sorted: 0.01(0), 0.02(1), 0.03(2), 0.04(3), 0.9(4)
        # Rule 0 (p=0.01, rank=1): min(0.01*5/1, 1.0) = 0.05
        # Rule 1 (p=0.02, rank=2): min(0.02*5/2, 1.0) = 0.05
        # Rule 2 (p=0.03, rank=3): min(0.03*5/3, 1.0) = 0.05
        # Rule 3 (p=0.04, rank=4): min(0.04*5/4, 1.0) = 0.05
        # Rule 4 (p=0.90, rank=5): min(0.90*5/5, 1.0) = 0.90
        assert result[0]["adjusted_p_value"] == pytest.approx(0.05, abs=1e-10)
        assert result[1]["adjusted_p_value"] == pytest.approx(0.05, abs=1e-10)
        assert result[2]["adjusted_p_value"] == pytest.approx(0.05, abs=1e-10)
        assert result[3]["adjusted_p_value"] == pytest.approx(0.05, abs=1e-10)
        assert result[4]["adjusted_p_value"] == pytest.approx(0.90, abs=1e-10)

    def test_correct_fdr_no_rejections(self):
        """correct(method='fdr') with no p-values below threshold."""
        rules = self.make_rules_with_pvalues([0.02, 0.1, 0.3])
        result = MultiTestingCorrector.correct(rules, method="fdr")
        assert all(not r["passes_correction"] for r in result)

    def test_correct_benjamini_hochberg_alias(self):
        """correct(method='benjamini_hochberg') works as alias for fdr."""
        rules = self.make_rules_with_pvalues([0.01, 0.9])
        result = MultiTestingCorrector.correct(
            rules, method="benjamini_hochberg",
        )
        assert result[0]["passes_correction"] is True
        assert result[1]["passes_correction"] is False

    # --- Deflated Sharpe via correct() ---

    def test_correct_deflated_sharpe(self):
        """correct(method='deflated_sharpe') enriches with DSR."""
        rules = self.make_rules_with_sharpes([0.5, 1.0, 2.0])
        result = MultiTestingCorrector.correct(
            rules, method="deflated_sharpe", N=100, m=10,
        )
        assert len(result) == 3
        for r in result:
            assert "adjusted_p_value" in r
            assert "passes_correction" in r

        # All DSR values > 0 for positive Sharpe
        for r in result:
            assert r["adjusted_p_value"] is not None
            assert r["adjusted_p_value"] > 0
            assert r["passes_correction"] is True

    def test_correct_deflated_sharpe_negative(self):
        """correct(deflated_sharpe) with negative Sharpe -> fails."""
        rules = self.make_rules_with_sharpes([-0.5, 0.0, 0.5])
        result = MultiTestingCorrector.correct(
            rules, method="deflated_sharpe", N=100, m=10,
        )
        # Negative DSR -> fails, zero DSR -> fails, positive DSR -> passes
        assert result[0]["passes_correction"] is False
        # DSR = 0 * factor = 0, and passes_correction requires > 0
        assert result[1]["passes_correction"] is False
        assert result[2]["passes_correction"] is True

    def test_correct_deflated_sharpe_missing_N_m(self):
        """correct(deflated_sharpe) without N/m raises ValueError."""
        rules = self.make_rules_with_sharpes([0.5, 1.0])
        with pytest.raises(ValueError, match="N.*observations.*m.*trials"):
            MultiTestingCorrector.correct(rules, method="deflated_sharpe")

    # --- Edge cases ---

    def test_correct_empty_rules(self):
        """correct() with empty rules returns empty list."""
        result = MultiTestingCorrector.correct([], method="fdr")
        assert result == []

    def test_correct_missing_p_value_raises(self):
        """correct() with missing p_value raises ValueError."""
        rules = [{"rule_id": "rule_0"}]  # no p_value
        with pytest.raises(ValueError, match="missing required 'p_value'"):
            MultiTestingCorrector.correct(rules, method="bonferroni")

    def test_correct_missing_sharpe_raises(self):
        """correct(deflated_sharpe) with missing sharpe_ratio raises."""
        rules = [{"rule_id": "rule_0"}]  # no sharpe_ratio
        with pytest.raises(ValueError, match="missing required 'sharpe_ratio'"):
            MultiTestingCorrector.correct(
                rules, method="deflated_sharpe", N=100, m=10,
            )

    def test_correct_invalid_method(self):
        """correct() with unknown method raises ValueError."""
        rules = self.make_rules_with_pvalues([0.01])
        with pytest.raises(ValueError, match="Unknown correction method"):
            MultiTestingCorrector.correct(rules, method="invalid")

    def test_correct_original_rules_unchanged(self):
        """correct() does not mutate the input list or dicts."""
        rules = self.make_rules_with_pvalues([0.01, 0.5])
        original_ids = [r["rule_id"] for r in rules]
        result = MultiTestingCorrector.correct(rules, method="bonferroni")
        # Original rules should not have enriched fields
        for r in rules:
            assert "adjusted_p_value" not in r
            assert "passes_correction" not in r
        # Original rule IDs unchanged
        assert [r["rule_id"] for r in rules] == original_ids
        # Result should have enriched fields
        for r in result:
            assert "adjusted_p_value" in r
            assert "passes_correction" in r

    def test_correct_different_q_value(self):
        """correct(fdr) respects custom q value."""
        # With q=0.01, only very small p-values are rejected
        rules = self.make_rules_with_pvalues([0.001, 0.02, 0.03])
        result = MultiTestingCorrector.correct(rules, method="fdr", q=0.01)
        # m=3, q=0.01
        # Sorted: 0.001(0), 0.02(1), 0.03(2)
        # Rank 1: threshold=0.0033, 0.001 <= 0.0033 -> reject
        # Rank 2: threshold=0.0067, 0.02  > 0.0067 -> stop
        assert result[0]["passes_correction"] is True
        assert result[1]["passes_correction"] is False
        assert result[2]["passes_correction"] is False
