"""
Side-effect-free adapter wrapping the simulation engine for training/evaluation.

Transforms dict-based SimulationInput → simulated SimulationOutput → dict.

Domain rules:
- Deterministic: same input → same output
- Side-effect-free: no DB writes, no exchange calls
- Owned by /simulation, consumed through stable dict contracts
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.engine import simulate


_ADAPTER_KINDS = ("TRAINING", "EVALUATION", "REPLAY", "PAPER", "LIVE_OUTCOME")


def _dict_to_candle(d: dict) -> Candle:
    return Candle(
        open=float(d.get("open", 0.0)),
        high=float(d.get("high", 0.0)),
        low=float(d.get("low", 0.0)),
        close=float(d.get("close", 0.0)),
        volume=float(d.get("volume", 0.0)),
        close_time_utc=str(d.get("close_time_utc", "")),
    )


def _dict_to_profile(profile: dict[str, Any]) -> SimulationProfile:
    """Convert a profile dict to a SimulationProfile dataclass."""
    mode_str = str(profile.get("mode", "SWING")).upper()
    return SimulationProfile(
        profile_version=str(profile.get("profile_version", "unknown")),
        mode=TradingMode(mode_str),
        primary_interval=str(profile.get("primary_interval", "4h")),
        max_holding_bars=int(profile.get("max_holding_bars", 30)),
        stop_multiplier=float(profile.get("stop_multiplier", 2.0)),
        target_multiplier=float(profile.get("target_multiplier", 2.5)),
        ambiguity_margin_r=float(profile.get("ambiguity_margin_r", 0.20)),
        min_action_edge_r=float(profile.get("min_action_edge_r", 0.35)),
        no_trade_default=bool(profile.get("no_trade_default", False)),
        context_intervals=list(profile.get("context_intervals", [])),
        refinement_intervals=list(profile.get("refinement_intervals", [])),
        stop_method=str(profile.get("stop_method", "atr_wide")),
        target_method=str(profile.get("target_method", "atr_wide")),
        mae_penalty_weight=float(profile.get("mae_penalty_weight", 1.0)),
        cost_penalty_weight=float(profile.get("cost_penalty_weight", 1.0)),
        time_penalty_weight=float(profile.get("time_penalty_weight", 0.3)),
    )


def _output_to_dict(output: SimulationOutput) -> dict[str, Any]:
    """Convert a SimulationOutput dataclass to a plain dict."""
    return {
        "simulation_run_id": output.simulation_run_id,
        "symbol": output.symbol,
        "decision_timestamp": output.decision_timestamp,
        "mode": output.mode,
        "primary_interval": output.primary_interval,
        "resolution_status": output.resolution_status,
        "invalidity_reason": output.invalidity_reason,
        "best_action": output.best_action,
        "second_best_action": output.second_best_action,
        "action_gap_r": output.action_gap_r,
        "regret_r": output.regret_r,
        "is_ambiguous": output.is_ambiguous,
        "monte_carlo_run_id": output.monte_carlo_run_id,
        "monte_carlo_family_version": output.monte_carlo_family_version,
        "lineage": {
            "simulation_family_version": output.lineage.simulation_family_version,
            "simulation_profile_version": output.lineage.simulation_profile_version,
            "cost_model_version": output.lineage.cost_model_version,
            "fee_model_version": output.lineage.fee_model_version,
            "slippage_model_version": output.lineage.slippage_model_version,
            "horizon_family": output.lineage.horizon_family,
            "stop_family": output.lineage.stop_family,
            "target_family": output.lineage.target_family,
            "time_exit_family": output.lineage.time_exit_family,
            "adapter_kind": output.lineage.adapter_kind,
        },
        "long_outcome": {
            "action": output.long_outcome.action,
            "realized_r_gross": output.long_outcome.realized_r_gross,
            "realized_r_net": output.long_outcome.realized_r_net,
            "fee_cost_r": output.long_outcome.fee_cost_r,
            "slippage_cost_r": output.long_outcome.slippage_cost_r,
            "total_cost_r": output.long_outcome.total_cost_r,
            "exit_reason": output.long_outcome.exit_reason,
            "exit_price": output.long_outcome.exit_price,
            "exit_bar_index": output.long_outcome.exit_bar_index,
            "hold_duration_bars": output.long_outcome.hold_duration_bars,
            "action_utility": output.long_outcome.action_utility,
            "path_metrics": {
                "mfe": output.long_outcome.path_metrics.mfe,
                "mae": output.long_outcome.path_metrics.mae,
                "mfe_r": output.long_outcome.path_metrics.mfe_r,
                "mae_r": output.long_outcome.path_metrics.mae_r,
                "time_to_mfe": output.long_outcome.path_metrics.time_to_mfe,
                "time_to_mae": output.long_outcome.path_metrics.time_to_mae,
                "path_quality_score": output.long_outcome.path_metrics.path_quality_score,
                "path_quality_bucket": output.long_outcome.path_metrics.path_quality_bucket,
            },
        },
        "short_outcome": {
            "action": output.short_outcome.action,
            "realized_r_gross": output.short_outcome.realized_r_gross,
            "realized_r_net": output.short_outcome.realized_r_net,
            "fee_cost_r": output.short_outcome.fee_cost_r,
            "slippage_cost_r": output.short_outcome.slippage_cost_r,
            "total_cost_r": output.short_outcome.total_cost_r,
            "exit_reason": output.short_outcome.exit_reason,
            "exit_price": output.short_outcome.exit_price,
            "exit_bar_index": output.short_outcome.exit_bar_index,
            "hold_duration_bars": output.short_outcome.hold_duration_bars,
            "action_utility": output.short_outcome.action_utility,
            "path_metrics": {
                "mfe": output.short_outcome.path_metrics.mfe,
                "mae": output.short_outcome.path_metrics.mae,
                "mfe_r": output.short_outcome.path_metrics.mfe_r,
                "mae_r": output.short_outcome.path_metrics.mae_r,
                "time_to_mfe": output.short_outcome.path_metrics.time_to_mfe,
                "time_to_mae": output.short_outcome.path_metrics.time_to_mae,
                "path_quality_score": output.short_outcome.path_metrics.path_quality_score,
                "path_quality_bucket": output.short_outcome.path_metrics.path_quality_bucket,
            },
        },
        "no_trade_outcome": {
            "saved_loss_r": output.no_trade_outcome.saved_loss_r,
            "saved_loss_score": output.no_trade_outcome.saved_loss_score,
            "missed_opportunity_r": output.no_trade_outcome.missed_opportunity_r,
            "missed_opportunity_score": output.no_trade_outcome.missed_opportunity_score,
            "no_trade_quality": output.no_trade_outcome.no_trade_quality,
            "was_correct_skip": output.no_trade_outcome.was_correct_skip,
        },
    }


def run_simulation(input_dict: dict[str, Any], adapter_kind: str = "TRAINING") -> dict[str, Any]:
    """Run the simulation engine from a dict-based input.

    This is the primary entry point for consuming simulation from outside
    the /simulation domain.

    Args:
        input_dict: Dict matching the SimulationInput schema.
        adapter_kind: One of TRAINING, EVALUATION, REPLAY, PAPER, LIVE_OUTCOME.

    Returns:
        Dict matching the SimulationOutput schema.

    Raises:
        ValueError: If input is missing required fields.
    """
    if adapter_kind not in _ADAPTER_KINDS:
        raise ValueError(f"Unknown adapter_kind: {adapter_kind}. Must be one of {_ADAPTER_KINDS}")

    input_copy = copy.deepcopy(input_dict)

    # Required fields
    symbol = str(input_copy.get("symbol", ""))
    decision_timestamp = str(input_copy.get("decision_timestamp", ""))
    entry_price = float(input_copy.get("entry_price", 0.0))
    atr = float(input_copy.get("atr", 0.0))
    mode_str = str(input_copy.get("mode", "SWING")).upper()

    if not symbol or not decision_timestamp or entry_price <= 0 or atr <= 0:
        raise ValueError(
            f"Missing or invalid required fields: symbol={symbol}, "
            f"timestamp={decision_timestamp}, entry_price={entry_price}, atr={atr}"
        )

    # Parse candles
    raw_candles = list(input_copy.get("future_path", {}).get("candles", []))
    candles = [_dict_to_candle(c) for c in raw_candles]

    # Parse profile
    raw_profile = dict(input_copy.get("profile", {}))
    profile = _dict_to_profile(raw_profile)
    # Override mode from profile if input doesn't specify
    if not mode_str or mode_str not in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        mode_str = profile.mode.value

    # Build SimulationInput
    sim_input = SimulationInput(
        symbol=symbol,
        decision_timestamp=decision_timestamp,
        mode=TradingMode(mode_str),
        primary_interval=str(input_copy.get("primary_interval", profile.primary_interval)),
        entry_price=entry_price,
        atr=atr,
        future_path=FuturePath(
            candles=candles,
            completeness_status=str(input_copy.get("future_path", {}).get("completeness_status", "COMPLETE")),
            expected_bars=int(input_copy.get("future_path", {}).get("expected_bars", 0)),
        ),
        profile=profile,
        simulation_family_version=str(input_copy.get("simulation_family_version", "simfam-1.0.0")),
        cost_model_version=str(input_copy.get("cost_model_version", "cost-1.0.0")),
    )

    # Run engine
    output = simulate(sim_input)

    # Set adapter kind in lineage
    output.lineage.adapter_kind = adapter_kind

    return _output_to_dict(output)


def run_training(input_dict: dict[str, Any]) -> dict[str, Any]:
    """Run simulation in TRAINING mode (side-effect-free)."""
    return run_simulation(input_dict, adapter_kind="TRAINING")


def run_evaluation(input_dict: dict[str, Any]) -> dict[str, Any]:
    """Run simulation in EVALUATION mode."""
    return run_simulation(input_dict, adapter_kind="EVALUATION")
