"""Import smoke tests for scripts/factor_central_sim and paper_accounting_bridge."""
import pytest


class TestCentralSimBridge:
    """#211: central_sim_bridge imports and basic functions work."""

    def test_import_signal_event_to_sim_input(self):
        from scripts.factor_central_sim import signal_event_to_sim_input, run_batch_simulation
        result = signal_event_to_sim_input({"symbol": "BTCUSDT"}, "SWING")
        assert result["symbol"] == "BTCUSDT"
        assert result["stop_multiplier"] > 0

    def test_run_batch_simulation_returns_metrics(self):
        from scripts.factor_central_sim import run_batch_simulation
        signals = [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]
        results = run_batch_simulation(signals, "SWING")
        assert len(results) == 2
        assert results[0]["central_net_R"] != 0.0
        assert results[0]["one_r"] > 0

    def test_cli_help(self):
        import subprocess
        r = subprocess.run(
            ["python", "scripts/factor_central_sim.py", "--help"],
            capture_output=True, text=True
        )
        assert r.returncode == 0
        assert "--mode" in r.stdout


class TestPaperAccountingBridge:
    """#277: paper_accounting_bridge functions work."""

    def test_compute_with_simulation_r(self):
        from runtime.services.paper_accounting_bridge import compute_with_simulation_r
        result = compute_with_simulation_r(
            entry_price=100.0, exit_price=110.0, atr=2.0,
            stop_multiplier=2.0, direction="LONG"
        )
        assert result["realized_r"] == 2.5  # (110-100)/(2*2)
        assert result["net_r"] < result["realized_r"]  # fee taken

    def test_compute_with_simulation_r_short(self):
        from runtime.services.paper_accounting_bridge import compute_with_simulation_r
        result = compute_with_simulation_r(
            entry_price=100.0, exit_price=90.0, atr=2.0,
            stop_multiplier=2.0, direction="SHORT"
        )
        assert result["realized_r"] == 2.5

    def test_compute_with_simulation_r_leverage_passthrough(self):
        from runtime.services.paper_accounting_bridge import compute_with_simulation_r
        result = compute_with_simulation_r(
            entry_price=100.0, exit_price=110.0, atr=2.0,
            stop_multiplier=2.0, direction="LONG", leverage=3
        )
        assert result["leverage"] == 3

    def test_wire_alpha_runner_signal_requires_exit_price(self):
        from runtime.services.paper_accounting_bridge import wire_alpha_runner_signal
        result = wire_alpha_runner_signal({"symbol": "BTCUSDT", "entry_price": 100.0})
        assert result is None  # no exit_price

    def test_import_no_error(self):
        from runtime.services.paper_accounting_bridge import (
            compute_with_simulation_r, wire_alpha_runner_signal
        )
        assert compute_with_simulation_r is not None
