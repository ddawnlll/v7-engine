# V7 Contract Strategy

## Purpose

This document defines the **contract strategy** for V7.

It does not replace the individual contract specifications.
Instead, it explains:

- why V7 keeps the V6 contract family
- what was already strong in V6
- what V7 must improve
- which new contract capabilities V7 needs
- how the individual contract documents relate to each other

This file is the architectural entrypoint for the V7 contract layer.

---

## Why This File Exists

V6 already established a strong contract discipline.

Its major strengths were:

- explicit runtime ↔ engine boundaries
- state-first request design
- decision-rich result design
- normalized decision-event lifecycle
- normalized trade-outcome lifecycle
- replay/live compatibility thinking
- explicit fallback and deterministic visibility

Those were not mistakes.
They are some of the strongest parts of the V6 system.

V7 does **not** replace that contract philosophy.
V7 builds on it.

However, V7 introduces new operating assumptions:

- centralized multi-symbol operation
- 60-symbol research and evaluation scope
- stronger simulation-native design
- stronger portfolio-awareness
- faster inference and evaluation paths
- more explicit multi-timeframe / multi-view state handling

Because of that, V7 needs a contract strategy that is:

- compatible with the clean V6 semantics
- but no longer limited to a purely single-state worldview

This document defines that strategy.

---

## Core Position

**V7 preserves the clean single-state semantics of V6, but extends them with batch-aware, multi-view, session-aware, and simulation-native structures so the engine can operate centrally across symbols and timeframes without losing auditability.**

That is the core contract position.

V7 is not a contract reset.
It is a contract extension.

---

## What Was Strong In V6

V6 contracts were strong for four reasons.

### 1. Clear role separation
V6 clearly separated:

- what runtime sends
- what engine returns
- what the system records as a decision
- what the system later records as an outcome

This should remain true in V7.

### 2. State-first request design
V6 did not reduce the request to a legacy signal shell.
It separated:

- raw market window
- derived state
- higher-timeframe context
- deterministic context
- runtime and execution context

This is still the correct request philosophy.

### 3. Decision/result vs system-event distinction
V6 correctly distinguished:

- `AnalysisResult` = engine output
- `DecisionEvent` = normalized system-level record of one evaluated decision

This remains one of the best architectural decisions in the system.

### 4. Outcome as a real lifecycle object
V6 correctly treated `TradeOutcome` as more than a label.
It included:

- execution truth
- path truth
- comparative truth
- ambiguity and regret
- replay/live compatibility

This is still the correct outcome philosophy.

---

## What Was Limited In V6

The main limitation in the V6 contracts was **not** poor semantics.
The main limitation was **scope**.

V6 contracts were intentionally designed around:

- one state
- one symbol
- one interval
- one request
- one result
- one event
- one outcome

That was a valid design for the first contract family.
But it is too narrow for V7’s architecture if left unextended.

The main gaps are:

1. no first-class batch/session layer
2. no native multi-view state contract
3. no explicit batch-level orchestration identity
4. no explicit portfolio-aware request additions
5. no explicit simulation-family grouping for comparative outcomes

These are the main V7 contract extensions.

---

## V7 Contract Design Principles

### 1. Preserve the single-state semantic core
The atomic contract unit remains valid:

- one request
- one result
- one decision event
- one trade outcome

This atomic unit is still needed for:

- auditability
- replay consistency
- model comparison
- runtime safety
- persistent lineage

V7 does not throw this away.

### 2. Add batch-aware structures above the atomic unit
V7 should add higher-level structures for grouped evaluation.

The likely additions are:

- `AnalysisBatchRequest`
- `AnalysisBatchResult`
- `DecisionSession`
- later evaluation or simulation run identifiers

These additions should not invalidate the atomic contract family.
They should wrap or group it.

### 3. Support multi-view state without breaking single-state auditability
V7 must support richer state views:

- primary interval
- higher-timeframe views
- optional future lower-timeframe refinement views

This should be done by extending request semantics, not by making the system ambiguous.

### 4. Keep runtime and engine responsibilities separate
V7 keeps the same boundary principle:

- runtime owns orchestration, persistence, execution control, and operational safety
- engine owns state interpretation, scoring, uncertainty-aware decisioning, and action recommendation

No contract extension should blur this boundary.

### 5. Keep simulation truth central
Contracts must remain compatible with the V7 architecture rule:

- one simulation engine defines labeling truth
- the same simulation semantics define evaluation truth
- trade outcomes must stay linkable to that truth

This means outcome and event lineage must become even more explicit, not less.

### 6. Keep evolution additive
V7 contracts should evolve through:

- additive sections
- additive fields
- new wrapper/grouping objects
- explicit versioning

Not through hidden semantic mutation.

---

## V7 Contract Family

The V7 contract family is split into two layers.

## Layer A — Atomic contracts
These remain the core system contracts:

1. `AnalysisRequest`
2. `AnalysisResult`
3. `DecisionEvent`
4. `TradeOutcome`

These remain the canonical semantic units.

## Layer B — Grouping and orchestration contracts
These are new V7-level extensions:

1. `AnalysisBatchRequest`
2. `AnalysisBatchResult`
3. `DecisionSession`
4. later `SimulationRun` / `EvaluationRun` concepts where needed

These group, coordinate, or summarize atomic decisions.

---

## Contract-by-Contract V7 Direction

### `AnalysisRequest`
V6 was already strong here.
V7 should preserve its structure and extend it with:

- multi-view state support
- clearer primary vs contextual interval semantics
- optional symbol metadata additions
- optional portfolio-aware fields
- optional correlation / cluster-aware fields

But the request should remain an **engine input contract**, not a portfolio controller.

### `AnalysisResult`
V6 was also strong here.
V7 should preserve its stable actionability and uncertainty surfaces while extending it with:

- clearer separation between raw and calibrated scores
- optional candidate decision surfaces
- more explicit economic score fields
- compatibility with batched inference outputs

But the result should remain an **engine output contract**, not a runtime policy object.

### `DecisionEvent`
V6 was strongest here.
V7 should keep the current lineage discipline and extend it with:

- batch/session identity
- optional rank/order within a decision batch
- optional portfolio-policy interpretation notes
- optional batch-level linkage for centralized evaluation and scan audit

### `TradeOutcome`
V6 was also very strong here.
V7 should extend it with:

- stronger simulation-family grouping
- richer counterfactual linkage
- explicit cost-model/version lineage
- optional portfolio context at decision time
- better grouping for comparative evaluation families

---

## V7 Additions That Matter Most

The following additions are the most important.

### 1. Batch identity
V7 should introduce explicit batch identity such as:

- `analysis_batch_id`
- `decision_session_id`

This enables:

- 60-symbol coordinated inference
- centralized evaluation audit
- portfolio-aware gating
- batch-level latency and scoring analysis

### 2. Multi-view market state
V7 should support state semantics such as:

- `primary_interval`
- `state_views`

instead of assuming the request only contains one effective market lens.

### 3. Result surface beyond one chosen action
V7 should make it easier to preserve the full decision surface.

That may include:

- `candidate_decisions`
- calibrated long / short / no-trade surfaces
- decision gap and ambiguity information

### 4. Simulation family lineage
V7 should make it easier to group outcomes generated under one simulation family.

This matters for:

- counterfactual evaluation
- comparative labeling
- forward simulation analysis
- replay/paper/live reconciliation

### 5. Portfolio-awareness without contract collapse
V7 should support lightweight portfolio-aware request and event fields without turning the contracts into portfolio engine schemas.

Examples:

- drawdown state
- current exposure state
- correlation cluster hints
- batch/session risk context

These should remain contextual, not controlling.

---

## What V7 Must Not Do

The contract layer must remain disciplined.

V7 must **not** do the following:

### 1. Replace atomic contracts with only batch contracts
The single-state semantic unit must remain first-class.

### 2. Turn request contracts into portfolio control objects
Portfolio context may appear, but orchestration and portfolio governance still live outside the request.

### 3. Turn result contracts into hidden execution policy
The result may contain scores and guidance, but execution policy still lives in the policy/runtime layer.

### 4. Duplicate full raw state across event and outcome objects
Event and outcome should summarize and link, not duplicate the whole world.

### 5. Add rich grouping without explicit identity
If batch or simulation grouping exists, it must be explicitly named and versioned.

---

## Recommended V7 Contract File Structure

The contract layer should live in:

```text
/docs/contracts/
  README.md
  analysis_request.md
  analysis_result.md
  decision_event.md
  trade_outcome.md
```

### File responsibilities

#### `README.md`
Defines:
- contract philosophy
- what remains from V6
- what changes in V7
- how the contract family is structured

#### `analysis_request.md`
Defines:
- what runtime sends to the engine

#### `analysis_result.md`
Defines:
- what the engine returns to runtime

#### `decision_event.md`
Defines:
- what the system records as a normalized evaluated decision

#### `trade_outcome.md`
Defines:
- what the system records as the eventual realized or projected consequence of that decision

---

## Per-Contract Generation Rules

These rules are global constraints for AI-assisted writing and editing.
They apply even if an individual contract file does not repeat them.

### `analysis_request.md`
Must define **engine input only**.

Do:
- define market-state input semantics
- define request identity, scope, state views, context, and quality surfaces
- define what runtime may send to the engine

Do not:
- define execution commands
- define order placement logic
- define portfolio governance logic
- define batch orchestration policy inside the atomic request contract
- embed future outcome knowledge

### `analysis_result.md`
Must define **engine output only**.

Do:
- define decision outputs
- define score surfaces
- define uncertainty, calibration-facing, and degradation semantics
- define what runtime can safely interpret from engine output

Do not:
- define runtime policy
- define execution ownership
- define portfolio control logic
- define downstream outcome truth
- embed hidden engine internals as required runtime fields

### `decision_event.md`
Must define **normalized system decision record only**.

Do:
- define lineage from request and result
- define normalized runtime interpretation
- define execution and outcome linkage surfaces
- define the canonical persisted record of one evaluated decision

Do not:
- define order internals
- duplicate the full raw request
- duplicate the full raw response
- redefine engine scoring semantics
- collapse event and outcome into one object

### `trade_outcome.md`
Must define **normalized outcome record only**.

Do:
- define realized or projected consequence of a decision
- define path, comparative, regret, and quality semantics
- define outcome readiness and resolution status
- define replay/live/paper compatibility of outcomes

Do not:
- rewrite the original decision with hindsight
- embed fill-book internals as core outcome semantics
- duplicate the full event or request payload
- turn the outcome object into a raw label-only schema
- mix execution ledger design into the normalized outcome contract

---

## Recommended Writing Order

The contract documents should be written in this order:

1. `README.md`
2. `analysis_request.md`
3. `analysis_result.md`
4. `decision_event.md`
5. `trade_outcome.md`

This order matches the actual lifecycle:

`request` → `result` → `event` → `outcome`

It also reduces repetition and semantic drift.

---

## Relationship To Other Architectural Documents

This contract strategy must remain aligned with:

- `vision.md`
- `architecture.md`
- `simulation.md`
- `model_policy.md`

In particular:

- `vision.md` defines why V7 exists
- `architecture.md` defines how V7 is structured
- this document defines how V7’s major system objects are shaped and related
- `simulation.md` defines the truth layer those objects must remain compatible with

---

## Immediate Next Step

After this strategy is accepted, the next contract document to write is:

- `analysis_request.md`

Because the request contract defines the first real engine boundary.

---

## Bottom Line

V6 already solved the hardest semantic problem:

- request
- result
- event
- outcome

as distinct first-class objects.

V7 should keep that discipline.

What V7 adds is not a new philosophy.
What V7 adds is a wider operating frame:

- multi-view state
- batch/session-aware orchestration
- stronger centralized evaluation
- stronger simulation-native lineage
- more explicit portfolio-aware context

So the V7 contract strategy is simple:

**keep the atomic clarity of V6**
**add the grouping and centralization V7 now needs**
**do not sacrifice auditability to gain speed**

