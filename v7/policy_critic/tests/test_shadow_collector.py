"""Tests for v7.policy_critic.shadow_collector — shadow replay buffer."""

import pytest

from v7.policy_critic.replay_buffer import (
    CRITIC_ACTION_LONG,
    CRITIC_ACTION_NO_TRADE,
    CRITIC_ACTION_SHORT,
)
from v7.policy_critic.shadow_collector import (
    _DEFAULT_TARGET_RATIOS,
    ShadowCollector,
    ShadowIntegration,
    ShadowTuple,
    SubsamplingStrategy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decision_event(**overrides) -> dict:
    """Build a minimal DecisionEvent dict for testing."""
    base = {
        "event_id": "de_test_001",
        "decision_event_id": "de_test_001",
        "symbol": "BTCUSDT",
        "event_type": "ENTER_LONG",
        "decision": "ENTER_LONG",
        "request": {
            "symbol": "BTCUSDT",
            "mode": "SWING",
            "decision": "ENTER_LONG",
            "confidence": 0.72,
            "entry_price": 64300.0,
            "stop_loss_price": 62000.0,
            "take_profit_price": 67000.0,
            "position_size_pct": 5.0,
            "execution_eligibility": {"overall_eligible": True},
            "market_context": {
                "atr": 1800.0,
                "spread_bps": 0.5,
                "volatility": 0.25,
            },
        },
    }
    base.update(overrides)
    return base


def _trade_outcome(**overrides) -> dict:
    """Build a minimal TradeOutcome dict for testing."""
    base = {
        "event_id": "de_test_001",
        "exit_reason": "TARGET_HIT",
        "realized_r_net": 0.85,
        "realized_r_gross": 1.20,
        "fee_cost_r": 0.20,
        "slippage_cost_r": 0.10,
        "funding_cost_r": 0.05,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Test ShadowTuple
# ---------------------------------------------------------------------------

class TestShadowTuple:
    """Test ShadowTuple dataclass."""

    def test_defaults(self):
        t = ShadowTuple(state={}, action="LONG", reward=0.0, next_state={}, terminal=False)
        assert t.symbol == ""
        assert t.event_id == ""

    def test_frozen(self):
        t = ShadowTuple(state={}, action="LONG", reward=0.0, next_state={}, terminal=False)
        with pytest.raises(AttributeError):
            t.action = "SHORT"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test ShadowCollector
# ---------------------------------------------------------------------------

class TestShadowCollector:
    """Test ShadowCollector static methods."""

    def test_collect_from_paper_basic(self):
        """Happy path: collect with full event and outcome."""
        event = _decision_event()
        outcome = _trade_outcome()
        shadow = ShadowCollector.collect_from_paper(event, outcome)
        assert shadow is not None
        assert isinstance(shadow, ShadowTuple)
        assert shadow.action == CRITIC_ACTION_LONG
        assert shadow.reward == 0.85
        assert shadow.terminal is False  # TARGET_HIT not COMPLETE
        assert shadow.symbol == "BTCUSDT"
        assert shadow.event_id == "de_test_001"

    def test_collect_no_outcome(self):
        """No trade outcome -> reward defaults to 0.0."""
        event = _decision_event()
        shadow = ShadowCollector.collect_from_paper(event, None)
        assert shadow is not None
        assert shadow.reward == 0.0
        assert shadow.terminal is False

    def test_collect_terminal_complete(self):
        """exit_reason=COMPLETE -> terminal=True."""
        event = _decision_event()
        outcome = _trade_outcome(exit_reason="COMPLETE")
        shadow = ShadowCollector.collect_from_paper(event, outcome)
        assert shadow is not None
        assert shadow.terminal is True

    def test_collect_terminal_flag(self):
        """terminal=True in outcome -> terminal=True."""
        event = _decision_event()
        outcome = _trade_outcome(terminal=True)
        shadow = ShadowCollector.collect_from_paper(event, outcome)
        assert shadow is not None
        assert shadow.terminal is True

    def test_collect_no_request(self):
        """Missing request/analysis_result -> None."""
        event = _decision_event()
        del event["request"]
        shadow = ShadowCollector.collect_from_paper(event, _trade_outcome())
        assert shadow is None

    def test_collect_unknown_action(self):
        """Unrecognised decision -> None."""
        event = _decision_event(decision="INVALID", event_type="INVALID",
                                request={"decision": "INVALID"})
        shadow = ShadowCollector.collect_from_paper(event, _trade_outcome())
        assert shadow is None

    def test_extract_state_basic(self):
        """Happy path: extract state from request."""
        event = _decision_event()
        request = event["request"]
        state = ShadowCollector.extract_state(request)
        assert state["symbol"] == "BTCUSDT"
        assert state["mode"] == "SWING"
        assert state["confidence"] == 0.72
        assert state["decision"] == "ENTER_LONG"
        assert state["gate_overall"] is True
        assert state["atr"] == 1800.0
        assert state["spread_bps"] == 0.5

    def test_extract_state_empty_request(self):
        """Empty request -> default values."""
        state = ShadowCollector.extract_state({})
        assert state["symbol"] == ""
        assert state["confidence"] == 0.0
        assert state["gate_overall"] is False

    def test_extract_state_no_market_context(self):
        """Missing market_context -> defaults."""
        request = {"symbol": "ETHUSDT", "mode": "SCALP", "decision": "HOLD"}
        state = ShadowCollector.extract_state(request)
        assert state["atr"] == 0.0

    def test_extract_action_from_top_level(self):
        """Action from top-level 'decision' key."""
        event = _decision_event()
        action = ShadowCollector.extract_action(event)
        assert action == CRITIC_ACTION_LONG

    def test_extract_action_from_request(self):
        """Fallback to request.decision when top-level missing."""
        event = _decision_event()
        del event["decision"]
        action = ShadowCollector.extract_action(event)
        assert action == CRITIC_ACTION_LONG

    def test_extract_action_short(self):
        """SHORT action maps correctly."""
        event = _decision_event(decision="ENTER_SHORT",
                                request={"decision": "ENTER_SHORT"})
        action = ShadowCollector.extract_action(event)
        assert action == CRITIC_ACTION_SHORT

    def test_extract_action_no_trade(self):
        """NO_TRADE / HOLD maps to NO_TRADE."""
        event = _decision_event(decision="HOLD",
                                request={"decision": "HOLD"})
        action = ShadowCollector.extract_action(event)
        assert action == CRITIC_ACTION_NO_TRADE

    def test_extract_action_no_decision(self):
        """No decision found -> None."""
        action = ShadowCollector.extract_action({})
        assert action is None

    def test_extract_reward_from_outcome(self):
        """Reward from realized_r_net."""
        outcome = _trade_outcome(realized_r_net=1.50)
        reward = ShadowCollector.extract_reward(outcome)
        assert reward == 1.50

    def test_extract_reward_none(self):
        """None outcome -> 0.0."""
        assert ShadowCollector.extract_reward(None) == 0.0

    def test_extract_reward_missing_field(self):
        """Missing realized_r_net -> 0.0."""
        assert ShadowCollector.extract_reward({}) == 0.0

    def test_is_terminal_complete(self):
        """exit_reason=COMPLETE -> True."""
        assert ShadowCollector.is_terminal(_trade_outcome(exit_reason="COMPLETE")) is True

    def test_is_terminal_take_profit(self):
        """exit_reason=TARGET_HIT -> False."""
        assert ShadowCollector.is_terminal(_trade_outcome(exit_reason="TARGET_HIT")) is False

    def test_is_terminal_flag(self):
        """terminal=True in outcome -> True."""
        assert ShadowCollector.is_terminal(_trade_outcome(terminal=True)) is True

    def test_is_terminal_none(self):
        """None outcome -> False."""
        assert ShadowCollector.is_terminal(None) is False

    def test_collect_with_next_state(self):
        """next_state_override is respected."""
        event = _decision_event()
        next_state = {"symbol": "BTCUSDT", "confidence": 0.65}
        shadow = ShadowCollector.collect_from_paper(
            event, _trade_outcome(), next_state_override=next_state
        )
        assert shadow is not None
        assert shadow.next_state == next_state

    def test_collect_analysis_result_fallback(self):
        """Fallback to analysis_result when request is missing."""
        event = _decision_event()
        del event["request"]
        event["analysis_result"] = {
            "symbol": "BTCUSDT",
            "mode": "SWING",
            "decision": "ENTER_LONG",
            "confidence": 0.72,
            "entry_price": 64300.0,
        }
        shadow = ShadowCollector.collect_from_paper(event, _trade_outcome())
        assert shadow is not None
        assert shadow.action == CRITIC_ACTION_LONG
        assert shadow.reward == 0.85


# ---------------------------------------------------------------------------
# Test SubsamplingStrategy
# ---------------------------------------------------------------------------

class TestSubsamplingStrategy:
    """Test SubsamplingStrategy rebalancing."""

    def _make_tuples(self, actions: list[str]) -> list[ShadowTuple]:
        """Create ShadowTuples with specified actions."""
        tuples = []
        for i, action in enumerate(actions):
            tuples.append(ShadowTuple(
                state={"idx": i},
                action=action,
                reward=0.0,
                next_state={},
                terminal=False,
                symbol="TEST",
                event_id=f"e{i}",
            ))
        return tuples

    def test_rebalance_no_tuples(self):
        """Empty list returns empty list."""
        strategy = SubsamplingStrategy()
        assert strategy.rebalance([]) == []

    def test_rebalance_preserves_single_action(self):
        """Single action class -> returned as-is."""
        tuples = self._make_tuples(["LONG", "LONG", "LONG"])
        strategy = SubsamplingStrategy()
        result = strategy.rebalance(tuples)
        assert len(result) == 3
        assert all(t.action == "LONG" for t in result)

    def test_rebalance_balanced(self):
        """Already-balanced distribution passes through mostly."""
        tuples = self._make_tuples(
            ["LONG"] * 35 + ["SHORT"] * 35 + ["NO_TRADE"] * 30
        )
        strategy = SubsamplingStrategy()
        result = strategy.rebalance(tuples)
        # Should have at most 35 + 35 + 30 = 100 tuples
        assert len(result) <= 100

    def test_rebalance_imbalanced(self):
        """Heavily skewed distribution gets rebalanced."""
        tuples = self._make_tuples(
            ["NO_TRADE"] * 800 + ["LONG"] * 100 + ["SHORT"] * 100
        )
        strategy = SubsamplingStrategy()
        result = strategy.rebalance(tuples)
        # Count per action
        counts = {}
        for t in result:
            counts[t.action] = counts.get(t.action, 0) + 1
        # NO_TRADE should be reduced significantly
        assert counts.get("NO_TRADE", 0) < 500

    def test_rebalance_preserves_order(self):
        """Relative order within each class is preserved."""
        tuples = self._make_tuples(
            ["LONG", "NO_TRADE", "SHORT", "NO_TRADE", "LONG", "NO_TRADE"]
        )
        strategy = SubsamplingStrategy()
        result = strategy.rebalance(tuples)
        # Check LONGs remain in original order
        long_actions = [t for t in result if t.action == "LONG"]
        assert len(long_actions) >= 1
        assert long_actions[0].event_id == "e0"

    def test_target_ratios_property(self):
        """target_ratios returns a copy of the configured ratios."""
        strategy = SubsamplingStrategy({"LONG": 0.5})
        ratios = strategy.target_ratios
        assert ratios["LONG"] == 0.5
        # Defaults for unspecified keys
        assert ratios["SHORT"] == _DEFAULT_TARGET_RATIOS["SHORT"]

    def test_custom_target_ratios(self):
        """Custom target ratios are respected."""
        tuples = self._make_tuples(
            ["LONG"] * 50 + ["SHORT"] * 50 + ["NO_TRADE"] * 200
        )
        strategy = SubsamplingStrategy({"LONG": 0.5, "SHORT": 0.5})
        result = strategy.rebalance(tuples)
        # NO_TRADE not in target ratios -> not downsampled
        assert any(t.action == "NO_TRADE" for t in result)


# ---------------------------------------------------------------------------
# Test ShadowIntegration
# ---------------------------------------------------------------------------

class TestShadowIntegration:
    """Test ShadowIntegration end-to-end."""

    def test_observe_basic(self):
        """Happy path: observe adds a tuple."""
        integration = ShadowIntegration()
        event = _decision_event()
        outcome = _trade_outcome()
        shadow = integration.observe(event, outcome)
        assert shadow is not None
        assert integration.size == 1

    def test_observe_skipped(self):
        """Invalid event -> None, size unchanged."""
        integration = ShadowIntegration()
        shadow = integration.observe({}, None)
        assert shadow is None
        assert integration.size == 0

    def test_observe_multiple(self):
        """Multiple observations accumulate."""
        integration = ShadowIntegration()
        for i in range(5):
            event = _decision_event(event_id=f"de_{i}", decision_event_id=f"de_{i}")
            outcome = _trade_outcome(realized_r_net=i * 0.1)
            integration.observe(event, outcome)
        assert integration.size == 5
        assert integration.get_statistics()["total_tuples"] == 5

    def test_fifo_eviction(self):
        """Buffer evicts oldest when max_size exceeded."""
        integration = ShadowIntegration(max_buffer_size=3)
        for i in range(5):
            event = _decision_event(event_id=f"de_{i}", decision_event_id=f"de_{i}")
            integration.observe(event, _trade_outcome())
        assert integration.size == 3
        # Oldest event_ids should be gone
        ids = [t.event_id for t in integration.buffer]
        assert "de_0" not in ids
        assert "de_2" in ids

    def test_get_statistics_empty(self):
        """Empty buffer returns all-zero stats."""
        integration = ShadowIntegration()
        stats = integration.get_statistics()
        assert stats["total_tuples"] == 0
        assert stats["action_distribution"] == {}
        assert stats["buffer_fill_pct"] == 0.0

    def test_get_statistics_populated(self):
        """Populated buffer returns meaningful stats."""
        integration = ShadowIntegration()
        # Use V7 decision names that map correctly to critic space
        actions_decision_map = [
            ("ENTER_LONG", 3),
            ("ENTER_SHORT", 2),
            ("HOLD", 5),
        ]
        for decision, count in actions_decision_map:
            for i in range(count):
                event = _decision_event(
                    event_id=f"de_{decision}_{i}",
                    decision_event_id=f"de_{decision}_{i}",
                    decision=decision,
                    request={"decision": decision,
                             "symbol": "BTCUSDT", "mode": "SWING"},
                )
                outcome = _trade_outcome(realized_r_net=0.5)
                integration.observe(event, outcome)
        stats = integration.get_statistics()
        assert stats["total_tuples"] == 10
        assert stats["action_distribution"]["LONG"] == 3
        assert stats["action_distribution"]["SHORT"] == 2
        assert stats["action_distribution"]["NO_TRADE"] == 5
        assert stats["unique_symbols"] == 1
        assert stats["buffer_fill_pct"] > 0
        assert stats["mean_reward"] == 0.5

    def test_get_statistics_terminal_ratio(self):
        """Terminal ratio is computed correctly."""
        integration = ShadowIntegration()
        # 2 terminal + 3 non-terminal
        for i in range(3):
            integration.observe(
                _decision_event(event_id=f"de_nt_{i}"),
                _trade_outcome(exit_reason="STOP_LOSS"),
            )
        for i in range(2):
            integration.observe(
                _decision_event(event_id=f"de_t_{i}"),
                _trade_outcome(exit_reason="COMPLETE"),
            )
        stats = integration.get_statistics()
        assert stats["terminal_count"] == 2
        assert stats["terminal_ratio"] == 0.4

    def test_get_subsampled(self):
        """Subsampled view returns rebalanced tuples."""
        integration = ShadowIntegration()
        for _ in range(100):
            integration.observe(
                _decision_event(decision="HOLD",
                                request={"decision": "HOLD",
                                         "symbol": "BTCUSDT", "mode": "SWING"}),
                _trade_outcome(realized_r_net=0.0),
            )
        for _ in range(10):
            integration.observe(
                _decision_event(),
                _trade_outcome(realized_r_net=1.0),
            )
        subsampled = integration.get_subsampled()
        assert len(subsampled) < 110  # NO_TRATE downsampled
        assert any(t.action == CRITIC_ACTION_LONG for t in subsampled)

    def test_get_subsampled_with_custom_ratios(self):
        """Custom ratios override defaults."""
        integration = ShadowIntegration()
        for _ in range(50):
            integration.observe(
                _decision_event(event_id=f"de_long_{_}",
                                decision="ENTER_LONG",
                                request={"decision": "ENTER_LONG",
                                         "symbol": "X", "mode": "SWING"}),
                _trade_outcome(realized_r_net=0.5),
            )
        subsampled = integration.get_subsampled({"LONG": 0.5, "SHORT": 0.5, "NO_TRADE": 0.0})
        # NO_TRADE ratio is 0.0 -> should be excluded
        assert subsampled  # non-empty
        for t in subsampled:
            assert t.action != "NO_TRADE"

    def test_clear(self):
        """Clear removes all tuples."""
        integration = ShadowIntegration()
        integration.observe(_decision_event(), _trade_outcome())
        assert integration.size == 1
        integration.clear()
        assert integration.size == 0
        assert integration.buffer == []

    def test_buffer_property(self):
        """buffer property returns a copy."""
        integration = ShadowIntegration()
        integration.observe(_decision_event(), _trade_outcome())
        buf = integration.buffer
        assert len(buf) == 1
        # Modifying returned list does not affect internal buffer
        buf.clear()
        assert integration.size == 1
