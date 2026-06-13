# Runtime AI Summary — Machine-Readable Authority Reference

## META

This document is a lossless dense synthesis of every markdown file in `/runtime/docs/`. It is designed for LLM code agents and AI-assisted engineering workflows. It is **NOT** for human reading. The entire runtime doc set has been compressed into this single reference preserving all rules, invariants, ownership boundaries, pipeline stages, schema tables, API routes, and diagnostics.

**Reading order for an AI:** Read this entire file first. Then consult specific authority docs for implementation details. This file is authoritative only where it directly quotes or faithfully restates authority docs; in case of conflict, the original doc wins.

**File count synthesized:** 13 markdown files
**Source tree:** /home/erfolg/src/v7-engine/runtime/docs/

### Cross-Domain Authority Notice

This document is the **runtime-local** authority summary for the operational Python backend, scan loop, analyzer, learning layer, API surface, and PostgreSQL schema.

- The root cross-domain contract authority lives in **`contracts/`** at the repo root.
- The root cross-domain governance lives in **`docs/architecture/governance.md`**.
- For V7-local pipeline semantics (simulation truth, runtime integration, contracts): see **`v7/docs/ai_summary.md`**.
- For simulation truth layer: see **`simulation/docs/ai_summary.md`**.
- For the repo-wide entry point: see **`ai_summary.md`** at the repo root.
- For the React operator interface: see **`interface/docs/ai_summary.md`** (workspace structure, page ownership, component architecture).

The V4 runtime has been promoted into the V7 authority tree. Cross-doc links within this tree still reference the legacy V4 layout (e.g. `/Users/hootie/src/trading-bot/v4/...`); those are legacy anchors awaiting path normalization.

---

## R.1 Runtime Architecture (runtime/docs/architecture.md)

### Core Decision
V7 keeps the existing React interface and runs a Python-first backend and engine runtime. Operational rule: one backend authority, one runtime authority, one persistence boundary. V3 Rust is retained only as an optional, narrow, replaceable reference; it is not the main runtime path.

### Primary Goals
- Operable locally without multi-process ambiguity
- Preserve the interface investment
- Persist operational state reliably in PostgreSQL
- Keep artifacts/archives in MongoDB
- Make startup, recovery, and debugging predictable

### Component Map
```
React Interface → HTTP → Python API Layer
  → Query + Admin Endpoints
  → Repository / ORM Boundary
  → Python Runtime Coordinator
    → Scan / Signal Engine
    → Execution / Risk
    → Market Ingestion
    → Calibration / Analytics Jobs
  → PostgreSQL (operational data)
  → MongoDB (archives and artifacts)
Exchange REST/Websocket → Market Ingestion
Rust v3 Reference → optional narrow reuse only → Scan, Market, Cal
```

### Ownership

| Layer | Owns |
|---|---|
| **Python** | API routes consumed by interface, runtime settings, scan orchestration, order execution orchestration, portfolio state, storage import/export/archive/restore, startup and diagnostics |
| **PostgreSQL** | Runtime settings, scan runs, signals, orders, fills, positions, portfolio snapshots, simulation metadata, operator-visible operational state |
| **MongoDB** | Archived operational snapshots, signal artifacts, simulation artifacts, drift/calibration event history, verbose retained logs/traces |
| **React interface** | Operator workflows, state visualization, storage control center, scan/trade/portfolio/market/admin screens |
| **Rust v3** | Only if justified and optional: isolated analytics kernels, isolated simulation kernels, isolated market-data helpers |

### Runtime Model
- **Dev mode:** Python API starts + Python runtime/background worker starts
- **Production:** Can split workers but persistence boundary remains one
- Rust v3 is optional reference only; no component may become the only way to run the system

---

## R.2 Runtime Flow (runtime/docs/runtime.md, runtime/docs/scanning.md)

### Market Data Runtime (`runtime/market_data.py`)
- Fetch candles from Binance through the existing Python client path
- Persist candles to PostgreSQL
- Fall back to cached PostgreSQL candles when exchange fetch fails
- Mark stale market data explicitly

### Scan Runtime (`runtime/scan_runtime.py`)
- Expand one scan request across symbols, intervals, and modes
- Fetch market data snapshots
- Derive higher-timeframe bias when possible
- Call the analyzer wrapper
- Persist scan runs
- Persist signal rows

### Autonomous Loop (`runtime/autonomous_loop.py`)
- Load runtime settings
- Pause or resume scanning
- Call the scan runtime periodically
- Call the paper-trade monitor periodically
- Isolate scan exceptions so one bad cycle does not kill the loop

### Scan Routes (`api/routes/scans.py`)
- List persisted scan runs
- Trigger manual scans
- Inspect one persisted scan run and its signals

### One Scan Cycle (active V4→V7 flow)

1. **Request arrives** at `POST /api/v3/scans` or `AutonomousLoop.run_once()` carrying `symbols`, `intervals`, `modes`, `requested_by`
2. **Scan run row created** in `scan_runtime.py` with `run_id = scan-<uuid>`, `status = RUNNING`, initial progress payload
3. **Scope expansion & pruning:**
   - Stage 1: mode-interval filtering — `_normalize_mode_intervals(...)` produces allowed `[(interval, mode), ...]` pairs; mode-ineligible interval pairs removed
   - Stage 2: symbol throttling — `UniverseFilterService.evaluate(symbols)` may remove symbols via seeded guardrails, stop-hit clusters, rolling stop-rate thresholds, cooldown windows
   - Result: `requested_symbols`, `active_symbols`, `throttled_symbols`; tasks for throttled symbols counted at `skip_stages.UNIVERSE_FILTER`
4. **Build fetch tasks:** `interval_tasks = [(symbol, interval) for symbol in active_symbols for interval in effective_intervals]`
5. **Fetch market snapshots** via `ThreadPoolExecutor` with `max_fetch_workers = min(resolved_workers, len(interval_tasks))`
   - Each fetch calls `_fetch_interval_bundle(symbol, interval)` → `_get_market_snapshot_cached(...)` + `_resolve_htf_trend(...)`
   - Market snapshots memoized; HTF trends memoized
   - Analysis runs in-process after each fetch future returns
6. **Analyze per mode:** for each `(symbol, interval, mode)` task, call analyzer wrapper
7. **Emit signals:** non-neutral eligible signals can create orders through paper execution
8. **Write progress snapshots, debug state, persisted result**
9. **Control-state deactivation** via `scan_control.deactivate_run(...)`

### Scan Control (`runtime/scan_control.py`)
- `activate_run(run_id, ...)`
- `deactivate_run()`
- Control state checked between symbol/interval/mode tasks for cooperative pause/stop
- `POST /api/v3/scans/control/pause`, `/resume`, `/stop`

### Autonomous Scan Constraints
- Blocked if circuit breaker status is `OPEN`
- Not blocked if circuit breaker status is `DEGRADED`
- Serialized by the loop — no concurrent overlapping runs
- Checks `AUTONOMOUS_ENABLED` setting, circuit breaker state, resolves per-mode interval policy before calling `ScanRuntime.run_scan()`

### Key Runtime Settings
- `PAPER_DEFAULT_BALANCE`
- `AUTONOMOUS_ENABLED`
- `LEARNING_CALIBRATION_ENABLED`
- `LEARNING_ADAPTIVE_STOP_ENABLED`
- `SESSION_NEW_YORK_ENABLED`

---

## R.3 Analyzer (runtime/docs/analyzer.md)

### Role
Layered, interpretable decision engine. The analyzer is called from scan runtime, not from the scheduler directly.

### Live Decision Order

1. **Circuit-breaker pre-check** — if `OPEN` → `NEUTRAL` at `CIRCUIT_BREAKER` stage; if `DEGRADED` → analysis continues with degraded multiplier later
2. **Regime detection** — from volatility and trend context; `MOMENTUM` hard-blocked; `SQUEEZE` may be blocked; `DEAD` may be blocked
3. **Trend detection** — from EMA state and momentum context; if direction cannot be established → `NEUTRAL` at `TREND`
4. **Structure evaluation** — support/resistance proximity, retest state, sweep state, recent high/low anchors; if unacceptable → `NEUTRAL` at `STRUCTURE`
5. **Entry confirmation** — explicit model with signals: breakout flag, breakout hold, retest hold, micro momentum, micro flow; exposed at `advanced_analysis.confirmation`
6. **Probability model** — derived from factor edge, distribution edge, volatility edge, microstructure edge; outputs `probability_raw`, `probability`, `probability_up`, `probability_down`, `component_scores`; exposed at `advanced_analysis.probability_model`
7. **Stop model** — structure-based stop (support/resistance/retest/sweep anchor) vs ATR floor stop (wider safer stop chosen); cap absurd width when required; re-check RR after stop widening; exposed at `advanced_analysis.stop_model`
8. **Timing model** — conditioned by regime, session, mode; produces `candles_target`, `candles_min`, `candles_max`, `time_stop_candles`, `stale_exit_candles`, `stale_exit_min_progress_pct`, `stale_exit_max_abs_r`, timing multipliers; trades can close via `EARLY_STALE_EXIT` before full time stop if elapsed candles exceed stale-exit threshold AND directional progress too weak AND open R near flat
9. **Execution-quality penalties** — multiplicative, interpretable: EMA extension, VWAP stretch, recent impulse extension, impulse decay (MACD, RSI), regime mean-reversion penalty, session penalty, worst setup bucket guardrail; breakdown at `decision_path.entry_quality_breakdown`
10. **Learning adjustments** — calibration multiplier, entry penalty, component penalty, execution penalty, stop multiplier; calibration defaults to bypass; adaptive stop defaults to bypass; calibration monotonicity must validate
11. **Final gating** — check confidence, RR, expected value; if any fail → `NEUTRAL` with stage in `decision_path.neutral_stage` (common: REGIME, TREND, STRUCTURE, OSCILLATOR, VOLUME, CONFIDENCE, RR, EV, CIRCUIT_BREAKER, INTERVAL_POLICY)
12. **Return `BUY`, `SELL`, or `NEUTRAL`**

### Key Inputs
- `symbol`, `interval`, `snap` (enriched market context), `ticker`, `mode`, optional `htf_trend`
- Snapshot fields: price, ATR, ATR_5bar_avg, ATR_expanding, BB_width, EMAs (9/21/50/200), recent_high/low, near_resistance/support, retest_support/resist, bullish/bearish_sweep, RSI/RSI_slope, MACD/MACD_signal/MACD_hist/MACD_hist_delta, stoch_K/D, stochRSI_K/D, ADX, vol_ratio, vol_slope, OBV_slope, session_liquidity_score, trade_intensity, orderbook_spread_bps, orderbook_microprice_deviation_bps, microstructure_source, session_label, htf_trend

### Per-Mode Config Surface (`analyzer_config.py`)
- `min_confidence`, `min_rr`, `min_expected_value_r`
- Regime behavior, confirmation policy, structure requirements
- Higher-timeframe opposition handling
- Current modes: `SWING`, `SCALP`, `AGGRESSIVE_SCALP`
- `AGGRESSIVE_SCALP` restricted to intervals up to `4h`

### Session Policy
- `SESSION_NEW_YORK_ENABLED=false` by default
- Session alias normalization: `OVERLAP`/`LONDON_OVERLAP`/`NY_OVERLAP` → `LONDON_NEW_YORK_OVERLAP`
- Session pressure feeds execution quality and diagnostics

### Circuit Breaker States
| State | Behavior |
|---|---|
| `CLOSED` | Analyzer proceeds normally |
| `DEGRADED` | Analyzer proceeds, confidence multiplied down |
| `OPEN` | Autonomous scan flow blocked; analyzer returns `NEUTRAL` with `CIRCUIT_BREAKER` stage |

### `decision_path` Contract
Keys on every final signal or neutral return:
- `neutral_stage`, `reason`, `mode`, `interval`, `session_label`, `circuit_status`
- `quality_multiplier`, `confidence_quality_multiplier`, `entry_quality_breakdown`
- `probability_raw`, `probability_final`, `confidence_raw`, `confidence_final`
- `risk_reward`, `expected_value`
- Neutral results preserve computed diagnostics (not zeroed)

### `audit_json` Contract
Frozen at signal time. Key fields:
- `threshold_checks`, `factor_scores`, `probability_components`
- `learning_adjustments_applied`
- `confidence_before_learning`, `confidence_after_learning`, `confidence_model_raw`, `confidence_post_learning`, `confidence_post_execution`
- `probability_before_learning`, `probability_after_learning`, `probability_model_raw`, `probability_post_learning`, `probability_post_execution`
- `execution_quality_multiplier`, `stop_model`, `confirmation`, `regime_policy`, `circuit_breaker_state`

### Position Sizing (Paper Execution)
- Allocation confidence capped at `80` (raw confidence can be higher for diagnostics)
- Wide-stop normalization: sizing does not reduce for stop widths ≤1.5 ATR; above 1.5 ATR, notional size scales down proportionally
- Sizing metadata: `risk_adjustment_factor`, `stop_distance_atr`, `stop_width_normalized`

### Universe Throttling
- Scan-runtime tactical containment layer; suppresses symbols before analysis
- Triggers: seeded guardrail list, consecutive stop-hit cluster, rolling stop-hit rate threshold
- Records: `skipped.symbol_throttled`, `skip_stages.UNIVERSE_FILTER`, `result.universe_filter`
- Cooldown-based, not permanent

### Primary Source Files
- `services/analyzer_core.py` — pipeline ordering, hard blockers, trend-to-direction, execution-quality aggregation, learning integration, circuit-breaker integration, gating, TradeSignal assembly
- `services/analyzer_config.py` — per-mode policy surface
- `services/analyzer_factors.py` — deterministic factor engine (regime, trend, structure, oscillators, momentum, volume, entry zone, stop-loss model, take-profit model, risk/reward)
- `services/analyzer_probability.py` — directional probability overlay
- `services/analyzer_reporting.py` — timing-conditioned analytics
- `services/analyzer_helpers.py` — helper utilities
- `services/learning_service.py` — adaptive correction layer
- `services/circuit_breaker_service.py` — circuit breaker state
- `services/audit_service.py` — freezes signal-time decision state into `audit_json`
- `services/universe_filter_service.py` — symbol throttling
- `services/decision_attribution_service.py` — component attribution
- `runtime/scan_runtime.py` — scan orchestration
- `runtime/paper_execution.py` — paper order execution

---

## R.4 Learning Layer (runtime/docs/learning.md)

### Purpose
Adaptive learning and self-correction layer on top of the analyzer. Converts persisted trade outcomes and classified failures into bounded execution adjustments. Does NOT replace the base analyzer; modifies the last mile of trade decision quality.

### Targets
- Reduce overconfidence
- Penalize repeated bad entry timing
- Penalize repeatedly failing components
- Widen stops when repeated stop-loss failures dominate
- Reject statistically bad execution patterns outright

### Activation Rules
Gated intentionally. Stays inactive until both: enough closed trades exist AND enough analyzed losses exist (anti-overfitting guard).

### Learning Profile Shape
- `generated_at`, `lookback_days`, `min_confidence`, `samples`
- `confidence_calibration` — closed trades grouped into confidence buckets; each bucket has avg predicted confidence, realized win rate, bounded calibration multiplier
- `entry_penalties` — tracks repeated `TIMING`/`Entry Logic` failures; live trade scored for early-entry risk (extension from EMA21/VWAP, breakout without retest, impulse extension, RSI stretch, microstructure leaning against trade); produces `entry_timing_risk` score → bounded `entry_penalty` with activation floor
- `stop_loss_adjustments` — adaptive stop-loss multiplier when failures concentrated in `RISK_MODEL`/`Stop Loss`/`STOP_LOSS_HIT`; widens stop buffer, stays bounded, strengthened when volatility expanding, weakened by regime-stability damping
- `component_penalties` — per-component penalties for `Stop Loss`, `Entry Logic`, `Trend Filter`, `RSI`, `MACD`, `Volume`; driven by failure frequency × avg severity × avg confidence; only applied to setups with matching factors
- `hard_rejection_rules` — statistically dominant failure cluster → analyzer returns `NEUTRAL` (intended for repeated bad execution patterns, not cosmetic nudges)
- `regime_stability` — evaluates whether recent sample is stable across regimes: `STABLE`/`MIXED`/`UNSTABLE`/`INSUFFICIENT_DATA`; unstable regimes reduce layer influence (on confidence, entry penalties, component penalties, adaptive stop widening, hard rejection sensitivity)
- `active_adjustments`, `top_penalties`, `status`

### Confidence Calibration
Two-layer model:
1. Global multiplier across the full recent sample
2. Per-bucket multiplier blended with global value when bucket has enough rows

Multiplier applied before final confidence gating. Overconfident buckets scaled down; reasonably calibrated buckets stay ~1.0; sparse buckets no longer silently default to 1.0 if wider sample is overconfident.

### Direct Execution Penalty
Applied immediately when setup is stretched in ways historically leading to bad path risk: stretched from VWAP, breakout without retest, adverse microstructure flow, extension from EMA21, impulse extension, RSI stretch. Multiplied directly into final confidence alongside learned entry and component penalties.

### Adaptive Stop Loss
When failures concentrated in RISK_MODEL / Stop Loss / STOP_LOSS_HIT:
- Widens stop buffer (bounded)
- Strengthened when volatility expanding
- Weakened by regime-stability damping

### Hard Rejection
Statistically dominant failure cluster → no order emitted, analyzer returns `NEUTRAL`.

### Runtime Refresh
Learning profile refreshed by background loop (`runtime/learning_loop.py`). Periodic recalculation from persisted data; does not block scan/trade execution.

### Per-Trade Audit Trail
Execution runtime persists frozen learning audit on order payload: `confidence_before`, `confidence_after`, `probability_before`, `probability_after`, `adjustments`, `applied_at_utc`.

### Effectiveness Reporting
Classifications: `IMPROVING`/`NEUTRAL`/`DEGRADING`/`INSUFFICIENT_DATA`. Compares adjusted trades vs baseline trades using average realized R, win rate, sample counts.

### API Routes
- `GET /api/v3/learning/profile` — active status, sample size, top penalties, calibration data, full profile, effectiveness summary
- `GET /api/admin/learning/profile`
- `GET /api/v3/learning/effectiveness` — per-adjustment status, adjusted vs baseline counts, average R deltas, win-rate deltas, overall health score
- `GET /api/admin/learning/effectiveness`

### Current Limits
- Repeated failure patterns decreasing over time: awaiting live observation
- Stop-loss hit rate decreasing measurably: awaiting live observation

---

## R.5 Self-Learning Layer (runtime/docs/self_learning.md)

### Role Boundary
V4 remains the signal engine (regime interpretation, signal generation, factor scoring, base probability/confidence, entry/stop/target proposals). Self-learning is an additive decision-correction layer:
- Correcting probability from historical truth
- Recommending safe action adjustments from learned context
- Retrieving similar historical memory from external storage
- Learning which contexts produce wins vs false positives

Does NOT replace direction logic. Early versions explicitly read-only with respect to trade direction. V4 signal remains the source signal for any self-learning correction.

### Production Scope (Narrow)
- `SWING` only first
- Binary outcome prediction first, action adjustment second
- If self-learning unavailable, V4 continues unchanged

### Decision Order
1. Base analyzer output from V4
2. Existing adjustment layers from earlier phases
3. Self-learning correction layer
4. Final acceptance or rejection

Every result attributable to original V4 signal through embedded comparison and attribution payload.

### Storage Roles
| Store | Role |
|---|---|
| **PostgreSQL** | Transactional truth for signals, orders, failures, audit trails, structured trade memories |
| **LanceDB** | Preferred external nearest-neighbor memory store |
| **Parquet** | Preferred offline dataset and evaluation slice format |
| **MLflow** | Preferred model lifecycle and promotion history store |

Local fallbacks: JSONL/CSV/JSON. All artifacts local-only and reproducible.

### Backup & Retention
- Back up: `data/memory/lancedb/`, `data/datasets/self_learning/`, `data/mlruns/`, `data/models/self_learning/`
- Restore order: PostgreSQL → model registry → datasets → external memory
- Retention: raw training sets latest 20/180 days, model checkpoints latest 10/365 days, memory embeddings compact after 90 days, evaluation snapshots latest 30/365 days

---

## R.6 Operational Schema (runtime/docs/schema.md)

### Rule
PostgreSQL is the operational system of record. Each table has one clear ownership purpose. Repositories expose small obvious CRUD functions around these tables.

### Key Tables

| Table | Written By | Read By | Key Columns |
|---|---|---|---|
| `v4_runtime_settings` | Settings API, operator updates | Health/settings routes, runtime boot, autonomous loop | `key`, `value`, `updated_at` |
| `v4_candles` | Market-data runtime, exchange bootstrap/refresh | Scan runtime, market routes, analyzer input builders | `symbol`, `interval`, `open_time_utc`, `close_time_utc`, `open`, `high`, `low`, `close`, `volume`, `source`, `stale` |
| `v4_scan_runs` | Manual scan runtime, autonomous loop | Scans routes, dashboard queries, admin summaries | `run_id`, `requested_by`, `status`, `symbols_csv`, `intervals_csv`, `modes_csv`, `signal_count`, `summary`, `error_text`, `created_at_utc`, `started_at_utc`, `finished_at_utc`, `payload_json`, `result_json` |
| `v4_signals` | Scan runtime, analyzer service integration | Markets routes, scan detail views, dashboard query | `signal_id`, `run_id`, `symbol`, `interval`, `mode`, `direction`, `confidence`, `regime`, `trend`, `trend_strength`, `summary`, `no_trade_reason`, `strategy_version`, `snapshot_json`, `features_json`, `factors_json`, `created_at_utc` |
| `v4_orders` | Paper execution runtime, manual order actions | Trades page, portfolio service, admin summaries | `order_id`, `signal_id`, `source`, `symbol`, `interval`, `mode`, `direction`, `status`, `entry`, `stop_loss`, `take_profit`, `close_price`, `risk_reward`, `confidence`, `opened_at_utc`, `closed_at_utc`, `payload_json` (carries execution accounting: `reserved_cost`, `entry_notional`, `fees`, `gross_proceeds`, `net_proceeds`, `budget_reconciled_at_utc`) |
| `v4_fills` | Paper execution runtime | Order inspection, position calculations, portfolio summaries | `fill_id`, `order_id`, `symbol`, `direction`, `quantity`, `price`, `fee`, `filled_at_utc` |
| `v4_positions` | Paper execution runtime, order close/update | Portfolio routes, trades page, dashboard summaries | `position_id`, `symbol`, `interval`, `mode`, `direction`, `quantity`, `average_entry`, `mark_price`, `unrealized_pnl`, `status`, `opened_at_utc`, `closed_at_utc`, `payload_json` |
| `v4_portfolio_snapshots` | Portfolio service, autonomous loop checkpoints | Portfolio routes, dashboard query | `snapshot_id`, `total_equity`, `cash_balance`, `unrealized_pnl`, `realized_pnl`, `open_positions`, `closed_trades` (payload: `paper_balance`, `invested_capital`, `net_r`) |
| `v4_paper_accounts` | Paper execution runtime, paper budget routes | Portfolio routes, admin paper budget panel, order open validation | `account_key`, `balance`, `created_at`, `updated_at`, `snapshot_json`, `created_at_utc` |
| `v4_alerts` | Alert service, health/runtime degradation detectors | Alerts routes, admin route, dashboard health summaries | `alert_id`, `severity`, `kind`, `scope`, `message`, `active`, `payload_json`, `detected_at_utc` |

### Additional Migration Tables (from `runtime/migrations/versions/`)
- `v4_signal_features`, `v4_trade_failures`, `v4_paper_budget`, `v4_circuit_breaker`, `v4_signal_audit`, `v4_self_learning_foundation`, `v4_improvements_registry`, `v4_analyzer_engine_contract`
- `v6_decision_events`, `runtime_state`, `runtime_state_profile_pk`, `model_registry`
- `simulation_decision_traces`, `simulation_presets`
- Profile-owned: `runtime_profile_identity_foundation`, `profile_account_and_config_foundation`, `profile_owned_storage`, `binance_usdm_profile_foundation`

### Repository Ownership
- `db/repos/settings_repo.py`, `candle_repo.py`, `scan_repo.py`, `signal_repo.py`, `order_repo.py`, `portfolio_repo.py`, `alert_repo.py`
- Each repository exposes only: `get_*`, `list_*`, `save_*`, `delete_*` where necessary

---

## R.7 API Surface (runtime/docs/api.md, runtime/docs/api_architecture_rule.md)

### Stack
FastAPI + Pydantic request/response models + built-in OpenAPI. Standardization layer: one typed backend contract, automatic validation, OpenAPI at runtime without a separate contract system.

### Versioning Rule
Keep interface route namespace under `/api/v3/*` for compatibility (avoids large frontend rename during backend rewrite). Internally, this is the V7 backend.

### API Shape Rule
Page-oriented, not storage-oriented — endpoints organized around operator screens and engine workflows, not raw tables.

### API Architecture Rules

**Rule 1: Public API paths are capability-based, not engine-version-based.**
Allowed: `/api/v3/health`, `/api/v3/analyze`, `/api/v3/scans`, `/api/v3/orders`, `/api/v3/portfolio`, future capability families like `/api/v3/review/*`, `/api/v3/operate/*`, `/api/v3/system/*`.
Disallowed: `/v6/analyze`, `/v6/decision-events`, `/v6/engine-behavior`, any public route forcing the client to know which internal engine generation is active.

**Rule 2: Engine generation belongs in metadata, not in route namespaces.**
Surfaced through payload fields: `engine_name`, `engine_version`, `model_artifact_version`, `fallback_used`, `fallback_reason`, `comparison_group_id`.

**Rule 3: `/api/v3/*` remains the compatibility contract.**
Existing interface and tests already depend on it. If versionless aliases added later, they must map to same handlers, preserve response contracts, not replace `/api/v3/*` abruptly.

**Rule 4: Engine switching is internal.**
Active engine selected through `AnalyzerEngineAdapter`, `AnalyzerEngineRegistryService`, engine manager/registry/config. Frontend must not switch base paths by engine generation.

**Rule 5: The adapter is the normalization boundary.**
`runtime/services/analyzer_engine_adapter.py` is the compatibility boundary. Public routes depend on normalized outputs.

**Rule 6: Future Phase 7 routes must be capability-centered.**
Introduce under `/api/v3/review/*`, `/api/v3/operate/*`, `/api/v3/system/*`. Any document proposing public `/v6/*` endpoints must be treated as outdated.

### Route Groups

#### Health And Runtime
- `GET /api/v3/health`, `GET /api/v3/engine/health`, `GET /api/v3/calibration/status`
- `GET /api/v3/learning/profile`, `GET /api/v3/learning/effectiveness`
- `GET /api/v3/settings`, `POST /api/v3/settings`
- Purpose: process health, DB health, exchange health, runtime settings, calibration readiness, adaptive learning profile/effectiveness

#### Dashboard
- `GET /api/v3/dashboard`
- Single response: top-level KPIs, recent scans, market movers, alerts summary, runtime summary

#### Markets
- `GET /api/v3/market/overview`, `GET /api/v3/market/signals`, `GET /api/v3/klines`, `GET /api/v3/analyze`
- Purpose: market list, ranked signals, chart candles, one-shot analyzer output
- Analyzer response highlights: `direction`, `confidence`, `probability`, `probability_up/down`, `expected_value`, `regime`, `trend`, `risk_reward`, `summary`, `snapshot`, `advanced_analysis`

#### Scans
- `GET /api/v3/scans`, `POST /api/v3/scans`
- `GET /api/v3/scans/control`, `POST /api/v3/scans/control/pause|resume|stop`
- `GET /api/v3/jobs`
- Responses include top-level `control` block with active run id, active status, desired state, current task

#### Orders And Portfolio
- `GET /api/v3/orders`, `GET /api/v3/portfolio`, `GET /api/v3/paper/balance`
- Action routes: `POST /api/v3/orders`, `PATCH /api/v3/orders/{order_id}`, `POST /api/v3/orders/{order_id}/close`
- `POST /api/v3/paper/deposit|reset|reconcile`
- Portfolio response: `summary.today_pnl`, `today_pnl_pct`, `three_day_pnl`, `three_day_pnl_pct`, `performance_windows.today`, `performance_windows.three_day`

#### Failure Analysis
- `GET /api/v3/failures`, `GET /api/v3/failures/{order_id}`
- `GET /api/v3/failures/summary`, `GET /api/v3/failures/weakness-profile`
- Admin aliases: `/api/admin/failures/*`
- Query params: `limit`, `offset`, `failure_source`, `blamed_component`, `severity_score`, `date_from`, `date_to`
- Summary: counts per `failure_source`/`blamed_component`, avg `severity_score`, avg `confidence`, `top_weakness`
- Weakness profile: `generated_at`, `lookback_days`, `total_losses_analyzed`, `top_failure_source`, `top_blamed_component`, `ranked_sources`, `ranked_components`

#### Learning
- `GET /api/v3/learning/profile`, `GET /api/v3/learning/effectiveness`
- Admin aliases: `/api/admin/learning/*`
- Profile: `active`, `sample_size`, `top_penalties`, `calibration_data`, `effectiveness_summary`, full `profile`
- Effectiveness: per-adjustment status, adjusted vs baseline counts, avg R delta, win-rate delta, overall health score

#### Storage & Admin
- `GET /api/v3/storage/status`, `POST /api/v3/storage/export|import|seed`
- `GET /api/v3/alerts`, `GET /api/v3/operator/alerts`, `GET /api/v3/logs`

#### Simulations
- No active simulation routes bound in the current interface (explicitly disabled until simulation backend reimplemented)

### Page Binding Map
| Page | Primary Routes |
|---|---|
| Dashboard | `GET /api/v3/dashboard` |
| Markets | `GET /api/v3/market/overview`, `/market/signals`, `/klines`, `/analyze` |
| Scans | `GET /api/v3/scans`, `POST /api/v3/scans`, `/scans/control` + pause/resume/stop |
| Trades | `GET /api/v3/orders` |
| Portfolio | `GET /api/v3/portfolio`, `/paper/balance` |
| Admin | `GET /api/v3/engine/health`, `/scans`, `/alerts`, `/logs`, `/settings` (GET+POST), `/paper/balance`, `/paper/deposit|reset` |
| Alerts | `GET /api/v3/alerts` |
| Storage | `GET /api/v3/storage/status`, `POST /api/v3/storage/export|import|seed` |
| Logs | `GET /api/v3/logs`, `/scans`, `/dashboard` |
| Simulations | disabled |

### Response Modeling Rules
- Each route has an explicit Pydantic response model (e.g. `DashboardResponse`, `MarketOverviewResponse`)
- Response models match what the page needs to render
- Explicit empty arrays instead of omitted fields
- Explicit degraded-state fields instead of silent partial failure
- Use `200` with explicit degraded fields when partial data is still useful
- `4xx` for bad client input, `5xx` for real backend failures
- Interface must never guess whether zeros mean empty state, degraded state, or failure

### What Not To Build
GraphQL, second gateway layer, separate contract service, custom code generation pipeline before backend is working, microservice split for routine page data.

---

## R.8 Runbook (runtime/docs/runbook.md)

**Scope:** Startup, DB, exchange, and stuck-scan recovery notes. Operational handbook for the merged V7 runtime.

Adjacent operational documents:
- `runtime/docs/engine_change_analysis_2026-04-02.md` — Change analysis with validation evidence and unresolved items
- `runtime/docs/engine_diagnostic_fix_plan.md` — Core findings from the diagnostic: two primary loss engines (stop-loss model failures at -74R, and time-stop occupation at -11R), config-only guardrails vs code changes, dependency order, rule to always separate autonomous from manual/interface trades

---

## R.9 Change Analysis Snapshot (runtime/docs/engine_change_analysis_2026-04-02.md)

### Scope
P0 attribution and calibration safety fixes, P1 stop-loss/timing/regime/session/time-stop work, P2 universe throttling, observability and rollout-validation additions.

### What Improved
- Stop-hit rate materially below original diagnostic's stop-loss-dominated failure picture
- Confidence ordering before learning remains monotonic on current sample
- Component attribution outcome propagation no longer zeroed
- Scan runtime can suppress repeat-offender symbols explicitly
- Rollout and analytics surfaces have enough observability to measure changes
- Timing estimates no longer purely distance-and-ATR based; session/regime conditioning explicit
- Stale positions have dedicated exit path (`EARLY_STALE_EXIT`)

### What Is Still Not Good
- Time-stop rate still too high at `54.65%`
- Expected-duration quality still poor: only `3.55%` within 25% band
- Post-learning confidence monotonicity only `MIXED`
- No manual closed-trade comparison set in 30-day sample
- `EARLY_STALE_EXIT` lacks new live data to measure impact

### Validation Evidence (2026-04-02)
- Focused regression suites: 34 tests passed
- Related runtime/analytics suite: 22 tests passed
- Broader engine suite: 70 tests passed
- Frontend build: passed
- Live 30-day trade sample: 258 closed trades, 47.29% win rate, +0.1359R avg realized R, 29.84% stop-hit rate, 54.65% time-stop rate, pre-learning monotonicity PASS, post-learning MIXED

---

## R.10 Engine Diagnostic Fix Plan (runtime/docs/engine_diagnostic_fix_plan.md)

### Core Findings
1. **Stop-loss model failures:** 74 losing trades, -74R
2. **Time-stop occupation:** secondary loss engine

### Rules
- Always separate `autonomous` trades from `manual/interface` trades in diagnostics
- Freeze engine settings and manifest state for every comparison window
- Treat very high time-stop rate as its own investigation track
- Do not trust learning calibration/effectiveness conclusions until attribution is fixed
- Do not make permanent session or symbol policy from tiny samples without OOS confirmation

---

## END OF RUNTIME AI SUMMARY

This document contains the complete lossless synthesis of every markdown file in `/runtime/docs/`. Every rule, invariant, ownership boundary, pipeline stage, schema table, API route, and diagnostic snapshot has been preserved.

**When to use this file:**
- Initial AI context loading for any runtime work
- Quick reference for API routes, schema tables, analyzer pipeline order
- Cross-checking runtime behavior against operational boundaries

**When to consult original docs:**
- When implementing specific analyzer pipeline changes
- When the summary's condensed form loses nuance
- For exact migration SQL or API response model schemas

**Canonical file paths for original runtime docs:**
- runtime/docs/README.md
- runtime/docs/architecture.md
- runtime/docs/runtime.md
- runtime/docs/scanning.md
- runtime/docs/analyzer.md
- runtime/docs/learning.md
- runtime/docs/self_learning.md
- runtime/docs/schema.md
- runtime/docs/api.md
- runtime/docs/api_architecture_rule.md
- runtime/docs/runbook.md
- runtime/docs/engine_change_analysis_2026-04-02.md
- runtime/docs/engine_diagnostic_fix_plan.md
