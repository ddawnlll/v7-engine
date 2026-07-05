# Simulation vs Runtime — Detailed Capability Comparison

## Executive Summary

| Aspect | Simulation (`/simulation`) | Runtime (`/runtime`) |
|--------|---------------------------|---------------------|
| **Purpose** | Economic truth authority — deterministic R-computation | Operational backend — live signal generation + paper/live execution |
| **State** | Fully implemented (S0-S6 complete) | Fully implemented, running in production |
| **Paper trading** | ❌ No — simulation is batch/offline | ✅ Yes — `PaperExecutionService` with full order lifecycle |
| **Live trading** | ❌ No | ✅ Yes — Binance USDM integration exists |
| **Cost model** | ✅ Full: fee + slippage + funding | ✅ Full: fee + slippage (via simulation integration) |
| **Analyzer** | ❌ No — consumes signals, doesn't generate them | ✅ Full: 12-stage decision pipeline with regime/trend/structure |
| **Learning layer** | ❌ No | ✅ Adaptive calibration + stop-loss adjustment |
| **PostgreSQL** | ❌ No | ✅ Full operational schema |
| **API surface** | ❌ No (library only) | ✅ Full FastAPI with 30+ endpoints |

---

## 1. Simulation Engine — What It Does

### Core Function
Takes `SimulationInput` (entry_price, ATR, future candles, profile) and produces `SimulationOutput`:
- Compares LONG_NOW, SHORT_NOW, and NO_TRADE under identical cost/exit semantics
- Computes `realized_r_net` per direction
- Selects `best_action` with ambiguity detection
- Records `PathMetrics` (MFE, MAE, time-to-MFE)
- Classifies `NoTradeOutcome` (SAVED_LOSS / MISSED_OPPORTUNITY / CORRECT / AMBIGUOUS)

### Cost Model (from `simulation/engine/costs.py`)
```
fee_cost_r = (entry_fee + exit_fee) / 1R
  - taker_fee_bps: 4.0 (0.04%)
  - maker_fee_bps: 2.0 (0.02%)
slippage_cost_r = (entry_slippage + exit_slippage) / 1R
  - slippage_bps: 1.0 (0.01%)
  - volatility_adjusted: true
funding_cost_r = funding_rate × holding_bars / 8
realized_r_net = realized_r_gross - fee_cost_r - slippage_cost_r - funding_cost_r
```

### Exit Logic (from `simulation/engine/exits.py`)
- Stop hit before target (conservative precedence)
- Same-candle ambiguity: stop takes precedence, recorded
- Time exit at max_holding_bars
- Horizon end: path exhausted without exit
- UNRESOLVED vs INVALIDATED as distinct states

### Mode Profiles
| Parameter | SWING | SCALP | AGGRESSIVE_SCALP |
|-----------|-------|-------|-----------------|
| Primary interval | 4h | 1h | 15m |
| Max holding bars | 30 | 12 | 5 |
| Stop multiplier | 2.0-2.5 | 1.5-2.0 | 1.0-1.5 |
| Target multiplier | 2.0-3.0 | 1.5-2.0 | 1.0-1.5 |
| Min action edge | 0.35R | 0.15R | 0.08R |

### Adapters
1. **TrainingAdapter** — side-effect-free, deterministic, for AlphaForge label generation
2. **EvaluationAdapter** — side-effect-free, for walk-forward validation
3. **ReplayDriver** — historical replay, no live exchange
4. **PaperDriver** — paper forward simulation, no order submission
5. **Monte Carlo** — N=100 perturbed paths, diagnostic only

### Key Constraint
**Simulation does NOT generate signals.** It evaluates signals that come from elsewhere (analyzer, AlphaForge, or manual input).

---

## 2. Runtime — What It Does

### Core Function
Operational Python backend that:
1. Fetches market data from Binance
2. Runs the analyzer to generate BUY/SELL/NEUTRAL signals
3. Executes paper trades or live orders
4. Manages portfolio state in PostgreSQL
5. Provides API for the React interface

### Analyzer Pipeline (12 stages)
1. Circuit-breaker pre-check
2. Regime detection (MOMENTUM/SQUEEZE/DEAD/etc.)
3. Trend detection (EMA-based)
4. Structure evaluation (support/resistance/retest)
5. Entry confirmation (breakout/retest/micro-momentum)
6. Probability model (factor edge + distribution edge + vol edge + microstructure)
7. Stop model (structure-based vs ATR floor)
8. Timing model (session-conditioned, stale-exit)
9. Execution-quality penalties (EMA extension, VWAP stretch, etc.)
10. Learning adjustments (calibration, entry penalty, component penalty)
11. Final gating (confidence, RR, expected value)
12. Return BUY/SELL/NEUTRAL

### Paper Trading System
`PaperExecutionService` provides:
- Full order lifecycle (open/close/cancel)
- Position sizing based on confidence
- Paper balance management (deposit/reset/reconcile)
- Stop/TP/Time-stop monitoring
- Stale exit logic (EARLY_STALE_EXIT)
- Failure classification
- Attribution service
- Portfolio snapshots with equity curve

### Database Schema (PostgreSQL)
- `v4_candles` — market data
- `v4_scan_runs` — scan orchestration
- `v4_signals` — generated signals with audit_json
- `v4_orders` — paper/live orders with execution accounting
- `v4_fills` — fill records
- `v4_positions` — position tracking
- `v4_portfolio_snapshots` — equity snapshots
- `v4_paper_accounts` — paper balance
- `v4_trade_failures` — failure classification
- `v4_circuit_breaker` — safety gate state

### Learning Layer
- Confidence calibration (per-bucket multipliers)
- Entry timing penalties
- Adaptive stop-loss widening
- Component penalties (per-indicator)
- Hard rejection rules
- Regime stability damping

### API Surface (30+ endpoints)
- `/api/v3/health`, `/api/v3/dashboard`
- `/api/v3/market/overview`, `/api/v3/analyze`
- `/api/v3/scans` (trigger + control)
- `/api/v3/orders`, `/api/v3/portfolio`
- `/api/v3/failures`, `/api/v3/learning`
- `/api/v3/paper/balance`, `/api/v3/paper/deposit`

---

## 3. Integration Between Them

### How They Connect
```
Runtime Analyzer → Signal → SimulationInput → SimulationEngine → SimulationOutput
                                                          ↓
                                              Runtime reads outcome
                                              → PaperExecution / Live Execution
```

### The Missing Link (Current State)
1. **Analyzer generates signals** using its own factor engine (regime, trend, structure, oscillators)
2. **Simulation evaluates those signals** off-line (batch mode via TrainingAdapter)
3. **AlphaForge consumes SimulationOutput** for label generation
4. **Runtime's PaperExecutionService** executes based on analyzer signals (NOT simulation outcomes)

### Critical Gap
**The runtime's analyzer does NOT call the simulation engine during live signal generation.** The analyzer's 12-stage pipeline produces BUY/SELL/NEUTRAL with its own internal probability/confidence model. The simulation engine is used separately for:
- Training label generation (AlphaForge)
- Backtesting validation
- Paper trade replay (historical)

This means:
- The analyzer's cost estimation is independent of simulation's cost model
- The analyzer's stop/target logic is independent of simulation's exit logic
- Paper trades use the analyzer's proposed SL/TP, not simulation-optimized levels

---

## 4. What AlphaForge Should Use

### For Factor Evaluation (Current)
AlphaForge's `factor_sprint.py` uses its own simplified evaluation:
- Cross-sectional Rank-IC
- Top-bottom spread
- Turnover

This is **correct for signal quality measurement** but misses:
- Realistic cost model (simulation has it)
- Stop/target optimization (simulation has it)
- Path quality metrics (simulation has MFE/MAE)
- No-trade quality classification (simulation has it)

### For Regime-Event Matrix (Next Step)
The regime-event matrix should be tested through the **simulation engine**, not just IC analysis:
1. Factor triggers → entry/stop/target proposal → SimulationInput
2. SimulationEngine evaluates → SimulationOutput with R-multiple
3. Aggregate per-regime: avg_R, win_rate, profit_factor

### Recommended Path
```
Factor Sprints (IC/IC_IR) → Regime-Event Matrix → Simulation Validation → Paper Trading
       ↓                         ↓                       ↓                     ↓
  Signal quality          Setup quality           R-multiple truth      Live validation
```

We're at step 2. Step 3 (simulation validation) is the critical missing piece before paper trading.
