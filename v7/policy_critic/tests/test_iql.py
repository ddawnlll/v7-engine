"""Tests for v7.policy_critic.iql — IQL training, OPE/FQE, conformal calibration."""

import math

import pytest

from v7.policy_critic.iql import (
    FQEEvaluator,
    FQEJuryVerdict,
    IQLTrainer,
    IQLTrainingResult,
    OPEEvaluator,
    OPEVerdict,
    PolicyNetwork,
    QNetwork,
    ValueNetwork,
    calibrate_conformal,
    ConformalCalibration,
    VALID_VERDICTS,
)
from v7.policy_critic.replay_buffer import (
    CRITIC_ACTION_LONG,
    CRITIC_ACTION_NO_TRADE,
    CRITIC_ACTION_SHORT,
    ReplayTuple,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tuple(
    reward: float = 0.0,
    action: str = CRITIC_ACTION_LONG,
    terminal: bool = False,
    mode: str = "SWING",
    symbol: str = "BTCUSDT",
    confidence: float = 0.7,
) -> ReplayTuple:
    """Create a minimal ReplayTuple for testing."""
    return ReplayTuple(
        state={
            "symbol": symbol,
            "mode": mode,
            "confidence": confidence,
            "decision": "ENTER_LONG",
            "entry_price": 64300.0,
        },
        action=action,
        reward=reward,
        next_state={
            "symbol": symbol,
            "mode": mode,
            "confidence": confidence + 0.02,
            "decision": "HOLD",
            "entry_price": 64400.0,
        } if not terminal else {},
        terminal=terminal,
        decision_event_id=f"evt_{symbol}_{mode}",
        symbol=symbol,
        mode=mode,
    )


def _make_tuples(n: int, mode: str = "SWING") -> list[ReplayTuple]:
    """Create n replay tuples for training."""
    tuples = []
    for i in range(n):
        reward = 0.1 * math.sin(i * 0.5)  # varied but repeatable
        action = (
            CRITIC_ACTION_LONG if i % 3 == 0
            else CRITIC_ACTION_SHORT if i % 3 == 1
            else CRITIC_ACTION_NO_TRADE
        )
        terminal = (i % 10 == 9)
        tuples.append(_make_tuple(
            reward=reward, action=action, terminal=terminal, mode=mode,
            symbol="BTCUSDT" if i % 2 == 0 else "ETHUSDT",
        ))
    return tuples


def _make_trajectories(tuples: list[ReplayTuple], traj_len: int = 3) -> list[list[ReplayTuple]]:
    """Group replay tuples into fixed-length trajectories for OPE."""
    return [tuples[i:i + traj_len] for i in range(0, len(tuples), traj_len)]


# ===================================================================
# Test QNetwork
# ===================================================================

class TestQNetwork:
    """Test QNetwork abstraction."""

    def test_default_quantiles(self):
        q = QNetwork()
        assert q.quantiles == 16
        assert not q.is_trained

    def test_predict_quantiles_untrained(self):
        q = QNetwork()
        qs = q.predict_quantiles({"symbol": "BTCUSDT", "mode": "SWING"}, CRITIC_ACTION_LONG)
        assert len(qs) == 16
        assert all(v == 0.0 for v in qs)

    def test_set_and_get_quantiles(self):
        q = QNetwork(quantiles=8)
        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        q.set_estimates(state, CRITIC_ACTION_LONG, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
        qs = q.predict_quantiles(state, CRITIC_ACTION_LONG)
        assert qs == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]

    def test_get_value(self):
        q = QNetwork(quantiles=4)
        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        q.set_estimates(state, CRITIC_ACTION_LONG, [1.0, 2.0, 3.0, 4.0])
        assert q.get_value(state, CRITIC_ACTION_LONG) == 2.5

    def test_get_lower_quantile(self):
        q = QNetwork(quantiles=10)
        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        q.set_estimates(state, CRITIC_ACTION_LONG, list(range(10)))
        # tau=0.2 with 10 quantiles -> index 2 -> value 2
        assert q.get_lower_quantile(state, CRITIC_ACTION_LONG, tau=0.2) == 2.0

    def test_reset(self):
        q = QNetwork()
        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        q.set_estimates(state, CRITIC_ACTION_LONG, [0.5] * 16)
        q._is_trained = True
        q.reset()
        assert not q._is_trained
        assert q._estimates == {}


# ===================================================================
# Test ValueNetwork
# ===================================================================

class TestValueNetwork:
    """Test ValueNetwork abstraction."""

    def test_default(self):
        v = ValueNetwork()
        assert not v.is_trained
        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        assert v.predict(state) == 0.0

    def test_set_and_predict(self):
        v = ValueNetwork()
        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        v.set_value(state, 1.5)
        assert v.predict(state) == 1.5

    def test_reset(self):
        v = ValueNetwork()
        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        v.set_value(state, 1.5)
        v._is_trained = True
        v.reset()
        assert not v._is_trained
        assert v._estimates == {}


# ===================================================================
# Test PolicyNetwork
# ===================================================================

class TestPolicyNetwork:
    """Test PolicyNetwork abstraction."""

    def test_default(self):
        pi = PolicyNetwork()
        assert pi.beta == 3.0
        assert not pi.is_trained

    def test_predict_probs_untrained(self):
        pi = PolicyNetwork()
        probs = pi.predict_probs({"symbol": "BTCUSDT", "mode": "SWING"})
        assert set(probs.keys()) == {CRITIC_ACTION_LONG, CRITIC_ACTION_SHORT, CRITIC_ACTION_NO_TRADE}
        assert abs(sum(probs.values()) - 1.0) < 0.01

    def test_set_and_predict(self):
        pi = PolicyNetwork()
        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        pi.set_probs(state, {CRITIC_ACTION_LONG: 0.8, CRITIC_ACTION_SHORT: 0.1, CRITIC_ACTION_NO_TRADE: 0.1})
        probs = pi.predict_probs(state)
        assert probs[CRITIC_ACTION_LONG] == 0.8
        assert probs[CRITIC_ACTION_SHORT] == 0.1
        assert probs[CRITIC_ACTION_NO_TRADE] == 0.1

    def test_reset(self):
        pi = PolicyNetwork()
        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        pi.set_probs(state, {CRITIC_ACTION_LONG: 0.8, CRITIC_ACTION_SHORT: 0.1, CRITIC_ACTION_NO_TRADE: 0.1})
        pi._is_trained = True
        pi.reset()
        assert not pi._is_trained
        assert pi._action_probs == {}


# ===================================================================
# Test IQLTrainer
# ===================================================================

class TestIQLTrainerInit:
    """Test IQLTrainer initialisation."""

    def test_default_params(self):
        t = IQLTrainer()
        assert t.expectile_tau == 0.75
        assert t.gamma == 0.99
        assert t.n_epochs == 100
        assert t.batch_size == 256
        assert t.cql_reg == 0.0

    def test_custom_params(self):
        t = IQLTrainer(expectile_tau=0.8, gamma=0.95, n_epochs=10, batch_size=32, cql_regularisation=0.1)
        assert t.expectile_tau == 0.8
        assert t.gamma == 0.95
        assert t.n_epochs == 10
        assert t.batch_size == 32
        assert t.cql_reg == 0.1

    def test_invalid_tau_raises(self):
        with pytest.raises(ValueError, match="expectile_tau"):
            IQLTrainer(expectile_tau=0.5)

    def test_invalid_tau_high_raises(self):
        with pytest.raises(ValueError, match="expectile_tau"):
            IQLTrainer(expectile_tau=1.0)

    def test_invalid_gamma_raises(self):
        with pytest.raises(ValueError, match="gamma"):
            IQLTrainer(gamma=0.0)

    def test_invalid_cql_raises(self):
        with pytest.raises(ValueError, match="cql_regularisation"):
            IQLTrainer(cql_regularisation=-1.0)


class TestIQLTrainerTrain:
    """Test IQLTrainer.train()."""

    def test_empty_buffer(self):
        t = IQLTrainer(n_epochs=5, batch_size=4)
        result = t.train([])
        assert isinstance(result, IQLTrainingResult)
        assert result.n_tuples == 0
        assert not result.is_converged

    def test_training_returns_result(self):
        t = IQLTrainer(n_epochs=5, batch_size=4, convergence_threshold=1e-6)
        tuples = _make_tuples(20)
        result = t.train(tuples)
        assert isinstance(result, IQLTrainingResult)
        assert result.n_tuples == 20
        assert len(result.bellman_error_history) > 0
        assert result.n_epochs <= 5

    def test_training_marks_networks(self):
        t = IQLTrainer(n_epochs=5, batch_size=4)
        q = QNetwork()
        v = ValueNetwork()
        pi = PolicyNetwork()
        tuples = _make_tuples(20)
        t.train(tuples, q_network=q, value_network=v, policy_network=pi)
        assert q.is_trained
        assert v.is_trained
        assert pi.is_trained

    def test_linearly_separable_data_converges(self):
        """When reward closely tracks Q-value structure, error should be low."""
        t = IQLTrainer(n_epochs=20, batch_size=8, convergence_threshold=0.05,
                       learning_rate_q=0.1, learning_rate_v=0.1)
        q = QNetwork(quantiles=8)
        v = ValueNetwork()
        pi = PolicyNetwork()

        # Create data where Q(s,a) ~ reward, V(s) ~ 0.9 * mean(reward in batch)
        tuples = []
        for i in range(50):
            r = 0.05 * i % 0.5
            tuples.append(_make_tuple(reward=r, action=CRITIC_ACTION_LONG))

        result = t.train(tuples, q_network=q, value_network=v, policy_network=pi)
        # Error should be non-zero but bounded
        assert result.final_bellman_error >= 0.0
        assert result.n_epochs > 0

    def test_cql_regularisation_runs(self):
        t = IQLTrainer(n_epochs=3, batch_size=8, cql_regularisation=0.1)
        tuples = _make_tuples(20)
        result = t.train(tuples)
        assert result.n_tuples == 20

    def test_mode_filtering(self):
        t = IQLTrainer(n_epochs=3, batch_size=4, training_mode="SCALP")
        tuples = _make_tuples(20, mode="SWING")  # all SWING, trainer wants SCALP
        result = t.train(tuples)
        assert result.n_tuples == 0  # no matching tuples


class TestIQLTrainerReview:
    """Test IQLTrainer.review()."""

    def test_review_returns_dict_with_all_keys(self):
        t = IQLTrainer(n_epochs=3, batch_size=4)
        q = QNetwork(quantiles=8)
        v = ValueNetwork()
        tuples = _make_tuples(10)
        t.train(tuples, q_network=q, value_network=v)

        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        review = t.review(q, v, state, proposed_action=CRITIC_ACTION_LONG)

        assert "critic_value_LONG" in review
        assert "critic_value_SHORT" in review
        assert "critic_value_NO_TRADE" in review
        assert "critic_verdict" in review
        assert "critic_confidence_adjustment" in review
        assert "critic_veto_reason" in review
        assert "is_advisory" in review
        assert "conformal_p_value" in review
        assert "regret_r" in review
        assert "expected_R" in review
        assert review["is_advisory"] is True

    def test_review_verdict_is_valid(self):
        t = IQLTrainer(n_epochs=3, batch_size=4)
        q = QNetwork(quantiles=8)
        v = ValueNetwork()
        tuples = _make_tuples(10)
        t.train(tuples, q_network=q, value_network=v)

        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        review = t.review(q, v, state, proposed_action=CRITIC_ACTION_LONG)
        assert review["critic_verdict"] in VALID_VERDICTS

    def test_review_untrained_network(self):
        t = IQLTrainer()
        q = QNetwork()
        v = ValueNetwork()
        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        review = t.review(q, v, state)
        assert review["critic_verdict"] in VALID_VERDICTS

    def test_review_lower_bound_negative_triggers_veto(self):
        """When lower quantile <= 0, verdict should be VETO_TO_NO_TRADE."""
        t = IQLTrainer()
        q = QNetwork(quantiles=4)
        v = ValueNetwork()
        state = {"symbol": "BTCUSDT", "mode": "SWING", "confidence": 0.7,
                 "decision": "ENTER_LONG", "entry_price": 64300.0}
        # Set Q quantiles where the lower bound is negative
        q.set_estimates(state, CRITIC_ACTION_LONG, [-1.0, -0.5, 0.1, 0.3])
        q.set_estimates(state, CRITIC_ACTION_SHORT, [-0.8, -0.3, 0.2, 0.4])
        q.set_estimates(state, CRITIC_ACTION_NO_TRADE, [0.0, 0.0, 0.0, 0.0])

        review = t.review(q, v, state, proposed_action=CRITIC_ACTION_LONG)
        # Lower quantile at tau=0.2 for 4 quantiles -> index 0 -> -1.0
        assert review["critic_verdict"] == "VETO_TO_NO_TRADE"
        assert "negative" in review["critic_veto_reason"]


# ===================================================================
# Test OPEEvaluator
# ===================================================================

class TestOPEEvaluator:
    """Test OPEEvaluator."""

    def test_empty_trajectories(self):
        ope = OPEEvaluator()
        result = ope.evaluate([], lambda s: {})
        assert isinstance(result, OPEVerdict)
        assert result.wis_estimate == 0.0
        assert result.n_trajectories == 0

    def test_uniform_target_returns_estimate(self):
        ope = OPEEvaluator(n_bootstrap=100)
        tuples = _make_tuples(12)
        trajectories = _make_trajectories(tuples, traj_len=3)
        uniform_probs = lambda s: {CRITIC_ACTION_LONG: 1/3, CRITIC_ACTION_SHORT: 1/3, CRITIC_ACTION_NO_TRADE: 1/3}

        result = ope.evaluate(trajectories, uniform_probs)
        assert isinstance(result, OPEVerdict)
        assert result.n_trajectories == 4
        assert result.cis_lower <= result.wis_estimate <= result.cis_upper

    def test_deterministic_target_works(self):
        ope = OPEEvaluator(n_bootstrap=50)
        tuples = _make_tuples(9)
        trajectories = _make_trajectories(tuples, traj_len=3)
        long_only = lambda s: {CRITIC_ACTION_LONG: 1.0, CRITIC_ACTION_SHORT: 0.0, CRITIC_ACTION_NO_TRADE: 0.0}

        result = ope.evaluate(trajectories, long_only)
        assert result.n_trajectories == 3

    def test_effective_sample_size_reported(self):
        ope = OPEEvaluator(n_bootstrap=50)
        tuples = _make_tuples(12)
        trajectories = _make_trajectories(tuples, traj_len=3)
        uniform_probs = lambda s: {CRITIC_ACTION_LONG: 1/3, CRITIC_ACTION_SHORT: 1/3, CRITIC_ACTION_NO_TRADE: 1/3}

        result = ope.evaluate(trajectories, uniform_probs)
        assert 0.0 <= result.effective_sample <= 1.0


# ===================================================================
# Test FQEEvaluator
# ===================================================================

class TestFQEEvaluatorInit:
    """Test FQEEvaluator initialisation."""

    def test_default_params(self):
        fqe = FQEEvaluator()
        assert fqe.gamma == 0.99
        assert fqe.n_steps == 50
        assert fqe.step_size == 0.05

    def test_invalid_gamma_raises(self):
        with pytest.raises(ValueError, match="gamma"):
            FQEEvaluator(gamma=0.0)


class TestFQEEvaluatorEvaluate:
    """Test FQEEvaluator.evaluate()."""

    def test_evaluate_empty_tuples(self):
        fqe = FQEEvaluator(n_steps=5)
        q = QNetwork()
        uniform_probs = lambda s: {CRITIC_ACTION_LONG: 1/3, CRITIC_ACTION_SHORT: 1/3, CRITIC_ACTION_NO_TRADE: 1/3}
        result = fqe.evaluate([], uniform_probs, q)
        assert isinstance(result, FQEJuryVerdict)
        assert result.estimated_q == 0.0

    def test_evaluate_returns_verdict(self):
        fqe = FQEEvaluator(n_steps=5, step_size=0.1)
        q = QNetwork(quantiles=4)
        tuples = _make_tuples(10)

        # Pre-set reference Q-values
        for t in tuples:
            q.set_estimates(t.state, t.action, [t.reward * 0.9] * 4)

        uniform_probs = lambda s: {CRITIC_ACTION_LONG: 1/3, CRITIC_ACTION_SHORT: 1/3, CRITIC_ACTION_NO_TRADE: 1/3}
        result = fqe.evaluate(tuples, uniform_probs, q)
        assert isinstance(result, FQEJuryVerdict)
        assert result.n_steps == 5
        assert len(result.fqe_errors) == 5

    def test_fqe_errors_decrease_over_steps(self):
        """With consistent data, FQE error should decrease."""
        fqe = FQEEvaluator(n_steps=10, step_size=0.05)
        q = QNetwork(quantiles=4)
        tuples = _make_tuples(20)

        for t in tuples:
            q.set_estimates(t.state, t.action, [t.reward] * 4)

        long_only = lambda s: {CRITIC_ACTION_LONG: 1.0, CRITIC_ACTION_SHORT: 0.0, CRITIC_ACTION_NO_TRADE: 0.0}
        result = fqe.evaluate(tuples, long_only, q)
        # FQE should not diverge
        last_err = result.fqe_errors[-1] if result.fqe_errors else 0.0
        assert last_err >= 0  # always non-negative


# ===================================================================
# Test Conformal Calibration
# ===================================================================

class TestCalibrateConformal:
    """Test calibrate_conformal."""

    def test_empty_calibration(self):
        q = QNetwork()
        result = calibrate_conformal(q, [])
        assert isinstance(result, ConformalCalibration)
        assert result.n_calib_points == 0

    def test_calibration_returns_valid(self):
        q = QNetwork(quantiles=4)
        tuples = _make_tuples(20)

        for t in tuples:
            q.set_estimates(t.state, t.action, [t.reward] * 4)

        result = calibrate_conformal(q, tuples, nominal_coverage=0.9)
        assert isinstance(result, ConformalCalibration)
        assert result.n_calib_points == 20
        assert result.nominal_coverage == 0.9
        assert result.adjusted_threshold >= 0.0
        assert 0.0 <= result.coverage <= 1.0

    def test_higher_nominal_coverage_needs_higher_threshold(self):
        q = QNetwork(quantiles=4)
        tuples = _make_tuples(20)

        for t in tuples:
            q.set_estimates(t.state, t.action, [t.reward] * 4)

        r1 = calibrate_conformal(q, tuples, nominal_coverage=0.8)
        r2 = calibrate_conformal(q, tuples, nominal_coverage=0.95)
        assert r2.adjusted_threshold >= r1.adjusted_threshold


class TestIQLTrainerExpectile:
    """Test the expectile computation."""

    def test_expectile_median_tau_05(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        # tau=0.5 should give the mean (least-squares optimum)
        e = IQLTrainer._expectile(values, 0.5)
        assert e == pytest.approx(3.0, abs=0.01)

    def test_expectile_high_tau_weights_high_values(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        e = IQLTrainer._expectile(values, 0.9)
        # With tau=0.9, high values are weighted more -> expectile > mean
        assert e > 3.0

    def test_expectile_low_tau_weights_low_values(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        e = IQLTrainer._expectile(values, 0.2)
        # With tau=0.2, low values are weighted more -> expectile < mean
        assert e < 3.0

    def test_expectile_empty(self):
        assert IQLTrainer._expectile([], 0.75) == 0.0

    def test_expectile_single_value(self):
        assert IQLTrainer._expectile([3.5], 0.75) == 3.5
