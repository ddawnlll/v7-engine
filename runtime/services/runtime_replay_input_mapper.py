"""Runtime payload -> SimulationInput mapper for replay-backed simulation.

This module is intentionally isolated from orchestration and result
materialization. It only converts one actionable historical runtime decision
point into the canonical ``SimulationInput`` contract consumed by
``simulation.adapters.replay_driver.ReplayDriver``.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pandas as pd

from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationProfile,
    TradingMode,
)


_MODE_DEFAULTS: dict[str, dict[str, Any]] = {
    "SWING": {
        "profile_version": "runtime-replay-swing-v1",
        "primary_interval": "4h",
        "max_holding_bars": 30,
        "stop_multiplier": 2.0,
        "target_multiplier": 2.0,
        "ambiguity_margin_r": 0.20,
        "min_action_edge_r": 0.35,
        "no_trade_default": False,
        "context_intervals": ["1d", "1h"],
        "refinement_intervals": ["1h"],
        "stop_method": "atr_wide",
        "target_method": "atr_wide",
        "mae_penalty_weight": 1.0,
        "cost_penalty_weight": 1.0,
        "time_penalty_weight": 0.3,
        "funding_rate": 0.0,
    },
    "SCALP": {
        "profile_version": "runtime-replay-scalp-v1",
        "primary_interval": "1h",
        "max_holding_bars": 12,
        "stop_multiplier": 1.5,
        "target_multiplier": 1.5,
        "ambiguity_margin_r": 0.10,
        "min_action_edge_r": 0.15,
        "no_trade_default": True,
        "context_intervals": ["4h", "15m"],
        "refinement_intervals": ["15m"],
        "stop_method": "atr_wide",
        "target_method": "atr_wide",
        "mae_penalty_weight": 2.0,
        "cost_penalty_weight": 2.0,
        "time_penalty_weight": 1.5,
        "funding_rate": 0.0,
    },
    "AGGRESSIVE_SCALP": {
        "profile_version": "runtime-replay-aggressive_scalp-v1",
        "primary_interval": "15m",
        "max_holding_bars": 5,
        "stop_multiplier": 1.0,
        "target_multiplier": 1.0,
        "ambiguity_margin_r": 0.05,
        "min_action_edge_r": 0.08,
        "no_trade_default": True,
        "context_intervals": ["1h", "5m"],
        "refinement_intervals": ["5m"],
        "stop_method": "atr_wide",
        "target_method": "atr_wide",
        "mae_penalty_weight": 3.0,
        "cost_penalty_weight": 3.0,
        "time_penalty_weight": 2.5,
        "funding_rate": 0.0,
    },
}


def _require_number(value: Any, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} is required and must be numeric") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} is required and must be > 0")
    return parsed


def _resolve_timestamp(value: Any) -> str:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.isoformat().replace("+00:00", "Z")


def _row_timestamp(row: dict[str, Any]) -> str:
    close_time = row.get("close_time")
    if close_time is not None and str(close_time) != "":
        return _resolve_timestamp(close_time)
    close_time_utc = row.get("close_time_utc")
    if close_time_utc is not None and str(close_time_utc) != "":
        return _resolve_timestamp(close_time_utc)
    open_time = row.get("open_time")
    if open_time is not None and str(open_time) != "":
        return _resolve_timestamp(open_time)
    raise ValueError("future_frame rows must provide close_time, close_time_utc, or open_time")


def _to_candle(row: dict[str, Any]) -> Candle:
    return Candle(
        open=float(row.get("open", 0.0)),
        high=float(row.get("high", 0.0)),
        low=float(row.get("low", 0.0)),
        close=float(row.get("close", 0.0)),
        volume=float(row.get("volume", 0.0)),
        close_time_utc=_row_timestamp(row),
    )


class RuntimeReplayInputMapper:
    """Build one canonical SimulationInput from runtime replay context."""

    def build_input(
        self,
        *,
        symbol: str,
        interval: str,
        mode: str,
        timestamp: str,
        signal: dict[str, Any],
        snapshot: dict[str, Any],
        future_frame: pd.DataFrame,
        simulation_profile: dict[str, Any] | None,
        execution_settings: dict[str, Any],
    ) -> SimulationInput:
        mode_key = str(mode).upper().strip()
        defaults = _MODE_DEFAULTS.get(mode_key)
        if defaults is None:
            raise ValueError(f"Unsupported mode for replay mapping: {mode}")

        profile_payload = {**defaults, **dict(simulation_profile or {})}
        primary_interval = str(profile_payload.get("primary_interval") or interval).strip()
        max_holding_bars = int(profile_payload.get("max_holding_bars") or 0)
        if max_holding_bars <= 0:
            raise ValueError("simulation profile max_holding_bars must be > 0")

        entry_price = signal.get("entry_price")
        if entry_price in (None, ""):
            entry_price = snapshot.get("close")
        entry_price = _require_number(entry_price, "entry_price")

        atr = signal.get("atr")
        if atr in (None, ""):
            atr = snapshot.get("atr")
        atr = _require_number(atr, "atr")

        future_rows = future_frame.to_dict(orient="records")
        capped_rows = future_rows[:max_holding_bars]
        candles = [_to_candle(row) for row in capped_rows]
        completeness = "COMPLETE" if len(future_rows) >= max_holding_bars else "PARTIAL"

        profile = SimulationProfile(
            profile_version=str(profile_payload.get("profile_version") or defaults["profile_version"]),
            mode=TradingMode(mode_key),
            primary_interval=primary_interval,
            max_holding_bars=max_holding_bars,
            stop_multiplier=float(profile_payload.get("stop_multiplier", defaults["stop_multiplier"])),
            target_multiplier=float(profile_payload.get("target_multiplier", defaults["target_multiplier"])),
            ambiguity_margin_r=float(profile_payload.get("ambiguity_margin_r", defaults["ambiguity_margin_r"])),
            min_action_edge_r=float(profile_payload.get("min_action_edge_r", defaults["min_action_edge_r"])),
            no_trade_default=bool(profile_payload.get("no_trade_default", defaults["no_trade_default"])),
            context_intervals=list(profile_payload.get("context_intervals", defaults["context_intervals"])),
            refinement_intervals=list(profile_payload.get("refinement_intervals", defaults["refinement_intervals"])),
            stop_method=str(profile_payload.get("stop_method", defaults["stop_method"])),
            target_method=str(profile_payload.get("target_method", defaults["target_method"])),
            mae_penalty_weight=float(profile_payload.get("mae_penalty_weight", defaults["mae_penalty_weight"])),
            cost_penalty_weight=float(profile_payload.get("cost_penalty_weight", defaults["cost_penalty_weight"])),
            time_penalty_weight=float(profile_payload.get("time_penalty_weight", defaults["time_penalty_weight"])),
            funding_rate=float(profile_payload.get("funding_rate", defaults["funding_rate"])),
        )

        return SimulationInput(
            symbol=str(symbol).upper().strip(),
            decision_timestamp=_resolve_timestamp(timestamp),
            mode=TradingMode(mode_key),
            primary_interval=primary_interval,
            entry_price=entry_price,
            atr=atr,
            future_path=FuturePath(
                candles=candles,
                completeness_status=completeness,
                expected_bars=max_holding_bars,
            ),
            profile=profile,
            simulation_family_version=str(
                execution_settings.get("simulation_family_version") or "simfam-1.0.0"
            ),
            cost_model_version=str(
                execution_settings.get("cost_model_version") or "cost-1.0.0"
            ),
        )

    @staticmethod
    def to_debug_dict(sim_input: SimulationInput) -> dict[str, Any]:
        """Dataclass -> dict helper for field-by-field parity assertions."""
        return asdict(sim_input)
