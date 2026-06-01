# V7 Architecture — Mode-Centric System

## Purpose

This document defines the revised V7 system architecture.

V7 is a **mode-centric**, centralized, simulation-native, contract-first trading system built around one economic truth layer and **three independent mode-specific hybrid supervised decision pipelines** (SWING, SCALP, AGGRESSIVE_SCALP).

The architecture is optimized for:

1. economic quality
2. simulation consistency
3. calibration reliability
4. multi-symbol clarity
5. editability
6. centralized configuration
7. **mode-aware regime adaptability**

---

## Architectural Summary

```text
Market Data → Mode Router → 3 Independent Pipelines
                  ↓
            ┌─────┴─────┐
            ↓           ↓
       SWING        SCALP         AGGRESSIVE_SCALP
       mode         mode          mode
            ↓           ↓           ↓
       [4h + 1d]    [1h + 4h]     [15m + 1h]
       sim_config   sim_config    sim_config
       labels       labels        labels
       model        model         model
       policy       policy        policy
       regime       regime        regime
```

Each mode pipeline is an independent instance of the same architecture:

```text
one market-state pipeline (shared)
→ one simulation truth layer (mode-configured)
→ one mode-specific label/evaluation language
→ one mode-specific hybrid supervised model
→ one explicit policy layer (regime-aware)
→ one portfolio layer (shared)
→ one risk gate (shared)
→ one runtime boundary (mode-routed)
```

The first learned model is not pure classification and not pure regression.

It is a **classification-first hybrid profitability model**:

- classification heads estimate action suitability
- regression heads estimate economic quality
- calibration makes the model outputs operationally safer
- policy combines those surfaces into one final recommendation

---

## Core Architectural Rules

### 1. One simulation truth layer (mode-configured)

The same simulation logic defines labels, replay evaluation, paper/live outcome interpretation, no-trade quality, regret, and cost-aware trade resolution — but with **mode-specific parameters** (primary timeframe, holding horizon, stop/target multipliers).

### 2. One canonical market-state language

Live inference, replay, dataset generation, and evaluation use the same state language. Features are **shared across modes**, built from canonical state.

### 3. One explicit contract family

Runtime and engine communicate through:

- `AnalysisRequest` (carries `requested_trade_mode` / `model_scope`)
- `AnalysisResult`
- `DecisionEvent`
- `TradeOutcome`

### 4. One primary model family first (per mode)

First phase is **XGBoost-first** for speed, portability, tabular strength, and transparent iteration. Each mode trains its own artifact bundle.

### 5. Hybrid model outputs are first-class

Each mode artifact must expose both:

- action probability / classification surfaces
- expected economic quality / regression surfaces

### 6. Runtime is not the model

Runtime owns orchestration, persistence, safety, fallback, and execution eligibility. The model produces decision evidence, not operational permission.

### 7. One central configuration root

All behavior must route through the unified config system. Mode-specific configs are nested under `simulation_configs.{swing,scalp,aggressive_scalp}`.

### 8. Features are shared across modes

Canonical state → features. Features are identical for all modes. Labels are **mode-specific**.

### 9. Regime awareness

Every mode integrates a rule-based regime detector. Regime modifies policy thresholds and stop/target behavior.

---

## Top-Level Layers

1. raw market data
2. canonical state construction
3. **mode router** → simulation and outcome truth (per mode)
4. **mode-specific** labels and shared features
5. **mode-specific** dataset and split
6. **mode-specific** hybrid model and calibration
7. **regime-aware** decision policy
8. portfolio interpretation (shared, correlation-aware)
9. risk gating
10. runtime lifecycle
11. evaluation and monitoring (mode-aware)

---

## 1. Raw Market Data

Responsibilities:

- acquire raw candle history
- store canonical raw history
- validate gaps, duplicates, corruption, and timestamp order
- expose consistent historical windows

First-phase assumptions:

- Binance candles
- **SWING mode:** primary 4h, context 1d, refinement 1h
- **SCALP mode:** primary 1h, context 4h, refinement 15m
- **AGGRESSIVE_SCALP mode:** primary 15m, context 1h, refinement 5m
- target universe: up to 60 symbols

Rules:

- raw data remains source-of-truth history
- no derived features are stored as raw truth
- missing/corrupted history is explicit

---

## 2. Canonical State Construction

Responsibilities:

- build one canonical state for one symbol and decision timestamp
- attach multiple interval views (4h, 1h, 15m primary + context + refinement per mode)
- attach volatility, regime, symbol metadata, quality, and freshness metadata
- provide identical semantics to live, replay, dataset, and evaluation

Rules:

- deterministic for the same input
- no future bars
- no runtime-only hidden side channel
- missingness is explicit

---

## 3. Simulation and Outcome Truth (Mode-Specific)

**⚠️ Simulation truth semantics now live in the top-level `/simulation` authority.**

See:
- `/simulation/docs/architecture.md` — component design and data flow
- `/simulation/docs/contracts.md` — SimulationInput, SimulationOutput contracts
- `/simulation/docs/profiles.md` — mode-specific profiles
- `/simulation/docs/ai_summary.md` — machine-readable synthesis

The `/simulation` engine compares `LONG_NOW`, `SHORT_NOW`, and `NO_TRADE` for the same state and future path under mode-specific stop, target, horizon, fee, and slippage semantics.

Rules:

- one simulation engine (mode-configured), owned by `/simulation`
- V7 runtime hosts/executes simulation operationally through stable contracts
- labels and evaluation share semantics
- no unresolved simulation becomes a final training label
- simulation-family version changes when meaning changes

---

## 4. Labels and Features

**Labels are mode-specific.** The same timestamp produces different label truths for SWING, SCALP, and AGGRESSIVE_SCALP.

Classification labels answer:

> Which action is preferable for this mode?

Regression labels answer:

> How profitable, risky, or costly is the action for this mode?

**Features are shared across modes** — derived from canonical state only.

Rules:

- no future leakage
- explicit feature schema versioning
- explicit label interpretation versioning
- compact, interpretable first-phase features
- shared multi-symbol model bias per mode

---

## 5. Dataset and Split

Datasets are temporal, lineage-preserving, and **mode-specific**.

Rows contain:

- symbol
- **mode** (SWING | SCALP | AGGRESSIVE_SCALP)
- primary interval
- timestamp
- feature vector (shared)
- classification targets (mode-specific)
- regression targets (mode-specific)
- simulation lineage
- label lineage
- feature schema lineage

Rules:

- no random IID primary split
- walk-forward evaluation first
- unresolved or invalid labels excluded by default
- ambiguous rows are explicitly handled
- symbol weighting prevents silent dominance

---

## 6. Hybrid Model and Calibration (Per Mode)

The first-phase learned system is **per mode**:

> **XGBoost-first hybrid supervised model per mode scope**

Recommended artifact shape (per mode):

```text
shared feature matrix
    ├── classification surfaces
    │   ├── P(LONG_NOW)
    │   ├── P(SHORT_NOW)
    │   └── P(NO_TRADE)
    └── regression surfaces
        ├── E[R | LONG_NOW]
        ├── E[R | SHORT_NOW]
        ├── expected adverse pressure / drawdown
        └── cost-adjusted expectancy
```

Calibration then maps raw classification scores into reliable probability/confidence surfaces (per mode).

Rules:

- XGBoost classifiers and regressors are both allowed
- raw scores are not runtime confidence
- regression heads are economic evidence, not direct execution permission
- model family can change without rewriting runtime contracts
- **do not train one artifact across incompatible modes**

---

## 7. Decision Policy (Regime-Aware)

Policy turns calibrated and economic surfaces into a normalized decision.

A directional action must pass:

- probability/confidence gate
- no-trade comparison gate
- expected-R gate
- cost-adjusted expectancy gate
- adverse-pressure/drawdown gate
- decision-margin gate
- **regime consistency gate**

If the evidence is weak, contradictory, degraded, or ambiguous, policy selects `NO_TRADE` explicitly.

**Regime modifiers** (section 5.4 of mode-centric doc) adjust confidence thresholds and directional bias based on detected market regime.

---

## 8. Portfolio Interpretation (Correlation-Aware)

Portfolio handles cross-symbol competition after single-candidate policy outputs exist.

It may:

- pass
- suppress
- down-rank
- annotate

First phase stays lightweight. It is not a full optimizer.

**Correlation-aware controls** (section 6.7 of mode-centric doc) prevent cluster overexposure.

Rules:

- portfolio is not model training
- no hidden portfolio veto
- concentration and cluster controls are explicit

---

## 9. Risk Gate

Risk is the final safety layer before execution eligibility.

It handles:

- kill switch
- exposure hard limits
- duplicate protection
- cooldowns
- stale/degraded result handling

Rules:

- hard guards stay hard
- model confidence cannot override operational safety
- risk blocks must be visible in lifecycle records

---

## 10. Runtime Lifecycle (Mode-Routed)

Runtime owns:

- request assembly (with `requested_trade_mode` / `model_scope`)
- **mode routing** → load scope-compatible artifact bundle
- result validation
- event creation
- execution eligibility
- persistence
- outcome lifecycle
- fallback visibility
- rollback and operational safety

Engine owns (per mode):

- hybrid model scoring
- calibrated decision evidence
- expected-R surfaces
- recommended action
- timing guidance
- degradation visibility

---

## Truth Hierarchy

When components disagree, the hierarchy is:

1. simulation truth
2. realized market outcome truth
3. contract truth
4. runtime interpretation truth
5. model explanation

The model does not define truth by itself.

---

## Bottom Line

V7 is mode-centric but intentionally simple at the system level:

```text
raw data
→ canonical state
→ mode router
  → SWING:     sim truth → labels → dataset → model → calibration → policy → portfolio → risk → runtime
  → SCALP:     sim truth → labels → dataset → model → calibration → policy → portfolio → risk → runtime
  → AGGRESSIVE_SCALP: sim truth → labels → dataset → model → calibration → policy → portfolio → risk → runtime
```

The purpose is to make economic truth central, behavior explicit, mode-aware, and iteration fast without repeating V6's structural drag.
