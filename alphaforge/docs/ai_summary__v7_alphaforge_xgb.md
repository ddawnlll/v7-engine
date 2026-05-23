# V7 AlphaForge XGB — COMPLETE AI SUMMARY

## META

This document is a dense, machine-readable AI implementation reference for adding a V7-compatible alpha generation system.
It is written for LLM implementation agents, Pi autonomous execution, and engineering review.
It consolidates the conversation decisions, the V7 architecture rules, the V7 mode-specific simulation semantics, and the v2.5.1 implementation-plan execution format.

**Generated:** 2026-05-23
**Review hardening version:** `v1.1_review_hardened`
**Recommended model/system name:** `V7 AlphaForge XGB`
**Artifact slug:** `v7_alphaforge_xgb`
**Model family:** XGBoost-first hybrid supervised alpha model
**Universe for MVP:** 20 high-liquidity symbols
**Artifact structure:** 3 mode-specific artifact bundles; no per-symbol model family in first phase
**Primary output language:** R-multiple / expected-R / calibrated action probability
**Primary execution target:** v7 Strategy Engine

---

## 1. ONE-SENTENCE DEFINITION

`V7 AlphaForge XGB` is a V7-compatible, mode-specific, 20-symbol global alpha generation layer that uses deterministic multi-timeframe market features, optional unsupervised anomaly/regime context, XGBoost classification/regression heads, and v7 simulation-derived R labels to produce calibrated LONG / SHORT / NO_TRADE evidence for SWING, SCALP, and AGGRESSIVE_SCALP modes.

---

## 2. CORE DECISION

The alpha model must not predict raw future price direction as its primary truth.
The alpha model must learn V7's own simulated economic truth.

**Correct target:**

```text
Given this symbol, timestamp, mode, market state, and V7 mode simulation config,
which action produces the best net R outcome: LONG_NOW, SHORT_NOW, or NO_TRADE?
```

**Incorrect target:**

```text
Will close[t+h] be higher than close[t]?
```

The final system is therefore **hybrid supervised**, not pure unsupervised.
Unsupervised models may create auxiliary anomaly and regime features only.
They must not define labels, execution authority, or trade truth.

---

## 3. MODEL NAME DECISION

### 3.1 Recommended name

**`V7 AlphaForge XGB`**

Rationale:

- `V7` keeps the model visibly inside the V7 architecture.
- `AlphaForge` communicates that the model forges usable alpha evidence rather than issuing unmanaged trades.
- `XGB` communicates the first-phase model family clearly.
- The name works as both a product/system name and an artifact prefix.

### 3.2 Artifact prefixes

```text
v7_alphaforge_xgb_swing_classifier
v7_alphaforge_xgb_swing_regressor_long_r
v7_alphaforge_xgb_swing_regressor_short_r
v7_alphaforge_xgb_scalp_classifier
v7_alphaforge_xgb_scalp_regressor_long_r
v7_alphaforge_xgb_scalp_regressor_short_r
v7_alphaforge_xgb_aggressive_classifier
v7_alphaforge_xgb_aggressive_regressor_long_r
v7_alphaforge_xgb_aggressive_regressor_short_r
```

### 3.3 Alternative names

```text
V7 AlphaCore XGB      # more conservative
V7 EdgeForge XGB      # more trading-edge focused
V7 SignalForge XGB    # less alpha-specific
V7 R-Alpha XGB        # most explicit about R-multiple training
```

**Decision:** use `V7 AlphaForge XGB` unless the repository already reserves the AlphaForge name.

---

## 4. NON-NEGOTIABLE ARCHITECTURAL RULES

1. V7 runtime owns orchestration, execution control, persistence, outcome lifecycle, risk hard gates, and runtime-hosted simulation.
2. `V7 AlphaForge XGB` owns alpha evidence: calibrated action probabilities, expected-R surfaces, confidence, anomaly/regime context consumption, and model lineage.
3. The model must not own broker execution, position sizing authority, hard safety blocks, or lifecycle event materialization.
4. The model must be trained per mode scope: SWING, SCALP, AGGRESSIVE_SCALP.
5. The system must not train one universal artifact across incompatible modes in first phase.
6. Features are computed from canonical market state only.
7. Labels are produced from V7 simulation truth only.
8. Classification and regression outputs are both first-class.
9. NO_TRADE is a first-class learned action.
10. Every degradation, missing context, fallback, or artifact mismatch must be visible.
11. No future bars, outcome echoes, future labels, or trade result fields may enter features.
12. Walk-forward or chronological validation is mandatory. IID random splits are forbidden for primary evaluation.

13. Unsupervised anomaly/regime artifacts must be fit per walk-forward fold on train-only windows; full-history unsupervised fitting is forbidden.
14. Every anomaly-derived feature row must carry fold-compatible anomaly artifact lineage and fit-window metadata.
15. Regime and deterministic policy influence must be visible in AnalysisResult, DecisionEvent, monitoring, and review surfaces.
16. SCALP interval authority is config-driven: primary=1h, context=4h, refinement=15m. Any SCALP primary=15m mention is invalid unless it refers to AGGRESSIVE_SCALP or SCALP refinement.
17. Symbol one-hot encoding is an MVP constraint, not a permanent design; encoding-family changes must be feature-layer swaps with explicit version bumps.

---

## 5. MODE-SPECIFIC CONFIG SUMMARY

| Parameter | SWING | SCALP | AGGRESSIVE_SCALP |
|---|---:|---:|---:|
| Primary interval | 4h | 1h | 15m |
| Context interval | 1d | 4h | 1h |
| Refinement interval | 1h | 15m | 5m |
| Max holding bars | 12-30 | 3-12 | 1-5 |
| Stop multiplier ATR | 2.0-2.5 | 1.5-2.0 | 1.0-1.5 |
| Target multiplier ATR | 2.0-3.0 | 1.5-2.0 | 1.0-1.5 |
| Ambiguity gap R | 0.20 | 0.10 | 0.05 |
| Min action edge R | 0.35 | 0.15 | 0.08 |
| NO_TRADE tendency | LOW | MEDIUM | HIGH |


### 5.1 Mode interpretation

**SWING** evaluates slower, larger-horizon economic edge using 4h primary candles, 1d context, and 1h refinement.
SWING is best used as trend bias, larger opportunity selection, and high-level direction quality.

**SCALP** evaluates medium-speed intraday economic edge using 1h primary candles, 4h context, and 15m refinement.
SCALP is the main practical alpha mode for V7 decisioning.

**AGGRESSIVE_SCALP** evaluates fast entry-quality edge using 15m primary candles, 1h context, and 5m refinement.
AGGRESSIVE_SCALP is highest-noise and highest-cost sensitivity; it should be stricter in live deployment even if labels have lower min_action_edge.


### 5.2 Interval authority rule

The table above is the only authoritative interval summary for first-phase implementation.
All code must resolve intervals from central config. Hardcoded mode intervals are forbidden outside tests and config fixtures.

```text
SCALP primary interval = 1h
SCALP context interval = 4h
SCALP refinement interval = 15m
AGGRESSIVE_SCALP primary interval = 15m
```

This resolves the potential `SCALP 1h vs 15m` ambiguity: `15m` belongs to SCALP refinement and AGGRESSIVE_SCALP primary, not SCALP primary.

---

## 6. HIGH-LEVEL ARCHITECTURE

```text
20 Symbol Universe
        │
        ▼
Multi-Timeframe Klines
5m / 15m / 1h / 4h / 1d
        │
        ▼
Canonical State Builder
symbol + timestamp + primary/context/refinement views
        │
        ▼
Shared Feature Engine
price/return/volatility/volume/technical/context/refinement features
        │
        ├───────────────────────────────┐
        ▼                               ▼
Unsupervised Context Layer        V7 Simulation Label Adapter
anomaly_score, regime_id          long_R, short_R, no_trade quality
liquidity shock, clusters         mode-specific stop/target/holding/cost
        │                               │
        └───────────────┬───────────────┘
                        ▼
             Mode-Specific Datasets
             SWING / SCALP / AGGRESSIVE
                        │
                        ▼
             Mode-Specific XGBoost Bundles
             classifier + expected-R regressors
                        │
                        ▼
             Calibration & Reliability Layer
             calibrated p_long/p_short/p_no_trade
             expected-R reliability buckets
                        │
                        ▼
             Alpha Score Builder
             long_alpha_R, short_alpha_R, confidence
                        │
                        ▼
             V7 Decision Engine
             policy + portfolio + risk + execution eligibility
```


---

## 6A. REVIEW HARDENING INVARIANTS

### 6A.1 Fold-scoped anomaly fitting

Unsupervised context is allowed only as a fold-scoped auxiliary feature layer.
Every anomaly detector, clusterer, regime model, scaler, and reducer must be fit on the current walk-forward fold's train window only.
The fitted anomaly artifact is stored beside the fold's model artifact bundle and referenced by feature rows.
Validation, holdout, replay, and paper rows may only be transformed by an anomaly artifact whose fit window ends at or before the fold train boundary.

Forbidden:

```text
fit anomaly detector on all history
then create anomaly_score for train/validation/test
```

Required lineage fields:

```text
fold_id
anomaly_artifact_id
anomaly_family_version
anomaly_fit_window_start_utc
anomaly_fit_window_end_utc
anomaly_transform_timestamp_utc
feature_schema_version
```

Dataset assembly must hard-fail or exclude rows where anomaly lineage crosses the fold boundary.

### 6A.2 Deterministic / regime override visibility

Regime-aware modifiers are not allowed to act as silent vetoes.
If policy changes a model-preferred action because of regime context, the suppression or threshold change must appear in both AnalysisResult and DecisionEvent.

Required reason codes:

```text
regime_gate_forced_no_trade
regime_blocked_direction
regime_threshold_multiplier_applied
regime_advisory_only
regime_policy_not_applied
```

Required constraint levels:

```text
ADVISORY
SOFT_BLOCK
HARD_BLOCK
```

Monitoring must slice no-trade decisions into at least:

```text
model_preferred_no_trade
regime_forced_no_trade
risk_forced_no_trade
fallback_safe_no_trade
```

### 6A.3 Symbol encoding upgrade path

First phase uses `symbol_one_hot_v1` over the approved 20-symbol universe.
This is intentionally an MVP constraint.
The feature schema must carry `symbol_encoding_family` and `symbol_universe_version` so future families can be swapped without touching simulation or labels.

Potential later families:

```text
symbol_target_encoding_v1
symbol_cluster_encoding_v1
symbol_embedding_features_v1
```

### 6A.4 SCALP interval consistency

SCALP must always resolve to:

```text
primary_interval = 1h
context_interval = 4h
refinement_interval = 15m
```

Dataset generation, simulation profile selection, label horizon family, feature builder, and live inference must all read those values from config.


---

## 7. DATA TABLES

### 7.1 raw_klines

Purpose: immutable source market data.

Required fields:

```text
symbol
timestamp
interval
open
high
low
close
volume
quote_volume
trade_count
taker_buy_volume
taker_buy_quote_volume
source
ingestion_timestamp_utc
data_quality_flags
```

Rules:

- Raw klines are never directly consumed by XGBoost.
- Raw klines must not contain derived feature columns.
- Gaps, duplicates, partial candles, and stale windows must be explicit.

### 7.2 canonical_state

Purpose: V7-compatible market state at one decision timestamp.

Required conceptual fields:

```text
symbol
state_timestamp_utc
mode
primary_interval
context_interval
refinement_interval
primary_window
context_window
refinement_window
derived_state
quality
metadata
```

Rules:

- Same input history must produce the same canonical state.
- Live, replay, training, and evaluation semantics must match.
- No future-derived fields are allowed.

### 7.3 alpha_feature_table

Purpose: model and V7 feature input.

Key fields:

```text
symbol
timestamp
mode
primary_interval
context_interval
refinement_interval
feature_schema_version
normalization_family_version
symbol_encoding_family_version
```

Feature families:

```text
primary_return_features
primary_candle_geometry_features
primary_volatility_features
primary_volume_liquidity_features
primary_technical_features
context_trend_regime_features
refinement_entry_timing_features
unsupervised_anomaly_regime_features
data_quality_missingness_flags
symbol_identity_or_symbol_metadata
```

### 7.4 alpha_label_table

Purpose: training labels only. Not used in live inference.

Required fields:

```text
symbol
timestamp
mode
simulation_family_version
label_interpretation_version
cost_model_version
horizon_family_version
long_R_net
short_R_net
long_R_gross
short_R_gross
long_cost_R
short_cost_R
long_mae_R
short_mae_R
long_mfe_R
short_mfe_R
no_trade_quality_label
best_action_label
second_best_action_label
gap_R
best_R
regret_R
saved_loss_score
missed_opportunity_score
path_quality_score
label_validity
ambiguity_reason
invalidity_reason
```

### 7.5 alpha_prediction_table

Purpose: runtime-facing model output consumed by V7.

Required fields:

```text
symbol
timestamp
mode
model_scope
primary_interval
p_long
p_short
p_no_trade
classification_margin
expected_R_long
expected_R_short
expected_cost_adjusted_R_long
expected_cost_adjusted_R_short
expected_drawdown_R_long
expected_drawdown_R_short
confidence
confidence_kind
long_alpha_R
short_alpha_R
recommended_alpha_action
model_artifact_version
calibration_artifact_version
policy_artifact_version
feature_schema_version
prediction_timestamp_utc
```

---

## 8. FEATURE DESIGN

### 8.1 Shared principles

Features are shared conceptually across modes, but their intervals and lookbacks are mode-specific.
The feature engine should use the same code paths for SWING, SCALP, and AGGRESSIVE_SCALP while resolving interval aliases from mode config.

### 8.2 Primary interval features

```text
return_1
return_2
return_3
return_6
return_12
return_24
log_return_1
cumulative_return_n
volatility_6
volatility_12
volatility_24
volatility_ratio_short_long
atr_14
range_zscore_20
close_position_in_candle
body_to_range_ratio
upper_wick_ratio
lower_wick_ratio
rsi_14
ma_distance_20
ma_distance_50
ema_distance_20
bollinger_position
volume_zscore_20
quote_volume_zscore_20
trade_count_zscore_20
taker_buy_ratio
volume_price_divergence
```

### 8.3 Context interval features

```text
context_return_3
context_return_6
context_trend_strength
context_rsi_14
context_ma_distance_20
context_volatility_regime
context_range_compression
context_breakout_state
context_market_regime
context_regime_confidence
```

### 8.4 Refinement interval features

```text
refinement_return_1
refinement_return_3
refinement_volume_zscore
refinement_taker_buy_ratio
refinement_range_zscore
refinement_close_position
refinement_micro_momentum
refinement_micro_reversal
entry_pressure_proxy
entry_zone_distance
entry_readiness_proxy
```

### 8.5 Unsupervised context features

Unsupervised learning is allowed only as a feature producer.

Allowed outputs:

```text
anomaly_score
volume_anomaly_score
liquidity_shock_score
regime_id
volatility_cluster
micro_regime_id
reconstruction_error
isolation_forest_score
```

Forbidden outputs:

```text
trade label
execution permission
hidden veto
future outcome proxy
unversioned cluster semantics
```

---

## 9. LABEL GENERATION

### 9.1 Core label algorithm

For each `symbol`, `timestamp`, and `mode`:

```text
1. Build canonical state using only history up to timestamp.
2. Resolve mode simulation config.
3. Compute ATR on primary interval.
4. Simulate LONG_NOW using refinement future path.
5. Simulate SHORT_NOW using refinement future path.
6. Compute NO_TRADE comparative quality.
7. Apply fee and slippage model.
8. Produce long_R_net and short_R_net.
9. Compute best_R and gap_R.
10. Apply mode-specific min_action_edge and ambiguity_gap.
11. Emit best_action_label and regression targets.
```

### 9.2 Action label rule

```text
best_R = max(long_R_net, short_R_net)
gap_R = abs(long_R_net - short_R_net)

if label invalid or unresolved:
    y_class = INVALID_OR_UNRESOLVED
elif gap_R < ambiguity_gap_R:
    y_class = AMBIGUOUS_STATE
elif best_R < min_action_edge_R:
    y_class = NO_TRADE
elif long_R_net > short_R_net:
    y_class = LONG_NOW
else:
    y_class = SHORT_NOW
```

### 9.3 Regression targets

Preferred first-phase targets:

```text
y_reg_long = long_R_net
y_reg_short = short_R_net
y_reg_long_mae = long_mae_R
y_reg_short_mae = short_mae_R
y_reg_long_cost_adjusted = long_R_net - long_cost_R
y_reg_short_cost_adjusted = short_R_net - short_cost_R
```

Optional single signed target:

```text
signed_best_R = long_R_net if best_action_label == LONG_NOW
signed_best_R = -short_R_net if best_action_label == SHORT_NOW
signed_best_R = 0 if best_action_label == NO_TRADE
```

Recommended model structure uses separate long and short R regressors rather than one signed regressor.

---

## 10. MODE-SPECIFIC DATASETS

Datasets must not mix incompatible mode truths.

Required datasets:

```text
alpha_dataset_swing
alpha_dataset_scalp
alpha_dataset_aggressive_scalp
```

Each dataset contains all 20 symbols for the mode.

### 10.1 Why global per-mode instead of per-symbol

- Better data volume.
- Learns common patterns across liquid symbols.
- Supports V7 centralized multi-symbol execution.
- Avoids maintaining 60 or more separate artifacts.
- Enables symbol-balanced evaluation and portfolio-aware candidate ranking.

### 10.2 Why not one universal multi-mode model

- SWING and AGGRESSIVE_SCALP solve different economic problems.
- Holding horizons, cost sensitivity, ambiguity thresholds, and feature cadence differ.
- One universal model may learn shortcuts and confuse mode semantics.
- Per-mode artifact bundles align with V7's model_scope rules.

---

## 11. TRAINING DESIGN

### 11.1 Artifact bundles

Per mode:

```text
action_classifier
long_expected_R_regressor
short_expected_R_regressor
long_adverse_pressure_regressor
short_adverse_pressure_regressor
optional_path_quality_regressor
calibration_artifact
reliability_artifact
policy_threshold_artifact
feature_schema_artifact
```

### 11.2 Training split

Primary evaluation must use walk-forward splits:

```text
minimum train window: 12 months
validation window: 2 months
optional holdout tail: 1 month
number of folds: 6
advance: validation window length
```

### 11.3 Sample weighting

Default:

```text
symbol_weight = inverse_frequency_by_symbol capped to max_weight
class_weight = configured for LONG / SHORT / NO_TRADE balance
row_weight = symbol_weight * class_weight * label_quality_weight
```

### 11.4 Exclusions

Exclude by default:

```text
UNRESOLVED labels
INVALIDATED labels
AMBIGUOUS_STATE rows from hard classification training
rows with future data gaps
rows with stale primary state
rows with incompatible mode config lineage
```

Preserve excluded rows with explicit exclusion reasons.

---

## 12. CALIBRATION AND RELIABILITY

Classification probabilities must be calibrated per mode.
Raw XGBoost scores are not runtime confidence.

Calibration outputs:

```text
calibrated_p_long
calibrated_p_short
calibrated_p_no_trade
calibrated_confidence
confidence_kind
reliability_error
action_bucket_realized_R
```

Regression reliability checks:

```text
predicted expected-R bucket vs realized average R
sign correctness by bucket
long expected-R reliability
short expected-R reliability
adverse pressure reliability
symbol/regime breakdown
```

If regression reliability is weak, policy must degrade expected-R gates explicitly.

---

## 13. ALPHA SCORE BUILDER

V7 consumes R-native alpha evidence.

Recommended formulas:

```text
long_alpha_R = calibrated_p_long * max(expected_R_long, 0) * confidence
short_alpha_R = calibrated_p_short * max(expected_R_short, 0) * confidence
```

Alternative directional score:

```text
directional_edge_R = (calibrated_p_long * expected_R_long) - (calibrated_p_short * expected_R_short)
```

Policy should not execute based on alpha score alone.
V7 must still apply policy, portfolio, risk, actionability, and execution eligibility gates.

---

## 14. V7 INTEGRATION CONTRACT

### 14.1 Runtime request path

```text
V7 Mode Controller
  → build AnalysisRequest with requested_trade_mode/model_scope
  → build canonical_state and state_views
  → call V7 AlphaForge XGB inference service
  → validate AnalysisResult-compatible alpha output
  → create DecisionEvent
  → apply V7 policy/portfolio/risk
  → execute or no-trade
```

### 14.2 Example inference payload

```json
{
  "symbol": "BTCUSDT",
  "timestamp": "2026-05-23T12:00:00Z",
  "mode": "SCALP",
  "model_scope": "SCALP",
  "primary_interval": "1h",
  "context_interval": "4h",
  "refinement_interval": "15m",
  "features": {
    "primary_return_3": 0.0061,
    "primary_volatility_12": 0.018,
    "primary_rsi_14": 61.2,
    "primary_volume_zscore_20": 2.1,
    "context_trend_strength": 0.74,
    "refinement_taker_buy_ratio": 0.58,
    "anomaly_score": 0.69
  }
}
```

### 14.3 Example model output

```json
{
  "symbol": "BTCUSDT",
  "timestamp": "2026-05-23T12:00:00Z",
  "mode": "SCALP",
  "model_scope": "SCALP",
  "model_name": "V7 AlphaForge XGB",
  "model_version": "v7_alphaforge_xgb_scalp_v1",
  "p_long": 0.64,
  "p_short": 0.13,
  "p_no_trade": 0.23,
  "expected_R_long": 0.31,
  "expected_R_short": -0.08,
  "confidence": 0.71,
  "confidence_kind": "calibrated",
  "long_alpha_R": 0.1409,
  "short_alpha_R": 0.0,
  "recommended_alpha_action": "LONG_NOW"
}
```

---

## 15. POLICY ALIGNMENT

V7 policy must compare:

```text
calibrated action probability
expected R
expected adverse pressure
cost-adjusted R
NO_TRADE probability
mode-specific min_action_edge
mode-specific ambiguity gap
regime modifier
portfolio pressure
risk hard gates
```

Suggested mode-specific policy thresholds for alpha output consumption:

```text
SWING:
  min_long_alpha_R: 0.20
  min_short_alpha_R: 0.20
  min_confidence: 0.58
  require_expected_R_above: 0.35

SCALP:
  min_long_alpha_R: 0.10
  min_short_alpha_R: 0.10
  min_confidence: 0.60
  require_expected_R_above: 0.15

AGGRESSIVE_SCALP:
  min_long_alpha_R: 0.06
  min_short_alpha_R: 0.06
  min_confidence: 0.65
  require_expected_R_above: 0.08
  extra_cost_filter_required: true
```

These thresholds are initial config proposals and must be tuned through walk-forward validation.

---

## 16. PHASE PLAN OVERVIEW

The implementation should be completed in 10 phases.

```text
Phase 0: Repo Alignment & Alpha Foundations
Phase 1: Contracts & Alpha Data Contract
Phase 2: Runtime Simulation Adapter & R-Label Engine
Phase 3: Multi-Timeframe Feature Engine & Unsupervised Context
Phase 4: Dataset Assembly, Walk-Forward Splits & Label QA
Phase 5: XGBoost Hybrid Model Training
Phase 6: Calibration, Reliability & Alpha Score Builder
Phase 7: V7 Policy/Portfolio/Risk Integration
Phase 8: Evaluation, Backtest, Paper & Shadow Validation
Phase 9: Deployment, Monitoring, Drift, Promotion & Rollback
```

Hard dependencies:

```text
1 -> 0
2 -> 1
3 -> 1
4 -> 2 + 3
5 -> 4
6 -> 5
7 -> 6
8 -> 5 + 6 + 7
9 -> 8
```

Soft iteration loops:

```text
3 <-> 4
5 <-> 6
6 <-> 7
8 <-> 9
```

---

## 17. REPOSITORY SHAPE

Recommended modules:

```text
src/v7/alpha/
  config/
  contracts/
  state/
  simulation_adapter/
  labels/
  features/
  anomaly/
  dataset/
  model/
  calibration/
  scoring/
  policy_bridge/
  evaluation/
  monitoring/
  runtime/

tests/v7/alpha/
  unit/
  integration/
  regression/
  golden/

configs/v7/alpha/
  alpha_defaults.yaml
  modes.yaml
  model_xgb.yaml
  simulation_profiles.yaml
  policy_thresholds.yaml
```

---

## 18. GLOBAL DEFINITION OF DONE

The alpha generation system is complete when all are true:

- Mode-specific datasets exist for SWING, SCALP, and AGGRESSIVE_SCALP.
- Labels are generated through V7-compatible simulation semantics.
- No future data leaks into feature rows.
- All feature schemas are versioned.
- XGBoost classifier and expected-R regressors train per mode.
- Calibration artifacts exist per mode.
- Alpha output is R-native and V7-compatible.
- V7 policy can consume `long_alpha_R` and `short_alpha_R` without hidden semantics.
- Walk-forward evaluation reports economic quality, no-trade quality, calibration, regression reliability, symbol stability, and regime stability.
- Paper/shadow deployment path exists before live eligibility.
- Rollback can revert model + calibration + policy bundles per mode.

---

## 19. FAILURE MODES TO PREVENT

```text
future leakage in feature engineering
separate label simulator divergent from V7 runtime simulation semantics
raw scores presented as calibrated confidence
mode-mixed datasets
per-symbol overfitting
NO_TRADE treated as fallback instead of action
ambiguous states forced into directional labels
missing context silently filled without flags
model score used as execution permission
unversioned label changes
unversioned cost/slippage changes
random train/test split used as primary evidence
live deployment without paper/shadow review
```

---

## 20. BOTTOM LINE

`V7 AlphaForge XGB` should be implemented as a V7-native alpha evidence engine, not as a standalone trading bot.
It must train one global model family per V7 mode using 20-symbol data, V7 simulation-derived R labels, shared deterministic features, optional unsupervised anomaly/regime features, XGBoost classification/regression heads, per-mode calibration, and a visible V7 policy bridge.

The system should produce fewer, higher-quality, cost-aware, mode-consistent trade candidates and should improve V7's ability to choose LONG, SHORT, or NO_TRADE without violating runtime ownership, policy gates, portfolio controls, or risk safety.


---

## 44. HARDENING ACCEPTANCE CHECKS

Implementation cannot be considered complete until the following checks pass:

```text
1. Fold-scoped anomaly artifacts are trained only on fold train windows.
2. Dataset builder rejects anomaly feature rows with fit-window leakage.
3. AnalysisResult exposes deterministic_interaction regime details.
4. DecisionEvent records regime gate reason codes when policy changes action.
5. Monitoring reports regime-forced no-trade share separately from model-preferred no-trade.
6. Feature schema includes symbol_encoding_family and symbol_universe_version.
7. SCALP interval defaults resolve from config to primary=1h/context=4h/refinement=15m.
8. No implementation hardcodes SCALP primary=15m.
```
