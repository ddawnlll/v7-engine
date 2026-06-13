# V4 Analyzer

This is the current source-of-truth for the live `v4` analyzer.

It is written for engineering handoff and LLM consumption.

Primary goals:

- explain the decision pipeline
- explain current hard blocks and penalties
- define the debug and audit contract
- document how learning, circuit breaker, and universe throttling interact with live analysis

Primary implementation files:

- [/Users/hootie/src/trading-bot/v4/services/analyzer_core.py](/Users/hootie/src/trading-bot/v4/services/analyzer_core.py)
- [/Users/hootie/src/trading-bot/v4/services/analyzer_config.py](/Users/hootie/src/trading-bot/v4/services/analyzer_config.py)
- [/Users/hootie/src/trading-bot/v4/services/analyzer_factors.py](/Users/hootie/src/trading-bot/v4/services/analyzer_factors.py)
- [/Users/hootie/src/trading-bot/v4/services/analyzer_probability.py](/Users/hootie/src/trading-bot/v4/services/analyzer_probability.py)
- [/Users/hootie/src/trading-bot/v4/services/analyzer_reporting.py](/Users/hootie/src/trading-bot/v4/services/analyzer_reporting.py)
- [/Users/hootie/src/trading-bot/v4/services/analyzer_helpers.py](/Users/hootie/src/trading-bot/v4/services/analyzer_helpers.py)
- [/Users/hootie/src/trading-bot/v4/services/learning_service.py](/Users/hootie/src/trading-bot/v4/services/learning_service.py)
- [/Users/hootie/src/trading-bot/v4/services/circuit_breaker_service.py](/Users/hootie/src/trading-bot/v4/services/circuit_breaker_service.py)
- [/Users/hootie/src/trading-bot/v4/services/audit_service.py](/Users/hootie/src/trading-bot/v4/services/audit_service.py)
- [/Users/hootie/src/trading-bot/v4/services/universe_filter_service.py](/Users/hootie/src/trading-bot/v4/services/universe_filter_service.py)
- [/Users/hootie/src/trading-bot/v4/runtime/scan_runtime.py](/Users/hootie/src/trading-bot/v4/runtime/scan_runtime.py)
- [/Users/hootie/src/trading-bot/v4/runtime/paper_execution.py](/Users/hootie/src/trading-bot/v4/runtime/paper_execution.py)

## Executive Summary

The analyzer is a layered, interpretable decision engine.

Live decision order:

1. evaluate circuit-breaker state
2. classify regime
3. determine trend and direction
4. score structure, oscillators, momentum, and volume
5. enforce entry confirmation policy
6. compute directional probability
7. derive stop, target, `RR`, and expected value
8. apply execution-quality penalties
9. apply learning adjustments
10. apply degraded circuit-breaker multiplier when relevant
11. gate by confidence, `RR`, and expected value
12. return `BUY`, `SELL`, or `NEUTRAL`

The analyzer is intentionally observable:

- `factors` explain the thesis
- `advanced_analysis.probability_model` explains the edge model
- `advanced_analysis.decision_path` explains pass/fail state
- `advanced_analysis.stop_model` explains stop construction
- `advanced_analysis.confirmation` explains entry confirmation
- `advanced_analysis.regime_policy` explains environment policy
- `audit_json` freezes the decision for later analysis

## Current Live Safety Policy

### Regime policy

Current hard or soft environment rules:

- `DEAD`
  - blocked for modes where `regime_dead == BLOCK`
- `MOMENTUM`
  - hard blocked by live safety policy
- `SQUEEZE`
  - blocked when `regime_squeeze == BLOCK`
- `MEAN_REVERSION`
  - allowed only with penalty via `regime_mean_reversion_penalty`

These decisions are exposed through:

- `advanced_analysis.regime_policy`
- `advanced_analysis.decision_path`
- `audit_json.regime_policy`

### Session policy

Current live guardrail:

- `SESSION_NEW_YORK_ENABLED=false` by default

Session pressure also feeds execution quality and diagnostics through:

- `session_label`
- `session_policy`
- session multiplier logic
- `decision_path.entry_quality_breakdown`

Session alias normalization is now explicit:

- `OVERLAP`
- `LONDON_OVERLAP`
- `NY_OVERLAP`

all normalize to:

- `LONDON_NEW_YORK_OVERLAP`

### Mode and interval policy

Current special-case policy:

- `AGGRESSIVE_SCALP` is restricted to intervals up to `4h`
- if requested on higher intervals, analyzer returns `NEUTRAL` at `INTERVAL_POLICY`

### Circuit breaker policy

Circuit breaker states:

- `CLOSED`
  - analyzer proceeds normally
- `DEGRADED`
  - analyzer proceeds, but confidence is multiplied down
- `OPEN`
  - autonomous scan flow is blocked
  - analyzer returns `NEUTRAL` with `CIRCUIT_BREAKER` stage

Important:

- `OPEN` blocks autonomous scanning and autonomous trade generation
- manual analysis tools can still be used outside that path

### Universe throttling

Universe throttling is not part of the pure analyzer function. It is a scan-runtime tactical containment layer.

It can suppress symbols before analysis when they meet throttle rules:

- seeded guardrail list
- consecutive stop-hit cluster
- rolling stop-hit rate threshold

This is handled in:

- [/Users/hootie/src/trading-bot/v4/services/universe_filter_service.py](/Users/hootie/src/trading-bot/v4/services/universe_filter_service.py)
- [/Users/hootie/src/trading-bot/v4/runtime/scan_runtime.py](/Users/hootie/src/trading-bot/v4/runtime/scan_runtime.py)

The analyzer itself does not know a symbol was skipped. The runtime records that as:

- `skipped.symbol_throttled`
- `skip_stages.UNIVERSE_FILTER`
- `result.universe_filter`

## Inputs

Main analyzer inputs:

- `symbol`
- `interval`
- `snap`
- `ticker`
- `mode`
- optional `htf_trend`

The analyzer expects `snap` to already contain enriched market context.

Important snapshot fields:

- price and volatility:
  - `price`
  - `atr`
  - `atr_5bar_avg`
  - `atr_expanding`
  - `bb_width`
- trend and moving averages:
  - `ema_9`
  - `ema_21`
  - `ema_50`
  - `ema_200`
- structure:
  - `recent_high`
  - `recent_low`
  - `near_resistance`
  - `near_support`
  - `retest_support`
  - `retest_resist`
  - `bullish_sweep`
  - `bearish_sweep`
- momentum and oscillators:
  - `rsi`
  - `rsi_slope`
  - `macd`
  - `macd_signal`
  - `macd_hist`
  - `macd_hist_delta`
  - `stoch_k`
  - `stoch_d`
  - `stochrsi_k`
  - `stochrsi_d`
  - `adx`
- volume and flow:
  - `vol_ratio`
  - `vol_slope`
  - `obv_slope`
  - `session_liquidity_score`
  - `trade_intensity`
- microstructure:
  - `orderbook_spread_bps`
  - `orderbook_microprice_deviation_bps`
  - `microstructure_source`
- session and higher timeframe:
  - `session_label`
  - `htf_trend`

## High-Level Components

### `analyzer_core.py`

Responsibilities:

- pipeline ordering
- hard blockers
- trend-to-direction mapping
- execution-quality aggregation
- learning integration
- circuit-breaker integration
- confidence, `RR`, and expected-value gating
- final `TradeSignal` assembly

### `analyzer_config.py`

Per-mode policy surface.

Defines:

- `min_confidence`
- `min_rr`
- `min_expected_value_r`
- regime behavior
- confirmation policy
- structure requirements
- higher-timeframe opposition handling

Current modes:

- `SWING`
- `SCALP`
- `AGGRESSIVE_SCALP`

### `analyzer_factors.py`

Deterministic factor engine.

Main outputs:

- regime
- trend
- trend strength
- structure factors
- oscillator factors
- momentum factor
- volume factor
- entry zone
- stop-loss model
- take-profit model
- risk/reward
- confirmation state

### `analyzer_probability.py`

Directional probability overlay.

Uses:

- factor context
- return distribution metrics
- volatility features
- microstructure features

Outputs:

- `probability_raw`
- `probability`
- `probability_up`
- `probability_down`
- probability component scores

### `learning_service.py`

Adaptive correction layer.

Current live behavior:

- calibration is feature-gated and disabled by default
- adaptive stop widening is disabled by default
- timing/component/execution penalties still work
- out-of-sample monotonicity is measured before calibration can be trusted

Important settings:

- `LEARNING_CALIBRATION_ENABLED`
- `LEARNING_ADAPTIVE_STOP_ENABLED`

### `audit_service.py`

Freezes signal-time decision state into `audit_json`.

### `paper_execution.py`

Consumes analyzer output for paper trades.

Important current policy:

- position sizing confidence is capped at `80` for allocation
- raw confidence diagnostics are preserved separately

## Decision Pipeline

### 1. Circuit-breaker pre-check

The analyzer first evaluates circuit state.

If state is `OPEN`:

- return `NEUTRAL`
- stage: `CIRCUIT_BREAKER`
- reason includes the breaker explanation

If state is `DEGRADED`:

- analysis continues
- degraded multiplier is applied later to confidence

### 2. Regime detection

Regime is computed from volatility and trend context.

Current notable outcomes:

- `MOMENTUM` is hard blocked
- `SQUEEZE` may be blocked
- `DEAD` may be blocked

### 3. Trend detection

Trend is determined from EMA state and momentum context.

If direction cannot be established:

- analyzer returns `NEUTRAL`
- stage: `TREND`

### 4. Structure evaluation

Structure scoring uses:

- support/resistance proximity
- retest state
- sweep state
- recent high/low anchors

If structure is unacceptable for the active mode:

- analyzer returns `NEUTRAL`
- stage: `STRUCTURE`

### 5. Entry confirmation

Confirmation is now an explicit model.

Current signals include:

- breakout flag
- breakout hold
- retest hold
- micro momentum
- micro flow

Current output:

```json
{
  "policy": "REQUIRE|OPTIONAL",
  "passed": true,
  "bonus": 1.12,
  "reasons": ["..."],
  "signals": {
    "breakout_flag": false,
    "breakout_hold": false,
    "retest_hold": true,
    "micro_momentum": true,
    "micro_flow": true
  }
}
```

This is exposed at:

- `advanced_analysis.confirmation`
- `audit_json.confirmation`

### 6. Probability model

Probability is derived from:

- factor edge
- distribution edge
- volatility edge
- microstructure edge

Output is stored under:

- `advanced_analysis.probability_model`

Important fields:

- `probability_raw`
- `probability`
- `probability_up`
- `probability_down`
- `component_scores`

### 7. Stop model

The stop model is no longer ATR-only.

Current logic:

1. compute a structure-based stop using recent support/resistance, retest, or sweep anchor
2. compute ATR floor stop separately
3. choose the wider safer stop
4. cap absurd width when required by mode/regime policy
5. re-check `RR` after stop widening

Current diagnostic payload:

```json
{
  "stop_method": "structure_stop|atr_floor|structure_stop_capped",
  "atr_floor_stop": 100.928571,
  "structure_stop": 98.92,
  "stop_distance": 3.0,
  "stop_distance_atr": 2.5,
  "regime": "TRENDING",
  "mode": "SCALP",
  "direction": "BUY"
}
```

This is exposed at:

- `advanced_analysis.stop_model`
- `audit_json.stop_model`

Wide-stop normalization is now explicit in paper sizing:

- sizing does not reduce for stop widths up to `1.5 ATR`
- above `1.5 ATR`, notional size scales down proportionally
- runtime floor remains bounded so size cannot collapse below the safety floor
- sizing metadata now includes:
  - `risk_adjustment_factor`
  - `stop_distance_atr`
  - `stop_width_normalized`

### 7b. Timing model and stale-exit policy

The timing model is now conditioned by:

- regime
- session
- mode

It produces:

- `candles_target`
- `candles_min`
- `candles_max`
- `time_stop_candles`
- `stale_exit_candles`
- `stale_exit_min_progress_pct`
- `stale_exit_max_abs_r`
- timing multipliers for regime and session

This is exposed at:

- `signal.timing_estimate`
- `advanced_analysis.timing_model`
- `audit_json.timing_model`

Operational behavior:

- trades can now close via `EARLY_STALE_EXIT`
- this happens before the full time stop if elapsed candles exceed the stale-exit threshold
- and directional progress remains too weak
- and open `R` stays near flat

This is meant to cut stale capital occupancy, not replace stop-loss logic.

### 8. Execution-quality penalties

Execution quality is multiplicative and interpretable.

Current penalty examples:

- EMA extension
- VWAP stretch
- recent impulse extension
- impulse decay from `MACD`
- impulse decay from `RSI`
- regime mean-reversion penalty
- session penalty
- worst setup bucket guardrail

The current multiplier breakdown is exposed in:

- `decision_path.entry_quality_breakdown`

### 9. Learning adjustments

Learning adjustments can apply:

- calibration multiplier
- entry penalty
- component penalty
- execution penalty
- stop multiplier

Current live safety constraints:

- calibration defaults to bypass
- adaptive stop defaults to bypass
- calibration monotonicity must validate before trust

Learning diagnostics live under:

- `advanced_analysis.learning_adjustments`
- `audit_json.learning_adjustments_applied`

### 10. Final gating

After probability, execution, and learning adjustments:

- confidence is checked
- `RR` is checked
- expected value is checked

If any fail:

- analyzer returns `NEUTRAL`
- stage is recorded in `decision_path.neutral_stage`

Common stages:

- `REGIME`
- `TREND`
- `STRUCTURE`
- `OSCILLATOR`
- `VOLUME`
- `CONFIDENCE`
- `RR`
- `EV`
- `CIRCUIT_BREAKER`
- `INTERVAL_POLICY`

## `decision_path` Contract

Every final signal or neutral return should expose a `decision_path`.

Current keys:

- `neutral_stage`
- `reason`
- `mode`
- `interval`
- `session_label`
- `circuit_status`
- `quality_multiplier`
- `confidence_quality_multiplier`
- `entry_quality_breakdown`
- `probability_raw`
- `probability_final`
- `confidence_raw`
- `confidence_final`
- `risk_reward`
- `expected_value`

Important behavior:

- neutral results preserve computed diagnostics instead of zeroing them
- this fixed the earlier misleading `0.0` confidence / `0.0` probability neutral outputs

## `audit_json` Contract

The audit trail is frozen at signal time.

Current important fields:

- `threshold_checks`
- `factor_scores`
- `probability_components`
- `learning_adjustments_applied`
- `confidence_before_learning`
- `confidence_after_learning`
- `confidence_model_raw`
- `confidence_post_learning`
- `confidence_post_execution`
- `probability_before_learning`
- `probability_after_learning`
- `probability_model_raw`
- `probability_post_learning`
- `probability_post_execution`
- `execution_quality_multiplier`
- `stop_model`
- `confirmation`
- `regime_policy`
- `circuit_breaker_state`

`post_execution` fields are currently placeholders at signal time and remain `null` until later outcome workflows use them.

## Scan Runtime Interaction

The analyzer is called from scan runtime, not from the scheduler directly.

Important runtime behavior:

- mode interval policy is enforced before analysis
- universe throttling can suppress symbols before analysis
- `skip_stages` counts why tasks were skipped
- scan debug now includes waiting and fetch-timeout context

Relevant scan result fields:

- `result.skipped`
- `result.skip_stages`
- `result.debug`
- `result.universe_filter`

## Position Sizing Interaction

Paper execution uses analyzer confidence for sizing.

Current policy:

- allocation confidence is capped at `80`
- raw analyzer confidence can still be higher for diagnostics
- wider stop geometry is compensated by runtime risk-adjustment logic

## Self-Learning Boundary

Self-learning foundations consume analyzer output but do not control it live.

Current downstream handoff:

- signal
- snapshot
- audit
- trade outcome

These feed:

- self-learning context
- trade memories
- counterfactual replays
- policy dataset rows
- expectancy labels
- shadow policy decisions

Hard rule:

- shadow policy is advisory-only
- analyzer and execution do not accept live behavioral changes from self-learning yet

## Current Known Strengths

- analyzer now preserves usable neutral diagnostics
- stop placement is structure-aware
- entry confirmation is explicit
- environment policy is visible
- scan/runtime visibility is materially stronger than before

## Current Known Weaknesses

- live time-stop rate is still high
- live time-stop quality is poor relative to expected duration
- early stale exit is now available, but it has not had enough new live samples yet to judge its impact
- post-learning confidence monotonicity is only mixed on the current live sample
- manual-vs-autonomous comparison currently lacks live manual closed-trade volume in the latest validation window

## Current Validation Snapshot

Validated `2026-04-02` with:

- focused regression suites: `34` tests passed
- related runtime/analytics suite: `22` tests passed
- broader engine suite from the same validation pass: `70` tests passed
- frontend build: passed
- live 30-day trade sample:
  - closed trades: `258`
  - win rate: `47.29%`
  - average realized `R`: `+0.1359R`
  - stop-hit rate: `29.84%`
  - time-stop rate: `54.65%`
  - pre-learning monotonicity: `PASS`
  - post-learning monotonicity: `MIXED`
  - time-stop cause mix:
    - `never_developed`: `67`
    - `stale_range_bound_hold`: `50`
    - `late_reversal`: `24`
  - time-stop quality mix:
    - `flat_positive`: `67`
    - `stale`: `50`
    - `adverse`: `24`
  - expected-duration within `25%` band: `3.55%`
  - source split in current sample:
    - `AUTO`: `258`
    - `MANUAL/INTERFACE`: `0`

This snapshot is not permanent truth. It is a dated validation point.
