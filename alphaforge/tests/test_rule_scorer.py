"""Tests for RuleScorer — multi-dimensional rule candidate evaluation.

Verifies that:

- Basic metrics (mean, median, positive_rate, lift, profit_factor, sharpe)
  are computed correctly for known inputs.
- symbol_stability produces correct per-symbol and cross-symbol aggregates.
- regime_stability produces correct per-regime and cross-regime aggregates.
- cost_stress correctly penalizes edge under fee multipliers.
- Empty/inactive rules return zero-filled results without crashing.
- Batch scoring (score_batch) produces identical results to single scoring.
- NaN values in target are handled safely.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from alphaforge.mine.rule_scorer import RuleScorer


# =========================================================================
# Deterministic reference data
# =========================================================================

_KNOWN_TARGET = np.array(
    [0.5, 0.3, -0.2, 0.1, -0.4, 0.6, -0.1, 0.2, 0.0, -0.3], dtype=float
)

_KNOWN_MASK = np.array(
    [True, True, True, True, True, True, True, True, True, True], dtype=bool
)

_KNOWN_SYMBOLS = np.array(
    ["BTCUSDT", "BTCUSDT", "BTCUSDT", "ETHUSDT", "ETHUSDT",
     "ETHUSDT", "SOLUSDT", "SOLUSDT", "SOLUSDT", "SOLUSDT"],
    dtype=object,
)

_KNOWN_REGIMES = np.array(
    ["TREND_UP", "TREND_UP", "RANGE", "RANGE", "TREND_DOWN",
     "TREND_DOWN", "TREND_UP", "RANGE", "TREND_DOWN", "TREND_UP"],
    dtype=object,
)

_RULE_DEMO = {"id": "rsi_gt_70", "feature": "rsi", "operator": ">", "threshold": 70}


# =========================================================================
# Helpers
# =========================================================================


def _ref_score(
    rule: dict | None = None, fee_r: float = 0.0
) -> dict:
    """Score the known dataset (all rows selected) — reference result."""
    scorer = RuleScorer()
    return scorer.score(
        rule=rule or _RULE_DEMO,
        masks={"active": _KNOWN_MASK},
        target=_KNOWN_TARGET,
        symbol_map=_KNOWN_SYMBOLS,
        regime_map=_KNOWN_REGIMES,
        fee_r=fee_r,
    )


# =========================================================================
# 1. Known input → expected score
# =========================================================================


class TestKnownInput:
    """Verify all basic metrics against hand-computed values."""

    @pytest.fixture(autouse=True)
    def result(self):
        self.r = _ref_score()

    def test_mean_net_R(self):
        """mean_net_R = 0.5+0.3-0.2+0.1-0.4+0.6-0.1+0.2+0.0-0.3 = 0.70 / 10 = 0.07"""
        assert abs(self.r["mean_net_R"] - 0.07) < 1e-12

    def test_median_net_R(self):
        """Sorted: [-0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.5, 0.6]
           Median of 10 values = avg of 5th (0.0) and 6th (0.1) = 0.05"""
        assert abs(self.r["median_net_R"] - 0.05) < 1e-12

    def test_positive_rate(self):
        """Values > 0: 0.5, 0.3, 0.1, 0.6, 0.2 → 5 / 10 = 0.5"""
        assert abs(self.r["positive_rate"] - 0.5) < 1e-12

    def test_lift_over_base(self):
        """base = mean(target) = 0.07, lift = 0.07 / 0.07 = 1.0"""
        assert abs(self.r["lift_over_base"] - 1.0) < 1e-12

    def test_lift_with_different_base(self):
        """When base_mean_net_R differs, lift reflects relative improvement."""
        scorer = RuleScorer()
        r = scorer.score(
            rule=_RULE_DEMO,
            masks={"active": _KNOWN_MASK},
            target=_KNOWN_TARGET,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
            base_mean_net_R=0.035,  # half of 0.07
            fee_r=0.0,
        )
        assert abs(r["lift_over_base"] - 2.0) < 1e-12

    def test_profit_factor(self):
        """Gains: 0.5+0.3+0.1+0.6+0.2 = 1.7
           Losses: |-0.2-0.4-0.1-0.3| = 1.0
           PF = 1.7 / 1.0 = 1.7"""
        assert abs(self.r["profit_factor"] - 1.7) < 1e-12

    def test_sharpe(self):
        """mean=0.07, std≈0.318, N=10 → 0.07/0.318*√10 ≈ 0.696"""
        assert abs(self.r["sharpe"] - 0.695) < 1e-2

    def test_n_observations(self):
        """All 10 rows active."""
        assert self.r["n_observations"] == 10

    def test_rule_id_in_result(self):
        """Rule id is propagated into the result."""
        assert self.r["rule_id"] == "rsi_gt_70"

    def test_lift_zero_base(self):
        """lift_over_base is 0 when base_mean_net_R is 0."""
        target_zero_mean = np.array([1.0, -1.0, 0.5, -0.5], dtype=float)
        mask = np.ones(4, dtype=bool)
        scorer = RuleScorer()
        r = scorer.score(
            rule=_RULE_DEMO,
            masks={"active": mask},
            target=target_zero_mean,
            symbol_map=np.array(["A", "A", "B", "B"]),
            regime_map=np.array(["X", "Y", "X", "Y"]),
            base_mean_net_R=0.0,
        )
        # mean of active = 0.0, base = 0.0 → lift = 0.0
        assert r["lift_over_base"] == 0.0


# =========================================================================
# 2. symbol_stability verification
# =========================================================================


class TestSymbolStability:
    """Per-symbol and cross-symbol metrics."""

    @pytest.fixture(autouse=True)
    def result(self):
        self.r = _ref_score()

    def test_per_symbol_three_symbols(self):
        """Three distinct symbols should appear."""
        assert set(self.r["symbol_stability"]["per_symbol"].keys()) == {
            "BTCUSDT", "ETHUSDT", "SOLUSDT"
        }

    def test_btc_mean(self):
        """BTCUSDT values: [0.5, 0.3, -0.2] → mean = 0.60/3 = 0.20"""
        btc = self.r["symbol_stability"]["per_symbol"]["BTCUSDT"]
        assert abs(btc["mean_net_R"] - 0.20) < 1e-12
        assert btc["count"] == 3

    def test_eth_mean(self):
        """ETHUSDT values: [0.1, -0.4, 0.6] → mean = 0.30/3 = 0.10"""
        eth = self.r["symbol_stability"]["per_symbol"]["ETHUSDT"]
        assert abs(eth["mean_net_R"] - 0.10) < 1e-12
        assert eth["count"] == 3

    def test_sol_mean(self):
        """SOLUSDT values: [-0.1, 0.2, 0.0, -0.3] → mean = -0.20/4 = -0.05"""
        sol = self.r["symbol_stability"]["per_symbol"]["SOLUSDT"]
        assert abs(sol["mean_net_R"] - (-0.05)) < 1e-12
        assert sol["count"] == 4

    def test_cross_symbol_cv(self):
        """Means = [0.20, 0.10, -0.05]
           mean_of_means = (0.20+0.10-0.05)/3 = 0.08333...
           std_of_means ≈ 0.1028...
           cv = 0.1028/0.08333 ≈ 1.234"""
        cv = self.r["symbol_stability"]["cross_symbol_cv"]
        assert cv > 0.0
        # Regression: known value for this dataset
        assert abs(cv - 1.234) < 1e-2

    def test_per_symbol_cv_non_infinite(self):
        """Per-symbol cv should be finite when mean != 0."""
        for sym_data in self.r["symbol_stability"]["per_symbol"].values():
            assert math.isfinite(sym_data["cv"]) or sym_data["cv"] == 0.0


# =========================================================================
# 3. regime_stability verification
# =========================================================================


class TestRegimeStability:
    """Per-regime and cross-regime metrics."""

    @pytest.fixture(autouse=True)
    def result(self):
        self.r = _ref_score()

    def test_per_regime_three_types(self):
        """Three regime types present."""
        assert set(self.r["regime_stability"]["per_regime"].keys()) == {
            "TREND_UP", "TREND_DOWN", "RANGE"
        }

    def test_trend_up_mean(self):
        """TREND_UP rows: indices 0(0.5),1(0.3),6(-0.1),9(-0.3)
           mean = 0.40/4 = 0.10"""
        tu = self.r["regime_stability"]["per_regime"]["TREND_UP"]
        assert abs(tu["mean_net_R"] - 0.10) < 1e-12
        assert tu["count"] == 4

    def test_trend_down_mean(self):
        """TREND_DOWN rows: indices 4(-0.4),5(0.6),8(0.0)
           mean = 0.20/3 ≈ 0.06667"""
        td = self.r["regime_stability"]["per_regime"]["TREND_DOWN"]
        assert abs(td["mean_net_R"] - 0.0666667) < 1e-5
        assert td["count"] == 3

    def test_range_mean(self):
        """RANGE rows: indices 2(-0.2),3(0.1),7(0.2)
           mean = 0.10/3 ≈ 0.03333"""
        rg = self.r["regime_stability"]["per_regime"]["RANGE"]
        assert abs(rg["mean_net_R"] - 0.0333333) < 1e-5
        assert rg["count"] == 3


# =========================================================================
# 4. cost_stress logic
# =========================================================================


class TestCostStress:
    """Fee multiplier stress scenarios."""

    def test_baseline_mean_matches(self):
        """Baseline mean in cost_stress matches mean_net_R."""
        r = _ref_score(fee_r=0.02)
        assert abs(
            r["cost_stress"]["baseline_mean_net_R"] - r["mean_net_R"]
        ) < 1e-12

    def test_fee_2x_reduces_mean(self):
        """2x fee subtracts fee_r per trade: mean drops by fee_r."""
        r = _ref_score(fee_r=0.02)
        fee_2x = r["cost_stress"]["scenarios"]["fee_2x"]
        expected_mean = 0.07 - 0.02  # fee_r * (2-1) = 0.02
        assert abs(fee_2x["mean_net_R"] - expected_mean) < 1e-12
        assert fee_2x["edge_survives"] is True

    def test_fee_10x_destroys_edge_with_sufficient_fee(self):
        """10x fee can flip edge negative when fee_r is large enough."""
        r = _ref_score(fee_r=0.05)
        fee_10x = r["cost_stress"]["scenarios"]["fee_10x"]
        # mean change = -(10-1)*0.05 = -0.45
        # stressed mean = 0.07 - 0.45 = -0.38
        assert fee_10x["mean_net_R"] < 0
        assert fee_10x["edge_survives"] is False

    def test_fee_5x_edge_survives_with_low_fee(self):
        """Small fee_r keeps edge positive even at 10x."""
        r = _ref_score(fee_r=0.002)  # very low fee
        for scenario in r["cost_stress"]["scenarios"].values():
            assert scenario["edge_survives"] is True

    def test_zero_fee_no_impact(self):
        """Zero fee_r produces no change across scenarios."""
        r = _ref_score(fee_r=0.0)
        for mult, scenario in r["cost_stress"]["scenarios"].items():
            assert abs(scenario["mean_change"]) < 1e-12
            assert scenario["edge_survives"] is True

    def test_mean_change_is_negative(self):
        """Mean change is always negative for positive fee_r."""
        r = _ref_score(fee_r=0.02)
        for scenario in r["cost_stress"]["scenarios"].values():
            assert scenario["mean_change"] < 0


# =========================================================================
# 5. Empty rule handling
# =========================================================================


class TestEmptyRule:
    """Rules with no active observations return zero-filled results."""

    def test_empty_mask(self):
        """All-false mask returns zeroed metrics."""
        scorer = RuleScorer()
        empty_mask = np.zeros(10, dtype=bool)
        result = scorer.score(
            rule=_RULE_DEMO,
            masks={"active": empty_mask},
            target=_KNOWN_TARGET,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
        )
        assert result["mean_net_R"] == 0.0
        assert result["median_net_R"] == 0.0
        assert result["positive_rate"] == 0.0
        assert result["n_observations"] == 0
        assert result["profit_factor"] == 0.0
        assert result["sharpe"] == 0.0

    def test_empty_mask_symbol_stability_empty(self):
        """Empty mask yields empty per-symbol dicts."""
        scorer = RuleScorer()
        empty_mask = np.zeros(10, dtype=bool)
        result = scorer.score(
            rule=_RULE_DEMO,
            masks={"active": empty_mask},
            target=_KNOWN_TARGET,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
        )
        assert result["symbol_stability"]["per_symbol"] == {}
        assert result["regime_stability"]["per_regime"] == {}

    def test_missing_active_key_falls_back(self):
        """Missing 'active' key falls back to first boolean array."""
        scorer = RuleScorer()
        # Only 'long' key provided
        masks = {"long": _KNOWN_MASK[:5], "short": np.zeros(5, dtype=bool)}
        shaved_target = _KNOWN_TARGET[:5]
        shaved_sym = _KNOWN_SYMBOLS[:5]
        shaved_reg = _KNOWN_REGIMES[:5]
        result = scorer.score(
            rule=_RULE_DEMO,
            masks=masks,
            target=shaved_target,
            symbol_map=shaved_sym,
            regime_map=shaved_reg,
        )
        assert result["n_observations"] == 5
        assert result["mean_net_R"] > 0

    def test_entirely_empty_masks_dict(self):
        """Empty masks dict should not crash."""
        scorer = RuleScorer()
        result = scorer.score(
            rule=_RULE_DEMO,
            masks={},
            target=_KNOWN_TARGET,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
        )
        assert result["n_observations"] == 0


# =========================================================================
# 6. NaN-safe behavior
# =========================================================================


class TestNaNSafety:
    """NaN values in target are handled without propagating."""

    def test_nan_in_target(self):
        """NaN values are ignored in mean/median/std computations."""
        target_with_nan = np.array(
            [0.5, np.nan, -0.2, 0.1, np.nan, 0.6, -0.1, 0.2, 0.0, -0.3], dtype=float
        )
        mask = np.array(
            [True, True, True, True, True, True, True, True, True, True], dtype=bool
        )
        scorer = RuleScorer()
        result = scorer.score(
            rule=_RULE_DEMO,
            masks={"active": mask},
            target=target_with_nan,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
        )
        # 8 non-NaN values, sum = 0.80, mean = 0.10
        assert abs(result["mean_net_R"] - 0.10) < 1e-12
        # n_observations is count of True in mask, not NaN-filtered count
        assert result["n_observations"] == 10

    def test_all_nan_target(self):
        """All-NaN target returns zeroed metrics."""
        target_all_nan = np.full(10, np.nan, dtype=float)
        scorer = RuleScorer()
        result = scorer.score(
            rule=_RULE_DEMO,
            masks={"active": _KNOWN_MASK},
            target=target_all_nan,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
        )
        assert result["mean_net_R"] == 0.0
        assert result["positive_rate"] == 0.0
        assert result["profit_factor"] == 0.0

    def test_nan_in_symbol_map_does_not_affect_scoring(self):
        """NaN in symbol_map is cleaned to 'NAN' string; scoring unaffected."""
        symbols_with_nan = _KNOWN_SYMBOLS.copy().astype(object)
        symbols_with_nan[0] = np.nan
        scorer = RuleScorer()
        result = scorer.score(
            rule=_RULE_DEMO,
            masks={"active": _KNOWN_MASK},
            target=_KNOWN_TARGET,
            symbol_map=symbols_with_nan,
            regime_map=_KNOWN_REGIMES,
        )
        per_symbol = result["symbol_stability"]["per_symbol"]
        assert "NAN" in per_symbol
        assert abs(result["mean_net_R"] - 0.07) < 1e-12  # unchanged


# =========================================================================
# 7. Batch scoring (parallel)
# =========================================================================


class TestBatchScoring:
    """score_batch produces identical results to single scoring."""

    def test_batch_matches_single(self):
        """Batch scoring matches single scoring for all rules."""
        rules = [
            {"id": "r1", "feature": "rsi", "operator": ">", "threshold": 70},
            {"id": "r2", "feature": "rsi", "operator": "<", "threshold": 30},
        ]
        # r1: first 7 rows active, r2: last 3 rows active
        masks_list = [
            {"active": np.array([True, True, True, True, True, True, True, False, False, False], dtype=bool)},
            {"active": np.array([False, False, False, False, False, False, False, True, True, True], dtype=bool)},
        ]
        scorer = RuleScorer()

        # Single scoring
        singles = [
            scorer.score(
                rule=rules[0],
                masks=masks_list[0],
                target=_KNOWN_TARGET,
                symbol_map=_KNOWN_SYMBOLS,
                regime_map=_KNOWN_REGIMES,
            ),
            scorer.score(
                rule=rules[1],
                masks=masks_list[1],
                target=_KNOWN_TARGET,
                symbol_map=_KNOWN_SYMBOLS,
                regime_map=_KNOWN_REGIMES,
            ),
        ]

        # Batch scoring
        batch = scorer.score_batch(
            rules=rules,
            masks_list=masks_list,
            target=_KNOWN_TARGET,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
            max_workers=2,
        )

        assert len(batch) == 2
        for i in range(2):
            for key in ("mean_net_R", "median_net_R", "positive_rate",
                        "lift_over_base", "profit_factor", "sharpe",
                        "n_observations"):
                assert abs(batch[i][key] - singles[i][key]) < 1e-12, (
                    f"Mismatch at rule {i}, key {key}: "
                    f"{batch[i][key]} vs {singles[i][key]}"
                )

    def test_batch_length_mismatch_raises(self):
        """Mismatched rules/masks_list lengths raise ValueError."""
        scorer = RuleScorer()
        with pytest.raises(ValueError, match="Length mismatch"):
            scorer.score_batch(
                rules=[{"id": "r1"}],
                masks_list=[{"active": _KNOWN_MASK}, {"active": _KNOWN_MASK}],
                target=_KNOWN_TARGET,
                symbol_map=_KNOWN_SYMBOLS,
                regime_map=_KNOWN_REGIMES,
            )

    def test_batch_sequential_fallback(self):
        """score_batch falls back to sequential when max_workers=1."""
        scorer = RuleScorer()
        masks_list = [{"active": _KNOWN_MASK}, {"active": _KNOWN_MASK}]
        rules = [{"id": "r1"}, {"id": "r2"}]
        batch = scorer.score_batch(
            rules=rules,
            masks_list=masks_list,
            target=_KNOWN_TARGET,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
            max_workers=1,
        )
        assert len(batch) == 2
        for r in batch:
            assert abs(r["mean_net_R"] - 0.07) < 1e-12

    def test_batch_returns_in_order(self):
        """Result order matches input order."""
        mask_a = np.array([True, True, True, False, False, False, False, False, False, False], dtype=bool)
        mask_b = np.array([False, False, False, False, False, False, False, False, False, True], dtype=bool)
        scorer = RuleScorer()
        batch = scorer.score_batch(
            rules=[{"id": "few"}, {"id": "single"}],
            masks_list=[{"active": mask_a}, {"active": mask_b}],
            target=_KNOWN_TARGET,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
        )
        assert batch[0]["n_observations"] == 3
        assert batch[1]["n_observations"] == 1


# =========================================================================
# 8. Mask resolution edge cases
# =========================================================================


class TestMaskResolution:
    """Various mask resolution strategies."""

    def test_combined_key_preferred(self):
        """'combined' key takes priority over 'active'."""
        combined = np.zeros(10, dtype=bool)
        combined[0] = True
        active = np.ones(10, dtype=bool)
        scorer = RuleScorer()
        result = scorer.score(
            rule=_RULE_DEMO,
            masks={"combined": combined, "active": active},
            target=_KNOWN_TARGET,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
        )
        assert result["n_observations"] == 1  # combined used

    def test_long_short_union(self):
        """Union of long and short masks when both present."""
        long = np.array([True, True, False, False, False, False, False, False, False, False], dtype=bool)
        short = np.array([False, False, True, True, False, False, False, False, False, False], dtype=bool)
        scorer = RuleScorer()
        result = scorer.score(
            rule=_RULE_DEMO,
            masks={"long": long, "short": short},
            target=_KNOWN_TARGET,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
        )
        assert result["n_observations"] == 4

    def test_rule_id_fallback_to_name(self):
        """rule_id falls back to 'name' when 'id' is absent."""
        scorer = RuleScorer()
        result = scorer.score(
            rule={"name": "test_rule"},
            masks={"active": _KNOWN_MASK},
            target=_KNOWN_TARGET,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
        )
        assert result["rule_id"] == "test_rule"


# =========================================================================
# 9. Deterministic reproducibility
# =========================================================================


class TestDeterminism:
    """Identical inputs produce identical outputs."""

    def test_reproducible(self):
        """Second call with same inputs produces same results."""
        scorer = RuleScorer()
        r1 = scorer.score(
            rule=_RULE_DEMO,
            masks={"active": _KNOWN_MASK},
            target=_KNOWN_TARGET,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
        )
        r2 = scorer.score(
            rule=_RULE_DEMO,
            masks={"active": _KNOWN_MASK},
            target=_KNOWN_TARGET,
            symbol_map=_KNOWN_SYMBOLS,
            regime_map=_KNOWN_REGIMES,
        )
        for key in ("mean_net_R", "median_net_R", "positive_rate",
                    "lift_over_base", "profit_factor", "sharpe",
                    "n_observations"):
            assert r1[key] == r2[key]

    def test_profit_factor_no_losses(self):
        """Profit factor is infinite when no losses exist."""
        all_gains = np.array([0.1, 0.2, 0.3, 0.4], dtype=float)
        scorer = RuleScorer()
        result = scorer.score(
            rule=_RULE_DEMO,
            masks={"active": np.ones(4, dtype=bool)},
            target=all_gains,
            symbol_map=np.array(["A", "A", "B", "B"]),
            regime_map=np.array(["X", "Y", "Y", "X"]),
        )
        # No losses → profit_factor = inf
        assert result["profit_factor"] == float("inf")

    def test_profit_factor_no_gains(self):
        """Profit factor is 0 when no gains exist."""
        all_losses = np.array([-0.1, -0.2, -0.3], dtype=float)
        scorer = RuleScorer()
        result = scorer.score(
            rule=_RULE_DEMO,
            masks={"active": np.ones(3, dtype=bool)},
            target=all_losses,
            symbol_map=np.array(["A", "A", "B"]),
            regime_map=np.array(["X", "X", "Y"]),
        )
        assert result["profit_factor"] == 0.0
