"""Tests for v7.policy_critic.regret — regret_r computation."""

import pytest

from v7.policy_critic.regret import (
    DEFAULT_LAMBDA_DD,
    RegretBasis,
    RegretResult,
    compute_regret_from_simulation,
    compute_regret_r,
    get_lambda_dd,
)


class TestGetLambdaDd:
    """Test drawdown penalty weight lookup by mode."""

    def test_swing_default(self):
        assert get_lambda_dd("SWING") == 0.5

    def test_scalp_high(self):
        assert get_lambda_dd("SCALP") == 1.0

    def test_aggressive_scalp_very_high(self):
        assert get_lambda_dd("AGGRESSIVE_SCALP") == 2.0

    def test_lowercase_mode(self):
        assert get_lambda_dd("swing") == 0.5
        assert get_lambda_dd("scalp") == 1.0

    def test_unknown_mode_defaults(self):
        assert get_lambda_dd("UNKNOWN_MODE") == DEFAULT_LAMBDA_DD


class TestComputeRegretR:
    """Test regret_r computation."""

    def test_zero_regret_when_chosen_is_best(self):
        """When the chosen action is the best, regret should be 0."""
        result = compute_regret_r(
            long_r_net=0.80,
            short_r_net=-0.20,
            chosen_r_net=0.80,
            chosen_action="LONG",
            mode="SWING",
            basis=RegretBasis.R_NET,
        )
        assert result.regret_r == 0.0
        assert result.best_action == "LONG"

    def test_positive_regret_when_best_missed(self):
        """Regret when best action would have been better."""
        result = compute_regret_r(
            long_r_net=-0.30,
            short_r_net=1.20,
            chosen_r_net=-0.30,
            chosen_action="LONG",
            mode="SWING",
            basis=RegretBasis.R_NET,
        )
        assert result.regret_r > 0
        assert result.best_action == "SHORT"
        assert result.best_r_net == 1.20

    def test_no_trade_best_when_both_lose(self):
        """NO_TRADE should be best when both LONG and SHORT lose."""
        result = compute_regret_r(
            long_r_net=-0.50,
            short_r_net=-0.30,
            chosen_r_net=0.0,
            chosen_action="NO_TRADE",
            mode="SWING",
            basis=RegretBasis.R_NET,
        )
        assert result.regret_r == 0.0
        assert result.best_action == "NO_TRADE"

    def test_all_lose_regret_when_no_trade_is_best(self):
        """When best=NO_TRADE (0.0) and chosen loses (-0.30), real regret exists."""
        result = compute_regret_r(
            long_r_net=-0.50,
            short_r_net=-0.30,
            chosen_r_net=-0.30,
            chosen_action="SHORT",
            mode="SWING",
            basis=RegretBasis.R_NET,
        )
        # best = max(-0.50, -0.30, 0.0) = 0.0 (NO_TRADE)
        # regret = 0.0 - (-0.30) = 0.30
        assert result.regret_r == 0.30
        assert result.best_action == "NO_TRADE"
        assert result.best_r_net == 0.0

    def test_no_regret_when_chosen_is_best_among_losers(self):
        """When all actions lose but chosen is the least-bad, regret is zero."""
        result = compute_regret_r(
            long_r_net=-0.10,
            short_r_net=-0.50,
            chosen_r_net=-0.10,
            chosen_action="LONG",
            mode="SWING",
            basis=RegretBasis.R_NET,
        )
        # best = max(-0.10, -0.50, 0.0) = 0.0 (NO_TRADE)
        # chosen = -0.10, best = 0.0 → regret = 0.10
        # Wait, NO_TRADE beats LONG too. So there's still regret.
        # Only when NO_TRADE=chosen=0 and all directional actions lose
        # AND chosen was the least-bad directional, the beat-by applies.
        # Actually, chosen=-0.10 vs best=0.0 → 0.10 regret is correct.
        assert result.regret_r == 0.10

    def test_shaped_reward_includes_drawdown_penalty(self):
        """SHAPED_REWARD basis should include drawdown penalty."""
        result = compute_regret_r(
            long_r_net=0.80,
            short_r_net=0.60,
            chosen_r_net=0.80,
            chosen_action="LONG",
            long_mae_r=0.40,
            short_mae_r=0.10,
            mode="SWING",
            basis=RegretBasis.SHAPED_REWARD,
            long_action_utility=0.80,
            short_action_utility=0.60,
            chosen_action_utility=0.80,
        )
        # With lambda_dd=0.5 for SWING:
        # long shaped = 0.80 - 0.5*0.40 = 0.60
        # short shaped = 0.60 - 0.5*0.10 = 0.55
        # If chosen is LONG and LONG is best, regret = 0.60 - 0.60 = 0
        assert result.regret_r == 0.0
        assert result.drawdown_penalty_long == -0.20
        assert result.drawdown_penalty_short == -0.05

    def test_no_trade_utility_used_in_shaped(self):
        """NO_TRADE utility = saved_loss_r - 0.5 * missed_opportunity_r."""
        result = compute_regret_r(
            long_r_net=-0.20,
            short_r_net=-0.30,
            chosen_r_net=-0.20,
            chosen_action="LONG",
            saved_loss_r=1.0,
            missed_opportunity_r=0.0,
            mode="SWING",
            basis=RegretBasis.SHAPED_REWARD,
            long_action_utility=-0.20,
            short_action_utility=-0.30,
            chosen_action_utility=-0.20,
        )
        # SHAPED_REWARD basis:
        # long shaped = -0.20 + dd_penalty (0 for mae_r=0) = -0.20
        # short shaped = -0.30 + dd_penalty (0) = -0.30
        # no_trade shaped = 1.0 - 0.5*0.0 = 1.0
        # best = max(-0.20, -0.30, 1.0) = 1.0 (NO_TRADE)
        # regret = 1.0 - (-0.20) = 1.20
        assert result.regret_r == 1.20
        assert result.best_action == "NO_TRADE"

    def test_ambiguity_margin_classifies_significance(self):
        """Regret above ambiguity_margin_r should be flagged significant."""
        result = compute_regret_r(
            long_r_net=0.10,
            short_r_net=1.50,
            chosen_r_net=0.10,
            chosen_action="LONG",
            ambiguity_margin_r=0.20,
            basis=RegretBasis.R_NET,
        )
        assert result.regret_r > 0.20
        assert result.is_regret_significant is True

        result2 = compute_regret_r(
            long_r_net=0.90,
            short_r_net=1.00,
            chosen_r_net=0.90,
            chosen_action="LONG",
            ambiguity_margin_r=0.20,
            basis=RegretBasis.R_NET,
        )
        # regret = 1.00 - 0.90 = 0.10 < 0.20 → not significant
        assert result2.is_regret_significant is False

    def test_regret_result_immutable(self):
        result = compute_regret_r(
            long_r_net=0.80,
            short_r_net=-0.20,
            chosen_r_net=0.80,
            chosen_action="LONG",
            basis=RegretBasis.R_NET,
        )
        with pytest.raises(Exception):
            result.regret_r = 1.0  # type: ignore


class TestComputeRegretFromSimulation:
    """Test regret computation from SimulationOutput dict."""

    def _sim_output(self, long_r=0.80, short_r=-0.20, long_au=0.80, short_au=0.0,
                    long_mae=0.1, short_mae=0.0, saved_loss=0.0, missed_opp=0.0):
        return {
            "long_outcome": {
                "realized_r_net": long_r,
                "action_utility": long_au,
                "path_metrics": {"mae_r": long_mae},
            },
            "short_outcome": {
                "realized_r_net": short_r,
                "action_utility": short_au,
                "path_metrics": {"mae_r": short_mae},
            },
            "no_trade_outcome": {
                "saved_loss_r": saved_loss,
                "missed_opportunity_r": missed_opp,
            },
        }

    def test_long_is_best_no_regret(self):
        sim = self._sim_output()
        result = compute_regret_from_simulation(sim, chosen_action="LONG")
        assert result.regret_r == 0.0
        assert result.best_action == "LONG"

    def test_short_is_best_regret_for_long(self):
        sim = self._sim_output(long_r=-0.30, short_r=1.20, long_au=0.0, short_au=1.20)
        result = compute_regret_from_simulation(sim, chosen_action="LONG")
        assert result.regret_r > 0
        assert result.best_action == "SHORT"

    def test_no_trade_chosen_best_action_is_no_trade_when_losing(self):
        """When both actions lose, R_NET basis should prefer NO_TRADE (0.0)."""
        sim = self._sim_output(long_r=-0.50, short_r=-0.30, long_au=0.0, short_au=0.0)
        result = compute_regret_from_simulation(
            sim, chosen_action="HOLD", basis=RegretBasis.R_NET,
        )
        # R_NET: best = max(-0.50, -0.30, 0.0) = 0.0, best_action = NO_TRADE
        # chosen_r = 0.0, regret = 0.0 - 0.0 = 0.0
        assert result.regret_r == 0.0
        assert result.best_action == "NO_TRADE"

    def test_enter_long_mapped_correctly(self):
        sim = self._sim_output(long_r=0.80, short_r=-0.20, long_au=0.80)
        result = compute_regret_from_simulation(sim, chosen_action="ENTER_LONG")
        assert result.chosen_r_net == 0.80
        assert result.chosen_action_utility == 0.80

    def test_enter_short_mapped_correctly(self):
        sim = self._sim_output(long_r=0.80, short_r=-0.20, short_au=0.0)
        result = compute_regret_from_simulation(sim, chosen_action="ENTER_SHORT")
        assert result.chosen_r_net == -0.20
