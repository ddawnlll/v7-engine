# V7 Vision

## Purpose

This document defines the architectural vision for **V7**.

V7 is the next-generation trading engine intended to replace the transition-heavy intelligence stack with a more centralized, economically honest, simulation-native, and rapidly editable learned system.

This is a **vision document**, not an implementation spec.
It defines what V7 is, why it exists, what success means, what design principles must guide it, and what V7 will deliberately do differently from V6.

---

## One-Sentence Definition

**V7 is a centralized, market-first, simulation-native learned trading engine that optimizes economic quality first, uses calibrated decision outputs, and evaluates long / short / no-trade actions through one unified forward-simulation truth layer.**

---

## Why V7 Exists

V6 established several important foundations:

* explicit runtime–engine contracts
* market-first labeling direction
* unified snapshot thinking
* walk-forward evaluation discipline
* decision and outcome normalization
* validation, verification, and rollback discipline

Those foundations were valuable.

But V6 also accumulated structural costs:

* transition architecture debt across V4, V5, and V6
* excessive selector and workflow complexity
* calibration that became operationally important without being structurally central
* backtesting and labeling logic that were not tightly unified enough
* economic quality that did not improve enough relative to system complexity
* a single-state mental model that did not align well with a 60-symbol centralized engine goal
* excessive change surface for routine edits and reconfiguration
* too many places to touch when changing one concern

V7 exists to keep the right foundations while removing the wrong weight.

V7 is not an iteration whose main goal is to become more elaborate.
V7 exists to become more **economically correct**, more **predictable**, more **centralized**, more **editable**, and more **configuration-simple**.

---

## Primary Goal

The primary goal of V7 is:

**to produce fewer, higher-quality trading decisions with stronger out-of-sample economic performance under realistic simulation and execution costs.**

This means:

* fewer but better trades
* stronger no-trade discipline
* higher expectancy R
* better calibration
* more stable behavior across symbols and regimes
* simpler system behavior that is easier to reason about and improve
* lower edit cost for common research changes

---

## Success Definition

V7 is not successful because it is newer, larger, or more technically ambitious.

V7 is successful only if it improves **economic trading quality** under realistic operating conditions **and** remains fast to modify, reconfigure, and evaluate.

### Primary success metrics

1. **Expectancy R**

   * average realized R per executed trade across out-of-sample forward simulation

2. **Risk-adjusted return**

   * expectancy and return quality under drawdown constraints

3. **No-trade quality**

   * the system correctly avoids low-quality and ambiguous states

4. **Calibration quality**

   * model scores reflect actual outcome quality and remain usable for decision thresholds

### Secondary success metrics

5. **Symbol consistency**

   * performance is not carried by only one or two symbols

6. **Regime consistency**

   * performance does not collapse outside one favored regime

7. **Operational predictability**

   * the system behaves in a stable, explainable, and auditable way

8. **Editability and iteration speed**

   * changing a feature, label rule, threshold policy, or evaluation metric should be a local change rather than a system-wide rewrite

9. **Configuration simplicity**

   * system behavior should be controlled through one centralized configuration surface with modular sub-configs, not scattered hidden switches

### Explicit non-metrics

The following are not success criteria by themselves:

* architectural richness
* number of subsystems
* number of reports
* raw classification accuracy
* more signals
* more complex model topology

If V7 does not improve economic quality, it is not successful.

---

## What V7 Is

V7 is:

* a **contract-compatible** learned trading engine
* a **centralized** system designed for multi-symbol operation
* a **market-first** learning system
* a **simulation-native** system where one forward simulation engine defines labeling and evaluation truth
* a **calibration-structural** decision system
* a **multi-symbol-aware** engine designed for 60-symbol operation
* a system optimized for **economic quality first**
* a system designed to remain **editable, configurable, reviewable, and testable**

---

## What V7 Is Not

V7 is not:

* a V4 correction layer
* a V5 continuation stack
* a transition-heavy architecture built by stacking legacy systems indefinitely
* a runtime rewrite
* a hidden deterministic veto system
* a confidence-first system with cosmetic calibration
* a model-accuracy project disconnected from economic reality
* a doc-heavy architecture exercise
* a black box with invisible fallbacks or hidden overrides
* a system where a small change requires editing many unrelated subsystems

---

## Core Architectural Position

V7 should be understood through six layers:

### 1. Runtime

Runtime remains responsible for:

* orchestration
* scheduling
* market-data flow
* persistence
* execution and paper/live control
* safety of the operational shell

### 2. Contract boundary

Runtime and engine interact only through explicit contracts:

* `AnalysisRequest`
* `AnalysisResult`
* `DecisionEvent`
* `TradeOutcome`

This boundary remains explicit, versioned, and testable.

### 3. State and simulation core

V7 introduces one central truth layer:

* canonical market-state construction
* unified forward simulation
* unified outcome semantics
* unified cost model

This layer is the core of V7.

### 4. Learned decision engine

The learned engine consumes market state and produces:

* long / short / no-trade action scores
* calibrated decision outputs
* uncertainty-aware decision information
* execution-relevant quality signals

### 5. Economic policy layer

Decision thresholds, no-trade rules, correlation exposure, drawdown gates, and position-sizing policy are explicit and auditable.

### 6. Review and lifecycle layer

V7 remains observable and controlled through:

* validation
* forward simulation
* promotion and rollback
* artifact versioning
* runtime review surfaces

---

## Strategic Difference From V6

V6 was a transition architecture.

It correctly preserved:

* runtime stability
* contract discipline
* V4 deterministic context reuse
* V5 foundation reuse
* review and promotion discipline

But V7 is not primarily a transition architecture.

V7 is a **consolidated architecture**.

### V6 posture

* V4 runtime remains operational owner
* V4 deterministic logic remains a strong context and safety source
* V5 remains reused infrastructure
* V6 becomes the learned layer inside that reuse-heavy structure

### V7 posture

* V7 owns its own learning pipeline end to end
* legacy systems may remain as compatibility or migration support
* deterministic logic is context, not governance
* simulation is the truth layer
* economic evaluation is the real authority
* modularity and centralized configuration are first-class constraints

In short:

* **V6 = transition-heavy learned layer**
* **V7 = consolidated economic decision engine**

---

## Market-First Principle

V7 must remain market-first.

That means:

* the market defines outcome truth
* legacy engines do not define ground truth
* labels come from simulated or realized market outcomes
* long, short, and no-trade are evaluated comparatively
* trade quality is judged by economic outcome, not by agreement with legacy rules

V4 or V5 outputs may appear as context or migration references.
They must not define the truth that V7 learns.

---

## Unified Simulation Principle

V7’s most important architectural rule is:

**one simulation engine defines the truth for labeling, evaluation, and production outcome interpretation.**

This means the following must share one logic surface:

* label generation
* forward evaluation
* trade-outcome generation
* cost modeling
* stop / target / time-exit semantics

There must not be one backtesting logic for research and another for labeling.
There must not be one cost model for training and another for evaluation.

If those diverge, V7 becomes economically untrustworthy.

---

## Calibration-Structural Principle

In V7, calibration is not cosmetic.

Calibration is part of the decision system itself.

This means:

* raw model scores are not directly trusted for action decisions
* calibrated scores are the basis for thresholds and policy
* calibration must be tracked per symbol and regime where justified
* confidence is not enough; calibrated reliability is what matters
* threshold policy must be aligned to the calibrated score distribution

A model without usable calibration is not decision-ready.

---

## No-Trade Is a First-Class Action

V7 must know when not to trade.

`NO_TRADE` is not:

* the absence of a signal
* a fallback after every other system fails
* a default suppressor for weak routing only

`NO_TRADE` is a real learned action that competes directly with:

* `LONG_NOW`
* `SHORT_NOW`

A correct skip is economically valuable and must be represented as such in labels, evaluation, and policy.

---

## Multi-Symbol Centralization

V7 is designed for a 60-symbol universe.

That does not require the runtime contract to become a multi-symbol batch object immediately.
But it does require the architecture to assume a multi-symbol research and evaluation world from the start.

This means:

* symbol-aware model inputs or evaluation slices
* symbol-level calibration and error analysis
* cross-symbol correlation awareness in the decision policy
* centralized forward simulation and reporting
* batch-oriented inference design where practical

V7 must not be mentally designed as 60 isolated single-symbol engines.

---

## Cost-Honest Labels

V7 labels must be economically honest.

This means labels are not based only on raw directional movement.
They must reflect:

* realistic fees
* slippage assumptions
* entry and exit rules
* stop / target / time-exit behavior
* comparative action quality between long, short, and no-trade

The correct question is not:

* “did price go up?”

The correct question is:

* “which action produced the best net economic outcome under the same simulated rules?”

---

## Runtime Boundary Remains Stable

V7 does not justify a runtime rewrite.

Runtime still owns:

* orchestration
* execution control
* persistence
* failure handling
* operator control surfaces

The engine still owns:

* market-state interpretation
* calibrated decision scoring
* uncertainty-aware action recommendation

The boundary remains one of V7’s strongest design protections.

---

## Deterministic Context Position

Deterministic logic may remain useful as:

* annotation
* context
* regime hint
* explicit warning source
* explicitly declared hard block in narrow cases

But deterministic logic must not silently define V7’s ceiling.

V7 rule:

* no silent deterministic veto
* no hidden suppression of learned opportunity
* deterministic influence must be visible and reviewable

Deterministic context is support, not sovereignty.

---

## Promotion Rule

V7 candidates are promoted only through out-of-sample economic evidence.

A candidate may be promoted only if forward simulation shows:

* positive expectancy R across meaningful out-of-sample periods
* acceptable drawdown behavior
* acceptable no-trade quality
* acceptable calibration quality
* acceptable symbol and regime stability

Architecture sophistication is never a promotion criterion by itself.

---

## Editability and Speed Principle

V7 must be easier to edit than V6.

That means:

* fewer subsystems
* fewer hidden policies
* one central configuration root
* one primary CLI entrypoint
* one simulation truth layer
* simpler threshold policy
* modular feature and label extensions
* minimal required documentation

The goal is not to remove rigor.
The goal is to remove unnecessary structural drag.

### Modularity rule

A change in one concern should ideally require editing:

* one primary module
* one config surface
* one test surface

not five subsystems.

### Configuration rule

V7 must be centrally configurable.

This means:

* one authoritative config loader
* modular sub-configs by concern
* no hidden config mutation through ad hoc scripts
* no configuration scattered across many orchestration layers

### AI-first readability rule

V7 design documents are primarily written for LLM code agents and AI-assisted engineering workflows.

That means documents should be:

* dense in constraints
* low in repetition
* explicit about what must not be changed
* explicit about ownership boundaries
* explicit about what is stable versus replaceable

The goal is not prose elegance.
The goal is high-signal machine-readable architectural clarity.

---

## What V7 Keeps From V6

V7 should keep these V6 principles:

* explicit request / result / event / outcome contracts
* market-first labeling philosophy
* unified snapshot / live-replay parity discipline
* no-trade as a first-class action
* explicit fallback visibility
* validation, promotion, and rollback discipline
* no silent deterministic veto

These were correct in V6 and remain correct in V7.

---

## What V7 Deliberately Changes

V7 deliberately changes the following:

* transition-heavy architecture becomes centralized architecture
* economic evaluation becomes the primary truth, not a downstream check
* calibration becomes structural, not cosmetic
* simulation becomes the single truth layer for labeling and evaluation
* multi-symbol thinking becomes native
* threshold policy becomes simpler and more explicit
* architecture is optimized for fast iteration and editability
* configuration becomes centralized rather than operationally scattered

---

## Non-Goals For The First V7 Design Phase

The first V7 design phase is not about:

* final model topology lock-in
* immediately solving every timeframe and execution style
* replacing the runtime shell
* building a giant document set
* adding specialist-routing complexity without evidence
* maximizing signals
* shipping an RL-first engine

The first V7 design phase is about:

* defining the right success criteria
* defining the right contracts
* defining the unified simulation truth layer
* defining the centralized architecture
* defining modularity and configuration rules
* creating a system that can reach economic quality faster

---

## Immediate Next Step

After this vision is accepted, the next documents should define:

1. `architecture.md`
2. `contracts.md`
3. `ai_summary.md`
4. `simulation.md`
5. `model_policy.md`
6. `roadmap.md`
7. `llm_rules.md`

Only after those are clear should implementation begin.

---

## Bottom Line

The V7 direction is simple:

**Keep the contract discipline.**
**Keep market-first learning.**
**Keep runtime stable.**
**Make simulation the truth layer.**
**Make calibration structural.**
**Make economic quality the first constraint.**
**Make configuration centralized.**
**Make changes local, fast, and hard to break.**
