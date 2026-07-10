"""AlphaForge Discovery Pipeline — profit-seeking alpha discovery.

This package bridges trained XGBoost models → simulation engine backtest →
profitability analysis → rejection or V7 handoff.

It answers a question neither AlphaForge nor the simulation engine answers alone:
"Does this trained model generate profitable simulated trades?"

Domain roles:
  AlphaForge  → alpha discovery (owns this pipeline)
  Simulation  → economic truth (simulation engine consumed as a library)
  V7          → policy acceptance (handoff packages produced for V7 gates)

Layer metric ownership (from discovery_authority.md):
  This pipeline computes trade-level metrics INTERNALLY for rejection decisions.
  The empirical report and handoff package correctly attribute metric ownership
  per the domain boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ═══════════════════════════════════════════════════════════════════════
# Phase 1: Core Data Types
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class TradeSignal:
    """Model-generated trade entry signal with entry-price context.

    Each signal represents one model prediction that exceeded the confidence
    threshold and was classified as LONG_NOW or SHORT_NOW.  The stop/target
    prices are pre-computed from the mode's multipliers so the simulation
    engine can consume them directly.
    """

    bar_index: int
    """Position in the aligned training frame (used to look up future candles)."""

    timestamp: int
    """Unix-ns timestamp of the entry bar."""

    symbol: str
    """Trading pair, e.g. 'BTCUSDT'."""

    side: str
    """'LONG' or 'SHORT'."""

    entry_price: float
    """Close price at entry (the bar's close)."""

    atr: float
    """ATR at entry time (14-bar)."""

    stop_price: float
    """Stop-loss level = entry ± ATR × stop_multiplier."""

    target_price: float
    """Take-profit level = entry ± ATR × target_multiplier."""

    confidence: float
    """Max softmax probability from the model (before threshold)."""

    model_score: float
    """Raw probability for the chosen class."""

    initial_risk: float
    """Entry price distance to stop in price units (|entry - stop|)."""


@dataclass
class BacktestTradeResult:
    """One trade result produced by the simulation engine.

    Wraps the raw SimulationOutput together with the originating signal
    metadata so downstream analysis can trace every trade back to its
    model prediction.
    """

    signal: TradeSignal
    """The trade signal that produced this result."""

    realized_r_net: float
    """Net R-multiple after all costs (simulation engine's authoritative value)."""

    realized_r_gross: float
    """Gross R-multiple before costs."""

    fee_cost_r: float
    """Fee cost in R units."""

    slippage_cost_r: float
    """Slippage cost in R units."""

    funding_cost_r: float = 0.0
    """Funding cost in R units (zero unless perpetual swap)."""

    hold_bars: int = 0
    """Actual bars held (from simulation engine)."""

    exit_price: float = 0.0
    """Price at exit."""

    exit_reason: str = ""
    """STOP_HIT / TARGET_HIT / TIME_EXIT / HORIZON_END."""

    path_quality_score: float = 0.0
    """Simulation engine's path quality (0-1)."""

    no_trade_saved_loss_r: float = 0.0
    """If NO_TRADE would have saved loss, how much."""

    no_trade_missed_opportunity_r: float = 0.0
    """If NO_TRADE missed opportunity, how much."""


@dataclass
class DiscoveryConfig:
    """Configuration for one discovery pipeline run."""

    mode: str = "SWING"
    """Trading mode: SWING / SCALP / AGGRESSIVE_SCALP."""

    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    """Symbols to include."""

    features: str = "all"
    """Feature group selection ('all' or comma-separated)."""

    folds: int = 6
    """Walk-forward validation fold count."""

    confidence_threshold: float = 0.55
    """Min softmax probability for a directional trade."""

    use_synthetic: bool = False
    """Force synthetic data when real data unavailable."""

    n_bars: int = 3000
    """Number of synthetic bars (synthetic mode only)."""

    panel_cache: str | None = None
    """Path to factor_sprint panel cache directory."""

    data_dir: str | None = None
    """Path to raw parquet data directory."""

    output_dir: str = "artifacts/discovery"
    """Output directory for reports and artifacts."""

    create_handoff: bool = True
    """Build V7 handoff package on successful discovery."""

    random_seed: int = 42
    """Random seed for reproducibility."""

    execution_mode: str = "TAKER"
    """Execution mode: TAKER / MAKER / HYBRID (Phase E)."""

    maker_fill_assumption: str = "base"
    """Maker fill probability tier: pessimistic / base / optimistic."""

    holdout_cutoff: str | None = None
    """ISO date string (e.g. '2026-04-07') for 3-month holdout reservation.
    When set, all data BEFORE this date is used for training/WFV, and the
    model is evaluated ONCE on data AFTER this date. Only the final evaluation
    on holdout data is reported — no retry, no tuning on holdout."""


@dataclass
class DiscoveryResult:
    """Result of one discovery pipeline run."""

    config: DiscoveryConfig
    """The configuration used for this run."""

    status: str = "ERROR"
    """PASS / REJECTED / ERROR."""

    rejection: dict | None = None
    """Rejection result details (when status=REJECTED)."""

    metrics: dict | None = None
    """Computed profitability metrics."""

    wfv_metrics: dict | None = None
    """Walk-forward validation metrics from training."""

    mode_research_report: dict | None = None
    """ModeResearchReport (built when alpha passes rejection)."""

    handoff: dict | None = None
    """V7HandoffPackage (built when create_handoff=True and alpha passes)."""

    trade_count: int = 0
    """Number of simulated active trades."""

    signal_count: int = 0
    """Number of trade signals generated."""

    duration_seconds: float = 0.0
    """Total pipeline duration."""

    errors: list[str] = field(default_factory=list)
    """Non-fatal errors encountered during the run."""


# ═══════════════════════════════════════════════════════════════════════
# Module exports
# ═══════════════════════════════════════════════════════════════════════

__all__ = [
    "TradeSignal",
    "BacktestTradeResult",
    "DiscoveryConfig",
    "DiscoveryResult",
]
