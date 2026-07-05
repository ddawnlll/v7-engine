"""
Minimal simulation contract types.

Uses dataclasses to define the SimulationInput → SimulationOutput
boundary. Aligned with simulation/docs/contracts.md and the
contracts/schemas JSON Schema definitions.

No dependency on v7, alphaforge, runtime, or interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Enums ────────────────────────────────────────────────────────────


class TradingMode(str, Enum):
    SWING = "SWING"
    SCALP = "SCALP"
    AGGRESSIVE_SCALP = "AGGRESSIVE_SCALP"


class Action(str, Enum):
    LONG_NOW = "LONG_NOW"
    SHORT_NOW = "SHORT_NOW"
    NO_TRADE = "NO_TRADE"
    AMBIGUOUS_STATE = "AMBIGUOUS_STATE"


class ResolutionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    UNRESOLVED = "UNRESOLVED"
    INVALIDATED = "INVALIDATED"


class ExitReason(str, Enum):
    STOP_HIT = "STOP_HIT"
    TARGET_HIT = "TARGET_HIT"
    TIME_EXIT = "TIME_EXIT"
    HORIZON_END = "HORIZON_END"
    UNRESOLVED = "UNRESOLVED"
    INVALIDATED = "INVALIDATED"


class NoTradeQuality(str, Enum):
    CORRECT_NO_TRADE = "CORRECT_NO_TRADE"
    SAVED_LOSS = "SAVED_LOSS"
    MISSED_OPPORTUNITY = "MISSED_OPPORTUNITY"
    AMBIGUOUS_NO_TRADE = "AMBIGUOUS_NO_TRADE"


class PathQualityBucket(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ── Value Objects ─────────────────────────────────────────────────────


@dataclass
class Candle:
    """Single OHLCV candle."""
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    close_time_utc: str = ""


@dataclass
class SimulationProfile:
    """Mode-specific simulation configuration."""
    profile_version: str
    mode: TradingMode
    primary_interval: str
    max_holding_bars: int
    stop_multiplier: float
    target_multiplier: float
    ambiguity_margin_r: float
    min_action_edge_r: float
    no_trade_default: bool
    context_intervals: list[str] = field(default_factory=list)
    refinement_intervals: list[str] = field(default_factory=list)
    stop_method: str = "atr_wide"
    target_method: str = "atr_wide"
    mae_penalty_weight: float = 1.0
    cost_penalty_weight: float = 1.0
    time_penalty_weight: float = 0.3
    funding_rate: float = 0.0


@dataclass
class FuturePath:
    """Future price path for simulation."""
    candles: list[Candle]
    completeness_status: str = "COMPLETE"
    expected_bars: int = 0


@dataclass
class SimulationInput:
    """Entry contract for simulation engine."""
    symbol: str
    decision_timestamp: str
    mode: TradingMode
    primary_interval: str
    entry_price: float
    atr: float
    future_path: FuturePath
    profile: SimulationProfile
    simulation_family_version: str = "simfam-1.0.0"
    cost_model_version: str = "cost-1.0.0"


# ── Output Types ──────────────────────────────────────────────────────


@dataclass
class PathMetrics:
    """MFE/MAE and quality metrics for a simulated path."""
    mfe: float = 0.0
    mae: float = 0.0
    mfe_r: float = 0.0
    mae_r: float = 0.0
    time_to_mfe: int = 0
    time_to_mae: int = 0
    path_quality_score: float = 0.0
    path_quality_bucket: str = "MEDIUM"


@dataclass
class ActionOutcome:
    """Economic outcome for one directional action (LONG_NOW or SHORT_NOW)."""
    action: str = ""
    realized_r_gross: float = 0.0
    realized_r_net: float = 0.0
    fee_cost_r: float = 0.0
    slippage_cost_r: float = 0.0
    funding_cost_r: float = 0.0
    total_cost_r: float = 0.0
    exit_reason: str = ""
    exit_price: float = 0.0
    exit_bar_index: int = 0
    hold_duration_bars: int = 0
    action_utility: float = 0.0
    path_metrics: PathMetrics = field(default_factory=PathMetrics)
    same_candle_ambiguity: bool = False


@dataclass
class NoTradeOutcome:
    """Quality assessment of NO_TRADE action."""
    saved_loss_r: float = 0.0
    saved_loss_score: float = 0.0
    missed_opportunity_r: float = 0.0
    missed_opportunity_score: float = 0.0
    no_trade_quality: str = "AMBIGUOUS_NO_TRADE"
    was_correct_skip: bool = False


@dataclass
class SimulationLineage:
    """Version and run identity for a simulation output."""
    simulation_family_version: str = ""
    simulation_profile_version: str = ""
    cost_model_version: str = ""
    fee_model_version: str = ""
    slippage_model_version: str = ""
    funding_model_version: str = ""
    horizon_family: str = ""
    stop_family: str = ""
    target_family: str = ""
    time_exit_family: str = ""
    adapter_kind: str = "TRAINING"


@dataclass
class SimulationOutput:
    """Exit contract from simulation engine — comparative outcomes."""
    simulation_run_id: str
    symbol: str
    decision_timestamp: str
    mode: str
    primary_interval: str
    resolution_status: str
    long_outcome: ActionOutcome
    short_outcome: ActionOutcome
    no_trade_outcome: NoTradeOutcome
    best_action: str
    action_gap_r: float
    regret_r: float
    is_ambiguous: bool
    lineage: SimulationLineage = field(default_factory=SimulationLineage)
    second_best_action: str = ""
    invalidity_reason: str = ""
    monte_carlo_run_id: str = ""
    monte_carlo_family_version: str = ""


@dataclass
class MonteCarloOutput:
    """Aggregated output from N Monte Carlo perturbations of a SimulationInput.

    Contains the baseline (unperturbed) simulation result plus N perturbed
    results with aggregate statistics for robustness assessment.

    Perturbation params record the noise parameters used so downstream
    consumers can interpret the distributional evidence.
    """
    baseline_output: SimulationOutput
    perturbed_outputs: list[SimulationOutput]
    monte_carlo_run_id: str
    perturbation_params: dict
    aggregate_stats: dict
