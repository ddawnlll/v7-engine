# V7 Architecture

## Purpose

This document defines the system architecture for **V7**.

It explains how V7 is structured end to end, how data and decisions flow through the system, which parts are authoritative, which parts are platform-specific, and which architectural rules must remain true as the implementation grows.

This is an **architecture document**, not a low-level implementation spec.
It defines the stable system shape and the relationships between the major components.

This document is written primarily for **LLM code agents and AI-assisted engineering workflows**.
It therefore prioritizes:

* explicit ownership boundaries
* low repetition
* dense constraints
* modularity rules
* configuration rules
* stable vs replaceable component clarity

---

## Architectural Summary

V7 is a **centralized, simulation-native, contract-first trading engine** built around one economic truth layer.

The system is designed around the following idea:

**one market-state pipeline**
→ **one simulation truth layer**
→ **one label/evaluation language**
→ **one decision engine**
→ **one explicit policy layer**
→ **one runtime integration boundary**

The architecture is intentionally smaller and more centralized than V6.

---

## Primary Architectural Goal

The architecture exists to optimize the following, in order:

1. economic quality
2. simulation consistency
3. calibration reliability
4. multi-symbol operational clarity
5. editability and implementation speed
6. centralized configuration simplicity

The architecture is not optimized for maximum subsystem richness.
It is optimized for producing a system that is economically honest, easier to reason about, faster to improve, and cheaper to modify.

---

## Core Architectural Rules

### 1. One simulation truth layer

The same simulation logic defines:

* label generation
* forward evaluation
* trade outcome interpretation
* cost-aware trade resolution

There must not be separate semantics for labeling and backtesting.

### 2. One canonical market-state language

Live inference, replay, dataset generation, and evaluation must all use the same snapshot/state language.

### 3. One explicit contract boundary

The runtime and the engine interact only through explicit contracts:

* `AnalysisRequest`
* `AnalysisResult`
* `DecisionEvent`
* `TradeOutcome`

### 4. One primary codebase

V7 uses one primary Python codebase.
Platform differences are handled at the compute backend and deployment level, not by forking the system logic.

### 5. One primary baseline model family

The first V7 implementation uses **XGBoost** as the primary model family.
This is a deliberate architectural choice for speed, simplicity, portability, and economic iteration.

### 6. One concern, one primary module

Each concern should have one primary implementation module.

Examples:

* simulation → one simulation module family
* labels → one label module family
* features → one feature module family
* thresholds → one policy module family
* evaluation → one evaluation module family

A change in one concern should not require a system-wide rewrite.

### 7. One central configuration root

V7 must have one authoritative configuration loader and one centralized configuration root.
Sub-configs may be modular, but behavior must not be scattered across hidden operational surfaces.

---

## Modularity and Configuration Principles

This section is a hard architectural constraint.

### Modularity rule

A change in one concern should ideally require editing:

* one primary module
* one config surface
* one test surface

not five subsystems.

### Replaceable internals rule

V7 internals should be replaceable behind stable contracts.

That means:

* contracts remain stable longer than implementation modules
* model family can change without redesigning runtime
* label policy can evolve without rewriting event semantics
* threshold policy can evolve without breaking request/result contracts

### Configuration rule

V7 must be centrally configurable.

This means:

* one authoritative config loader
* modular sub-configs by concern
* no hidden config mutation through ad hoc scripts
* no behavior controlled only by shell wrappers or local hacks
* no second orchestration system becoming the real source of truth

### CLI rule

V7 must be **CLI-first**, not Makefile-first.

This means:

* one primary Python CLI entrypoint
* one standard invocation path for research and operations
* helper scripts may exist, but they do not define the system

### AI-editability rule

The architecture must be easy for LLM code agents to modify safely.

That means:

* local changes should stay local
* constraints must be explicit
* stable and unstable surfaces must be obvious
* documents and modules should be easy to map one-to-one

---

## Top-Level System Shape

V7 has eight top-level architectural layers:

1. **Raw market data layer**
2. **State construction layer**
3. **Simulation and outcome layer**
4. **Label and feature layer**
5. **Dataset and split layer**
6. **Model and calibration layer**
7. **Decision policy layer**
8. **Runtime and lifecycle layer**

These layers are described below.

---

## 1. Raw Market Data Layer

This layer is responsible for acquiring and storing canonical raw market data.

### Responsibilities

* download raw candles from Binance
* store canonical raw history
* validate structural integrity
* detect gaps, duplicates, and invalid rows
* expose consistent access to historical windows

### Inputs

* Binance kline data

### Outputs

* canonical raw candle storage
* raw data quality reports

### Rules

* raw data is stored as source-of-truth history
* no external indicator feeds are downloaded
* no derived features are stored as source-of-truth market input
* missing or corrupted history is flagged explicitly
* raw data logic stays isolated from feature logic

### Initial data scope

The first V7 scope assumes:

* Binance raw candles
* primary decision interval: `4h`
* higher-timeframe context: `1d`
* first-phase refinement/timing context: `1h`
* one shared interval-aware, multi-view model family (no separate primary model families per interval)
* no averaged interval outputs; a single atomic request provides one unified decision surface
* 60-symbol design target

The first implementation may stage rollout on fewer symbols, but the architecture must be built for 60-symbol operation from the start.

---

## 2. State Construction Layer

This layer builds the canonical market state used everywhere in V7.

### Responsibilities

* construct the canonical snapshot/state object for one market state
* compute derived local state from raw candles
* attach regime, volatility, and quality metadata
* expose identical state semantics to live, replay, training, and evaluation

### Inputs

* raw candles
* system configuration
* optional runtime execution context

### Outputs

* canonical market state / snapshot

### State contents

The canonical market state includes:

* recent raw candle windows
* higher-timeframe context
* derived local state
* volatility and regime context
* data-quality and freshness metadata
* symbol and interval identity
* optional runtime execution context

### Rules

* state construction must be deterministic for the same input history
* live and replay must use the same builder logic
* deterministic annotations may exist as context, but they are not the source of truth
* adding a new state feature should be a local change in the state/feature layer, not a runtime rewrite

---

## 3. Simulation and Outcome Layer

This is the most important layer in V7.

It is the system’s economic truth layer.

### Responsibilities

* simulate long / short / no-trade outcomes from a candidate state
* apply cost-aware trade semantics
* resolve stop / target / time-exit behavior
* compute realized and comparative action quality
* produce normalized outcome records

### Inputs

* canonical market states
* future candle path
* cost model
* stop / target / horizon policy

### Outputs

* simulated action outcomes
* normalized trade-outcome records
* economic-quality metrics

### Core rule

There is only **one simulation engine**, treated as a shared core truth module.

That same engine is used for:

* label generation
* out-of-sample forward evaluation
* runtime paper trading (which is forward simulation)
* historical replay (using the same core under a replay driver)
* production-side outcome normalization

Simulation should be profile/adaptor-friendly for V6 and V7 inputs. Runtime consumes this simulation core; runtime does not own simulation truth semantics.

### Economic semantics

This layer computes:

* realized return
* realized R
* fees paid
* slippage cost
* hold duration
* MFE / MAE
* path quality
* counterfactual best action
* regret and missed-opportunity measures

### Rules

* cost modeling must be explicit
* stop/target/time-exit semantics must be versioned
* labeling and evaluation must share identical semantics
* no separate backtesting truth is allowed
* simulation rule changes should be localized to the simulation layer and versioned clearly

---

## 4. Label and Feature Layer

This layer transforms simulated and state information into model-ready training data.

### Responsibilities

* generate action-comparative labels
* generate label quality flags
* compute model feature columns from state
* keep feature generation modular and minimal

### Labeling approach

V7 uses **action-comparative, net-cost labels**.

For each candidate state, V7 compares:

* `LONG_NOW`
* `SHORT_NOW`
* `NO_TRADE`

under the same simulation semantics.

The primary question is:

> Which action produced the best net economic outcome under the same cost-aware simulation rules?

### Primary labels

The initial architecture assumes the following label families:

* `best_action_label`
* `best_action_r`
* `second_best_action`
* `action_gap_r`
* `path_quality_label`
* `outcome_quality_label`
* `label_quality`
* `is_ambiguous`
* `is_good_no_trade`

### Feature approach

The first V7 implementation is **XGBoost-first**, so the feature layer is explicit and modular.

Feature families may include:

* price returns and momentum
* volatility and range structure
* volume and participation features
* higher-timeframe alignment features
* symbol-aware metadata features
* regime and transition features
* data-quality flags where appropriate

### Rules

* labels are market-first, not legacy-engine-first
* labels are cost-aware
* features are derived locally
* feature generation is modular and easily extensible
* adding a new feature should require minimal architectural change
* adding a new label family should remain a local change inside the labeling layer plus config and tests

---

## 5. Dataset and Split Layer

This layer assembles trainable datasets and temporal evaluation splits.

### Responsibilities

* build datasets from states, labels, and features
* apply quality filters and weighting
* build temporal train / validation / test partitions
* support walk-forward evaluation
* produce dataset manifests and dataset reports

### Inputs

* canonical states
* labels
* features

### Outputs

* train/validation/test datasets
* walk-forward fold definitions
* dataset metadata and reports

### Rules

* time order is never violated
* no random split is used for the primary trading evaluation path
* walk-forward or future-relative evaluation is required
* label quality and data quality can influence sample inclusion or weights
* split behavior must remain config-driven, not hardcoded across many modules

### Initial split posture

The architecture supports:

* temporal train / validation / test splits
* expanding-window walk-forward evaluation
* future-relative holdouts

---

## 6. Model and Calibration Layer

This layer trains the learned decision engine.

### Primary model family

The initial V7 model family is:

* **XGBoost**

This is a deliberate design choice.

### Why XGBoost-first

* fast iteration
* strong tabular baseline
* simpler production behavior
* portable artifacts across Linux ROCm and macOS CPU
* lower implementation and debugging complexity
* easier alignment with explicit features and explicit policy

### Responsibilities

* train model artifacts
* score long / short / no-trade decisions
* export portable model artifacts
* support CPU and ROCm-based execution paths where appropriate
* fit and apply calibration

### Calibration

Calibration is a first-class structural component.

The model layer must support:

* calibrated decision outputs
* symbol-aware calibration where justified
* regime-aware calibration where justified
* calibration diagnostics and reliability reporting

### Rules

* thresholds operate on calibrated scores, not raw scores
* artifacts must be portable across supported platforms
* feature schema and model artifact versioning are mandatory
* calibration quality is part of model readiness, not a later optional add-on
* model family changes must not require rewriting the rest of the architecture

---

## 7. Decision Policy Layer

This layer turns calibrated scores into actual economic decisions.

### Responsibilities

* apply explicit thresholds
* compare long / short / no-trade outputs
* enforce decision margins
* enforce edge filters
* enforce risk and exposure filters
* prepare execution-relevant recommendations

### Initial policy shape

The first V7 policy should remain simple and explicit.

Typical decision gates include:

* `long_threshold`
* `short_threshold`
* `no_trade_threshold`
* `decision_margin`
* `minimum_edge`
* optional regime filters
* optional cooldown or exposure constraints

### Portfolio-aware controls

Because V7 is designed for 60-symbol operation, the policy layer must eventually support:

* cross-symbol correlation awareness
* cluster exposure limits
* drawdown budget awareness
* no-trade preference in low-edge or high-risk environments

### Rules

* policy remains explicit and reviewable
* policy is simpler than V6 selector-heavy logic
* hidden selector complexity is avoided unless it shows clear economic benefit
* calibrated reliability is more important than raw score magnitude
* policy changes should be local to the policy layer plus config and tests

---

## 8. Runtime and Lifecycle Layer

This layer integrates V7 into the operational system.

### Responsibilities

* assemble requests
* run model inference
* produce typed results
* record decision events
* record and later resolve trade outcomes
* manage artifacts, promotion, rollback, and health

### Runtime role

Runtime remains the operational shell.
It still owns:

* scheduling
* orchestration
* persistence
* execution control
* fallback safety
* operator interfaces

### Engine role

The engine owns:

* market-state interpretation
* calibrated action scoring
* uncertainty-aware output
* action recommendation

### Rules

* runtime and engine remain separated
* no hidden fallback is allowed
* degraded behavior is explicit
* contract fields remain versioned and visible
* `DecisionEvent` and `TradeOutcome` remain first-class lifecycle objects
* runtime orchestration must not become the hidden source of configuration truth

---

## Platform Support Architecture

V7 must support multiple platforms without fragmenting the system logic.

### Supported platform roles

#### 1. Linux + ROCm AMD GPU

This is the **authoritative training and benchmark platform**.

Use cases:

* primary model training
* heavy inference benchmarking
* authoritative performance and promotion evidence
* GPU-accelerated experimentation where supported

#### 2. macOS + CPU

This is a **first-class development and inference platform**.

Use cases:

* local development
* debugging
* simulation and dataset building
* local model training where practical
* artifact loading and inference validation

#### 3. Android + CPU

This is an **optional future inference-only deployment target**.

Use cases:

* thin client inference consumption
* lightweight local signal evaluation if later required

It is not part of the first V7 core implementation.

### Platform rules

* Linux + ROCm defines the authoritative benchmark and final training environment
* macOS must support the full core pipeline on CPU
* artifacts must be portable across Linux ROCm and macOS CPU
* core business logic remains platform-agnostic
* only compute backend and deployment surfaces vary by platform

---

## Model Portability Rule

The system must support cross-platform model artifact usage.

### Required portability behavior

* a model trained on Linux ROCm must be loadable on macOS CPU
* feature schema must remain identical across platforms
* artifact formats must use portable model serialization
* platform-specific Python pickling is not considered a portable artifact strategy

### Initial implication

The XGBoost-first architecture is preferred partly because it simplifies this portability story.

---

## Inference Topology

V7 is designed for centralized multi-symbol operation.

### Long-term inference posture

Where practical, inference should support batched multi-symbol processing rather than treating the system as many disconnected single-symbol engines.

### Initial implementation posture

The initial contract may still evaluate one market state per request, but the architecture must remain consistent with a centralized multi-symbol research and execution worldview.

This means:

* symbol-aware evaluation
* centralized reporting
* cross-symbol risk controls
* no design assumptions that prevent future batching

---

## Components That Remain From V6

V7 keeps the following architectural ideas from V6:

* explicit runtime–engine contract boundary
* request / result / event / outcome separation
* market-first labeling principle
* live/replay parity requirement
* no-trade as a first-class action
* explicit fallback visibility
* validation and promotion discipline
* no silent deterministic veto

These remain correct.

---

## Components V7 Reduces or Removes

V7 deliberately reduces or removes the following V6 tendencies:

* transition-heavy V4 + V5 + V6 structural stacking
* selector-heavy threshold logic
* excessive operator-surface complexity as a substitute for economic clarity
* confidence-first reasoning without structural calibration alignment
* architecture sprawl that slows research and implementation
* feature and policy changes that require wide system edits
* configuration scattered across multiple operational layers

---

## Authoritative Truth Hierarchy

When V7 components disagree, the truth hierarchy is:

1. **simulation truth**
2. **market outcome truth**
3. **contract truth**
4. **runtime interpretation truth**
5. **model score explanation**

This hierarchy matters.

The model does not define truth by itself.
The simulation and realized outcome layer define truth.

---

## Repository Design Direction

The implementation should remain centralized and small.

The repository should be organized around:

* one core config path
* one CLI entrypoint
* one data path
* one simulation engine
* one label path
* one feature path
* one dataset path
* one model path
* one evaluation path

The system should not require many overlapping orchestration surfaces.

### Recommended configuration shape

V7 should use:

* one authoritative config loader
* one merged runtime config object
* modular config files by concern

Examples of concern boundaries:

* base/system
* symbols and universe
* simulation
* labels
* features
* model
* policy
* evaluation

The architecture should support modular config files without losing one central source of truth.

---

## Documentation Philosophy

V7 should avoid document sprawl.

The architecture must be understandable from a small set of central files:

* `vision.md`
* `architecture.md`
* `contracts.md`
* `ai_summary.md`
* `simulation.md`
* `model_policy.md`
* `roadmap.md`
* `llm_rules.md`

Everything else should remain implementation detail or generated operational output unless genuinely necessary.

### AI-first documentation rule

Documents should be written so that LLM code agents can:

* extract constraints quickly
* identify ownership quickly
* identify stable interfaces quickly
* avoid making forbidden changes

This means architecture documents should prefer:

* explicit lists
* short sections
* low narrative repetition
* high constraint density

---

## Immediate Next Architectural Steps

After this document is accepted, the next architectural documents should define:

1. `contracts.md`
2. `ai_summary.md`
3. `simulation.md`
4. `model_policy.md`
5. `roadmap.md`
6. `llm_rules.md`

After those are done, implementation should begin with:

* config
* CLI
* raw data ingestion
* raw data validation
* snapshot builder
* simulation engine
* label generation
* feature generation
* dataset assembly
* XGBoost baseline training
* calibration
* decision policy
* forward evaluation

---

## Bottom Line

The V7 architecture is intentionally simple at its core:

**raw market data**
→ **canonical market state**
→ **unified simulation truth**
→ **action-comparative labels and explicit features**
→ **temporal datasets**
→ **XGBoost-first calibrated model**
→ **explicit decision policy**
→ **runtime integration through stable contracts**

This architecture exists for one reason:

**to make economic truth central, system behavior explicit, configuration centralized, and iteration speed high enough that V7 can improve faster than V6 without repeating V6’s structural drag.**
