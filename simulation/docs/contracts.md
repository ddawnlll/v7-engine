# Simulation Contracts — Input/Output Schemas

## Purpose

This document defines the stable contract surfaces for `/simulation`. Every consumer (`v7/` runtime, `alphaforge/` labels/evaluation) interacts with simulation through these contracts.

Contracts are versioned. Breaking changes bump a version. All fields carry lineage.

## Contract Family

| Contract | Direction | Role |
|---|---|---|
| `SimulationInput` | Consumer → Simulation | Encodes what to simulate |
| `SimulationOutput` | Simulation → Consumer | Encodes comparative outcomes |
| `ActionOutcome` | Embedded in Output | Per-action path result |
| `NoTradeOutcome` | Embedded in Output | No-trade quality result |
| `SimulationProfile` | Config → Resolver | Mode-specific parameters |
| `CostModelRef` | Config → Resolver | Cost profile reference |
| `ExitResolution` | Embedded in Outcome | How and why a path exited |
| `PathMetrics` | Embedded in Outcome | MFE, MAE, quality scores |
| `SimulationLineage` | Embedded in Output | Version/run identity |
| `AdapterRunMetadata` | Adapter → Output | Adapter kind and run ID |
| `MonteCarloOutput` | MC Driver → Consumer | Distributional evidence |

---

## SimulationInput

The entry contract. Encodes a single simulation scenario.

```yaml
SimulationInput:
  # ── Identity & Scope ──
  symbol: string                    # e.g., "BTCUSDT"
  decision_timestamp: utc_timestamp
  mode: SWING | SCALP | AGGRESSIVE_SCALP
  primary_interval: string          # e.g., "4h", "1h", "15m"

  # ── Market State ──
  canonical_state_lineage:
    state_version: string           # canonical state schema version
    feature_schema_version: string  # feature schema version
    source_data_version: string     # raw data version

  # ── Future Path ──
  future_path:
    candles:                        # array of OHLCV candles
      - open: number
        high: number
        low: number
        close: number
        volume: number
        close_time_utc: utc_timestamp
    completeness_status: COMPLETE | PARTIAL | CORRUPTED
    expected_bars: integer

  # ── Profile References ──
  profile_refs:
    simulation_profile_version: string
    simulation_family_version: string
    cost_model_version: string
    fee_model_version: string
    slippage_model_version: string
    horizon_family: string           # e.g., "swing_horizon", "scalp_horizon"
    stop_family: string              # e.g., "atr_wide", "atr_medium", "atr_tight"
    target_family: string            # e.g., "atr_wide", "atr_medium", "atr_tight"
    time_exit_family: string         # e.g., "hold_then_exit"
    invalidation_multiplier: number  # default 2.0

  # ── Entry Context ──
  entry_price: number                # canonical entry price (from state)
  atr: number                        # ATR value for stop/target sizing

  # ── Metadata ──
  metadata:
    adapter_kind: TRAINING | EVALUATION | REPLAY | PAPER | LIVE_OUTCOME
    entry_timing_annotation: optional
      # Metadata-only in first version. Must not silently shift entry_price.
    run_id: optional string           # External run ID for tracking
```

---

## SimulationOutput

The exit contract. Contains all comparative outcomes.

```yaml
SimulationOutput:
  # ── Identity ──
  simulation_run_id: string
  symbol: string
  decision_timestamp: utc_timestamp
  mode: SWING | SCALP | AGGRESSIVE_SCALP
  primary_interval: string

  # ── Resolution ──
  resolution_status: COMPLETE | UNRESOLVED | INVALIDATED
  invalidity_reason: optional string   # present only if INVALIDATED

  # ── Comparative Outcomes ──
  long_outcome: ActionOutcome
  short_outcome: ActionOutcome
  no_trade_outcome: NoTradeOutcome

  # ── Action Selection ──
  best_action: LONG_NOW | SHORT_NOW | NO_TRADE | AMBIGUOUS_STATE
  second_best_action: optional LONG_NOW | SHORT_NOW | NO_TRADE
  action_gap_r: number                # utility gap between best and second-best
  regret_r: number                    # regret relative to best action
  is_ambiguous: boolean               # true if action_gap_r < ambiguity_margin

  # ── Lineage ──
  lineage:
    simulation_family_version: string
    simulation_profile_version: string
    cost_model_version: string
    fee_model_version: string
    slippage_model_version: string
    horizon_family: string
    stop_family: string
    target_family: string
    time_exit_family: string
    adapter_kind: TRAINING | EVALUATION | REPLAY | PAPER | LIVE_OUTCOME

  # ── Optional MC Lineage ──
  monte_carlo_run_id: optional string  # present only for MC simulations
  monte_carlo_family_version: optional string
```

---

## ActionOutcome

Per-action (LONG_NOW or SHORT_NOW) path result.

```yaml
ActionOutcome:
  action: LONG_NOW | SHORT_NOW

  # ── Economic Result ──
  realized_r_gross: number            # gross R before fees/slippage
  realized_r_net: number              # net R after fees/slippage
  fee_cost_r: number                  # fee cost in R terms
  slippage_cost_r: number             # slippage cost in R terms
  total_cost_r: number                # fee_cost_r + slippage_cost_r

  # ── Exit ──
  exit_resolution: ExitResolution
  exit_price: number
  exit_bar_index: integer             # bar index within future_path
  hold_duration_bars: integer

  # ── Path Metrics ──
  path_metrics: PathMetrics

  # ── Action-Pair Comparisons ──
  # (included for downstream label deduplication)
  action_utility: number              # mode-weighted composite utility
```

## ExitResolution

```yaml
ExitResolution:
  exit_reason: STOP_HIT | TARGET_HIT | TIME_EXIT | HORIZON_END | UNRESOLVED | INVALIDATED
  stop_hit: boolean
  target_hit: boolean
  time_exit: boolean
  horizon_end: boolean
  stop_before_target: boolean         # stop triggered before target in same bar
  target_before_stop: boolean         # target triggered before stop in same bar
  same_candle_ambiguity: boolean      # stop and target both triggered in same bar
  ambiguous_resolution: string        # how ambiguity was resolved (e.g., "conservative_stop_first")
```

## NoTradeOutcome

```yaml
NoTradeOutcome:
  # ── Saved Loss ──
  # (How much loss was avoided by not taking the worst directional action)
  saved_loss_r: number               # max(0, -min(long_r_net, short_r_net))
  saved_loss_score: number           # 0–1 normalized

  # ── Missed Opportunity ──
  # (How much gain was missed by not taking the best directional action)
  missed_opportunity_r: number       # max(0, max(long_r_net, short_r_net))
  missed_opportunity_score: number   # 0–1 normalized

  # ── Quality ──
  no_trade_quality: CORRECT_NO_TRADE | SAVED_LOSS | MISSED_OPPORTUNITY | AMBIGUOUS_NO_TRADE
  was_correct_skip: boolean
```

## PathMetrics

```yaml
PathMetrics:
  mfe: number                        # maximum favourable excursion (price terms)
  mae: number                        # maximum adverse excursion (price terms)
  mfe_r: number                      # MFE in R terms
  mae_r: number                      # MAE in R terms (stored as negative or absolute per convention)
  time_to_mfe: integer               # bars from entry to MFE
  time_to_mae: integer               # bars from entry to MAE
  path_quality_score: number         # 0–1 composite (MFE/MAE ratio, smoothness, drawdown depth)
  path_quality_bucket: HIGH | MEDIUM | LOW
```

## SimulationProfile

Mode-specific configuration (by reference, not embedded in every input).

```yaml
SimulationProfile:
  profile_version: string
  mode: SWING | SCALP | AGGRESSIVE_SCALP
  primary_interval: string           # "4h", "1h", "15m"
  context_intervals: [string]        # ["1d", "1h"] for SWING, etc.
  refinement_intervals: [string]     # ["1h"] for SWING, etc.
  max_holding_bars: integer
  stop_method: string                # "atr_wide", "atr_medium", "atr_tight"
  stop_multiplier: number            # ATR multiplier
  target_method: string              # "atr_wide", "atr_medium", "atr_tight"
  target_multiplier: number          # ATR multiplier
  ambiguity_margin_r: number         # min gap to declare best action
  min_action_edge_r: number          # min edge to prefer directional over NO_TRADE
  mae_penalty_weight: number         # higher = MAE punished more in utility
  cost_penalty_weight: number        # higher = costs punished more in utility
  time_penalty_weight: number        # higher = time to MFE punished more in utility
  no_trade_default: boolean          # if true, NO_TRADE is default when ambiguous
```

## CostModelRef

```yaml
CostModelRef:
  cost_model_version: string
  fee_model_version: string
  slippage_model_version: string
  maker_fee_bps: number              # basis points
  taker_fee_bps: number
  slippage_bps: number               # base slippage in basis points
  slippage_volatility_adjust: boolean # whether slippage scales with volatility
  minimum_fee_quote: optional number  # minimum fee in quote currency
```

## SimulationLineage

```yaml
SimulationLineage:
  simulation_family_version: string
  simulation_profile_version: string
  cost_model_version: string
  fee_model_version: string
  slippage_model_version: string
  horizon_family: string
  stop_family: string
  target_family: string
  time_exit_family: string
  monte_carlo_family_version: optional string
  adapter_kind: TRAINING | EVALUATION | REPLAY | PAPER | LIVE_OUTCOME
```

## MonteCarloOutput

```yaml
MonteCarloOutput:
  monte_carlo_run_id: string
  monte_carlo_family_version: string
  base_simulation_run_id: string     # links to the realized simulation
  num_paths: integer                 # number of perturbed paths generated
  expected_r_distribution:
    mean: number
    std: number
    p5: number                      # 5th percentile
    p25: number
    p50: number
    p75: number
    p95: number
  downside_risk: number              # expected shortfall / CVaR
  target_before_stop_probability: number
  stop_before_target_probability: number
  tail_risk: number                  # worst-case beyond p5
  confidence_stability: number       # how stable the expected R is across paths
```

## Contract Versioning Policy

| Change | Version Bump |
|---|---|
| New optional field added | Minor (patch-level) |
| Field renamed or removed | Major |
| Field semantics changed | Major |
| New contract added | Minor |
| Contract removed | Major |

## Relationship to AlphaForge Label Schemas

AlphaForge label fields map directly from simulation output:

| AlphaForge Field | SimulationOutput Field |
|---|---|
| `long_R_net` | `long_outcome.realized_r_net` |
| `short_R_net` | `short_outcome.realized_r_net` |
| `best_action_label` | `best_action` |
| `label_validity` | Derived from `resolution_status` + `is_ambiguous` |
| `saved_loss_score` | `no_trade_outcome.saved_loss_score` |
| `missed_opportunity_score` | `no_trade_outcome.missed_opportunity_score` |
| `path_quality_score` | `long_outcome.path_metrics.path_quality_score` or `short_outcome.path_metrics.path_quality_score` (for the best action) |
| `gap_R` | `action_gap_r` |

## Relationship to V7 TradeOutcome

V7 TradeOutcome fields map from simulation output:

| TradeOutcome Field | SimulationOutput Field |
|---|---|
| `realized_outcome.realized_r` | `best_action` outcome `realized_r_net` |
| `realized_outcome.fees_paid` | Best action `fee_cost_r` + `slippage_cost_r` |
| `realized_outcome.exit_reason` | Best action `exit_resolution.exit_reason` |
| `path_metrics.mfe_r` | Best action `path_metrics.mfe_r` |
| `path_metrics.mae_r` | Best action `path_metrics.mae_r` |
| `comparative_outcome.counterfactual_best_action` | `best_action` |
| `comparative_outcome.regret_r` | `regret_r` |
| `observability.horizon_family` | `lineage.horizon_family` |

---

## Document Authority

**Canonical hub:** [ai_summary.md](ai_summary.md) — read this first for the full system synthesis and table of contents.

**Related docs for this topic:**

| [architecture.md](architecture.md) | Where contracts fit in the component design |
| [profiles.md](profiles.md) | SimulationProfile and CostModelRef schemas |
| [no_trade_quality.md](no_trade_quality.md) | NoTradeOutcome and quality classifications |
| [lineage_and_versioning.md](lineage_and_versioning.md) | Version fields used in all contracts |
    
**Parent:** [../README.md](../README.md) — authority overview and ownership diagram.

**For implementation:** See [phases/](phases/) for v4.1.1 phase plans S0–S6.

**For validation:** See [validation.md](validation.md) for required test gates.

