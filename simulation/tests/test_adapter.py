"""Tests for simulation/adapter.py — dict-based simulation entry point."""

import pytest
from simulation.adapter import run_simulation, run_training, _dict_to_profile


def _valid_input(**overrides) -> dict:
    """Minimal valid SimulationInput dict."""
    base = {
        "symbol": "BTCUSDT",
        "decision_timestamp": "2026-06-01T12:00:00Z",
        "mode": "SWING",
        "primary_interval": "4h",
        "entry_price": 50000.0,
        "atr": 1000.0,
        "future_path": {
            "candles": [
                {"open": 50200, "high": 50500, "low": 50100, "close": 50400},
                {"open": 50400, "high": 51000, "low": 50300, "close": 50800},
                {"open": 50800, "high": 51500, "low": 50700, "close": 51300},
                {"open": 51300, "high": 52000, "low": 51200, "close": 51800},
                {"open": 51800, "high": 52600, "low": 51700, "close": 52500},
            ],
        },
        "profile": {
            "profile_version": "swing_test-1.0",
            "mode": "SWING",
            "primary_interval": "4h",
            "max_holding_bars": 30,
            "stop_multiplier": 2.0,
            "target_multiplier": 2.5,
            "ambiguity_margin_r": 0.20,
            "min_action_edge_r": 0.35,
            "no_trade_default": False,
        },
    }
    base.update(overrides)
    return base


class TestRunSimulation:
    def test_bullish_path_returns_long_win(self):
        result = run_simulation(_valid_input())
        assert result["symbol"] == "BTCUSDT"
        assert result["best_action"] in ("LONG_NOW",)
        assert result["long_outcome"]["exit_reason"] == "TARGET_HIT"
        assert result["long_outcome"]["realized_r_net"] > 0

    def test_bearish_path_returns_short_win(self):
        inp = _valid_input(
            future_path={"candles": [
                {"open": 49800, "high": 49900, "low": 49300, "close": 49400},
                {"open": 49400, "high": 49500, "low": 48500, "close": 48600},
                {"open": 48600, "high": 48800, "low": 47300, "close": 47400},
            ]},
        )
        result = run_simulation(inp)
        assert result["short_outcome"]["exit_reason"] == "TARGET_HIT"
        assert result["short_outcome"]["realized_r_net"] > 0

    def test_flat_path_returns_time_exit(self):
        inp = _valid_input(
            atr=500.0,
            future_path={"candles": [
                {"open": 50100, "high": 50300, "low": 50000, "close": 50200},
                {"open": 50200, "high": 50400, "low": 50100, "close": 50300},
            ]},
            profile={
                "profile_version": "swing_wide-1.0",
                "mode": "SWING",
                "max_holding_bars": 2,
                "stop_multiplier": 5.0,
                "target_multiplier": 5.0,
                "ambiguity_margin_r": 0.20,
                "min_action_edge_r": 0.35,
                "no_trade_default": False,
            },
        )
        result = run_simulation(inp)
        assert result["long_outcome"]["exit_reason"] == "TIME_EXIT"

    def test_includes_optional_fields(self):
        result = run_simulation(_valid_input())
        # Path metrics
        assert "path_metrics" in result["long_outcome"]
        assert result["long_outcome"]["path_metrics"]["mfe_r"] >= 0
        # No-trade outcome
        assert "saved_loss_score" in result["no_trade_outcome"]
        # Lineage
        assert result["lineage"]["adapter_kind"] == "TRAINING"

    def test_adapter_kind_propagates(self):
        result = run_simulation(_valid_input(), adapter_kind="EVALUATION")
        assert result["lineage"]["adapter_kind"] == "EVALUATION"

    def test_run_training_uses_training_kind(self):
        result = run_training(_valid_input())
        assert result["lineage"]["adapter_kind"] == "TRAINING"

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValueError, match="Missing or invalid"):
            run_simulation({"symbol": ""})

    def test_invalid_adapter_kind_raises(self):
        with pytest.raises(ValueError, match="Unknown adapter_kind"):
            run_simulation(_valid_input(), adapter_kind="INVALID")


class TestDictToProfile:
    def test_minimal_profile(self):
        result = _dict_to_profile({"mode": "SWING"})
        assert result.mode.value == "SWING"
        assert result.max_holding_bars == 30
        assert result.stop_multiplier == 2.0

    def test_full_profile(self):
        result = _dict_to_profile({
            "mode": "SCALP",
            "primary_interval": "1h",
            "max_holding_bars": 12,
            "stop_multiplier": 1.5,
            "target_multiplier": 1.8,
            "ambiguity_margin_r": 0.10,
            "min_action_edge_r": 0.15,
            "no_trade_default": True,
            "context_intervals": ["4h", "15m"],
            "refinement_intervals": ["15m"],
            "mae_penalty_weight": 2.0,
            "cost_penalty_weight": 2.0,
            "time_penalty_weight": 1.5,
        })
        assert result.mode.value == "SCALP"
        assert result.max_holding_bars == 12
        assert result.no_trade_default is True


class TestDeterminism:
    def test_same_input_same_output(self):
        inp = _valid_input()
        r1 = run_simulation(inp)
        r2 = run_simulation(inp)
        assert r1["best_action"] == r2["best_action"]
        assert r1["long_outcome"]["realized_r_net"] == r2["long_outcome"]["realized_r_net"]
        assert r1["short_outcome"]["realized_r_net"] == r2["short_outcome"]["realized_r_net"]

    def test_different_input_different_output(self):
        bullish = run_simulation(_valid_input(mode="SWING", atr=1000))
        bearish = run_simulation(_valid_input(mode="SWING", atr=500))
        assert bullish is not bearish
