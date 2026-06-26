"""Tests for v7.policy_critic.replay_buffer — replay buffer and tuple construction."""

import pytest

from v7.policy_critic.replay_buffer import (
    CRITIC_ACTION_LONG,
    CRITIC_ACTION_SHORT,
    CRITIC_ACTION_NO_TRADE,
    ReplayBuffer,
    ReplayTuple,
    build_replay_tuple,
    build_state_feature_vector,
    map_decision_to_critic_action,
)


class TestMapDecisionToCriticAction:
    """Test V7 decision -> critic action space mapping."""

    def test_enter_long_maps_to_long(self):
        assert map_decision_to_critic_action("ENTER_LONG") == CRITIC_ACTION_LONG

    def test_enter_short_maps_to_short(self):
        assert map_decision_to_critic_action("ENTER_SHORT") == CRITIC_ACTION_SHORT

    def test_exit_long_maps_to_no_trade(self):
        assert map_decision_to_critic_action("EXIT_LONG") == CRITIC_ACTION_NO_TRADE

    def test_exit_short_maps_to_no_trade(self):
        assert map_decision_to_critic_action("EXIT_SHORT") == CRITIC_ACTION_NO_TRADE

    def test_hold_maps_to_no_trade(self):
        assert map_decision_to_critic_action("HOLD") == CRITIC_ACTION_NO_TRADE

    def test_unknown_decision_raises(self):
        with pytest.raises(ValueError, match="Unknown decision"):
            map_decision_to_critic_action("INVALID_ACTION")


class TestBuildStateFeatureVector:
    """Test state feature vector construction from AnalysisResult."""

    def _minimal_analysis_result(self, **overrides):
        base = {
            "analysis_result_id": "ar_test_001",
            "request_id": "req_001",
            "decision": "ENTER_LONG",
            "confidence": 0.72,
            "stop_loss_price": 62000.0,
            "take_profit_price": 67000.0,
            "entry_price": 64300.0,
            "position_size_pct": 5.0,
            "reasoning": "Test",
            "model_signature": "swing_v1@abc",
            "analysis_timestamp": "2026-06-01T12:00:00Z",
            "execution_eligibility": {
                "confidence_gate": True,
                "risk_gate": True,
                "regime_gate": True,
                "cost_gate": True,
                "overall_eligible": True,
            },
            "mode": "SWING",
            "symbol": "BTCUSDT",
        }
        base.update(overrides)
        return base

    def test_basic_state_extraction(self):
        ar = self._minimal_analysis_result()
        state = build_state_feature_vector(analysis_result=ar)
        assert state["symbol"] == "BTCUSDT"
        assert state["mode"] == "SWING"
        assert state["confidence"] == 0.72
        assert state["entry_price"] == 64300.0
        assert state["decision"] == "ENTER_LONG"

    def test_gate_flags_extracted(self):
        ar = self._minimal_analysis_result()
        state = build_state_feature_vector(analysis_result=ar)
        assert state["gate_confidence"] is True
        assert state["gate_risk"] is True
        assert state["gate_regime"] is True
        assert state["gate_cost"] is True
        assert state["gate_overall"] is True

    def test_missing_eligibility_handled(self):
        ar = self._minimal_analysis_result()
        del ar["execution_eligibility"]
        state = build_state_feature_vector(analysis_result=ar)
        # Should not raise; gates default to False when eligibility is not a dict
        # (it'll be missing so eligibility defaults to {} which is a dict, just empty)
        assert state["gate_confidence"] is False

    def test_kwargs_merged_into_state(self):
        ar = self._minimal_analysis_result()
        state = build_state_feature_vector(
            analysis_result=ar,
            regime_label="bull",
            atr=1800.0,
            volatility=0.028,
        )
        assert state["regime_label"] == "bull"
        assert state["atr"] == 1800.0
        assert state["volatility"] == 0.028

    def test_kwargs_override_conflict_preserved(self):
        """kwargs collision with existing state keys now raises ValueError."""
        ar = self._minimal_analysis_result()
        with pytest.raises(ValueError, match="collide"):
            build_state_feature_vector(
                analysis_result=ar,
                confidence=0.99,  # collision
            )

    def test_kwargs_collision_with_gate_key_raises(self):
        """kwargs that collide with a gate_* key also raise ValueError."""
        ar = self._minimal_analysis_result()
        with pytest.raises(ValueError, match="collide"):
            build_state_feature_vector(
                analysis_result=ar,
                gate_confidence=False,  # collision with eligibility gate key
            )

    def test_kwargs_collision_lists_all_offending_keys(self):
        """Multiple collisions should list all offending keys in the error."""
        ar = self._minimal_analysis_result()
        with pytest.raises(ValueError, match=r"collide.*(confidence|symbol|symbol.*confidence)"):
            build_state_feature_vector(
                analysis_result=ar,
                confidence=0.99,
                symbol="ETHUSDT",
            )

    def test_kwargs_no_collision_works(self):
        """Distinct keys should still be merged without error."""
        ar = self._minimal_analysis_result()
        state = build_state_feature_vector(
            analysis_result=ar,
            regime_label="bull",
            atr=1800.0,
            volatility=0.028,
            spread_bps=2.0,
        )
        assert state["regime_label"] == "bull"
        assert state["atr"] == 1800.0
        assert state["volatility"] == 0.028
        assert state["spread_bps"] == 2.0
        # Base keys should remain untouched
        assert state["confidence"] == 0.72
        assert state["symbol"] == "BTCUSDT"

    def test_hold_decision_state(self):
        ar = self._minimal_analysis_result(decision="HOLD", confidence=0.40)
        state = build_state_feature_vector(analysis_result=ar)
        assert state["decision"] == "HOLD"
        assert state["confidence"] == 0.40


class TestBuildReplayTuple:
    """Test ReplayTuple construction from contracts."""

    def _minimal_analysis_result(self, **overrides):
        return {
            "analysis_result_id": "ar_test_001",
            "request_id": "req_001",
            "decision": "ENTER_LONG",
            "confidence": 0.72,
            "stop_loss_price": 62000.0,
            "take_profit_price": 67000.0,
            "entry_price": 64300.0,
            "position_size_pct": 5.0,
            "reasoning": "Test",
            "model_signature": "swing_v1@abc",
            "analysis_timestamp": "2026-06-01T12:00:00Z",
            "execution_eligibility": {
                "confidence_gate": True,
                "risk_gate": True,
                "regime_gate": True,
                "cost_gate": True,
                "overall_eligible": True,
            },
            "mode": "SWING",
            "symbol": "BTCUSDT",
            **overrides,
        }

    def test_basic_tuple_from_long_decision(self):
        ar = self._minimal_analysis_result()
        tup = build_replay_tuple(
            analysis_result=ar,
            realized_r_net=0.85,
            next_state={"confidence": 0.65},
            terminal=False,
        )
        assert tup.action == CRITIC_ACTION_LONG
        assert tup.reward == 0.85
        assert tup.next_state["confidence"] == 0.65
        assert tup.terminal is False
        assert tup.symbol == "BTCUSDT"
        assert tup.mode == "SWING"

    def test_no_trade_tuple(self):
        ar = self._minimal_analysis_result(decision="HOLD")
        tup = build_replay_tuple(
            analysis_result=ar,
            realized_r_net=0.0,
            terminal=True,
        )
        assert tup.action == CRITIC_ACTION_NO_TRADE
        assert tup.reward == 0.0
        assert tup.terminal is True

    def test_simulation_output_preferred_for_reward(self):
        """When simulation_output is given, it should override explicit params."""
        ar = self._minimal_analysis_result()
        sim_out = {
            "long_outcome": {
                "realized_r_net": 1.25,
                "realized_r_gross": 1.50,
                "fee_cost_r": 0.10,
                "slippage_cost_r": 0.05,
                "funding_cost_r": 0.10,
            },
        }
        tup = build_replay_tuple(
            analysis_result=ar,
            simulation_output=sim_out,
            realized_r_net=0.85,  # Should be overridden
        )
        assert tup.reward == 1.25
        assert tup.realized_r_gross == 1.50
        assert tup.fee_cost_r == 0.10

    def test_short_action_from_simulation(self):
        ar = self._minimal_analysis_result(decision="ENTER_SHORT")
        sim_out = {
            "short_outcome": {
                "realized_r_net": -0.35,
                "realized_r_gross": 0.10,
                "fee_cost_r": 0.15,
                "slippage_cost_r": 0.10,
                "funding_cost_r": 0.20,
            },
        }
        tup = build_replay_tuple(
            analysis_result=ar,
            simulation_output=sim_out,
        )
        assert tup.action == CRITIC_ACTION_SHORT
        assert tup.reward == -0.35
        assert tup.fee_cost_r == 0.15

    def test_no_trade_reward_zero(self):
        """NO_TRADE always has reward 0.0 regardless of simulation output."""
        ar = self._minimal_analysis_result(decision="HOLD")
        sim_out = {
            "no_trade_outcome": {
                "saved_loss_r": 0.50,
                "missed_opportunity_r": 0.30,
            },
        }
        tup = build_replay_tuple(
            analysis_result=ar,
            simulation_output=sim_out,
        )
        assert tup.action == CRITIC_ACTION_NO_TRADE
        assert tup.reward == 0.0

    def test_replay_tuple_immutable(self):
        ar = self._minimal_analysis_result()
        tup = build_replay_tuple(analysis_result=ar, realized_r_net=0.5)
        with pytest.raises(Exception):
            tup.reward = 1.0  # type: ignore


class TestReplayBuffer:
    """Test ReplayBuffer FIFO storage."""

    def _make_tuple(self, symbol="BTCUSDT", mode="SWING", reward=0.5):
        return ReplayTuple(
            state={"symbol": symbol, "mode": mode},
            action=CRITIC_ACTION_LONG,
            reward=reward,
            next_state={},
            terminal=False,
            decision_event_id="evt_test",
            symbol=symbol,
            mode=mode,
        )

    def test_add_and_len(self):
        buf = ReplayBuffer(capacity=10)
        buf.add(state={}, action=CRITIC_ACTION_LONG, reward=0.5, next_state={}, terminal=False)
        assert len(buf) == 1

    def test_capacity_eviction(self):
        buf = ReplayBuffer(capacity=3)
        for i in range(5):
            buf.add(state={}, action=CRITIC_ACTION_LONG, reward=float(i), next_state={}, terminal=False)
        assert len(buf) == 3
        # First two should be evicted; rewards should be 2, 3, 4
        rewards = [t.reward for t in buf.sample(3)]
        assert rewards == [2.0, 3.0, 4.0]

    def test_sample_returns_newest(self):
        buf = ReplayBuffer(capacity=10)
        for i in range(5):
            buf.add(state={}, action=CRITIC_ACTION_LONG, reward=float(i), next_state={}, terminal=False)
        sample = buf.sample(3)
        assert len(sample) == 3
        assert [t.reward for t in sample] == [2.0, 3.0, 4.0]

    def test_sample_more_than_available(self):
        buf = ReplayBuffer(capacity=100)
        buf.add(state={}, action=CRITIC_ACTION_LONG, reward=1.0, next_state={}, terminal=False)
        buf.add(state={}, action=CRITIC_ACTION_SHORT, reward=2.0, next_state={}, terminal=False)
        sample = buf.sample(10)
        assert len(sample) == 2

    def test_sample_by_mode(self):
        buf = ReplayBuffer(capacity=10)
        buf.add(
            state={}, action=CRITIC_ACTION_LONG, reward=1.0,
            next_state={}, terminal=False, mode="SWING",
        )
        buf.add(
            state={}, action=CRITIC_ACTION_LONG, reward=2.0,
            next_state={}, terminal=False, mode="SWING",
        )
        buf.add(
            state={}, action=CRITIC_ACTION_SHORT, reward=3.0,
            next_state={}, terminal=False, mode="SCALP",
        )
        swing_sample = buf.sample_by_mode("SWING", 5)
        assert len(swing_sample) == 2
        assert all(t.mode == "SWING" for t in swing_sample)

        scalp_sample = buf.sample_by_mode("SCALP", 5)
        assert len(scalp_sample) == 1
        assert scalp_sample[0].mode == "SCALP"

    def test_clear(self):
        buf = ReplayBuffer(capacity=10)
        buf.add(state={}, action=CRITIC_ACTION_LONG, reward=0.5, next_state={}, terminal=False)
        assert len(buf) == 1
        buf.clear()
        assert len(buf) == 0

    def test_terminal_tuple(self):
        tup = self._make_tuple()
        tup2 = ReplayTuple(
            state={"symbol": "ETHUSDT"},
            action=CRITIC_ACTION_NO_TRADE,
            reward=0.0,
            next_state={},
            terminal=True,
            decision_event_id="evt_term",
            symbol="ETHUSDT",
            mode="SWING",
        )
        assert tup2.terminal is True
        assert tup2.reward == 0.0
