"""RegimeEvaluator tests — per-regime aggregation, flag detection, edge cases.

Tests the RegimeEvaluator class from alphaforge.validation.regime_eval:
- All four regimes correctly aggregate expectancy_r, win_rate, trade_count
- Catastrophic loss in single regime pattern detection
- Edge-only-in-rare-regime and rare-regime-untradeable flags
- Empty/missing data handling
- NaN/Inf filtering
- Constructor validation
- Deterministic output

WS-06-NO-FAKE-TESTS: Negative tests only — verify correctness of aggregation
and flag logic. No profitability claims, no model training.
"""

from __future__ import annotations

import math
import pytest

from alphaforge.validation.contracts import RegimeLabel
from alphaforge.validation.regime_eval import (
    CATASTROPHIC_LOSS_EXPECTANCY_R_THRESHOLD,
    MIN_TOTAL_FOLDS_FOR_FLAGS,
    RARE_REGIME_FOLD_FRACTION,
    STABILITY_REGIME_LABELS,
    RegimeEvaluator,
    _detect_catastrophic_loss,
    _detect_edge_in_rare_regime,
    _safe_mean,
    compute_symbol_regime_matrix,
)


# =========================================================================
# Helpers
# =========================================================================


def _all_regime_map() -> dict:
    """6 folds spread across all 4 regimes."""
    return {
        0: RegimeLabel.TREND_UP,
        1: RegimeLabel.TREND_UP,
        2: RegimeLabel.TREND_DOWN,
        3: RegimeLabel.RANGE,
        4: RegimeLabel.RANGE,
        5: RegimeLabel.TRANSITION,
    }


def _balanced_metrics() -> tuple:
    """Balanced metrics for 6 folds — all regimes have positive edge."""
    exp = {
        0: 0.4, 1: 0.5,   # TREND_UP
        2: 0.3,            # TREND_DOWN
        3: 0.2, 4: 0.25,  # RANGE
        5: 0.15,           # TRANSITION
    }
    wr = {
        0: 0.55, 1: 0.58,
        2: 0.52,
        3: 0.50, 4: 0.51,
        5: 0.48,
    }
    tc = {
        0: 100, 1: 110,
        2: 95,
        3: 80, 4: 85,
        5: 70,
    }
    return exp, wr, tc


# =========================================================================
# _safe_mean tests
# =========================================================================


class TestSafeMean:
    """Unit tests for the _safe_mean helper."""

    def test_normal_values(self):
        """_safe_mean computes correct average for normal values."""
        result = _safe_mean([1.0, 2.0, 3.0])
        assert result == pytest.approx(2.0)

    def test_empty_list_returns_none(self):
        """_safe_mean returns None for empty list."""
        assert _safe_mean([]) is None

    def test_filters_nan(self):
        """_safe_mean excludes NaN values."""
        result = _safe_mean([1.0, float("nan"), 3.0])
        assert result == pytest.approx(2.0)

    def test_filters_inf(self):
        """_safe_mean excludes Inf values."""
        result = _safe_mean([1.0, float("inf"), 3.0])
        assert result == pytest.approx(2.0)

    def test_all_nan_returns_none(self):
        """_safe_mean returns None when all values are NaN."""
        result = _safe_mean([float("nan"), float("nan")])
        assert result is None

    def test_single_value(self):
        """_safe_mean with single value returns that value."""
        assert _safe_mean([42.0]) == pytest.approx(42.0)

    def test_negative_values(self):
        """_safe_mean handles negative values correctly."""
        result = _safe_mean([-1.0, -2.0, -3.0])
        assert result == pytest.approx(-2.0)


# =========================================================================
# RegimeEvaluator constructor tests
# =========================================================================


class TestRegimeEvaluatorConstructor:
    """Constructor validation tests."""

    def test_accepts_valid_mapping(self):
        """Constructor accepts Dict[int, RegimeLabel]."""
        e = RegimeEvaluator({0: RegimeLabel.TREND_UP})
        assert isinstance(e, RegimeEvaluator)

    def test_rejects_non_dict(self):
        """Constructor raises TypeError for non-dict input."""
        with pytest.raises(TypeError, match="must be a dict"):
            RegimeEvaluator("not a dict")  # type: ignore[arg-type]

    def test_accepts_empty_dict(self):
        """Constructor accepts empty dict."""
        e = RegimeEvaluator({})
        assert isinstance(e, RegimeEvaluator)

    def test_fold_regime_map_property_returns_copy(self):
        """fold_regime_map property returns a copy, not the original."""
        original = {0: RegimeLabel.TREND_UP}
        e = RegimeEvaluator(original)
        copy1 = e.fold_regime_map
        copy2 = e.fold_regime_map
        assert copy1 == original
        assert copy2 == original
        # Mutating the returned dict does not affect the evaluator
        copy1[99] = RegimeLabel.RANGE
        assert e.fold_regime_map == original


# =========================================================================
# evaluate() tests — aggregation correctness
# =========================================================================


class TestEvaluateAggregation:
    """Tests for per-regime metric aggregation."""

    def test_all_four_regimes_aggregated(self):
        """All four regimes correctly aggregate expectancy_r, win_rate, trade_count."""
        e = RegimeEvaluator(_all_regime_map())
        exp, wr, tc = _balanced_metrics()
        result = e.evaluate(exp, wr, tc)

        regimes = result["regimes"]

        # TREND_UP: folds 0,1
        assert regimes["TREND_UP"]["expectancy_r"] == pytest.approx((0.4 + 0.5) / 2)
        assert regimes["TREND_UP"]["win_rate"] == pytest.approx((0.55 + 0.58) / 2)
        assert regimes["TREND_UP"]["trade_count"] == 210
        assert regimes["TREND_UP"]["fold_count"] == 2

        # TREND_DOWN: fold 2
        assert regimes["TREND_DOWN"]["expectancy_r"] == pytest.approx(0.3)
        assert regimes["TREND_DOWN"]["win_rate"] == pytest.approx(0.52)
        assert regimes["TREND_DOWN"]["trade_count"] == 95
        assert regimes["TREND_DOWN"]["fold_count"] == 1

        # RANGE: folds 3,4
        assert regimes["RANGE"]["expectancy_r"] == pytest.approx((0.2 + 0.25) / 2)
        assert regimes["RANGE"]["win_rate"] == pytest.approx((0.50 + 0.51) / 2)
        assert regimes["RANGE"]["trade_count"] == 165
        assert regimes["RANGE"]["fold_count"] == 2

        # TRANSITION: fold 5
        assert regimes["TRANSITION"]["expectancy_r"] == pytest.approx(0.15)
        assert regimes["TRANSITION"]["win_rate"] == pytest.approx(0.48)
        assert regimes["TRANSITION"]["trade_count"] == 70
        assert regimes["TRANSITION"]["fold_count"] == 1

    def test_total_folds_evaluated(self):
        """total_folds_evaluated matches the intersection of fold IDs."""
        e = RegimeEvaluator({0: RegimeLabel.TREND_UP, 1: RegimeLabel.TREND_DOWN, 2: RegimeLabel.RANGE})
        exp = {0: 0.1, 1: 0.2, 2: 0.3}
        wr = {0: 0.5, 1: 0.5, 2: 0.5}
        tc = {0: 10, 1: 20, 2: 30}
        result = e.evaluate(exp, wr, tc)
        assert result["total_folds_evaluated"] == 3

    def test_folds_per_regime_counts(self):
        """folds_per_regime correctly counts fold distribution."""
        e = RegimeEvaluator(_all_regime_map())
        exp, wr, tc = _balanced_metrics()
        result = e.evaluate(exp, wr, tc)

        fpr = result["folds_per_regime"]
        assert fpr["TREND_UP"] == 2
        assert fpr["TREND_DOWN"] == 1
        assert fpr["RANGE"] == 2
        assert fpr["TRANSITION"] == 1

    def test_unpopulated_regime_has_null_metrics(self):
        """A regime with no folds has None for expectancy_r and win_rate."""
        e = RegimeEvaluator({0: RegimeLabel.TREND_UP, 1: RegimeLabel.TREND_UP})
        exp = {0: 0.1, 1: 0.2}
        wr = {0: 0.5, 1: 0.5}
        tc = {0: 10, 1: 20}
        result = e.evaluate(exp, wr, tc)

        for reg_name in ["TREND_DOWN", "RANGE", "TRANSITION"]:
            assert result["regimes"][reg_name]["expectancy_r"] is None
            assert result["regimes"][reg_name]["win_rate"] is None
            assert result["regimes"][reg_name]["trade_count"] == 0
            assert result["regimes"][reg_name]["fold_count"] == 0


# =========================================================================
# evaluate() tests — edge cases / missing data
# =========================================================================


class TestEvaluateEdgeCases:
    """Edge case tests for evaluate()."""

    def test_empty_input_returns_empty_breakdown(self):
        """Empty fold sets produce an empty breakdown with no flags."""
        e = RegimeEvaluator({0: RegimeLabel.TREND_UP})
        result = e.evaluate({}, {}, {})
        assert result["total_folds_evaluated"] == 0
        assert result["catastrophic_loss_in_single_regime"] is False
        assert result["edge_only_in_rare_regime"] is False
        assert all(
            result["regimes"][r.value]["expectancy_r"] is None
            for r in RegimeLabel
        )

    def test_empty_regime_map(self):
        """Evaluator with empty regime map handles metrics gracefully."""
        e = RegimeEvaluator({})
        exp = {0: 0.1}
        wr = {0: 0.5}
        tc = {0: 10}
        result = e.evaluate(exp, wr, tc)
        assert result["total_folds_evaluated"] == 0

    def test_fold_in_regime_map_but_not_metrics(self):
        """Fold present in regime_map but missing from one metric dict is skipped."""
        e = RegimeEvaluator({0: RegimeLabel.TREND_UP, 1: RegimeLabel.TREND_UP})
        exp = {0: 0.3}  # fold 1 missing
        wr = {0: 0.5, 1: 0.6}
        tc = {0: 10, 1: 20}
        result = e.evaluate(exp, wr, tc)
        # Only fold 0 is in the intersection
        assert result["total_folds_evaluated"] == 1

    def test_fold_in_metrics_but_not_regime_map(self):
        """Fold in metrics but not in regime_map is skipped."""
        e = RegimeEvaluator({0: RegimeLabel.TREND_UP})
        exp = {0: 0.3, 99: 0.9}  # fold 99 not in regime map
        wr = {0: 0.5, 99: 0.8}
        tc = {0: 10, 99: 50}
        result = e.evaluate(exp, wr, tc)
        assert result["total_folds_evaluated"] == 1

    def test_zero_trade_count_aggregates_correctly(self):
        """Zero trade counts are correctly summed."""
        e = RegimeEvaluator({0: RegimeLabel.TREND_UP, 1: RegimeLabel.TREND_UP})
        exp = {0: 0.0, 1: 0.0}
        wr = {0: 0.0, 1: 0.0}
        tc = {0: 0, 1: 0}
        result = e.evaluate(exp, wr, tc)
        assert result["regimes"]["TREND_UP"]["trade_count"] == 0
        assert result["regimes"]["TREND_UP"]["expectancy_r"] == 0.0

    def test_nan_in_metrics_filtered(self):
        """NaN values in expectancy_r are filtered from aggregation."""
        e = RegimeEvaluator({0: RegimeLabel.TREND_UP, 1: RegimeLabel.TREND_UP})
        exp = {0: 0.3, 1: float("nan")}
        wr = {0: 0.5, 1: 0.5}
        tc = {0: 10, 1: 20}
        result = e.evaluate(exp, wr, tc)
        # NaN filtered; only 0.3 contributes
        assert result["regimes"]["TREND_UP"]["expectancy_r"] == pytest.approx(0.3)

    def test_all_nan_in_regime_yields_null(self):
        """When all values in a regime are NaN, expectancy_r is None."""
        e = RegimeEvaluator({0: RegimeLabel.TREND_UP, 1: RegimeLabel.TREND_UP})
        exp = {0: float("nan"), 1: float("nan")}
        wr = {0: 0.5, 1: 0.5}
        tc = {0: 10, 1: 20}
        result = e.evaluate(exp, wr, tc)
        assert result["regimes"]["TREND_UP"]["expectancy_r"] is None


# =========================================================================
# Catastrophic loss detection tests
# =========================================================================


class TestCatastrophicLossDetection:
    """Tests for catastrophic loss in single regime detection."""

    def test_detects_catastrophic_loss(self):
        """One regime deeply negative, others positive -> flag fires."""
        regimes = {
            "TREND_UP":    {"expectancy_r": 0.4, "fold_count": 3},
            "TREND_DOWN":  {"expectancy_r": -1.2, "fold_count": 2},
            "RANGE":       {"expectancy_r": 0.2, "fold_count": 3},
            "TRANSITION":  {"expectancy_r": 0.1, "fold_count": 1},
        }
        flag, reg = _detect_catastrophic_loss(regimes, total_folds=9)
        assert flag is True
        assert reg == "TREND_DOWN"

    def test_no_catastrophic_loss_when_all_similar(self):
        """When all regimes are above threshold, no flag."""
        regimes = {
            "TREND_UP":   {"expectancy_r": 0.4, "fold_count": 3},
            "TREND_DOWN": {"expectancy_r": 0.1, "fold_count": 2},
            "RANGE":      {"expectancy_r": 0.2, "fold_count": 3},
            "TRANSITION": {"expectancy_r": 0.05, "fold_count": 1},
        }
        flag, reg = _detect_catastrophic_loss(regimes, total_folds=9)
        assert flag is False
        assert reg is None

    def test_no_flag_when_all_regimes_bad(self):
        """When ALL regimes are below threshold, no single-regime flag."""
        regimes = {
            "TREND_UP":   {"expectancy_r": -1.0, "fold_count": 3},
            "TREND_DOWN": {"expectancy_r": -1.5, "fold_count": 3},
            "RANGE":      {"expectancy_r": -0.8, "fold_count": 2},
        }
        flag, reg = _detect_catastrophic_loss(regimes, total_folds=8)
        assert flag is False

    def test_no_flag_with_insufficient_folds(self):
        """Catastrophic loss requires MIN_TOTAL_FOLDS_FOR_FLAGS."""
        regimes = {
            "TREND_UP":   {"expectancy_r": 0.3, "fold_count": 1},
            "TREND_DOWN": {"expectancy_r": -1.0, "fold_count": 2},
        }
        flag, reg = _detect_catastrophic_loss(regimes, total_folds=3)
        assert flag is False

    def test_no_flag_with_single_regime(self):
        """Need at least 2 regimes with data to compare."""
        regimes = {
            "TREND_UP":   {"expectancy_r": -1.0, "fold_count": 5},
            "TREND_DOWN": {"expectancy_r": None, "fold_count": 0},
            "RANGE":      {"expectancy_r": None, "fold_count": 0},
            "TRANSITION": {"expectancy_r": None, "fold_count": 0},
        }
        flag, reg = _detect_catastrophic_loss(regimes, total_folds=5)
        assert flag is False

    def test_catastrophic_loss_exactly_at_threshold(self):
        """Expectancy_r exactly at threshold: not flagged (<, not <=)."""
        regimes = {
            "TREND_UP":   {"expectancy_r": 0.3, "fold_count": 3},
            "TREND_DOWN": {"expectancy_r": CATASTROPHIC_LOSS_EXPECTANCY_R_THRESHOLD, "fold_count": 2},
            "RANGE":      {"expectancy_r": 0.2, "fold_count": 2},
        }
        flag, reg = _detect_catastrophic_loss(regimes, total_folds=7)
        assert flag is False  # -0.5 is NOT < -0.5

    def test_catastrophic_loss_just_below_threshold(self):
        """Expectancy_r just below threshold: flagged."""
        regimes = {
            "TREND_UP":   {"expectancy_r": 0.3, "fold_count": 3},
            "TREND_DOWN": {
                "expectancy_r": CATASTROPHIC_LOSS_EXPECTANCY_R_THRESHOLD - 0.001,
                "fold_count": 2,
            },
            "RANGE": {"expectancy_r": 0.2, "fold_count": 3},
        }
        flag, reg = _detect_catastrophic_loss(regimes, total_folds=8)
        assert flag is True
        assert reg == "TREND_DOWN"


# =========================================================================
# Edge in rare regime detection tests
# =========================================================================


class TestEdgeInRareRegimeDetection:
    """Tests for edge-only-in-rare-regime and rare-regime-untradeable flags."""

    def test_edge_only_in_rare_regime(self):
        """Positive edge exists only in regimes with <= 15% of folds."""
        # 20 total folds: rare threshold = 3 (15% of 20)
        # TREND_UP: 2 folds (rare), positive edge
        # Others: lots of folds (not rare), non-positive edge
        regimes = {
            "TREND_UP":   {"expectancy_r": 0.5, "fold_count": 2},
            "TREND_DOWN": {"expectancy_r": -0.1, "fold_count": 8},
            "RANGE":      {"expectancy_r": -0.05, "fold_count": 7},
            "TRANSITION": {"expectancy_r": 0.0, "fold_count": 3},
        }
        edge_rare, rare_untradeable = _detect_edge_in_rare_regime(regimes, total_folds=20)
        assert edge_rare is True
        # TREND_UP has positive edge but is rare, so rare_untradeable is False
        assert rare_untradeable is True  # TREND_DOWN is not rare but has negative edge; RANGE has negative; TRANSITION has zero

        # Actually let me re-check: rare_regimes are those with fold_count <= rare_threshold (3)
        # TREND_UP: fold_count=2 <= 3 -> rare, positive edge
        # TREND_DOWN: fold_count=8 > 3 -> not rare, negative
        # RANGE: fold_count=7 > 3 -> not rare, negative
        # TRANSITION: fold_count=3 <= 3 -> rare, edge=0 (not positive)
        # Positive regimes: TREND_UP
        # Non-positive regimes: TREND_DOWN, RANGE, TRANSITION
        # All positive regimes (TREND_UP) are in rare_regimes -> edge_only_in_rare = True
        # Rare regimes with negative/zero edge: TRANSITION -> rare_untradeable = True
        assert edge_rare is True
        assert rare_untradeable is True

    def test_no_edge_only_in_rare_when_common_regime_has_edge(self):
        """When a non-rare regime has positive edge, flag is False."""
        regimes = {
            "TREND_UP":   {"expectancy_r": 0.5, "fold_count": 2},   # rare
            "TREND_DOWN": {"expectancy_r": 0.3, "fold_count": 8},   # NOT rare, positive
            "RANGE":      {"expectancy_r": -0.05, "fold_count": 7},
            "TRANSITION": {"expectancy_r": 0.0, "fold_count": 3},
        }
        edge_rare, _ = _detect_edge_in_rare_regime(regimes, total_folds=20)
        assert edge_rare is False

    def test_no_flag_when_all_regimes_have_edge(self):
        """When all regimes have positive edge, edge_only_in_rare is False."""
        regimes = {
            "TREND_UP":   {"expectancy_r": 0.5, "fold_count": 2},
            "TREND_DOWN": {"expectancy_r": 0.3, "fold_count": 8},
            "RANGE":      {"expectancy_r": 0.1, "fold_count": 7},
            "TRANSITION": {"expectancy_r": 0.05, "fold_count": 3},
        }
        edge_rare, _ = _detect_edge_in_rare_regime(regimes, total_folds=20)
        assert edge_rare is False

    def test_no_flag_with_insufficient_folds(self):
        """Edge-in-rare requires MIN_TOTAL_FOLDS_FOR_FLAGS."""
        regimes = {
            "TREND_UP":   {"expectancy_r": 0.5, "fold_count": 1},
            "TREND_DOWN": {"expectancy_r": -0.1, "fold_count": 2},
        }
        edge_rare, rare_untradeable = _detect_edge_in_rare_regime(regimes, total_folds=3)
        assert edge_rare is False
        assert rare_untradeable is False

    def test_no_flag_with_single_regime(self):
        """Need at least 2 regimes with data."""
        regimes = {
            "TREND_UP":   {"expectancy_r": 0.5, "fold_count": 10},
            "TREND_DOWN": {"expectancy_r": None, "fold_count": 0},
            "RANGE":      {"expectancy_r": None, "fold_count": 0},
            "TRANSITION": {"expectancy_r": None, "fold_count": 0},
        }
        edge_rare, rare_untradeable = _detect_edge_in_rare_regime(regimes, total_folds=10)
        assert edge_rare is False
        assert rare_untradeable is False

    def test_rare_regime_untradeable(self):
        """Rare regime with non-positive edge triggers rare_regime_untradeable."""
        regimes = {
            "TREND_UP":   {"expectancy_r": 0.5, "fold_count": 8},
            "TREND_DOWN": {"expectancy_r": 0.3, "fold_count": 7},
            "RANGE":      {"expectancy_r": 0.1, "fold_count": 3},    # rare, positive
            "TRANSITION": {"expectancy_r": -0.2, "fold_count": 2},   # rare, negative
        }
        edge_rare, rare_untradeable = _detect_edge_in_rare_regime(regimes, total_folds=20)
        # All positive regimes: TREND_UP (not rare), TREND_DOWN (not rare), RANGE (rare)
        # Not all positive are rare -> edge_only_in_rare = False
        # TRANSITION is rare and has negative edge -> rare_untradeable = True
        assert edge_rare is False
        assert rare_untradeable is True


# =========================================================================
# End-to-end flag integration tests
# =========================================================================


class TestFlagIntegration:
    """Integration tests verifying flags flow through evaluate() correctly."""

    def test_catastrophic_loss_flag_in_evaluate(self):
        """Catastrophic loss flows correctly through evaluate()."""
        e = RegimeEvaluator({
            0: RegimeLabel.TREND_UP,
            1: RegimeLabel.TREND_UP,
            2: RegimeLabel.TREND_DOWN,
            3: RegimeLabel.TREND_DOWN,
            4: RegimeLabel.RANGE,
            5: RegimeLabel.RANGE,
            6: RegimeLabel.TRANSITION,
            7: RegimeLabel.TRANSITION,
        })
        exp = {
            0: 0.4, 1: 0.5,    # TREND_UP: mean 0.45
            2: -1.2, 3: -1.0,  # TREND_DOWN: mean -1.1 (catastrophic)
            4: 0.2, 5: 0.25,   # RANGE: mean 0.225
            6: 0.1, 7: 0.05,   # TRANSITION: mean 0.075
        }
        wr = {i: 0.5 for i in range(8)}
        tc = {i: 100 for i in range(8)}

        result = e.evaluate(exp, wr, tc)
        assert result["catastrophic_loss_in_single_regime"] is True
        assert result["catastrophic_loss_regime"] == "TREND_DOWN"
        assert result["total_folds_evaluated"] == 8

    def test_edge_only_in_rare_flag_in_evaluate(self):
        """Edge only in rare regime flows through evaluate()."""
        # 20 folds: TREND_UP has 3 folds (rare at 15% of 20=3), positive edge
        # TREND_DOWN has 17 folds, negative edge
        regime_map = {}
        exp = {}
        wr = {}
        tc = {}
        fid = 0
        for _ in range(3):
            regime_map[fid] = RegimeLabel.TREND_UP
            exp[fid] = 0.5
            wr[fid] = 0.55
            tc[fid] = 50
            fid += 1
        for _ in range(17):
            regime_map[fid] = RegimeLabel.TREND_DOWN
            exp[fid] = -0.1
            wr[fid] = 0.48
            tc[fid] = 50
            fid += 1

        e = RegimeEvaluator(regime_map)
        result = e.evaluate(exp, wr, tc)
        assert result["edge_only_in_rare_regime"] is True

    def test_no_false_positive_on_balanced_data(self):
        """Balanced data across all regimes produces no flags."""
        e = RegimeEvaluator(_all_regime_map())
        exp, wr, tc = _balanced_metrics()
        result = e.evaluate(exp, wr, tc)
        assert result["catastrophic_loss_in_single_regime"] is False
        assert result["edge_only_in_rare_regime"] is False
        assert result["rare_regime_untradeable"] is False


# =========================================================================
# Determinism and structural tests
# =========================================================================


class TestDeterminismAndStructure:
    """Tests for deterministic output and structure."""

    def test_output_keys_present(self):
        """evaluate() returns all required keys."""
        e = RegimeEvaluator({0: RegimeLabel.TREND_UP})
        exp = {0: 0.1}
        wr = {0: 0.5}
        tc = {0: 10}
        result = e.evaluate(exp, wr, tc)

        required_keys = {
            "regimes", "edge_only_in_rare_regime", "rare_regime_untradeable",
            "catastrophic_loss_in_single_regime", "catastrophic_loss_regime",
            "total_folds_evaluated", "folds_per_regime",
        }
        assert set(result.keys()) == required_keys

    def test_all_regime_names_in_regimes_dict(self):
        """regimes dict contains all four canonical regime names."""
        e = RegimeEvaluator({0: RegimeLabel.TREND_UP})
        result = e.evaluate({0: 0.1}, {0: 0.5}, {0: 10})
        for r in RegimeLabel:
            assert r.value in result["regimes"], f"Missing {r.value}"

    def test_deterministic_output(self):
        """Same inputs produce identical outputs."""
        e = RegimeEvaluator(_all_regime_map())
        exp, wr, tc = _balanced_metrics()

        result1 = e.evaluate(exp, wr, tc)
        result2 = e.evaluate(exp, wr, tc)
        assert result1 == result2

    def test_regime_metrics_have_required_keys(self):
        """Per-regime dicts contain all required metric keys."""
        e = RegimeEvaluator({0: RegimeLabel.TREND_UP})
        result = e.evaluate({0: 0.1}, {0: 0.5}, {0: 10})
        for reg_data in result["regimes"].values():
            assert set(reg_data.keys()) == {
                "expectancy_r", "win_rate", "trade_count", "fold_count"
            }


# =========================================================================
# Symbol x Regime stability matrix tests
# =========================================================================


class TestSymbolRegimeMatrix:
    """Tests for compute_symbol_regime_matrix()."""

    def test_single_symbol_all_uptrend(self):
        """Single symbol, all TREND_UP produces stable matrix."""
        labels = {"BTC": ["TREND_UP"] * 50}
        result = compute_symbol_regime_matrix(labels)

        assert result["num_symbols"] == 1
        assert result["matrix"]["BTC"]["TREND_UP"] == 1.0
        assert result["matrix"]["BTC"]["RANGE"] == 0.0
        assert result["stability_scores"]["BTC"] == 1.0
        assert result["dominant_regime"]["BTC"] == "TREND_UP"
        assert result["avg_stability"] == 1.0

    def test_two_symbols_different_distributions(self):
        """Two symbols with different regime mixes produce different matrices."""
        labels = {
            "BTC": ["TREND_UP"] * 30 + ["RANGE"] * 20,
            "ETH": ["TREND_DOWN"] * 25 + ["TRANSITION"] * 25,
        }
        result = compute_symbol_regime_matrix(labels)

        assert result["num_symbols"] == 2
        assert result["matrix"]["BTC"]["TREND_UP"] == pytest.approx(0.6)
        assert result["matrix"]["BTC"]["RANGE"] == pytest.approx(0.4)
        assert result["matrix"]["ETH"]["TREND_DOWN"] == pytest.approx(0.5)
        assert result["matrix"]["ETH"]["TRANSITION"] == pytest.approx(0.5)

    def test_unknown_regime_label(self):
        """Labels not in the standard set go to OTHER."""
        labels = {"TEST": ["TREND_UP", "MYSTERY_REGIME", "RANGE"]}
        result = compute_symbol_regime_matrix(labels)
        assert result["matrix"]["TEST"]["TREND_UP"] == pytest.approx(1 / 3)
        assert result["matrix"]["TEST"]["OTHER"] == pytest.approx(1 / 3)

    def test_empty_input(self):
        """Empty dict returns empty matrix with zero stats."""
        result = compute_symbol_regime_matrix({})
        assert result["num_symbols"] == 0
        assert result["matrix"] == {}
        assert result["avg_stability"] == 0.0

    def test_empty_symbol_list(self):
        """Symbol with empty label list returns zero fractions."""
        labels = {"BTC": []}
        result = compute_symbol_regime_matrix(labels)
        assert result["matrix"]["BTC"]["TREND_UP"] == 0.0
        assert result["stability_scores"]["BTC"] == 1.0
        assert result["dominant_regime"]["BTC"] == "NONE"

    def test_stability_score_with_transitions(self):
        """Frequent regime transitions produce low stability score."""
        # Alternating regimes = max transitions
        labels = {"BTC": ["TREND_UP", "TREND_DOWN"] * 25}
        result = compute_symbol_regime_matrix(labels)
        # 50 bars, 49 transitions out of 49 max = stability 0.0
        assert result["stability_scores"]["BTC"] == 0.0

    def test_stability_score_partial(self):
        """Partial transitions produce intermediate stability."""
        # 10 TREND_UP, then 10 RANGE = 1 transition out of 19 max
        labels = {"BTC": ["TREND_UP"] * 10 + ["RANGE"] * 10}
        result = compute_symbol_regime_matrix(labels)
        expected = 1.0 - (1 / 19)
        assert result["stability_scores"]["BTC"] == pytest.approx(expected)

    def test_dominant_regime(self):
        """Most frequent regime is correctly identified."""
        labels = {"BTC": ["TREND_UP"] * 40 + ["RANGE"] * 10 + ["TREND_DOWN"] * 5}
        result = compute_symbol_regime_matrix(labels)
        assert result["dominant_regime"]["BTC"] == "TREND_UP"

    def test_cross_symbol_consistency(self):
        """Identically distributed symbols have CV=0."""
        labels = {
            "BTC": ["TREND_UP"] * 25 + ["RANGE"] * 25,
            "ETH": ["TREND_UP"] * 25 + ["RANGE"] * 25,
        }
        result = compute_symbol_regime_matrix(labels)
        # Both have 0.5 TREND_UP, so CV = 0
        assert result["cross_symbol_consistency"]["TREND_UP"] == 0.0
        assert result["cross_symbol_consistency"]["RANGE"] == 0.0

    def test_cross_symbol_consistency_nonzero(self):
        """Different distributions produce nonzero CV."""
        labels = {
            "BTC": ["TREND_UP"] * 50,
            "ETH": ["RANGE"] * 50,
        }
        result = compute_symbol_regime_matrix(labels)
        # One has 1.0 TREND_UP, other has 0.0 -> mean 0.5, std ~0.5, CV=1.0
        assert result["cross_symbol_consistency"]["TREND_UP"] == pytest.approx(1.0)
        assert result["cross_symbol_consistency"]["RANGE"] == pytest.approx(1.0)


# =========================================================================
# No-ML-import scan
# =========================================================================


class TestNoMLImports:
    """Verify zero ML library imports in regime_eval module."""

    def test_no_ml_imports(self):
        """regime_eval.py contains zero xgboost/sklearn/tf/torch imports."""
        forbidden = [
            "xgboost", "XGBClassifier", "XGBRegressor",
            "sklearn", "tensorflow", "torch",
        ]
        import alphaforge.validation.regime_eval as rmod

        for term in forbidden:
            assert not hasattr(rmod, term), (
                f"regime_eval has attribute '{term}'"
            )

    def test_no_fit_call_in_source(self):
        """No 'fit(' call in regime_eval source."""
        import inspect
        import alphaforge.validation.regime_eval as rmod

        src = inspect.getsource(rmod)
        assert "fit(" not in src, "regime_eval contains 'fit('"
