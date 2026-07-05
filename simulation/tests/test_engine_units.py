"""Unit tests for simulation engine internal logic.

Covers: no-trade quality, path quality, action selection, utility computation.
"""

from simulation.contracts.models import ActionOutcome, NoTradeOutcome, PathMetrics, SimulationProfile, TradingMode
from simulation.engine.engine import _build_no_trade_outcome, _path_quality, _path_quality_bucket, _select_best_action
from simulation.engine.exits import compute_utility


def _swing_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="test",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=30,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.20,
        min_action_edge_r=0.35,
        no_trade_default=False,
        mae_penalty_weight=1.0,
        cost_penalty_weight=1.0,
        time_penalty_weight=0.3,
    )


def _action(realized_r_net: float, utility: float = 0.0) -> ActionOutcome:
    return ActionOutcome(
        action="TEST",
        realized_r_net=realized_r_net,
        action_utility=utility or realized_r_net,
    )


# ── Path Quality ─────────────────────────────────────────────────────

class TestPathQuality:
    def test_high_quality(self):
        assert _path_quality(2.0, -0.5) >= 0.70  # mfe/mae ratio = 4.0

    def test_medium_quality(self):
        assert 0.40 <= _path_quality(1.0, -0.8) < 0.70  # ratio = 1.25

    def test_low_quality(self):
        assert _path_quality(0.3, -0.9) < 0.40  # ratio < 0.5

    def test_no_mfe(self):
        assert _path_quality(0.0, -1.0) == 0.0

    def test_zero_mae_does_not_crash(self):
        score = _path_quality(1.0, 0.0)
        assert 0.0 <= score <= 1.0

    def test_bucket_high(self):
        assert _path_quality_bucket(2.0, -0.5) == "HIGH"

    def test_bucket_medium(self):
        assert _path_quality_bucket(1.0, -0.8) == "MEDIUM"

    def test_bucket_low(self):
        assert _path_quality_bucket(0.3, -0.9) == "LOW"


# ── No-Trade Quality ─────────────────────────────────────────────────

class TestNoTradeQuality:
    def test_correct_no_trade(self):
        """Both directions near zero or negative."""
        long = _action(0.0)
        short = _action(0.0)
        result = _build_no_trade_outcome(long, short, _swing_profile())

        assert result.no_trade_quality == "CORRECT_NO_TRADE"
        assert result.was_correct_skip
        assert result.saved_loss_r == 0.0
        assert result.missed_opportunity_r == 0.0

    def test_saved_loss(self):
        """One direction lost money."""
        long = _action(-0.5)
        short = _action(-1.2)
        result = _build_no_trade_outcome(long, short, _swing_profile())

        assert result.no_trade_quality == "SAVED_LOSS"
        assert result.was_correct_skip
        assert result.saved_loss_r == 1.2  # worst = -1.2, saved = 1.2

    def test_missed_opportunity(self):
        """Best direction beat min_action_edge."""
        long = _action(0.8)
        short = _action(-0.3)
        result = _build_no_trade_outcome(long, short, _swing_profile())

        assert result.no_trade_quality == "MISSED_OPPORTUNITY"
        assert not result.was_correct_skip
        assert result.missed_opportunity_r == 0.8

    def test_ambiguous_no_trade(self):
        """Best direction positive but below min_action_edge, and saved_loss applies."""
        long = _action(0.20)
        short = _action(-0.10)
        result = _build_no_trade_outcome(long, short, _swing_profile())

        # saved_loss_r = 0.10, missed_opportunity_r = 0.0 (below edge)
        # Both saved_loss_r > 0 and missed_opportunity_r == 0 → SAVED_LOSS
        assert result.no_trade_quality in ("SAVED_LOSS", "AMBIGUOUS_NO_TRADE")
        assert result.was_correct_skip

    def test_saved_loss_score_capped(self):
        """Saved loss score is capped at 1.0."""
        long = _action(-10.0)
        short = _action(-10.0)
        result = _build_no_trade_outcome(long, short, _swing_profile())

        assert result.saved_loss_r == 10.0
        assert result.saved_loss_score <= 1.0


# ── Action Selection ─────────────────────────────────────────────────

class TestSelectBestAction:
    def test_long_wins(self):
        result, second, gap, regret, ambiguous = _select_best_action(
            _action(1.0, utility=1.0),
            _action(-0.5, utility=-0.5),
            NoTradeOutcome(saved_loss_r=0.0, missed_opportunity_r=1.0),
            _swing_profile(),
        )
        assert result == "LONG_NOW"

    def test_short_wins(self):
        result, second, gap, regret, ambiguous = _select_best_action(
            _action(-0.5, utility=-0.5),
            _action(1.0, utility=1.0),
            NoTradeOutcome(saved_loss_r=0.5, missed_opportunity_r=0.0),
            _swing_profile(),
        )
        assert result == "SHORT_NOW"

    def test_no_trade_wins_on_saved_loss(self):
        nt = NoTradeOutcome(saved_loss_r=0.8, missed_opportunity_r=0.0)
        result, second, gap, regret, ambiguous = _select_best_action(
            _action(-0.6, utility=-0.6),
            _action(-0.7, utility=-0.7),
            nt,
            _swing_profile(),
        )
        assert result == "NO_TRADE"

    def test_ambiguous_no_trade_default_false(self):
        result, second, gap, regret, ambiguous = _select_best_action(
            _action(0.10, utility=0.10),
            _action(0.05, utility=0.05),
            NoTradeOutcome(saved_loss_r=0.0, missed_opportunity_r=0.10),
            _swing_profile(),
        )
        assert result == "AMBIGUOUS_STATE"
        assert ambiguous


# ── Utility Computation ──────────────────────────────────────────────

class TestComputeUtility:
    def test_basic(self):
        u = compute_utility(1.0, -0.3, 0.05, 2, _swing_profile())
        # 1.0 - 1.0*0.3 - 1.0*0.05 - 0.3*2*0.1 = 1.0 - 0.3 - 0.05 - 0.06 = 0.59
        assert abs(u - 0.59) < 0.01

    def test_negative_penalty(self):
        u = compute_utility(-1.0, -1.0, 0.1, 5, _swing_profile())
        assert u < 0

    def test_scalp_weights(self):
        profile = SimulationProfile(
            profile_version="test",
            mode=TradingMode.SCALP,
            primary_interval="1h",
            max_holding_bars=12,
            stop_multiplier=1.5,
            target_multiplier=1.8,
            ambiguity_margin_r=0.10,
            min_action_edge_r=0.15,
            no_trade_default=False,
            mae_penalty_weight=2.0,
            cost_penalty_weight=2.0,
            time_penalty_weight=1.5,
        )
        u = compute_utility(1.0, -0.3, 0.05, 2, profile)
        # 1.0 - 2.0*0.3 - 2.0*0.05 - 1.5*2*0.1 = 1.0 - 0.6 - 0.1 - 0.3 = 0.0
        assert abs(u - 0.0) < 0.01
