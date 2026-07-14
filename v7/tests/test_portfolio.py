"""Tests for v7.portfolio — PortfolioManager and PortfolioResult."""

import pytest

from v7.portfolio import (
    CORRELATION_GROUPS,
    DEFAULT_CONFIG,
    PortfolioManager,
    PortfolioResult,
)


class TestPortfolioResult:
    """PortfolioResult dataclass construction and defaults."""

    def test_default_construction(self):
        """Default construction should produce empty/zero values."""
        result = PortfolioResult()
        assert result.suppressed == []
        assert result.ranked == []
        assert result.exposure_remaining_pct == 100.0
        assert result.concentration_warnings == []

    def test_frozen(self):
        """PortfolioResult should be frozen (immutable)."""
        result = PortfolioResult()
        with pytest.raises(AttributeError):
            result.suppressed = ["BTCUSDT"]

    def test_full_construction(self):
        """Construction with all fields should store values correctly."""
        result = PortfolioResult(
            suppressed=["BTCUSDT", "ETHUSDT"],
            ranked=[{"symbol": "SOLUSDT", "expected_r_net": 0.5}],
            exposure_remaining_pct=45.0,
            concentration_warnings=["BTCUSDT over 10% limit"],
        )
        assert result.suppressed == ["BTCUSDT", "ETHUSDT"]
        assert result.ranked == [{"symbol": "SOLUSDT", "expected_r_net": 0.5}]
        assert result.exposure_remaining_pct == 45.0
        assert result.concentration_warnings == ["BTCUSDT over 10% limit"]


class TestPortfolioManagerConstruction:
    """PortfolioManager construction and defaults."""

    def test_default_config(self):
        """Default config should be a copy of DEFAULT_CONFIG."""
        pm = PortfolioManager()
        assert pm.config["max_position_pct"] == DEFAULT_CONFIG["max_position_pct"]
        assert pm.config["max_cluster_exposure_pct"] == DEFAULT_CONFIG["max_cluster_exposure_pct"]
        assert pm.config["max_total_exposure_pct"] == DEFAULT_CONFIG["max_total_exposure_pct"]
        assert pm.config["max_simultaneous_positions"] == DEFAULT_CONFIG["max_simultaneous_positions"]
        assert pm.config["correlation_groups"] == CORRELATION_GROUPS

    def test_custom_config_overrides(self):
        """Custom config should merge with defaults, overriding matching keys."""
        pm = PortfolioManager({"max_position_pct": 5.0, "custom_key": "val"})
        assert pm.config["max_position_pct"] == 5.0
        assert pm.config["custom_key"] == "val"
        assert pm.config["max_cluster_exposure_pct"] == 15.0  # default unchanged


class TestSuppressOverconcentration:
    """PortfolioManager.suppress_overconcentration."""

    def _make_decision(self, symbol, expected_r=0.5, confidence=0.7, size=8.0):
        return {
            "symbol": symbol,
            "expected_r_net": expected_r,
            "confidence": confidence,
            "position_size_pct": size,
        }

    def test_suppresses_over_limit(self):
        """Symbol with combined exposure > max_position_pct should be suppressed."""
        pm = PortfolioManager({"max_position_pct": 10.0})
        decisions = [self._make_decision("BTCUSDT", size=8.0)]
        # Current exposure 5% + proposed 8% = 13% > 10%
        filtered = pm.suppress_overconcentration(decisions, {"BTCUSDT": 5.0})
        assert filtered == []

    def test_allows_under_limit(self):
        """Symbol with combined exposure <= max_position_pct should be kept."""
        pm = PortfolioManager({"max_position_pct": 10.0})
        decisions = [self._make_decision("BTCUSDT", size=4.0)]
        filtered = pm.suppress_overconcentration(decisions, {"BTCUSDT": 5.0})
        assert filtered == decisions

    def test_mixed_symbols(self):
        """Only over-concentrated symbols should be suppressed."""
        pm = PortfolioManager({"max_position_pct": 10.0})
        decisions = [
            self._make_decision("BTCUSDT", size=8.0),
            self._make_decision("ETHUSDT", size=3.0),
            self._make_decision("SOLUSDT", size=6.0),
        ]
        filtered = pm.suppress_overconcentration(
            decisions, {"BTCUSDT": 5.0, "ETHUSDT": 0.0, "SOLUSDT": 5.0}
        )
        symbols = {d["symbol"] for d in filtered}
        assert "BTCUSDT" not in symbols  # 8+5=13 > 10
        assert "ETHUSDT" in symbols      # 3+0=3 <= 10
        assert "SOLUSDT" not in symbols  # 6+5=11 > 10

    def test_no_current_exposure(self):
        """Symbol with no current exposure should pass if within limit."""
        pm = PortfolioManager({"max_position_pct": 10.0})
        decisions = [self._make_decision("BTCUSDT", size=8.0)]
        filtered = pm.suppress_overconcentration(decisions, {})
        assert len(filtered) == 1
        assert filtered[0]["symbol"] == "BTCUSDT"


class TestSuppressCorrelated:
    """PortfolioManager.suppress_correlated."""

    def _make_decision(self, symbol, expected_r=0.5, confidence=0.7, size=8.0):
        return {
            "symbol": symbol,
            "expected_r_net": expected_r,
            "confidence": confidence,
            "position_size_pct": size,
        }

    def test_suppresses_cluster_excess(self):
        """When a cluster exceeds max_cluster_exposure, lowest-ranked should be suppressed."""
        groups = {"layer1": {"SOLUSDT", "ADAUSDT"}}
        pm = PortfolioManager({"max_cluster_exposure_pct": 15.0})
        decisions = [
            self._make_decision("SOLUSDT", expected_r=0.8, size=10.0),
            self._make_decision("ADAUSDT", expected_r=0.4, size=8.0),
        ]
        filtered = pm.suppress_correlated(decisions, groups)
        # SOLUSDT (r=0.8) ranked higher, should keep; ADAUSDT (r=0.4) should drop
        symbols = {d["symbol"] for d in filtered}
        assert "SOLUSDT" in symbols
        assert "ADAUSDT" not in symbols

    def test_keeps_within_cluster_limit(self):
        """All decisions within cluster limit should be kept."""
        groups = {"layer1": {"SOLUSDT", "ADAUSDT"}}
        pm = PortfolioManager({"max_cluster_exposure_pct": 20.0})
        decisions = [
            self._make_decision("SOLUSDT", expected_r=0.5, size=8.0),
            self._make_decision("ADAUSDT", expected_r=0.4, size=8.0),
        ]
        filtered = pm.suppress_correlated(decisions, groups)
        assert len(filtered) == 2

    def test_no_group_match(self):
        """Symbols not in any group should never be suppressed."""
        pm = PortfolioManager()
        decisions = [self._make_decision("UNKNOWN", size=10.0)]
        filtered = pm.suppress_correlated(decisions, {"btc": {"BTCUSDT"}})
        assert len(filtered) == 1

    def test_empty_groups(self):
        """Empty groups dict should keep all decisions."""
        pm = PortfolioManager()
        decisions = [self._make_decision("BTCUSDT", size=10.0)]
        filtered = pm.suppress_correlated(decisions, {})
        assert len(filtered) == 1


class TestApplyPositionLimits:
    """PortfolioManager.apply_position_limits."""

    def _make_decision(self, symbol, expected_r=0.5, confidence=0.7, size=8.0):
        return {
            "symbol": symbol,
            "expected_r_net": expected_r,
            "confidence": confidence,
            "position_size_pct": size,
        }

    def test_respects_max_positions(self):
        """Decisions beyond max_positions should be suppressed (lowest-ranked first)."""
        pm = PortfolioManager()
        decisions = [
            self._make_decision("BTCUSDT", expected_r=0.9, size=5.0),
            self._make_decision("ETHUSDT", expected_r=0.7, size=5.0),
            self._make_decision("SOLUSDT", expected_r=0.5, size=5.0),
        ]
        filtered = pm.apply_position_limits(decisions, max_positions=2, max_exposure_pct=50.0)
        assert len(filtered) == 2
        symbols = {d["symbol"] for d in filtered}
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols
        assert "SOLUSDT" not in symbols

    def test_respects_max_exposure(self):
        """Decisions beyond max_exposure_pct should be suppressed."""
        pm = PortfolioManager()
        decisions = [
            self._make_decision("BTCUSDT", expected_r=0.9, size=30.0),
            self._make_decision("ETHUSDT", expected_r=0.7, size=30.0),
        ]
        # max_exposure_pct=40 means only BTCUSDT (30) fits
        filtered = pm.apply_position_limits(decisions, max_positions=10, max_exposure_pct=40.0)
        assert len(filtered) == 1
        assert filtered[0]["symbol"] == "BTCUSDT"

    def test_empty_decisions(self):
        """Empty list should return empty."""
        pm = PortfolioManager()
        filtered = pm.apply_position_limits([], max_positions=10, max_exposure_pct=50.0)
        assert filtered == []

    def test_zero_max_positions(self):
        """Zero max_positions should suppress all."""
        pm = PortfolioManager()
        decisions = [self._make_decision("BTCUSDT", size=5.0)]
        filtered = pm.apply_position_limits(decisions, max_positions=0, max_exposure_pct=50.0)
        assert filtered == []


class TestEvaluatePortfolio:
    """PortfolioManager.evaluate_portfolio integration."""

    def _make_request(self, symbol, mode="SWING"):
        return {
            "symbol": symbol,
            "mode": mode,
            "requested_trade_mode": mode,
        }

    def _make_result(self, symbol, passed=True, expected_r=0.5, confidence=0.7, size=8.0):
        return {
            "symbol": symbol,
            "passed": passed,
            "decision": "ENTER_LONG",
            "expected_r": expected_r,
            "confidence": confidence,
            "position_size_pct": size,
            "entry_price": 50000.0,
            "stop_loss_price": 48000.0,
            "take_profit_price": 55000.0,
        }

    def test_happy_path(self):
        """Basic portfolio evaluation with no suppression."""
        pm = PortfolioManager()
        requests = [
            self._make_request("BTCUSDT"),
            self._make_request("ETHUSDT"),
        ]
        results = [
            self._make_result("BTCUSDT", expected_r=0.8, size=5.0),
            self._make_result("ETHUSDT", expected_r=0.6, size=5.0),
        ]
        positions = {}
        result = pm.evaluate_portfolio(requests, results, positions)
        assert result.suppressed == []
        assert len(result.ranked) == 2
        assert result.ranked[0]["symbol"] == "BTCUSDT"  # higher expected_r
        assert result.exposure_remaining_pct == 90.0

    def test_overconcentration_suppression(self):
        """Over-concentrated symbols should be suppressed."""
        pm = PortfolioManager({"max_position_pct": 10.0})
        requests = [self._make_request("BTCUSDT")]
        results = [self._make_result("BTCUSDT", size=8.0)]
        positions = {"BTCUSDT": {"size_pct": 5.0, "side": "LONG"}}
        result = pm.evaluate_portfolio(requests, results, positions)
        assert "BTCUSDT" in result.suppressed
        assert result.ranked == []

    def test_non_passing_results_excluded(self):
        """Policy-non-passing results should be excluded from decisions."""
        pm = PortfolioManager()
        requests = [
            self._make_request("BTCUSDT"),
            self._make_request("ETHUSDT"),
        ]
        results = [
            self._make_result("BTCUSDT", passed=True, size=5.0),
            self._make_result("ETHUSDT", passed=False, size=5.0),
        ]
        positions = {}
        result = pm.evaluate_portfolio(requests, results, positions)
        assert len(result.ranked) == 1
        assert result.ranked[0]["symbol"] == "BTCUSDT"

    def test_exposure_remaining_correct(self):
        """Exposure remaining should reflect total used by positions + new decisions."""
        pm = PortfolioManager()
        requests = [self._make_request("BTCUSDT")]
        results = [self._make_result("BTCUSDT", size=8.0)]
        positions = {"ETHUSDT": {"size_pct": 5.0, "side": "LONG"}}
        result = pm.evaluate_portfolio(requests, results, positions)
        # 5% (ETH existing) + 8% (BTC new) = 13% used, 87% remaining
        assert result.exposure_remaining_pct == 87.0


class TestCorrelationGroupsDefault:
    """Default correlation groups should be well-formed."""

    def test_correlation_groups_defined(self):
        """CORRELATION_GROUPS should have expected structure."""
        assert "btc_cluster" in CORRELATION_GROUPS
        assert "eth_cluster" in CORRELATION_GROUPS
        assert "layer1" in CORRELATION_GROUPS
        assert "defi" in CORRELATION_GROUPS
        assert "BTCUSDT" in CORRELATION_GROUPS["btc_cluster"]
        assert "ETHUSDT" in CORRELATION_GROUPS["eth_cluster"]

    def test_no_symbol_overlap(self):
        """No symbol should appear in multiple groups."""
        seen: set[str] = set()
        for members in CORRELATION_GROUPS.values():
            for sym in members:
                assert sym not in seen, f"{sym} appears in multiple groups"
                seen.add(sym)


class TestRankingOrder:
    """Ranking sort order inside evaluate_portfolio."""

    def _make_request(self, symbol):
        return {"symbol": symbol, "mode": "SWING"}

    def _make_result(self, symbol, expected_r, confidence=0.7, size=5.0):
        return {
            "symbol": symbol,
            "passed": True,
            "decision": "ENTER_LONG",
            "expected_r": expected_r,
            "confidence": confidence,
            "position_size_pct": size,
        }

    def test_higher_expected_r_ranked_first(self):
        """Higher expected_r_net decisions should rank higher."""
        pm = PortfolioManager()
        requests = [self._make_request("A"), self._make_request("B")]
        results = [
            self._make_result("A", expected_r=0.9),
            self._make_result("B", expected_r=0.5),
        ]
        result = pm.evaluate_portfolio(requests, results, {})
        assert result.ranked[0]["symbol"] == "A"
        assert result.ranked[1]["symbol"] == "B"

    def test_deterministic_tie_break(self):
        """Ties should be broken alphabetically by symbol."""
        pm = PortfolioManager()
        requests = [self._make_request("BTCUSDT"), self._make_request("ETHUSDT")]
        results = [
            self._make_result("BTCUSDT", expected_r=0.5),
            self._make_result("ETHUSDT", expected_r=0.5),
        ]
        result = pm.evaluate_portfolio(requests, results, {})
        # Both have same expected_r and confidence, so sorted alphabetically reversed:
        # -expected_r = -0.5, -confidence = -0.7, symbol ascending
        # A < B in symbol => ETHUSDT < BTCUSDT alphabetically
        # Wait: ETHUSDT > BTCUSDT alphabetically. Actually B < E, so BTCUSDT first
        assert result.ranked[0]["symbol"] == "BTCUSDT"
        assert result.ranked[1]["symbol"] == "ETHUSDT"


class TestExistingPositionLimits:
    """New candidates must respect holdings opened on earlier timestamps."""

    @staticmethod
    def _request(symbol):
        return {"symbol": symbol, "mode": "SCALP"}

    @staticmethod
    def _result(symbol, size=5.0):
        return {
            "symbol": symbol,
            "passed": True,
            "decision": "ENTER_LONG",
            "expected_r": 0.3,
            "confidence": 0.8,
            "position_size_pct": size,
        }

    def test_existing_cluster_exposure_blocks_correlated_candidate(self):
        pm = PortfolioManager({"max_cluster_exposure_pct": 10.0})
        result = pm.evaluate_portfolio(
            [self._request("SOLUSDT")], [self._result("SOLUSDT", 5.0)],
            {"ADAUSDT": {"size_pct": 8.0, "side": "LONG"}},
        )
        assert result.ranked == []
        assert result.suppressed == ["SOLUSDT"]

    def test_existing_total_exposure_blocks_candidate(self):
        pm = PortfolioManager({"max_total_exposure_pct": 10.0})
        result = pm.evaluate_portfolio(
            [self._request("BTCUSDT")], [self._result("BTCUSDT", 5.0)],
            {"ETHUSDT": {"size_pct": 8.0, "side": "LONG"}},
        )
        assert result.ranked == []
        assert result.suppressed == ["BTCUSDT"]

    def test_existing_position_count_blocks_candidate(self):
        pm = PortfolioManager({"max_simultaneous_positions": 1})
        result = pm.evaluate_portfolio(
            [self._request("BTCUSDT")], [self._result("BTCUSDT", 5.0)],
            {"ETHUSDT": {"size_pct": 5.0, "side": "LONG"}},
        )
        assert result.ranked == []
        assert result.suppressed == ["BTCUSDT"]
