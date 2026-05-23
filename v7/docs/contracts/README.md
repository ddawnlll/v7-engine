# V7 Contracts README

## Purpose

This document defines the **V7 contract family strategy**.

It answers one question:

> How should V7 define its core runtime/engine/lifecycle objects so the system stays atomic, replay-compatible, batch-aware, and easy to evolve?

This is a strategy and boundary document.

It is not:
- a pipeline implementation doc
- a broker/exchange integration doc
- a database schema
- a model architecture paper

---

## Core Position

V7 is **not** a contract reset.

V7 is a disciplined extension of the V6 contract direction.

That means:

- keep the atomic semantic unit
- keep request/result/event/outcome as first-class lifecycle objects
- add batch/session-aware grouping above that atomic core
- keep live and replay on the same semantic language
- avoid turning runtime contracts into giant blobs

---

## The Contract Family

V7 should treat the following objects as one family:

### Layer A — Atomic lifecycle objects
- `AnalysisRequest`
- `AnalysisResult`
- `DecisionEvent`
- `TradeOutcome`

These are the canonical per-state lifecycle contracts.

### Layer B — Grouping / orchestration objects
- `AnalysisBatchRequest`
- `AnalysisBatchResult`
- `DecisionSession`

These exist to support:
- centralized multi-symbol scanning
- grouped review
- GPU batching
- replay/evaluation grouping

Layer B must never destroy Layer A atomicity.

---

## Atomic Rule

The core V7 semantic unit remains:

- one symbol
- one primary interval
- one evaluated market state
- one request
- one result
- one event
- one outcome

This rule is the backbone of the family.

Batching, grouping, sessions, and scans are built **around** the atomic unit, not instead of it.

---

## Why This Family Exists

Without a shared contract family, the system fragments into:
- request objects in one shape
- result objects in another shape
- runtime records in another shape
- replay records in another shape
- evaluation objects in yet another shape

V7 should avoid that fragmentation.

The family exists to keep:

- boundaries explicit
- lineage stable
- replay/live comparable
- review/audit surfaces usable
- implementation AI-friendly

---

## Ownership Model

The family is shared, but ownership differs.

### Engine-facing contracts
- `AnalysisRequest`
- `AnalysisResult`

### System/lifecycle contracts
- `DecisionEvent`
- `TradeOutcome`

That means:
- request/result define the runtime ↔ engine boundary
- event/outcome define the system’s normalized lifecycle records

Shared family, different ownership.

---

## One-Line Deterministic System Definition

In this contract family, **deterministic system** means:

> any explicit non-learned logic or annotations that can influence interpretation, gating, fallback, or review of a decision.

Examples:
- regime hints
- allowed/blocked action annotations
- deterministic safety blocks
- rule-based degradation handling

Deterministic logic may assist the system, but must not silently replace learned decision semantics.

---

## Layer A Object Intent

### `AnalysisRequest`
Atomic runtime-to-engine input:
- what exact state should be analyzed?

### `AnalysisResult`
Atomic engine-to-runtime output:
- what did the engine conclude?

### `DecisionEvent`
Atomic normalized lifecycle record:
- what was evaluated, what came back, and how did runtime interpret it?

### `TradeOutcome`
Atomic normalized consequence record:
- what eventually happened afterward?

---

## Layer B Object Intent

### `AnalysisBatchRequest`
A grouping object for many atomic requests.

### `AnalysisBatchResult`
A grouping object for many atomic results.

### `DecisionSession`
A session/grouping object that ties related decisions together for:
- scans
- review
- replay comparison
- promotion evidence

### Writing status for Layer B
Layer B is intentionally deferred until the Layer A family and the core pipeline docs are stable.

That means:
- Layer B is part of the design
- Layer B is **not** required to lock the atomic family
- Layer B docs should be written after simulation / evaluation / policy docs stabilize

This keeps the current scope controlled.

---

## What V7 Must Preserve From V6

V7 should preserve the following V6 wins:

- explicit request/result contracts
- state-first rather than signal-first thinking
- normalized event and outcome lifecycle objects
- replay/live semantic alignment
- explicit degradation/fallback visibility
- no-trade as a first-class concept
- path-aware and counterfactual-aware outcome language

---

## What V7 Must Extend

V7 should extend V6 in the following ways:

- clearer atomic vs grouping layers
- explicit batch/session lineage
- stronger canonical-state discipline
- stronger economic fields
- stronger simulation-family lineage
- stronger cost-model lineage
- optional decision-time portfolio/risk context
- advisory-first timing-readiness surface

---

## What V7 Must Not Do

V7 must not:

1. collapse many symbols into one atomic request/result
2. turn event/outcome into giant raw payload duplicates
3. silently rewrite model meaning in runtime
4. hide degraded paths
5. hide deterministic vetoes
6. mix broker execution internals into core contracts
7. couple replay and live to different semantic species
8. add Layer B objects in a way that breaks atomic auditability

---

## Version Field Cheat Sheet

This family uses several version fields on purpose.

### `contract_version`
The boundary-family version.
Use when request/result/event/outcome family semantics change materially.

### `state_schema_version`
The meaning of `canonical_state`.
Use when state structure or interpretation changes materially.

### `response_schema_version`
The meaning of the stable result surface.
Use when result semantics change materially.

### `event_schema_version`
The meaning of the normalized event object.
Use when event semantics change materially.

### `outcome_schema_version`
The meaning of the normalized outcome object.
Use when outcome semantics change materially.

### `snapshot_builder_version`
The state-construction logic version.
Use when replay/live-parity-relevant request assembly changes.

### Artifact versions
Examples:
- `model_artifact_version`
- `calibration_artifact_version`
- `policy_artifact_version`

Use these to track the producing artifacts, not the contract semantics themselves.

---

## Generation Rules Per Contract

### Request
Must define:
- atomic scope
- canonical state
- explicit lineage/versioning
- quality/degradation visibility

Must not define:
- execution commands
- future truth
- multi-symbol aggregation

### Result
Must define:
- recommended action
- confidence
- expected R
- actionability
- execution guidance
- degradation visibility

Must not define:
- broker payloads
- outcome truth
- multi-request aggregation

### Event
Must define:
- normalized lifecycle record
- request/result linkage
- runtime interpretation
- execution linkage
- outcome linkage

Must not define:
- full raw request duplication
- full raw result duplication
- fill internals

### Outcome
Must define:
- decision linkage
- execution truth
- path truth
- comparative truth
- finality/readiness

Must not define:
- raw label-builder internals
- full request/result duplication
- hidden hindsight rewrites

---

## Current Lock Position

The V7 family can now be considered locked at the **semantic architecture** level for:

- `AnalysisRequest`
- `AnalysisResult`
- `DecisionEvent`
- `TradeOutcome`

This means:
- the big structural decisions are stable
- only targeted clarification or additive fields should be expected next

Layer B can remain deferred without blocking progress.

---

## Final Position

V7 contracts should be understood as one coherent family:

- atomic at the core
- batch-aware above the core
- explicit about ownership
- explicit about degradation and lineage
- replay/live compatible
- small enough to stay stable
- rich enough to support learning and audit

That is the contract foundation V7 should build on.
