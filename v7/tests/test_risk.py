"""Tests for v7.risk — RiskManager and RiskResult."""

import pytest

from v7.portfolio import PortfolioResult
from v7.risk import DEFAULT_CONFIG, GuardResult, RiskManager, RiskResult


class TestRiskResult:
    """RiskResult dataclass construction and defaults."""

    def test_default_construction(self):
        """Default construction should produce safe state."""
        result = RiskResult()
        assert result.risk_ok is True
        assert result.blocking_guards == []
        assert result.drawdown_state == {}
        assert result.warnings == []

    def test_frozen(self):
        """RiskResult should be frozen (immutable)."""
        result = RiskResult()
        with pytest.raises(AttributeError):
            result.risk_ok = False

    def test_full_construction(self):
        """Construction with all fields should store values correctly."""
        result = RiskResult(
            risk_ok=False,
            blocking_guards=["max_drawdown", "kill_switch_active"],
            drawdown_state={"current_drawdown_pct": 30.0},
            warnings=["Drawdown breach"],
        )
        assert result.risk_ok is False
        assert "max_drawdown" in result.blocking_guards
        assert result.drawdown_state["current_drawdown_pct"] == 30.0
        assert result.warnings == ["Drawdown breach"]


class TestGuardResult:
    """GuardResult internal dataclass."""

    def test_default_metadata_empty(self):
        """Default metadata should be empty dict."""
        g = GuardResult(passed=True, reason="OK")
        assert g.metadata == {}


class TestRiskManagerConstruction:
    """RiskManager construction and defaults."""

    def test_default_config(self):
        """Default config should match DEFAULT_CONFIG."""
        rm = RiskManager()
        assert rm.config["max_drawdown_pct"] == DEFAULT_CONFIG["max_drawdown_pct"]
        assert rm.config["max_exposure_per_symbol_pct"] == DEFAULT_CONFIG["max_exposure_per_symbol_pct"]
        assert rm.config["kill_switch_enabled"] is True

    def test_custom_config_overrides(self):
        """Custom config should merge with defaults."""
        rm = RiskManager({"max_drawdown_pct": 15.0})
        assert rm.config["max_drawdown_pct"] == 15.0
        assert rm.config["max_exposure_per_symbol_pct"] == 10.0  # default unchanged


class TestCheckMaxDrawdown:
    """RiskManager.check_max_drawdown guard."""

    def test_passes_when_below_limit(self):
        """Drawdown below threshold should pass."""
        rm = RiskManager({"max_drawdown_pct": 25.0})
        result = rm.check_max_drawdown({
            "account_value": 90_000,
            "peak_value": 100_000,
        })
        assert result.passed is True
        assert "exceeds" not in result.reason

    def test_blocks_when_at_limit(self):
        """Drawdown at exactly threshold should block."""
        rm = RiskManager({"max_drawdown_pct": 10.0})
        result = rm.check_max_drawdown({
            "account_value": 90_000,
            "peak_value": 100_000,
        })
        # drawdown = (100k - 90k)/100k = 10% — equals threshold
        assert result.passed is False

    def test_blocks_when_above_limit(self):
        """Drawdown above threshold should block."""
        rm = RiskManager({"max_drawdown_pct": 10.0})
        result = rm.check_max_drawdown({
            "account_value": 80_000,
            "peak_value": 100_000,
        })
        assert result.passed is False
        assert "Drawdown" in result.reason

    def test_uses_precomputed_drawdown_when_given(self):
        """Explicit current_drawdown_pct should be used over computed value."""
        rm = RiskManager({"max_drawdown_pct": 25.0})
        result = rm.check_max_drawdown({
            "account_value": 95_000,
            "peak_value": 100_000,
            "current_drawdown_pct": 30.0,  # override
        })
        assert result.passed is False

    def test_handles_zero_values(self):
        """Zero or negative values should not cause errors."""
        rm = RiskManager()
        result = rm.check_max_drawdown({
            "account_value": 0,
            "peak_value": 0,
        })
        # drawdown will be 0.0 (insufficient data), should still pass
        assert result.passed is True

    def test_handles_peak_below_account(self):
        """Peak below account value (unrealistic) should not cause error."""
        rm = RiskManager({"max_drawdown_pct": 25.0})
        result = rm.check_max_drawdown({
            "account_value": 100_000,
            "peak_value": 90_000,
        })
        # drawdown = max(0, (90k-100k)/90k) = max(0, -0.11) = 0
        assert result.passed is True


class TestCheckMaxExposurePerSymbol:
    """RiskManager.check_max_exposure_per_symbol guard."""

    def _sample_portfolio_result(self, ranked=None):
        if ranked is None:
            ranked = []
        return PortfolioResult(ranked=ranked)

    def test_passes_within_limits(self):
        """Positions within per-symbol limit should pass."""
        rm = RiskManager({"max_exposure_per_symbol_pct": 10.0})
        result = rm.check_max_exposure_per_symbol(
            portfolio_result=self._sample_portfolio_result(),
            account_state={
                "positions": {
                    "BTCUSDT": {"size_pct": 5.0, "side": "LONG"},
                    "ETHUSDT": {"size_pct": 3.0, "side": "LONG"},
                }
            },
        )
        assert result.passed is True

    def test_blocks_over_limit(self):
        """Position exceeding per-symbol limit should block."""
        rm = RiskManager({"max_exposure_per_symbol_pct": 10.0})
        result = rm.check_max_exposure_per_symbol(
            portfolio_result=self._sample_portfolio_result(),
            account_state={
                "positions": {
                    "BTCUSDT": {"size_pct": 15.0, "side": "LONG"},
                }
            },
        )
        assert result.passed is False
        assert "exceeds" in result.reason

    def test_checks_proposed_positions(self):
        """Proposed positions in portfolio_result should also be checked."""
        rm = RiskManager({"max_exposure_per_symbol_pct": 10.0})
        result = rm.check_max_exposure_per_symbol(
            portfolio_result=self._sample_portfolio_result(
                ranked=[{"symbol": "SOLUSDT", "position_size_pct": 12.0}]
            ),
            account_state={"positions": {}},
        )
        assert result.passed is False

    def test_combined_current_and_proposed(self):
        """Combined current + proposed exposure should be checked."""
        rm = RiskManager({"max_exposure_per_symbol_pct": 10.0})
        result = rm.check_max_exposure_per_symbol(
            portfolio_result=self._sample_portfolio_result(
                ranked=[{"symbol": "BTCUSDT", "position_size_pct": 6.0}]
            ),
            account_state={
                "positions": {
                    "BTCUSDT": {"size_pct": 5.0, "side": "LONG"},
                }
            },
        )
        # 5% current + 6% proposed = 11% > 10%
        assert result.passed is False

    def test_none_portfolio_result(self):
        """None portfolio_result should not cause errors."""
        rm = RiskManager({"max_exposure_per_symbol_pct": 10.0})
        result = rm.check_max_exposure_per_symbol(
            portfolio_result=None,
            account_state={"positions": {}},
        )
        assert result.passed is True

    def test_empty_positions(self):
        """Empty positions dict should pass."""
        rm = RiskManager()
        result = rm.check_max_exposure_per_symbol(
            portfolio_result=self._sample_portfolio_result(),
            account_state={"positions": {}},
        )
        assert result.passed is True


class TestCheckKillSwitch:
    """RiskManager.check_kill_switch guard."""

    def test_passes_when_inactive(self):
        """Kill switch inactive should pass."""
        rm = RiskManager()
        result = rm.check_kill_switch({"kill_switch_active": False})
        assert result.passed is True

    def test_blocks_when_active(self):
        """Kill switch active should block."""
        rm = RiskManager()
        result = rm.check_kill_switch({"kill_switch_active": True})
        assert result.passed is False
        assert "kill switch" in result.reason.lower()

    def test_skips_when_disabled(self):
        """Kill switch disabled in config should skip the guard."""
        rm = RiskManager({"kill_switch_enabled": False})
        result = rm.check_kill_switch({"kill_switch_active": True})
        assert result.passed is True
        assert "disabled" in result.reason.lower()

    def test_defaults_to_inactive(self):
        """Missing kill_switch_active should default to False (inactive)."""
        rm = RiskManager()
        result = rm.check_kill_switch({})
        assert result.passed is True


class TestCheckAccountIntegrity:
    """RiskManager.check_account_integrity guard."""

    def test_passes_with_valid_value(self):
        """Positive account value should pass."""
        rm = RiskManager()
        result = rm.check_account_integrity({"account_value": 100_000})
        assert result.passed is True

    def test_blocks_missing_value(self):
        """Missing account_value should block."""
        rm = RiskManager()
        result = rm.check_account_integrity({})
        assert result.passed is False
        assert "missing" in result.reason.lower()

    def test_blocks_zero_value(self):
        """Zero account_value should block."""
        rm = RiskManager()
        result = rm.check_account_integrity({"account_value": 0})
        assert result.passed is False

    def test_blocks_negative_value(self):
        """Negative account_value should block."""
        rm = RiskManager()
        result = rm.check_account_integrity({"account_value": -100})
        assert result.passed is False


class TestCheckHardGuards:
    """RiskManager.check_hard_guards integration."""

    def _sample_portfolio_result(self):
        return PortfolioResult()

    def _healthy_account(self, **overrides):
        state = {
            "account_value": 100_000,
            "peak_value": 100_000,
            "total_exposure_pct": 10.0,
            "positions": {},
            "kill_switch_active": False,
            "daily_loss_pct": 0.0,
        }
        state.update(overrides)
        return state

    def test_all_guards_pass(self):
        """Healthy state should pass all guards."""
        rm = RiskManager()
        result = rm.check_hard_guards(
            portfolio_result=self._sample_portfolio_result(),
            account_state=self._healthy_account(),
        )
        assert result.risk_ok is True
        assert result.blocking_guards == []

    def test_drawdown_blocks(self):
        """Drawdown breach should block and be reported."""
        rm = RiskManager({"max_drawdown_pct": 10.0})
        result = rm.check_hard_guards(
            portfolio_result=self._sample_portfolio_result(),
            account_state=self._healthy_account(account_value=80_000, peak_value=100_000),
        )
        assert result.risk_ok is False
        assert "max_drawdown" in result.blocking_guards
        assert result.drawdown_state["current_drawdown_pct"] == 20.0

    def test_kill_switch_blocks(self):
        """Active kill switch should block."""
        rm = RiskManager()
        result = rm.check_hard_guards(
            portfolio_result=self._sample_portfolio_result(),
            account_state=self._healthy_account(kill_switch_active=True),
        )
        assert result.risk_ok is False
        assert "kill_switch_active" in result.blocking_guards

    def test_exposure_blocks(self):
        """Exceeding per-symbol exposure should block."""
        rm = RiskManager({"max_exposure_per_symbol_pct": 10.0})
        result = rm.check_hard_guards(
            portfolio_result=self._sample_portfolio_result(),
            account_state=self._healthy_account(
                positions={"BTCUSDT": {"size_pct": 15.0, "side": "LONG"}}
            ),
        )
        assert result.risk_ok is False
        assert "max_exposure_per_symbol" in result.blocking_guards

    def test_account_integrity_blocks(self):
        """Missing account value should block."""
        rm = RiskManager()
        result = rm.check_hard_guards(
            portfolio_result=self._sample_portfolio_result(),
            account_state={"kill_switch_active": False},
        )
        assert result.risk_ok is False
        assert "account_integrity" in result.blocking_guards

    def test_multiple_guards_block(self):
        """Multiple simultaneous failures should all be reported."""
        rm = RiskManager({"max_drawdown_pct": 10.0, "max_exposure_per_symbol_pct": 5.0})
        result = rm.check_hard_guards(
            portfolio_result=self._sample_portfolio_result(),
            account_state={
                "account_value": 70_000,
                "peak_value": 100_000,
                "positions": {"BTCUSDT": {"size_pct": 10.0, "side": "LONG"}},
                "kill_switch_active": True,
            },
        )
        assert result.risk_ok is False
        assert "max_drawdown" in result.blocking_guards
        assert "max_exposure_per_symbol" in result.blocking_guards
        assert "kill_switch_active" in result.blocking_guards
        assert len(result.blocking_guards) == 3

    def test_none_portfolio_result(self):
        """None portfolio_result should not crash check_hard_guards."""
        rm = RiskManager()
        result = rm.check_hard_guards(
            portfolio_result=None,
            account_state=self._healthy_account(),
        )
        assert result.risk_ok is True
