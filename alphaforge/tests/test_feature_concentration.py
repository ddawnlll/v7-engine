"""Test feature concentration computation and G5 gate integration.

P0.9F: Tests compute_feature_concentration (HHI math, edge cases)
and _gate_g5's feature-dominance check.
"""

import pytest
import numpy as np

from alphaforge.reports.stability import compute_feature_concentration
from alphaforge.handoff.builders import _gate_g5


class TestComputeFeatureConcentration:
    """Unit tests for compute_feature_concentration HHI math."""

    def test_empty_dict(self):
        result = compute_feature_concentration({})
        assert result["num_features"] == 0
        assert result["top_feature"] == "NONE"

    def test_equal_distribution(self):
        """10 features with equal importance."""
        imp = {f"feat_{i}": 1.0 for i in range(10)}
        result = compute_feature_concentration(imp)
        assert result["num_features"] == 10
        assert result["top_feature_share"] == pytest.approx(0.1)
        # HHI for 10 equal shares: 10 * (0.1)^2 = 0.1
        assert result["feature_concentration_hhi"] == pytest.approx(0.1)

    def test_single_dominant_feature(self):
        """1 feature with 97% importance."""
        imp = {"dominator": 97.0}
        for i in range(9):
            imp[f"other_{i}"] = 1.0 / (i + 1)
        result = compute_feature_concentration(imp)
        assert result["num_features"] == 10
        assert result["top_feature"] == "dominator"
        assert result["top_feature_share"] > 0.95
        assert result["feature_concentration_hhi"] > 0.9

    def test_perfect_concentration(self):
        """Single feature with 100% importance."""
        imp = {"only_one": 1.0}
        result = compute_feature_concentration(imp)
        assert result["num_features"] == 1
        assert result["top_feature"] == "only_one"
        assert result["top_feature_share"] == pytest.approx(1.0)
        assert result["feature_concentration_hhi"] == pytest.approx(1.0)
        assert result["top3_features"] == ["only_one"]

    def test_zero_total_importance(self):
        """All features have zero importance."""
        imp = {"a": 0.0, "b": 0.0}
        result = compute_feature_concentration(imp)
        assert result["num_features"] == 2
        assert result["top_feature"] == "NONE"
        assert result["top_feature_share"] == 0.0

    def test_top3_extraction(self):
        """Top-3 features and their combined share."""
        imp = {"a": 50.0, "b": 30.0, "c": 15.0, "d": 5.0}
        result = compute_feature_concentration(imp)
        assert result["top3_features"] == ["a", "b", "c"]
        assert result["top3_share"] == pytest.approx(0.95)  # (50+30+15)/100

    def test_hhi_math(self):
        """Verify HHI = sum of squared shares."""
        imp = {"x": 0.6, "y": 0.3, "z": 0.1}
        result = compute_feature_concentration(imp)
        # shares: 0.6, 0.3, 0.1 → HHI = 0.36 + 0.09 + 0.01 = 0.46
        assert result["feature_concentration_hhi"] == pytest.approx(0.46)

    def test_per_feature_shares(self):
        imp = {"a": 2.0, "b": 2.0}
        result = compute_feature_concentration(imp)
        assert result["per_feature_shares"]["a"] == pytest.approx(0.5)
        assert result["per_feature_shares"]["b"] == pytest.approx(0.5)


class TestGateG5FeatureConcentration:
    """Tests for _gate_g5 feature dominance check."""

    def _make_mrr(self, symbols=None, top_share=0.0):
        if symbols is None:
            symbols = ["BTCUSDT", "ETHUSDT"]
        return {
            "report_id": "test-g5-001",
            "data_scope": {"symbols": symbols},
            "feature_concentration": {
                "num_features": 10,
                "top_feature": "dominator" if top_share > 0.5 else "some_feat",
                "top_feature_share": top_share,
                "feature_concentration_hhi": top_share ** 2,
            },
        }

    def test_pass_low_feature_concentration(self):
        """Top feature share below threshold → PASS."""
        _, status = _gate_g5(self._make_mrr(top_share=0.3))
        assert status == "PASS"

    def test_pending_extreme_feature_dominance(self):
        """97% dominant feature → PENDING."""
        _, status = _gate_g5(self._make_mrr(top_share=0.97))
        assert status == "PENDING"

    def test_pending_single_symbol(self):
        """n_symbols < 2 → PENDING regardless of feature conc."""
        _, status = _gate_g5(self._make_mrr(symbols=["BTCUSDT"], top_share=0.1))
        assert status == "PENDING"

    def test_pass_no_feature_data(self):
        """No feature_concentration in report → PASS as long as symbols >= 2."""
        report = {
            "report_id": "test-g5-002",
            "data_scope": {"symbols": ["BTCUSDT", "ETHUSDT"]},
        }
        _, status = _gate_g5(report)
        assert status == "PASS"

    def test_evidence_includes_feature_info(self):
        """Evidence string must reference feature concentration."""
        evidence, _ = _gate_g5(self._make_mrr(top_share=0.3))
        assert "feature_concentration" in evidence
        assert "top=" in evidence
        assert "share=" in evidence
