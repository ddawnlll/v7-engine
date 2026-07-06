from __future__ import annotations

from datetime import timedelta

import pandas as pd

from runtime.services.replay_backed_simulation_orchestrator import (
    ReplayBackedSimulationOrchestrator,
)
from runtime.services.runtime_replay_input_mapper import RuntimeReplayInputMapper
from runtime.services.simulation_output_result_materializer import (
    SimulationOutputResultMaterializer,
)
from simulation.adapters.replay_driver import ReplayDriver


def _build_primary_frame() -> pd.DataFrame:
    start = pd.Timestamp("2026-07-01T00:00:00Z")
    rows = []
    price = 100.0
    for idx in range(100):
        open_time = start + timedelta(hours=idx)
        close_time = open_time + timedelta(hours=1)
        close = price + 0.1
        high = close + 0.6
        low = price - 0.4
        if idx == 80:
            high = 102.1
            low = 99.8
            close = 100.8
        if idx == 81:
            high = 102.5
            low = 100.5
            close = 102.2
        if idx == 82:
            high = 103.0
            low = 101.9
            close = 102.8
        if idx == 83:
            high = 103.7
            low = 102.4
            close = 103.4
        rows.append(
            {
                "open_time": open_time,
                "close_time": close_time,
                "open": price,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000.0 + idx,
                "trades": 200 + idx,
                "quote_volume": (1000.0 + idx) * close,
            }
        )
        price = close
    return pd.DataFrame(rows)


class _FakeCandleLoader:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def load(self, symbol: str, interval: str, start, end) -> pd.DataFrame:
        if interval == "4h":
            return self.frame.iloc[::4].reset_index(drop=True)
        return self.frame.copy()


class _FakeAnalyzer:
    def analyze(self, *, symbol, interval, mode, snapshot, runtime_context, timestamp, **kwargs):
        if timestamp == "2026-07-04T09:00:00+00:00":
            return {
                "signal": {
                    "direction": "BUY",
                    "confidence": 72.0,
                    "entry_price": 100.8,
                    "stop_loss": 99.3,
                    "take_profit": 103.8,
                    "summary": "buy breakout replay",
                },
                "direction": "BUY",
                "confidence": 72.0,
                "signal_status": "ACTIONABLE",
                "summary": "buy breakout replay",
            }
        return {
            "signal": {"direction": "NEUTRAL", "confidence": 0.0, "summary": "neutral"},
            "direction": "NEUTRAL",
            "confidence": 0.0,
            "signal_status": "FILTERED",
        }


class TestReplayBackedSimulationOrchestrator:
    def test_runs_full_window_and_materializes_replay_driver_result(self):
        frame = _build_primary_frame()
        orchestrator = ReplayBackedSimulationOrchestrator(
            candle_loader=_FakeCandleLoader(frame),
            analyzer=_FakeAnalyzer(),
        )

        payload = {
            "period_start": "2026-07-01",
            "period_end": "2026-07-06",
            "symbols": ["BTCUSDT"],
            "intervals": ["1h"],
            "modes": ["SCALP"],
            "capital": 10000.0,
            "risk_per_trade_pct": 1.0,
            "min_confidence": 55.0,
            "scan_workers": 1,
            "execution_settings": {
                "simulation_family_version": "simfam-2.1.0",
                "cost_model_version": "cost-2.1.0",
                "fee_bps": 4.0,
                "slippage_bps": 1.0,
                "time_forward_step_bars": 1,
            },
            "simulation_profile": {
                "profile_version": "scalp-profile-v2",
                "primary_interval": "1h",
                "max_holding_bars": 3,
                "stop_multiplier": 1.5,
                "target_multiplier": 2.0,
                "ambiguity_margin_r": 0.10,
                "min_action_edge_r": 0.15,
                "no_trade_default": False,
                "context_intervals": ["4h", "15m"],
                "refinement_intervals": ["15m"],
                "stop_method": "atr_wide",
                "target_method": "atr_wide",
                "mae_penalty_weight": 2.0,
                "cost_penalty_weight": 2.0,
                "time_penalty_weight": 1.5,
                "funding_rate": 0.0,
            },
        }

        result = orchestrator.run(payload)

        assert result["status"] == "COMPLETED"
        assert len(result["results"]) == 1
        actual = result["results"][0]

        idx = 81 - 1
        snapshot = orchestrator._indicator_frame is not None
        assert snapshot is True

        from runtime.services.incremental_indicators import extract_snapshot

        row_snapshot = extract_snapshot(orchestrator._indicator_frame, idx)
        signal = {
            "direction": "BUY",
            "confidence": 72.0,
            "entry_price": 100.8,
            "stop_loss": 99.3,
            "take_profit": 103.8,
            "summary": "buy breakout replay",
        }
        future_frame = frame.iloc[idx + 1 : idx + 1 + 3].reset_index(drop=True)
        mapper = RuntimeReplayInputMapper()
        sim_input = mapper.build_input(
            symbol="BTCUSDT",
            interval="1h",
            mode="SCALP",
            timestamp="2026-07-04T09:00:00+00:00",
            signal=signal,
            snapshot=row_snapshot,
            future_frame=future_frame,
            simulation_profile=payload["simulation_profile"],
            execution_settings=payload["execution_settings"],
        )
        sim_output = ReplayDriver().run(sim_input)
        expected = SimulationOutputResultMaterializer().to_runtime_result(
            sim_output=sim_output,
            selected_direction="BUY",
            quantity_context={
                "risk_amount": 100.0,
                "quantity": 66.66666666666667,
                "entry_price": 100.8,
                "notional": 6720.0,
                "stop_loss": 99.3,
                "take_profit": 103.8,
            },
            run_context={
                "symbol": "BTCUSDT",
                "interval": "1h",
                "mode": "SCALP",
                "confidence": 72.0,
                "opened_at": "2026-07-04T08:00:00+00:00",
                "closed_at": sim_input.future_path.candles[sim_output.long_outcome.exit_bar_index].close_time_utc,
                "created_at_utc": sim_input.future_path.candles[sim_output.long_outcome.exit_bar_index].close_time_utc,
                "entry_reason": "engine_signal",
                "engine_summary": "buy breakout replay",
                "fee_bps": 4.0,
                "slippage_bps": 1.0,
                "time_forward_step_bars": 1,
                "entry_price": 100.8,
            },
        )

        assert actual["details"]["trade_id"].startswith("replay-")
        assert expected["details"]["trade_id"].startswith("replay-")
        actual["details"]["trade_id"] = "replay-id"
        expected["details"]["trade_id"] = "replay-id"
        actual["details"]["simulation_run_id"] = "sim-run"
        expected["details"]["simulation_run_id"] = "sim-run"
        assert actual == expected
        assert actual["details"]["comparative_outcomes"]["long_outcome"]["realized_r_net"] > 0
        assert result["metrics"]["trade_count"] == 1
