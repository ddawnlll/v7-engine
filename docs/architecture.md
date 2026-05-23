# V7 Architecture

## Purpose

This document defines the revised V7 system architecture.

V7 is a centralized, simulation-native, contract-first trading system built around one economic truth layer and one hybrid supervised decision engine.

The architecture is optimized for:

1. economic quality
2. simulation consistency
3. calibration reliability
4. multi-symbol clarity
5. editability
6. centralized configuration

---

## Architectural Summary

```text
one market-state pipeline
→ one simulation truth layer
→ one label/evaluation language
→ one hybrid supervised model
→ one explicit policy layer
→ one portfolio layer
→ one risk gate
→ one runtime boundary
```

The first learned model is not pure classification and not pure regression.

It is a **classification-first hybrid profitability model**:

- classification heads estimate action suitability
- regression heads estimate economic quality
- calibration makes the model outputs operationally safer
- policy combines those surfaces into one final recommendation

---

## Core Architectural Rules

### 1. One simulation truth layer

The same simulation logic defines labels, replay evaluation, paper/live outcome interpretation, no-trade quality, regret, and cost-aware trade resolution.

### 2. One canonical market-state language

Live inference, replay, dataset generation, and evaluation use the same state language.

### 3. One explicit contract family

Runtime and engine communicate through:

- `AnalysisRequest`
- `AnalysisResult`
- `DecisionEvent`
- `TradeOutcome`

### 4. One primary model family first

First phase is **XGBoost-first** for speed, portability, tabular strength, and transparent iteration.

### 5. Hybrid model outputs are first-class

The model artifact must expose both:

- action probability / classification surfaces
- expected economic quality / regression surfaces

### 6. Runtime is not the model

Runtime owns orchestration, persistence, safety, fallback, and execution eligibility. The model produces decision evidence, not operational permission.

### 7. One central configuration root

All behavior must route through the unified config system. No hidden shell-script semantics or local config mutation should become the real authority.

---

## Top-Level Layers

1. raw market data
2. canonical state construction
3. simulation and outcome truth
4. labels and features
5. dataset and split
6. hybrid model and calibration
7. decision policy
8. portfolio interpretation
9. risk gating
10. runtime lifecycle
11. evaluation and monitoring

---

## 1. Raw Market Data

Responsibilities:

- acquire raw candle history
- store canonical raw history
- validate gaps, duplicates, corruption, and timestamp order
- expose consistent historical windows

First-phase assumptions:

- Binance candles
- primary decision interval: 4h
- higher-timeframe context: 1d
- refinement/timing context: 1h
- target universe: up to 60 symbols

Rules:

- raw data remains source-of-truth history
- no derived features are stored as raw truth
- missing/corrupted history is explicit

---

## 2. Canonical State Construction

Responsibilities:

- build one canonical state for one symbol and decision timestamp
- attach 4h primary, 1d context, and 1h refinement views
- attach volatility, regime, symbol metadata, quality, and freshness metadata
- provide identical semantics to live, replay, dataset, and evaluation

Rules:

- deterministic for the same input
- no future bars
- no runtime-only hidden side channel
- missingness is explicit

---

## 3. Simulation and Outcome Truth

Simulation is the economic truth core.

It compares:

- `LONG_NOW`
- `SHORT_NOW`
- `NO_TRADE`

for the same state and future path under the same stop, target, horizon, fee, and slippage semantics.

It computes:

- realized R
- fee/slippage adjusted R
- MFE / MAE
- path quality
- regret
- saved-loss and missed-opportunity scores
- resolution status

Rules:

- one simulation engine
- labels and evaluation share semantics
- no unresolved simulation becomes a final training label
- simulation-family version changes when meaning changes

---

## 4. Labels and Features

Labels are derived from simulation truth.

Classification labels answer:

> Which action is preferable?

Regression labels answer:

> How profitable, risky, or costly is the action?

Features are derived from canonical state only.

Rules:

- no future leakage
- explicit feature schema versioning
- explicit label interpretation versioning
- compact, interpretable first-phase features
- shared multi-symbol model bias

---

## 5. Dataset and Split

Datasets are temporal and lineage-preserving.

Rows contain:

- symbol
- primary interval
- timestamp
- feature vector
- classification targets
- regression targets
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

## 6. Hybrid Model and Calibration

The first-phase learned system is:

> **XGBoost-first hybrid supervised model**

Recommended artifact shape:

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

Calibration then maps raw classification scores into reliable probability/confidence surfaces.

Rules:

- XGBoost classifiers and regressors are both allowed
- raw scores are not runtime confidence
- regression heads are economic evidence, not direct execution permission
- model family can change without rewriting runtime contracts

---

## 7. Decision Policy

Policy turns calibrated and economic surfaces into a normalized decision.

A directional action must pass:

- probability/confidence gate
- no-trade comparison gate
- expected-R gate
- cost-adjusted expectancy gate
- adverse-pressure/drawdown gate
- decision-margin gate

If the evidence is weak, contradictory, degraded, or ambiguous, policy selects `NO_TRADE` explicitly.

---

## 8. Portfolio Interpretation

Portfolio handles cross-symbol competition after single-candidate policy outputs exist.

It may:

- pass
- suppress
- down-rank
- annotate

First phase stays lightweight. It is not a full optimizer.

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

## 10. Runtime Lifecycle

Runtime owns:

- request assembly
- result validation
- event creation
- execution eligibility
- persistence
- outcome lifecycle
- fallback visibility
- rollback and operational safety

Engine owns:

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

V7 is intentionally simple at the system level:

```text
raw data
→ canonical state
→ simulation truth
→ labels/features
→ temporal dataset
→ XGBoost-first hybrid model
→ calibration
→ policy
→ portfolio
→ risk
→ runtime contracts
```

The purpose is to make economic truth central, behavior explicit, and iteration fast without repeating V6's structural drag.
