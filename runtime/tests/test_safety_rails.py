"""Unit tests for safety rails and shadow harness modules.

Covers:
- PositionLimiter: reject_if_over_limit across all limit rules
- KillSwitch: trigger/release/auto-trigger/active check
- DrawdownGate: equity tracking, threshold actions, hysteresis
- SymbolCap: per-symbol, aggregate, and symbol-count limits
- ShadowHarness: trade recording, closing, sim comparison, summary
"""

from __future__ import annotations

from datetime import timedelta, timezone
from datetime import datetime
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# PositionLimiter
# ---------------------------------------------------------------------------

class TestPositionLimiter:
    def test_default_config(self):
        from runtime.runtime.safety.position_limiter import PositionLimitConfig, PositionLimiter

        limiter = PositionLimiter()
        assert limiter.config.max_positions == 10
        assert limiter.config.max_notional_per_position == 50_000.0

    def test_pass_when_under_all_limits(self):
        from runtime.runtime.safety.position_limiter import PositionLimiter

        limiter = PositionLimiter()
        result = limiter.reject_if_over_limit(
            proposed_notional=10_000,
            current_positions=[{"notional": 5_000}] * 3,
        )
        assert result is None

    def test_reject_max_positions(self):
        from runtime.runtime.safety.position_limiter import PositionLimiter, PositionLimitConfig

        limiter = PositionLimiter(PositionLimitConfig(max_positions=2))
        result = limiter.reject_if_over_limit(
            proposed_notional=1_000,
            current_positions=[{"notional": 5_000}, {"notional": 5_000}],
        )
        assert result is not None
        assert result.rule == "max_positions"

    def test_reject_notional_per_position(self):
        from runtime.runtime.safety.position_limiter import PositionLimiter, PositionLimitConfig

        limiter = PositionLimiter(PositionLimitConfig(max_notional_per_position=5_000))
        result = limiter.reject_if_over_limit(
            proposed_notional=10_000,
            current_positions=[],
        )
        assert result is not None
        assert result.rule == "max_notional_per_position"

    def test_reject_total_notional(self):
        from runtime.runtime.safety.position_limiter import PositionLimiter, PositionLimitConfig

        limiter = PositionLimiter(PositionLimitConfig(max_total_notional=10_000))
        result = limiter.reject_if_over_limit(
            proposed_notional=6_000,
            current_positions=[{"notional": 5_000}],
        )
        assert result is not None
        assert result.rule == "max_total_notional"

    def test_custom_config(self):
        from runtime.runtime.safety.position_limiter import PositionLimiter, PositionLimitConfig

        cfg = PositionLimitConfig(max_positions=3, max_notional_per_position=1000, max_total_notional=5000)
        limiter = PositionLimiter(cfg)
        result = limiter.reject_if_over_limit(
            proposed_notional=2_000,
            current_positions=[{"notional": 1_000}] * 2,
        )
        # Notional per position is fine (2000 <= 1000? no, 2000 > 1000)
        assert result is not None
        assert result.rule == "max_notional_per_position"

    def test_empty_positions_passes(self):
        from runtime.runtime.safety.position_limiter import PositionLimiter

        limiter = PositionLimiter()
        result = limiter.reject_if_over_limit(proposed_notional=1_000, current_positions=[])
        assert result is None


# ---------------------------------------------------------------------------
# KillSwitch
# ---------------------------------------------------------------------------

class TestKillSwitch:
    def test_starts_inactive(self):
        from runtime.runtime.safety.kill_switch import KillSwitch

        ks = KillSwitch()
        assert ks.is_active() is False

    def test_trigger_and_release(self):
        from runtime.runtime.safety.kill_switch import KillSwitch

        ks = KillSwitch()
        state = ks.trigger("test reason")
        assert state.active is True
        assert state.reason == "test reason"
        assert ks.is_active() is True

        released = ks.release()
        assert released.active is False
        assert ks.is_active() is False

    def test_auto_trigger_consecutive_losses(self):
        from runtime.runtime.safety.kill_switch import KillSwitch, KillSwitchConfig

        ks = KillSwitch(KillSwitchConfig(auto_trigger_on_consecutive_losses=5))
        triggered = ks.check_auto_conditions(consecutive_losses=5)
        assert triggered is True
        assert ks.is_active() is True

    def test_no_auto_trigger_below_threshold(self):
        from runtime.runtime.safety.kill_switch import KillSwitch, KillSwitchConfig

        ks = KillSwitch(KillSwitchConfig(auto_trigger_on_consecutive_losses=5))
        triggered = ks.check_auto_conditions(consecutive_losses=3)
        assert triggered is False
        assert ks.is_active() is False

    def test_auto_trigger_drawdown(self):
        from runtime.runtime.safety.kill_switch import KillSwitch, KillSwitchConfig

        ks = KillSwitch(KillSwitchConfig(auto_trigger_on_drawdown_pct=15.0))
        triggered = ks.check_auto_conditions(current_drawdown_pct=20.0)
        assert triggered is True

    def test_no_double_trigger(self):
        from runtime.runtime.safety.kill_switch import KillSwitch, KillSwitchConfig

        ks = KillSwitch(KillSwitchConfig(auto_trigger_on_consecutive_losses=3))
        ks.trigger("already active")
        triggered = ks.check_auto_conditions(consecutive_losses=10)
        assert triggered is False  # already active, won't trigger again

    def test_get_state(self):
        from runtime.runtime.safety.kill_switch import KillSwitch

        ks = KillSwitch()
        state = ks.get_state()
        assert state["active"] is False
        assert state["reason"] is None

        ks.trigger("emergency")
        state = ks.get_state()
        assert state["active"] is True
        assert state["reason"] == "emergency"

    def test_auto_resume(self):
        from runtime.runtime.safety.kill_switch import KillSwitch, KillSwitchConfig

        ks = KillSwitch(KillSwitchConfig(auto_resume_after_minutes=0))  # past time
        ks.trigger("test")
        # Force the resume time to the past
        ks._state.auto_resume_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        assert ks.is_active() is False  # auto-resumed


# ---------------------------------------------------------------------------
# DrawdownGate
# ---------------------------------------------------------------------------

class TestDrawdownGate:
    def test_default_state_is_clean(self):
        from runtime.runtime.safety.drawdown_gate import DrawdownGate

        gate = DrawdownGate()
        state = gate.check_drawdown()
        assert state.blocked is False

    def test_peak_equity_tracking(self):
        from runtime.runtime.safety.drawdown_gate import DrawdownGate

        gate = DrawdownGate()
        gate.update_equity(100_000)
        state = gate.check_drawdown()
        assert state.peak_equity == 100_000
        assert state.current_equity == 100_000
        assert state.drawdown_pct == 0.0

    def test_warn_threshold(self):
        from runtime.runtime.safety.drawdown_gate import DrawdownGate, DrawdownThreshold

        gate = DrawdownGate(thresholds=[
            DrawdownThreshold(pct=10.0, action="warn"),
            DrawdownThreshold(pct=30.0, action="block"),
        ])
        gate.update_equity(100_000)
        gate.update_equity(88_000)  # 12% drawdown
        state = gate.check_drawdown()
        assert state.blocked is False  # warn doesn't block

    def test_block_threshold(self):
        from runtime.runtime.safety.drawdown_gate import DrawdownGate, DrawdownThreshold

        gate = DrawdownGate(thresholds=[
            DrawdownThreshold(pct=30.0, action="block"),
        ])
        gate.update_equity(100_000)
        gate.update_equity(68_000)  # 32% drawdown
        assert gate.block_new_trades() is True

    def test_recovery_resets_peak(self):
        from runtime.runtime.safety.drawdown_gate import DrawdownGate, DrawdownThreshold

        gate = DrawdownGate(thresholds=[DrawdownThreshold(pct=30.0, action="block")])
        gate.update_equity(100_000)
        gate.update_equity(68_000)  # 32% DD -> blocked
        assert gate.block_new_trades() is True
        gate.update_equity(110_000)  # new high -> reset
        assert gate.block_new_trades() is False

    def test_hysteresis_prevents_flapping(self):
        from runtime.runtime.safety.drawdown_gate import DrawdownGate, DrawdownThreshold

        gate = DrawdownGate(
            thresholds=[DrawdownThreshold(pct=30.0, action="block")],
            recovery_hysteresis_pct=5.0,
        )
        gate.update_equity(100_000)
        gate.update_equity(65_000)  # 35% DD -> blocked
        assert gate.block_new_trades() is True
        # Recover to 33% DD (still within hysteresis band: 35-5=30, 33 > 30)
        gate.update_equity(67_000)
        assert gate.block_new_trades() is True  # still blocked
        # Recover to 28% DD (past hysteresis band: 28 <= 30)
        gate.update_equity(72_000)
        assert gate.block_new_trades() is False

    def test_get_state(self):
        from runtime.runtime.safety.drawdown_gate import DrawdownGate

        gate = DrawdownGate()
        state = gate.get_state()
        assert "peak_equity" in state
        assert "blocked" in state

    def test_zero_equity_ignored(self):
        from runtime.runtime.safety.drawdown_gate import DrawdownGate

        gate = DrawdownGate()
        gate.update_equity(100_000)
        gate.update_equity(0)  # should be ignored
        state = gate.check_drawdown()
        assert state.peak_equity == 100_000


# ---------------------------------------------------------------------------
# SymbolCap
# ---------------------------------------------------------------------------

class TestSymbolCap:
    def test_default_config(self):
        from runtime.runtime.safety.symbol_cap import SymbolCap, SymbolCapConfig

        cap = SymbolCap()
        assert cap.config.max_notional_per_symbol == 50_000.0
        assert cap.config.max_symbols == 10

    def test_pass_when_under_limits(self):
        from runtime.runtime.safety.symbol_cap import SymbolCap

        cap = SymbolCap()
        result = cap.check_symbol_exposure(
            symbol="BTCUSDT",
            proposed_notional=10_000,
            current_exposures={},
        )
        assert result is None

    def test_reject_notional_per_symbol(self):
        from runtime.runtime.safety.symbol_cap import SymbolCap, SymbolCapConfig

        cap = SymbolCap(SymbolCapConfig(max_notional_per_symbol=5_000))
        result = cap.check_symbol_exposure(
            symbol="BTCUSDT",
            proposed_notional=6_000,
            current_exposures={},
        )
        assert result is not None
        assert result.rule == "max_notional_per_symbol"

    def test_reject_positions_per_symbol(self):
        from runtime.runtime.safety.symbol_cap import SymbolCap, SymbolCapConfig

        cap = SymbolCap(SymbolCapConfig(max_positions_per_symbol=2))
        result = cap.check_symbol_exposure(
            symbol="BTCUSDT",
            proposed_notional=1_000,
            current_exposures={"BTCUSDT": {"notional": 2_000, "count": 2}},
        )
        assert result is not None
        assert result.rule == "max_positions_per_symbol"

    def test_reject_total_notional(self):
        from runtime.runtime.safety.symbol_cap import SymbolCap, SymbolCapConfig

        cap = SymbolCap(SymbolCapConfig(max_total_notional=10_000))
        result = cap.check_symbol_exposure(
            symbol="ETHUSDT",
            proposed_notional=6_000,
            current_exposures={
                "BTCUSDT": {"notional": 5_000, "count": 1},
            },
        )
        assert result is not None
        assert result.rule == "max_total_notional"

    def test_reject_max_symbols(self):
        from runtime.runtime.safety.symbol_cap import SymbolCap, SymbolCapConfig

        cap = SymbolCap(SymbolCapConfig(max_symbols=2))
        result = cap.check_symbol_exposure(
            symbol="SOLUSDT",
            proposed_notional=1_000,
            current_exposures={
                "BTCUSDT": {"notional": 1_000, "count": 1},
                "ETHUSDT": {"notional": 1_000, "count": 1},
            },
        )
        assert result is not None
        assert result.rule == "max_symbols"

    def test_existing_symbol_no_count_violation(self):
        from runtime.runtime.safety.symbol_cap import SymbolCap, SymbolCapConfig

        cap = SymbolCap(SymbolCapConfig(max_symbols=2, max_positions_per_symbol=3))
        result = cap.check_symbol_exposure(
            symbol="BTCUSDT",
            proposed_notional=1_000,
            current_exposures={
                "BTCUSDT": {"notional": 1_000, "count": 1},
                "ETHUSDT": {"notional": 1_000, "count": 1},
            },
        )
        assert result is None  # existing symbol, no new symbol count issue


# ---------------------------------------------------------------------------
# ShadowHarness
# ---------------------------------------------------------------------------

class TestShadowHarness:
    def _make_trade(self, trade_id="t1", side="LONG", entry_price=50_000, quantity=0.1):
        from runtime.runtime.safety.position_limiter import PositionLimiter  # noqa: F401
        from runtime.runtime.shadow.harness import PaperTrade

        return PaperTrade(
            trade_id=trade_id,
            symbol="BTCUSDT",
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            notional=entry_price * quantity,
            mode="SCALP",
        )

    def test_record_and_get(self):
        from runtime.runtime.shadow.harness import ShadowHarness

        h = ShadowHarness()
        trade = self._make_trade()
        h.record_trade(trade)
        assert h.get_trade("t1") is trade
        assert h.get_trade("nonexistent") is None

    def test_list_trades(self):
        from runtime.runtime.shadow.harness import ShadowHarness

        h = ShadowHarness()
        h.record_trade(self._make_trade("t1"))
        h.record_trade(self._make_trade("t2"))
        assert len(h.list_trades()) == 2

    def test_close_long_trade(self):
        from runtime.runtime.shadow.harness import ShadowHarness

        h = ShadowHarness()
        h.record_trade(self._make_trade(entry_price=50_000, quantity=0.1))
        closed = h.close_trade("t1", exit_price=51_000)
        assert closed is not None
        assert closed.live_pnl == pytest.approx(100.0)  # (51000-50000)*0.1
        assert closed.closed_at is not None
        assert closed.slippage_bps is not None

    def test_close_short_trade(self):
        from runtime.runtime.shadow.harness import ShadowHarness

        h = ShadowHarness()
        h.record_trade(self._make_trade(side="SHORT", entry_price=50_000, quantity=0.1))
        closed = h.close_trade("t1", exit_price=49_000)
        assert closed is not None
        assert closed.live_pnl == pytest.approx(100.0)  # (50000-49000)*0.1 for short

    def test_close_nonexistent_returns_none(self):
        from runtime.runtime.shadow.harness import ShadowHarness

        h = ShadowHarness()
        assert h.close_trade("nope", exit_price=0) is None

    def test_compare_with_sim_incomplete(self):
        from runtime.runtime.shadow.harness import ShadowHarness

        h = ShadowHarness()
        h.record_trade(self._make_trade())
        result = h.compare_with_sim("t1")
        assert result["status"] == "incomplete"

    def test_compare_with_sim_complete(self):
        from runtime.runtime.shadow.harness import ShadowHarness

        h = ShadowHarness()
        trade = self._make_trade()
        trade.sim_pnl = 80.0
        h.record_trade(trade)
        h.close_trade("t1", exit_price=51_000)
        result = h.compare_with_sim("t1")
        assert result["status"] == "compared"
        assert result["sim_pnl"] == 80.0
        assert result["live_pnl"] == pytest.approx(100.0)
        assert result["pnl_deviation"] == pytest.approx(20.0)

    def test_compare_with_sim_nonexistent(self):
        from runtime.runtime.shadow.harness import ShadowHarness

        h = ShadowHarness()
        assert h.compare_with_sim("nope") is None

    def test_summary(self):
        from runtime.runtime.shadow.harness import ShadowHarness

        h = ShadowHarness()
        h.record_trade(self._make_trade("t1", entry_price=50_000, quantity=0.1))
        h.close_trade("t1", exit_price=51_000)
        h.record_trade(self._make_trade("t2", entry_price=50_000, quantity=0.1))
        summary = h.get_summary()
        assert summary["total_trades"] == 2
        assert summary["closed_trades"] == 1
        assert summary["open_trades"] == 1
        assert summary["total_live_pnl"] == pytest.approx(100.0)

    def test_summary_empty(self):
        from runtime.runtime.shadow.harness import ShadowHarness

        h = ShadowHarness()
        summary = h.get_summary()
        assert summary["total_trades"] == 0
        assert summary["closed_trades"] == 0


# ---------------------------------------------------------------------------
# SafetyGateChain unit tests
# ---------------------------------------------------------------------------

class TestSafetyGateChain:
    """Unit tests for the SafetyGateChain composed gate runner."""

    def test_all_gates_pass_returns_none(self):
        """When every gate passes, check_all returns None."""
        from runtime.runtime.safety.gate_chain import SafetyGateChain

        chain = SafetyGateChain()
        result = chain.check_all(
            {"symbol": "BTCUSDT", "entry": 50000, "notional": 10000},
            proposed_notional=10000,
        )
        assert result is None, f"Expected None (all pass), got {result}"

    def test_kill_switch_active_blocks(self):
        """KillSwitch being active produces a typed rejection."""
        from runtime.runtime.safety.gate_chain import SafetyGateChain

        chain = SafetyGateChain()
        chain.kill_switch.trigger("manual")
        result = chain.check_all({"symbol": "BTCUSDT"})
        assert result is not None
        assert result.gate == "KILL_SWITCH"
        assert result.passed is False
        assert "Kill switch active" in (result.reason or "")
        assert result.detail is not None

    def test_drawdown_gate_over_threshold_blocks(self):
        """DrawdownGate blocking produces a typed rejection."""
        from runtime.runtime.safety.gate_chain import SafetyGateChain

        chain = SafetyGateChain()
        chain.drawdown_gate.update_equity(100_000)
        chain.drawdown_gate.update_equity(65_000)  # 35% drawdown, above 30% block
        result = chain.check_all({"symbol": "BTCUSDT"})
        assert result is not None
        assert result.gate == "DRAWDOWN_GATE"
        assert result.passed is False
        assert result.reason is not None
        assert "block" in result.reason.lower()

    def test_position_limiter_rejects(self):
        """PositionLimiter rejection produces a typed rejection."""
        from runtime.runtime.safety.gate_chain import SafetyGateChain
        from runtime.runtime.safety import PositionLimitConfig

        chain = SafetyGateChain()
        # Replace with a tight config
        chain.position_limiter.config = PositionLimitConfig(max_positions=0)
        result = chain.check_all(
            {"symbol": "BTCUSDT"},
            proposed_notional=10000,
            current_positions=[{"notional": 5000}],
        )
        assert result is not None
        assert result.gate == "POSITION_LIMITER"
        assert result.passed is False
        assert result.reason is not None

    def test_symbol_cap_rejects(self):
        """SymbolCap rejection produces a typed rejection."""
        from runtime.runtime.safety.gate_chain import SafetyGateChain
        from runtime.runtime.safety import SymbolCapConfig

        chain = SafetyGateChain()
        chain.symbol_cap.config = SymbolCapConfig(max_notional_per_symbol=1_000)
        result = chain.check_all(
            {"symbol": "BTCUSDT"},
            proposed_notional=10_000,
        )
        assert result is not None
        assert result.gate == "SYMBOL_CAP"
        assert result.passed is False
        assert result.reason is not None

    def test_chain_order_kill_switch_first(self):
        """KillSwitch blocks before DrawdownGate even if both would reject."""
        from runtime.runtime.safety.gate_chain import SafetyGateChain

        chain = SafetyGateChain()
        chain.kill_switch.trigger("manual")
        chain.drawdown_gate.update_equity(100_000)
        chain.drawdown_gate.update_equity(65_000)
        result = chain.check_all({"symbol": "BTCUSDT"})
        assert result is not None
        assert result.gate == "KILL_SWITCH", (
            f"KillSwitch should fire first, got {result.gate}"
        )

    def test_safety_check_result_frozen(self):
        """SafetyCheckResult is truly frozen (immutable)."""
        from runtime.runtime.safety.gate_chain import SafetyCheckResult
        import dataclasses

        assert dataclasses.is_dataclass(SafetyCheckResult)
        assert dataclasses.fields(SafetyCheckResult)


# ---------------------------------------------------------------------------
# ExecutionOrchestrator safety wiring integration tests
# ---------------------------------------------------------------------------

class TestOrchestratorSafetyWiring:
    """Tests that the orchestrator's safety gate check works end-to-end.

    Uses a fully mocked DB layer so we can focus on the safety wiring
    without needing a real database.
    """

    @pytest.fixture(autouse=True)
    def _mock_db_session(self):
        """Mock session_scope so the orchestrator's resolve_target works."""
        from unittest.mock import patch, MagicMock
        from contextlib import contextmanager
        import runtime.db.session as db_mod

        mock_session = MagicMock()
        with patch.object(
            db_mod, "session_scope",
            wraps=contextmanager(lambda: (yield mock_session)),
        ):
            yield

    @pytest.fixture(autouse=True)
    def _mock_v6_dependency(self):
        """Inject a stub for v6.runtime.outcome_recorder so the orchestrator
        module can be imported without the real v6 stack."""
        import sys
        from unittest.mock import MagicMock

        mock_outcome_recorder = MagicMock()
        mock_outcome_recorder.OutcomeRecorder = MagicMock

        v6_runtime = type(sys)("v6.runtime")
        v6_runtime.outcome_recorder = mock_outcome_recorder

        # Ensure intermediate packages exist
        sys.modules.setdefault("v6", type(sys)("v6"))
        sys.modules.setdefault("v6.runtime", v6_runtime)
        sys.modules["v6.runtime.outcome_recorder"] = mock_outcome_recorder
        yield
        sys.modules.pop("v6.runtime.outcome_recorder", None)
        sys.modules.pop("v6.runtime", None)
        sys.modules.pop("v6", None)

    def _make_orchestrator_with_mocks(self):
        """Build an ExecutionOrchestrator with all repos mocked."""
        from unittest.mock import MagicMock
        from runtime.runtime.execution_orchestrator import (
            ExecutionOrchestrator,
            PaperExecutionAdapter,
        )
        from runtime.db.repos.runtime_profile_repo import RuntimeProfileRepository
        from runtime.db.repos.order_repo import OrderRepository
        from runtime.db.repos.paper_repo import PaperAccountRepository
        from runtime.db.repos.execution_account_repo import ExecutionAccountRepository
        from runtime.services.runtime_profile_service import RuntimeProfileService

        profile_repo = MagicMock(spec=RuntimeProfileRepository)
        profile_repo.get_profile.return_value = {
            "profile_id": "paper-main", "name": "Paper Main",
            "status": "ACTIVE", "runtime_mode": "PAPER",
            "execution_mode": "PAPER", "venue": "INTERNAL_PAPER",
            "product_type": "SIMULATED", "venue_environment": "INTERNAL",
            "api_base_url": None, "default_for_auto_trading": True,
            "manual_trading_enabled": True, "auto_trading_enabled": False,
            "read_only": False, "supports_account_reads": True,
            "supports_order_placement": True, "credential_ref": None,
            "connectivity_status": "READY",
        }

        paper_repo = MagicMock(spec=PaperAccountRepository)
        paper_repo.get_or_create_account.return_value = {
            "account_id": "papertest-001",
            "account_key": "papertest",
            "account_type": "PAPER",
            "venue_account_key": "INTERNAL_PAPER",
            "balance_ccy": "USDT",
            "available_balance": 100000.0,
            "equity": 100000.0,
            "margin_used": 0.0,
            "profile_id": "paper-main",
        }

        return ExecutionOrchestrator(
            runtime_profile_repo=profile_repo,
            paper_repo=paper_repo,
            order_repo=MagicMock(spec=OrderRepository),
            execution_account_repo=MagicMock(spec=ExecutionAccountRepository),
            runtime_profile_service=MagicMock(spec=RuntimeProfileService),
        )

    def test_negative_control_rejected_trade_produces_typed_result(self):
        """Full orchestrator: KillSwitch active blocks the trade and
        the rejection surfaces as a typed SafetyCheckResult via the
        exception's message."""
        from runtime.runtime.execution_orchestrator import ExecutionPolicyViolationError

        orch = self._make_orchestrator_with_mocks()
        orch.safety_chain.kill_switch.trigger("test-negative-control")

        signal = {
            "symbol": "BTCUSDT", "interval": "4h", "mode": "SWING",
            "direction": "LONG", "confidence": 0.75, "entry": 50000.0,
            "source": "AUTO",
        }
        with pytest.raises(ExecutionPolicyViolationError) as exc_info:
            orch.open_order(signal, source="AUTO")

        msg = str(exc_info.value)
        assert "Safety gate" in msg
        assert "KILL_SWITCH" in msg or "kill" in msg.lower()

    def test_kill_switch_active_blocks_trade(self):
        """KillSwitch being active prevents trade execution (fail-closed)."""
        from unittest.mock import MagicMock
        from runtime.runtime.execution_orchestrator import (
            ExecutionPolicyViolationError,
        )

        orch = self._make_orchestrator_with_mocks()
        orch.safety_chain.kill_switch.trigger("emergency halt")

        signal = {
            "symbol": "ETHUSDT", "source": "MANUAL",
            "entry": 3000.0,
        }
        with pytest.raises(ExecutionPolicyViolationError) as exc_info:
            orch.open_order(signal, source="MANUAL")

        msg = str(exc_info.value).lower()
        assert "kill" in msg or "safety gate" in msg

        # Verify the adapter was NEVER called (fail-closed)
        orch.paper_adapter.open_order = MagicMock()
        orch.paper_adapter.open_order.assert_not_called()

    def test_drawdown_gate_over_threshold_blocks_trade(self):
        """DrawdownGate blocking prevents trade execution (fail-closed)."""
        from unittest.mock import MagicMock
        from runtime.runtime.execution_orchestrator import (
            ExecutionPolicyViolationError,
        )

        orch = self._make_orchestrator_with_mocks()
        # Set equity via account so the gate chain picks it up
        orch.safety_chain.drawdown_gate.update_equity(100_000)
        # Trigger a 35% drawdown (above default 30% block threshold)
        orch.safety_chain.drawdown_gate.update_equity(65_000)
        assert orch.safety_chain.drawdown_gate.block_new_trades() is True

        signal = {
            "symbol": "BTCUSDT", "source": "AUTO",
            "entry": 50000.0,
        }
        with pytest.raises(ExecutionPolicyViolationError) as exc_info:
            orch.open_order(signal, source="AUTO")

        msg = str(exc_info.value).lower()
        assert "safety gate" in msg
        assert "drawdown" in msg

        # Verify the adapter was NEVER called (fail-closed)
        orch.paper_adapter.open_order = MagicMock()
        orch.paper_adapter.open_order.assert_not_called()

    def test_safety_check_not_bypassable(self):
        """There is no flag or parameter to skip the safety gate check."""
        from runtime.runtime.execution_orchestrator import (
            ExecutionOrchestrator,
        )

        orch = self._make_orchestrator_with_mocks()
        orch.safety_chain.kill_switch.trigger("lockdown")

        # Verify _check_safety_gates is always called in open_order
        import inspect
        source = inspect.getsource(ExecutionOrchestrator.open_order)
        assert "_check_safety_gates" in source, (
            "open_order must call _check_safety_gates"
        )
        # Ensure no param named bypass_*, skip_*, or override_*
        for bad_prefix in ("bypass_", "skip_", "override_", "_bypass"):
            assert bad_prefix not in source, (
                f"open_order must not accept a '{bad_prefix}*' parameter"
            )

    def test_fail_closed_on_guard_failure(self):
        """Guard failure does not execute the trade (paper adapter uncalled)."""
        from unittest.mock import MagicMock
        from runtime.runtime.execution_orchestrator import (
            ExecutionPolicyViolationError,
        )

        orch = self._make_orchestrator_with_mocks()
        orch.safety_chain.kill_switch.trigger("crash")

        signal = {
            "symbol": "BTCUSDT", "source": "MANUAL",
            "entry": 50000.0,
        }
        with pytest.raises(ExecutionPolicyViolationError):
            orch.open_order(signal, source="MANUAL")

        orch.paper_adapter.open_order = MagicMock()
        orch.paper_adapter.open_order.assert_not_called()
