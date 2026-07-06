from __future__ import annotations

from simulation.contracts.models import (
    ActionOutcome,
    NoTradeOutcome,
    PathMetrics,
    SimulationLineage,
    SimulationOutput,
)

from runtime.services.simulation_output_result_materializer import SimulationOutputResultMaterializer


def _sample_output() -> SimulationOutput:
    return SimulationOutput(
        simulation_run_id="simrun-001",
        symbol="BTCUSDT",
        decision_timestamp="2026-07-06T10:00:00Z",
        mode="SCALP",
        primary_interval="1h",
        resolution_status="COMPLETE",
        long_outcome=ActionOutcome(
            action="LONG_NOW",
            realized_r_gross=1.4,
            realized_r_net=1.2,
            fee_cost_r=0.1,
            slippage_cost_r=0.1,
            total_cost_r=0.2,
            exit_reason="TARGET_HIT",
            exit_price=103.0,
            exit_bar_index=4,
            hold_duration_bars=4,
            action_utility=1.18,
            path_metrics=PathMetrics(
                mfe=2.0,
                mae=-0.5,
                mfe_r=1.8,
                mae_r=-0.4,
                time_to_mfe=3,
                time_to_mae=1,
                path_quality_score=0.88,
                path_quality_bucket="HIGH",
            ),
        ),
        short_outcome=ActionOutcome(
            action="SHORT_NOW",
            realized_r_gross=-0.8,
            realized_r_net=-1.0,
            fee_cost_r=0.1,
            slippage_cost_r=0.1,
            total_cost_r=0.2,
            exit_reason="STOP_HIT",
            exit_price=101.5,
            exit_bar_index=2,
            hold_duration_bars=2,
            action_utility=-0.95,
            path_metrics=PathMetrics(path_quality_score=0.2, path_quality_bucket="LOW"),
            same_candle_ambiguity=True,
        ),
        no_trade_outcome=NoTradeOutcome(
            saved_loss_r=1.0,
            saved_loss_score=0.9,
            missed_opportunity_r=1.2,
            missed_opportunity_score=0.8,
            no_trade_quality="MISSED_OPPORTUNITY",
            was_correct_skip=False,
        ),
        best_action="LONG_NOW",
        second_best_action="NO_TRADE",
        action_gap_r=0.2,
        regret_r=1.0,
        is_ambiguous=False,
        lineage=SimulationLineage(
            simulation_family_version="simfam-2.1.0",
            simulation_profile_version="scalp-v2",
            cost_model_version="cost-3.0.0",
            fee_model_version="fee-1.0.0",
            slippage_model_version="slip-1.0.0",
            funding_model_version="fund-1.0.0",
            horizon_family="horizon-1.0.0",
            stop_family="stop-1.0.0",
            target_family="target-1.0.0",
            time_exit_family="time-1.0.0",
            adapter_kind="REPLAY",
        ),
    )


def _base_quantity_context() -> dict[str, float]:
    return {
        "entry_price": 100.0,
        "quantity": 2.5,
        "risk_amount": 250.0,
        "notional": 250.0,
    }


def _base_run_context() -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "mode": "SCALP",
        "confidence": 78.0,
        "opened_at": "2026-07-06T10:00:00Z",
        "closed_at": "2026-07-06T14:00:00Z",
        "trade_id": "trade-001",
        "time_forward_step_bars": 1,
        "engine_summary": "runtime replay signal",
        "fee_bps": 4.0,
        "slippage_bps": 1.0,
        "created_at_utc": "2026-07-06T14:00:01Z",
    }


class TestSimulationOutputResultMaterializer:
    def test_materializes_long_selected_trade_exactly(self):
        materializer = SimulationOutputResultMaterializer()
        result = materializer.to_runtime_result(
            sim_output=_sample_output(),
            selected_direction="BUY",
            quantity_context=_base_quantity_context(),
            run_context=_base_run_context(),
        )

        assert result == {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "mode": "SCALP",
            "direction": "BUY",
            "confidence": 78.0,
            "outcome": "WIN",
            "realized_r": 1.2,
            "details": {
                "trade_id": "trade-001",
                "symbol": "BTCUSDT",
                "direction": "BUY",
                "mode": "SCALP",
                "interval": "1h",
                "entry_price": 100.0,
                "exit_price": 103.0,
                "effective_entry_price": 100.0,
                "effective_exit_price": 103.0,
                "pnl": 300.0,
                "pnl_pct": 120.0,
                "confidence": 78.0,
                "hold_time_hours": 4.0,
                "status": "CLOSED",
                "opened_at": "2026-07-06T10:00:00Z",
                "closed_at": "2026-07-06T14:00:00Z",
                "stop_reason": None,
                "entry_reason": "replay_driver",
                "exit_reason": "take_profit",
                "risk_amount": 250.0,
                "notional": 250.0,
                "fees": 50.0,
                "fee_bps": 4.0,
                "slippage_bps": 1.0,
                "time_forward_step_bars": 1,
                "engine_summary": "runtime replay signal",
                "close_index": 4,
                "resolution_status": "COMPLETE",
                "adapter_kind": "REPLAY",
                "simulation_run_id": "simrun-001",
                "comparative_outcomes": {
                    "long_outcome": {
                        "action": "LONG_NOW",
                        "realized_r_gross": 1.4,
                        "realized_r_net": 1.2,
                        "fee_cost_r": 0.1,
                        "slippage_cost_r": 0.1,
                        "funding_cost_r": 0.0,
                        "total_cost_r": 0.2,
                        "exit_reason": "TARGET_HIT",
                        "exit_price": 103.0,
                        "exit_bar_index": 4,
                        "hold_duration_bars": 4,
                        "action_utility": 1.18,
                        "path_metrics": {
                            "mfe": 2.0,
                            "mae": -0.5,
                            "mfe_r": 1.8,
                            "mae_r": -0.4,
                            "time_to_mfe": 3,
                            "time_to_mae": 1,
                            "path_quality_score": 0.88,
                            "path_quality_bucket": "HIGH",
                        },
                        "same_candle_ambiguity": False,
                    },
                    "short_outcome": {
                        "action": "SHORT_NOW",
                        "realized_r_gross": -0.8,
                        "realized_r_net": -1.0,
                        "fee_cost_r": 0.1,
                        "slippage_cost_r": 0.1,
                        "funding_cost_r": 0.0,
                        "total_cost_r": 0.2,
                        "exit_reason": "STOP_HIT",
                        "exit_price": 101.5,
                        "exit_bar_index": 2,
                        "hold_duration_bars": 2,
                        "action_utility": -0.95,
                        "path_metrics": {
                            "mfe": 0.0,
                            "mae": 0.0,
                            "mfe_r": 0.0,
                            "mae_r": 0.0,
                            "time_to_mfe": 0,
                            "time_to_mae": 0,
                            "path_quality_score": 0.2,
                            "path_quality_bucket": "LOW",
                        },
                        "same_candle_ambiguity": True,
                    },
                    "no_trade_outcome": {
                        "saved_loss_r": 1.0,
                        "saved_loss_score": 0.9,
                        "missed_opportunity_r": 1.2,
                        "missed_opportunity_score": 0.8,
                        "no_trade_quality": "MISSED_OPPORTUNITY",
                        "was_correct_skip": False,
                    },
                },
                "selection_summary": {
                    "best_action": "LONG_NOW",
                    "second_best_action": "NO_TRADE",
                    "action_gap_r": 0.2,
                    "regret_r": 1.0,
                    "is_ambiguous": False,
                },
                "path_metrics": {
                    "mfe": 2.0,
                    "mae": -0.5,
                    "mfe_r": 1.8,
                    "mae_r": -0.4,
                    "time_to_mfe": 3,
                    "time_to_mae": 1,
                    "path_quality_score": 0.88,
                    "path_quality_bucket": "HIGH",
                },
                "same_candle_ambiguity": False,
                "selected_action": "LONG_NOW",
                "selected_action_utility": 1.18,
                "materialized_from": "SimulationOutputResultMaterializer",
            },
            "created_at_utc": "2026-07-06T14:00:01Z",
        }

    def test_materializes_short_selected_trade_exactly(self):
        materializer = SimulationOutputResultMaterializer()
        result = materializer.to_runtime_result(
            sim_output=_sample_output(),
            selected_direction="SHORT",
            quantity_context=_base_quantity_context(),
            run_context=_base_run_context(),
        )

        assert result["direction"] == "SELL"
        assert result["outcome"] == "LOSS"
        assert result["realized_r"] == -1.0
        assert result["details"]["exit_reason"] == "stop_loss"
        assert result["details"]["stop_reason"] == "stop_loss"
        assert result["details"]["pnl"] == -250.0
        assert result["details"]["fees"] == 50.0
        assert result["details"]["same_candle_ambiguity"] is True
        assert result["details"]["selected_action"] == "SHORT_NOW"

    def test_materializes_no_trade_case_and_preserves_comparative_evidence(self):
        materializer = SimulationOutputResultMaterializer()
        result = materializer.to_runtime_result(
            sim_output=_sample_output(),
            selected_direction="NO_TRADE",
            quantity_context=_base_quantity_context(),
            run_context=_base_run_context(),
        )

        assert result["direction"] == "NO_TRADE"
        assert result["outcome"] == "NO_TRADE"
        assert result["realized_r"] == 0.0
        assert result["details"]["status"] == "CLOSED"
        assert result["details"]["exit_reason"] == "no_trade"
        assert result["details"]["pnl"] == 0.0
        assert result["details"]["comparative_outcomes"]["no_trade_outcome"]["no_trade_quality"] == "MISSED_OPPORTUNITY"
        assert result["details"]["adapter_kind"] == "REPLAY"
