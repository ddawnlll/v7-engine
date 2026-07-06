"""Project SimulationOutput into legacy runtime simulation result rows.

This module is a runtime-owned presentation layer. It does not perform
economic settlement; it only projects already-computed simulation truth into
the result shape expected by existing runtime diagnostics and export paths.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from simulation.contracts.models import SimulationOutput


_DIRECTION_ALIASES = {
    "BUY": "LONG_NOW",
    "LONG": "LONG_NOW",
    "LONG_NOW": "LONG_NOW",
    "SELL": "SHORT_NOW",
    "SHORT": "SHORT_NOW",
    "SHORT_NOW": "SHORT_NOW",
    "NEUTRAL": "NO_TRADE",
    "NO_TRADE": "NO_TRADE",
}

_RUNTIME_DIRECTION = {
    "LONG_NOW": "BUY",
    "SHORT_NOW": "SELL",
    "NO_TRADE": "NO_TRADE",
}

_EXIT_REASON_MAP = {
    "STOP_HIT": "stop_loss",
    "TARGET_HIT": "take_profit",
    "TIME_EXIT": "time_stop",
    "HORIZON_END": "horizon_end",
    "UNRESOLVED": "unresolved",
    "INVALIDATED": "invalidated",
}

_INTERVAL_TO_HOURS = {
    "1m": 1.0 / 60.0,
    "3m": 3.0 / 60.0,
    "5m": 5.0 / 60.0,
    "15m": 0.25,
    "30m": 0.5,
    "1h": 1.0,
    "2h": 2.0,
    "4h": 4.0,
    "6h": 6.0,
    "8h": 8.0,
    "12h": 12.0,
    "1d": 24.0,
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_selected_action(selected_direction: str) -> str:
    key = str(selected_direction or "").strip().upper()
    resolved = _DIRECTION_ALIASES.get(key)
    if resolved is None:
        raise ValueError(f"Unsupported selected_direction: {selected_direction}")
    return resolved


def _interval_hours(interval: Any) -> float | None:
    return _INTERVAL_TO_HOURS.get(str(interval or "").strip().lower())


class SimulationOutputResultMaterializer:
    """Translate one SimulationOutput into a legacy runtime result row."""

    def to_runtime_result(
        self,
        *,
        sim_output: SimulationOutput,
        selected_direction: str,
        quantity_context: dict[str, Any],
        run_context: dict[str, Any],
    ) -> dict[str, Any]:
        selected_action = _resolve_selected_action(selected_direction)
        runtime_direction = _RUNTIME_DIRECTION[selected_action]
        risk_amount = _to_float(quantity_context.get("risk_amount"), 0.0)
        quantity = _to_float(quantity_context.get("quantity"), 0.0)
        entry_price = _to_float(
            quantity_context.get("entry_price", run_context.get("entry_price")),
            0.0,
        )
        notional = _to_float(
            quantity_context.get("notional"),
            quantity * entry_price,
        )
        trade_id = str(
            run_context.get("trade_id")
            or f"replay-{sim_output.simulation_run_id}-{selected_action.lower()}"
        )
        created_at_utc = str(run_context.get("created_at_utc") or sim_output.decision_timestamp)
        interval = str(run_context.get("interval") or sim_output.primary_interval)
        hold_hours_per_bar = _interval_hours(interval)

        if selected_action == "LONG_NOW":
            selected_outcome = sim_output.long_outcome
        elif selected_action == "SHORT_NOW":
            selected_outcome = sim_output.short_outcome
        else:
            selected_outcome = None

        if selected_outcome is None:
            return {
                "symbol": str(run_context.get("symbol") or sim_output.symbol),
                "interval": interval,
                "mode": str(run_context.get("mode") or sim_output.mode),
                "direction": runtime_direction,
                "confidence": _to_float(run_context.get("confidence"), 0.0),
                "outcome": "NO_TRADE",
                "realized_r": 0.0,
                "details": {
                    "trade_id": trade_id,
                    "symbol": str(run_context.get("symbol") or sim_output.symbol),
                    "direction": runtime_direction,
                    "mode": str(run_context.get("mode") or sim_output.mode),
                    "interval": interval,
                    "entry_price": entry_price,
                    "exit_price": entry_price,
                    "effective_entry_price": entry_price,
                    "effective_exit_price": entry_price,
                    "pnl": 0.0,
                    "pnl_pct": 0.0,
                    "confidence": _to_float(run_context.get("confidence"), 0.0),
                    "hold_time_hours": 0.0,
                    "status": "CLOSED",
                    "opened_at": str(run_context.get("opened_at") or sim_output.decision_timestamp),
                    "closed_at": str(run_context.get("closed_at") or sim_output.decision_timestamp),
                    "stop_reason": None,
                    "entry_reason": "replay_driver_no_trade",
                    "exit_reason": "no_trade",
                    "risk_amount": risk_amount,
                    "notional": notional,
                    "fees": 0.0,
                    "fee_bps": _to_float(run_context.get("fee_bps"), 0.0),
                    "slippage_bps": _to_float(run_context.get("slippage_bps"), 0.0),
                    "time_forward_step_bars": int(run_context.get("time_forward_step_bars") or 1),
                    "engine_summary": str(
                        run_context.get("engine_summary")
                        or f"ReplayDriver selected NO_TRADE ({sim_output.no_trade_outcome.no_trade_quality})"
                    ),
                    "close_index": None,
                    "resolution_status": sim_output.resolution_status,
                    "adapter_kind": sim_output.lineage.adapter_kind,
                    "simulation_run_id": sim_output.simulation_run_id,
                    "selected_action": selected_action,
                    "selected_action_utility": 0.0,
                    "comparative_outcomes": {
                        "long_outcome": asdict(sim_output.long_outcome),
                        "short_outcome": asdict(sim_output.short_outcome),
                        "no_trade_outcome": asdict(sim_output.no_trade_outcome),
                    },
                    "selection_summary": {
                        "best_action": sim_output.best_action,
                        "second_best_action": sim_output.second_best_action,
                        "action_gap_r": sim_output.action_gap_r,
                        "regret_r": sim_output.regret_r,
                        "is_ambiguous": sim_output.is_ambiguous,
                    },
                    "materialized_from": "SimulationOutputResultMaterializer",
                },
                "created_at_utc": created_at_utc,
            }

        pnl = selected_outcome.realized_r_net * risk_amount
        pnl_pct = (pnl / notional * 100.0) if notional else 0.0
        normalized_exit_reason = _EXIT_REASON_MAP.get(selected_outcome.exit_reason, str(selected_outcome.exit_reason or "").lower())
        status = "CLOSED"
        if sim_output.resolution_status == "UNRESOLVED":
            status = "UNRESOLVED"
        elif sim_output.resolution_status == "INVALIDATED":
            status = "INVALIDATED"
        elif normalized_exit_reason == "stop_loss":
            status = "STOPPED_OUT"

        hold_time_hours = None
        if hold_hours_per_bar is not None:
            hold_time_hours = selected_outcome.hold_duration_bars * hold_hours_per_bar

        return {
            "symbol": str(run_context.get("symbol") or sim_output.symbol),
            "interval": interval,
            "mode": str(run_context.get("mode") or sim_output.mode),
            "direction": runtime_direction,
            "confidence": _to_float(run_context.get("confidence"), 0.0),
            "outcome": "WIN" if selected_outcome.realized_r_net > 0 else "LOSS" if selected_outcome.realized_r_net < 0 else "BREAKEVEN",
                "realized_r": selected_outcome.realized_r_net,
                "details": {
                    "trade_id": trade_id,
                    "symbol": str(run_context.get("symbol") or sim_output.symbol),
                    "direction": runtime_direction,
                    "mode": str(run_context.get("mode") or sim_output.mode),
                "interval": interval,
                "entry_price": entry_price,
                "exit_price": selected_outcome.exit_price,
                "effective_entry_price": entry_price,
                "effective_exit_price": selected_outcome.exit_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "confidence": _to_float(run_context.get("confidence"), 0.0),
                "hold_time_hours": hold_time_hours,
                "status": status,
                    "opened_at": str(run_context.get("opened_at") or sim_output.decision_timestamp),
                    "closed_at": str(run_context.get("closed_at") or run_context.get("opened_at") or sim_output.decision_timestamp),
                    "stop_reason": normalized_exit_reason if normalized_exit_reason == "stop_loss" else None,
                    "entry_reason": str(run_context.get("entry_reason") or "replay_driver"),
                    "exit_reason": normalized_exit_reason,
                    "risk_amount": risk_amount,
                    "notional": notional,
                    "fees": selected_outcome.total_cost_r * risk_amount,
                    "fee_bps": _to_float(run_context.get("fee_bps"), 0.0),
                    "slippage_bps": _to_float(run_context.get("slippage_bps"), 0.0),
                    "time_forward_step_bars": int(run_context.get("time_forward_step_bars") or 1),
                "engine_summary": str(
                    run_context.get("engine_summary")
                    or f"ReplayDriver selected {selected_action} ({sim_output.best_action})"
                    ),
                    "close_index": selected_outcome.exit_bar_index,
                    "resolution_status": sim_output.resolution_status,
                    "adapter_kind": sim_output.lineage.adapter_kind,
                    "simulation_run_id": sim_output.simulation_run_id,
                    "comparative_outcomes": {
                        "long_outcome": asdict(sim_output.long_outcome),
                        "short_outcome": asdict(sim_output.short_outcome),
                        "no_trade_outcome": asdict(sim_output.no_trade_outcome),
                    },
                    "selection_summary": {
                        "best_action": sim_output.best_action,
                    "second_best_action": sim_output.second_best_action,
                        "action_gap_r": sim_output.action_gap_r,
                        "regret_r": sim_output.regret_r,
                        "is_ambiguous": sim_output.is_ambiguous,
                    },
                    "path_metrics": asdict(selected_outcome.path_metrics),
                    "same_candle_ambiguity": selected_outcome.same_candle_ambiguity,
                    "selected_action": selected_action,
                    "selected_action_utility": selected_outcome.action_utility,
                    "materialized_from": "SimulationOutputResultMaterializer",
                },
                "created_at_utc": created_at_utc,
            }
