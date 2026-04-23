# V7 AI Summary

## Purpose

This is the shortest authoritative summary of V7 for AI-assisted implementation.

It answers:

> If an LLM only reads one compact summary before diving into detailed docs, what must it know?

---

## V7 In One Page

V7 is a centralized, market-state-first trading system designed for:

- shared multi-symbol operation
- one canonical state language
- one simulation truth layer
- one compact contract family
- one unified config surface
- explicit runtime vs engine ownership
- compact, analyzable docs and modules

It is not a greenfield reset.
It is an extension and cleanup of the strongest V6 ideas.

---

## Contract Family

### `AnalysisRequest`
Runtime-to-engine input.
Atomic:
- one symbol
- one primary interval
- one canonical state

### `AnalysisResult`
Engine-to-runtime output.
Carries:
- recommended action
- confidence
- expected R
- entry / stop / target
- timing guidance
- degradation visibility

### `DecisionEvent`
Runtime/lifecycle-owned normalized decision record.
Not emitted by the model.

### `TradeOutcome`
Lifecycle-owned normalized consequence record.
Larger than a label.

For exact semantics, read:
- `contracts/README.md`
- then the four contract docs

---

## First-Phase Defaults

- target universe up to **60 symbols**
- primary interval: **4h**
- higher-timeframe context: **1d**
- optional later refinement: **1h**
- first-phase model: **XGBoost-first**
- first-phase calibration: **global**
- timing extension:
  - `entry_readiness`
  - `entry_valid_for_bars`
  - advisory-first in normal operation

A timing extension only becomes a hard execution gate after evaluation and monitoring evidence support the move.

---

## Pipeline In One View

### Simulation
Single authoritative truth layer.

### Labels
Market-first, comparative, no-trade-aware.

### Features
Derived only from canonical state.

### Dataset
Time-correct, lineage-correct, walk-forward.

### Model
Shared multi-symbol first phase.

### Calibration
Explicit and versioned.

### Policy
Turns calibrated surfaces into `LONG_NOW`, `SHORT_NOW`, or `NO_TRADE`.

### Portfolio
Cross-symbol suppression / down-ranking.

### Risk
Hard and soft execution safety after portfolio interpretation.

### Evaluation
Economic-quality-first.

### Monitoring
Tracks both model quality and lifecycle integrity.

Portfolio and risk are separate on purpose:
- portfolio manages cross-symbol pressure
- risk manages hard/soft execution safety

---

## Runtime In One View

Runtime owns:
- request assembly
- result validation
- event creation
- execution eligibility
- persistence
- outcome lifecycle
- operational safety

Engine owns:
- interpretation of state
- score generation
- confidence
- expected R
- decision recommendation
- timing guidance

Runtime is not being rewritten first.
It is being integrated to the V7 contract family incrementally.
For operational details, read:
- `runtime/runtime_integration.md`
- `runtime/fallback_policy.md`
- `runtime/deployment_safety.md`

---

## Non-Negotiable Rules

These are not just slogans.
Their detailed semantics live in the linked authority docs.

- no hidden fallback → `runtime/fallback_policy.md`
- no future leakage → `pipeline/features.md`, `pipeline/dataset.md`, `pipeline/labels.md`
- no hidden deterministic veto → contract family + runtime integration
- no training on unresolved outcomes → `pipeline/labels.md`, `contracts/trade_outcome.md`
- no config sprawl outside the unified config surface → `v7_llm_rules.md`
- no giant docs repeating each other → `v7_doc_writing_guide.md`

---

## What To Read Next

If implementation is about:
- contracts → start at `contracts/README.md`
- runtime behavior → start at `runtime/runtime_integration.md`
- model/pipeline → start at `pipeline/simulation.md`
- repo editing behavior → read `v7_llm_rules.md`

---

## Final Position

V7 should feel boring in structure and strong in semantics.

That is intentional.

The goal is not maximum novelty.
The goal is a system that humans and LLMs can both understand, change, and test safely.
