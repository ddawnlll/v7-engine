from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from runtime.services.runtime_replay_input_mapper import RuntimeReplayInputMapper
from simulation.contracts.models import Candle, FuturePath, SimulationInput, SimulationProfile, TradingMode


class TestRuntimeReplayInputMapper:
    def test_maps_runtime_payload_to_simulation_input_exactly(self):
        mapper = RuntimeReplayInputMapper()

        signal = {
            "entry_price": 101.25,
        }
        snapshot = {
            "close": 101.0,
            "atr": 2.5,
        }
        future_frame = pd.DataFrame(
            [
                {
                    "open_time": "2026-07-01T01:00:00Z",
                    "close_time": "2026-07-01T02:00:00Z",
                    "open": 101.3,
                    "high": 102.0,
                    "low": 100.9,
                    "close": 101.8,
                    "volume": 1500.0,
                },
                {
                    "open_time": "2026-07-01T02:00:00Z",
                    "close_time": "2026-07-01T03:00:00Z",
                    "open": 101.8,
                    "high": 102.4,
                    "low": 101.4,
                    "close": 102.2,
                    "volume": 1200.0,
                },
                {
                    "open_time": "2026-07-01T03:00:00Z",
                    "close_time": "2026-07-01T04:00:00Z",
                    "open": 102.2,
                    "high": 102.9,
                    "low": 101.7,
                    "close": 102.6,
                    "volume": 1100.0,
                },
            ]
        )
        simulation_profile = {
            "profile_version": "custom-scalp-v2",
            "primary_interval": "1h",
            "max_holding_bars": 3,
            "stop_multiplier": 1.6,
            "target_multiplier": 1.8,
            "ambiguity_margin_r": 0.11,
            "min_action_edge_r": 0.17,
            "no_trade_default": False,
            "context_intervals": ["4h", "15m"],
            "refinement_intervals": ["15m"],
            "stop_method": "atr_custom",
            "target_method": "atr_custom",
            "mae_penalty_weight": 2.5,
            "cost_penalty_weight": 2.25,
            "time_penalty_weight": 1.75,
            "funding_rate": 0.0002,
        }
        execution_settings = {
            "simulation_family_version": "simfam-2.1.0",
            "cost_model_version": "cost-3.0.0",
        }

        mapped = mapper.build_input(
            symbol="btcusdt",
            interval="1h",
            mode="scalp",
            timestamp="2026-07-01T01:00:00Z",
            signal=signal,
            snapshot=snapshot,
            future_frame=future_frame,
            simulation_profile=simulation_profile,
            execution_settings=execution_settings,
        )

        expected = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T01:00:00Z",
            mode=TradingMode.SCALP,
            primary_interval="1h",
            entry_price=101.25,
            atr=2.5,
            future_path=FuturePath(
                candles=[
                    Candle(open=101.3, high=102.0, low=100.9, close=101.8, volume=1500.0, close_time_utc="2026-07-01T02:00:00Z"),
                    Candle(open=101.8, high=102.4, low=101.4, close=102.2, volume=1200.0, close_time_utc="2026-07-01T03:00:00Z"),
                    Candle(open=102.2, high=102.9, low=101.7, close=102.6, volume=1100.0, close_time_utc="2026-07-01T04:00:00Z"),
                ],
                completeness_status="COMPLETE",
                expected_bars=3,
            ),
            profile=SimulationProfile(
                profile_version="custom-scalp-v2",
                mode=TradingMode.SCALP,
                primary_interval="1h",
                max_holding_bars=3,
                stop_multiplier=1.6,
                target_multiplier=1.8,
                ambiguity_margin_r=0.11,
                min_action_edge_r=0.17,
                no_trade_default=False,
                context_intervals=["4h", "15m"],
                refinement_intervals=["15m"],
                stop_method="atr_custom",
                target_method="atr_custom",
                mae_penalty_weight=2.5,
                cost_penalty_weight=2.25,
                time_penalty_weight=1.75,
                funding_rate=0.0002,
            ),
            simulation_family_version="simfam-2.1.0",
            cost_model_version="cost-3.0.0",
        )

        assert asdict(mapped) == asdict(expected)

    def test_uses_snapshot_close_and_atr_fallbacks(self):
        mapper = RuntimeReplayInputMapper()

        mapped = mapper.build_input(
            symbol="ethusdt",
            interval="4h",
            mode="SWING",
            timestamp="2026-07-02T00:00:00Z",
            signal={},
            snapshot={"close": 2500.0, "atr": 125.0},
            future_frame=pd.DataFrame(
                [
                    {
                        "open_time": "2026-07-02T04:00:00Z",
                        "close_time": "2026-07-02T08:00:00Z",
                        "open": 2500.0,
                        "high": 2525.0,
                        "low": 2480.0,
                        "close": 2510.0,
                        "volume": 500.0,
                    }
                ]
            ),
            simulation_profile=None,
            execution_settings={},
        )

        assert mapped.entry_price == 2500.0
        assert mapped.atr == 125.0
        assert mapped.future_path.completeness_status == "PARTIAL"
        assert mapped.future_path.expected_bars == 30

    def test_missing_atr_raises(self):
        mapper = RuntimeReplayInputMapper()

        try:
            mapper.build_input(
                symbol="btcusdt",
                interval="1h",
                mode="SCALP",
                timestamp="2026-07-01T01:00:00Z",
                signal={"entry_price": 100.0},
                snapshot={"close": 100.0},
                future_frame=pd.DataFrame([]),
                simulation_profile=None,
                execution_settings={},
            )
        except ValueError as exc:
            assert "atr" in str(exc).lower()
        else:
            raise AssertionError("Expected ValueError for missing ATR")
