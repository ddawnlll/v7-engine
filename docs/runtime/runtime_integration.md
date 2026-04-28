# V7 Runtime Integration

## Purpose

This document defines how V7 runtime should integrate with the V7 contract family:

- `AnalysisRequest`
- `AnalysisResult`
- `DecisionEvent`
- `TradeOutcome`

It answers one question:

> Given the V7 contracts, how should runtime assemble requests, validate results, create events, make execution decisions, and later attach outcomes without collapsing boundaries?

This is an integration document.

It is not:
- a full runtime rewrite plan
- a broker implementation spec
- a database schema
- a scheduler design
- a training pipeline document

Those belong elsewhere.

---

## Core Position

V7 runtime should **not** be rewritten from scratch right now.

Instead, runtime should be treated as:

- the orchestration shell
- the execution shell
- the persistence shell
- the safety shell
- the lifecycle materialization shell

The engine stack owns:
- market-state interpretation
- simulation truth semantics (one shared simulation core used by both V6 and V7)
- score generation
- confidence
- expected R
- recommended action
- timing guidance
- uncertainty/degradation visibility

Runtime owns:
- orchestration, execution, persistence, and lifecycle
- paper trading (which is simply forward simulation using the shared simulation core)
- historical replay driver (which wraps the shared simulation core)
- execution eligibility and safety gates
- request assembly
- result validation
- execution eligibility
- persistence
- event creation
- outcome attachment
- operational safeguards
- `scope_router` selection from `requested_trade_mode` / `model_scope`
- model artifact selection and scope compatibility validation
- blocking or downgrading `scope_mismatch` to visible safe behavior

This preserves the V7 boundary discipline already established by the request/result/event/outcome family. fileciteturn20file1 fileciteturn33file0 fileciteturn21file0 fileciteturn27file0

---

## Integration Flow

The normalized V7 runtime flow should be:

```text
Market/Data State
→ Request Builder
→ AnalysisRequest
→ Scope Router (`requested_trade_mode` / `model_scope`)
→ Scope-Compatible Artifact Selection
→ Engine
→ AnalysisResult
→ Result Validator
→ Runtime Interpretation
→ DecisionEvent
→ Execution Eligibility
→ Execution / No Execution
→ TradeOutcome
```

This ordering matters.

### Why this order matters
- request is the engine input
- result is the engine output
- event is the runtime-owned normalized lifecycle record
- outcome is the later consequence record

Runtime must not skip the event layer.

---

## Runtime Responsibilities

Runtime should own the following responsibilities.

### 1. Request assembly
Runtime constructs a valid `AnalysisRequest` from:
- data state
- config
- optional portfolio/risk context
- batch/session context

### 2. Result validation
Runtime verifies that the returned `AnalysisResult`:
- matches the request
- is structurally valid
- has required fields
- has internally consistent actionability and execution guidance

### 3. Runtime interpretation
Runtime may classify the result further for system behavior, including:
- actionable vs review-only
- blocked vs degraded
- persist vs skip
- execution eligible vs not eligible

### 4. Event creation
Runtime creates `DecisionEvent` immediately after a valid normalized result exists.

### 5. Execution eligibility
Runtime applies operational gates before order placement.

### 6. Outcome lifecycle
Runtime creates or updates `TradeOutcome` as lifecycle information becomes available.

---

## Boundary Rules

### Engine must not own
- broker order submission
- persistence schemas
- trade outcome materialization
- event creation
- execution ledgers

### Runtime must not own
- re-deriving model scores
- silently rewriting the engine decision
- inventing hidden action semantics
- replacing contract-defined fields with ad hoc local logic

### Shared contract family, different ownership
- request/result are engine-facing
- event/outcome are system-facing

This distinction should remain explicit in code and docs.

---

## Request Integration Rules

Runtime must produce one atomic `AnalysisRequest` per:
- symbol
- primary interval
- evaluated market state

Fast scanning and GPU batching should happen through:
- `analysis_batch_id`
- `decision_session_id`
- batch orchestration outside the atomic request

Runtime request builder should:
- preserve `state_schema_version`
- preserve `snapshot_builder_version`
- preserve `request_kind`
- keep `canonical_state` authoritative
- keep timing-free future leakage out of the request
- include `requested_trade_mode`, `model_scope`, `primary_interval`, `context_intervals`, and `refinement_intervals`
- ensure one request targets one selected scope rather than asking all scopes to compete

This remains aligned with the V7 request contract. fileciteturn20file1

---

## Result Integration Rules

Runtime must treat `AnalysisResult` as the authoritative engine output surface.

That means runtime should use:
- `recommended_action`
- `direction`
- `confidence`
- `confidence_kind`
- `expected_r`
- `expected_drawdown`
- `entry_price`
- `stop_loss`
- `take_profit`
- `time_sensitivity`
- `entry_readiness`
- `entry_valid_for_bars`
- `fallback_used`
- `degraded_reason`

Runtime may interpret and gate these fields, but must not silently replace them.

Runtime must also persist `model_scope`, `trade_mode`, artifact lineage, and calibration lineage in `DecisionEvent` / `TradeOutcome` where relevant. Runtime may run separate configured scans per scope, but it must not ask all model scopes for outputs and average them.

This follows the revised V7 result contract, where confidence remains first-class, expected R remains first-class, and timing extension fields are advisory-first. fileciteturn33file0

---

## Actionability vs Execution Eligibility

This distinction is critical.

### Engine actionability
Comes from result-side fields such as:
- `recommended_action`
- `is_actionable`
- `confidence`
- `expected_r`
- timing guidance
- degradation fields

### Runtime execution eligibility
Comes from operational gates such as:
- exchange availability
- duplicate prevention
- cooldowns
- account state
- risk hard limits
- position constraints
- runtime kill switches

### Rule
A result may be:
- economically actionable
but
- operationally not executable

Runtime must record that distinction explicitly rather than hiding it in logs.

---

## Recommended Execution Eligibility Stack

Runtime should move away from:
- `confidence >= min_confidence => execute`

and toward a layered gate:

### 1. Structural validity
- request/result match
- required fields exist
- no illegal values

### 2. Engine actionability
- `is_actionable == true`
- `recommended_action in {LONG_NOW, SHORT_NOW}`

### 3. Confidence gate
- `confidence >= min_confidence`

### 4. Economic gate
- `expected_r >= min_expected_r`
- optional `expected_drawdown <= max_expected_drawdown`

### 5. Timing gate
Initially advisory-only:
- inspect `entry_readiness`
- inspect `entry_valid_for_bars`

Later optional hard gate:
- disallow `MISSED`
- optionally disallow or down-rank `CHASING`

### 6. Operational hard gate
- exchange healthy
- no duplicate position conflict
- cooldown clear
- not blocked by account/risk controls

This keeps confidence central without making it the only execution condition.

---

## Timing Extension Integration

The revised `AnalysisResult` added a small timing extension:
- `entry_readiness`
- `entry_valid_for_bars`
- optional `entry_expiry_utc`

Runtime integration should treat these as:

### Phase 1
- validate
- persist
- log
- review

### Phase 2
- compare against later outcome quality

### Phase 3
- optionally use as execution gate

Runtime should **not** immediately turn these into a complex timing planner.

This keeps runtime load manageable while making the signal measurable. fileciteturn33file0

---

## Result Validation Checklist

Before runtime uses a result, it should validate:

- request linkage is consistent
- `requested_trade_mode`, `model_scope`, and artifact lineage are scope-compatible
- `recommended_action` and `direction` are consistent
- `is_actionable` is legal for the given status
- `confidence` is present and valid
- `expected_r` is present and valid
- actionable directional trades include:
  - `entry_price`
  - `stop_loss`
  - `take_profit`
  - `time_sensitivity`
- if present:
  - `entry_readiness` is legal
  - `entry_valid_for_bars` is non-negative and bounded
- fallback/degradation fields are internally consistent

A bad result should be rejected before execution handling.

---

## DecisionEvent Materialization Rules

Runtime should create `DecisionEvent`:
- after a valid `AnalysisResult`
- before final execution outcome is known
- using the same atomic scope as request/result

The event must summarize:
- what was evaluated
- what the engine said
- how runtime interpreted it
- what happened next in execution eligibility

It must not:
- duplicate the full request
- duplicate the full result
- wait until final trade outcome exists

This matches the V6 event principle and the V7 event revision direction. fileciteturn21file0

---

## TradeOutcome Materialization Rules

Runtime should create or update `TradeOutcome`:
- after `DecisionEvent` exists
- when enough information exists to attach an initial outcome state
- even if the outcome is only `PENDING`

Outcome should later evolve to:
- `RESOLVED`
- `PARTIALLY_RESOLVED`
- `INVALIDATED`
- `UNAVAILABLE`

This preserves lifecycle truth and avoids treating delayed outcomes as missing objects. fileciteturn27file0

---

## Recommended Runtime State Transitions

```text
Result Validated
→ Event Created
→ Execution Eligibility Evaluated
→ Executed / Skipped / Blocked / Deferred
→ Outcome Created (possibly PENDING)
→ Outcome Updated Until Final
```

This is the lifecycle runtime should own.

---

## Persistence Guidance

Runtime persistence should prefer:

### Store directly
- core request identifiers
- core result identifiers
- core event identifiers
- core outcome identifiers
- normalized status/actionability/execution path fields

### Store by reference
- large payloads
- raw feature dumps
- optional debug artifacts
- large replay support artifacts

Do not let runtime persistence depend on giant opaque blobs for normal operation.

---

## Config Surface

Any runtime operational setting introduced for V7 should go through the unified config system.

Examples:
- `min_confidence`
- `min_expected_r`
- `max_expected_drawdown`
- `enable_entry_timing_observability`
- `enable_entry_readiness_gate`
- `blocked_entry_readiness_states`
- `min_entry_valid_for_bars`
- `runtime_safe_action_on_degraded_result`

Do not hardcode these in business logic.

---

## Minimum Runtime Changes Required For V7

These are the minimum practical changes needed.

### Request side
- support V7 request shape, including `requested_trade_mode` / `model_scope`
- support `canonical_state`
- support batch/session lineage
- preserve request versions

### Result side
- support V7 result shape
- validate timing extension fields
- persist confidence/expected R/timing fields

### Event side
- create V7 `DecisionEvent`
- include timing echoes from result
- include runtime interpretation
- include execution eligibility outcome

### Outcome side
- create V7 `TradeOutcome`
- include batch/session lineage
- include optional `evaluation_run_id`
- include optional `simulation_run_id`
- include cost/simulation lineage if available

### Observability side
- log actionability and execution eligibility separately
- log timing extension fields
- log suppression reasons explicitly

---

## Changes That Can Wait

These do **not** have to happen immediately:

- full runtime rewrite
- complex timing planner
- wide action-family expansion
- major broker abstraction rewrite
- full legacy cleanup
- heavy runtime-side strategy orchestration

This keeps V7 tractable.

---

## Recommended Rollout Order

### Phase 1
- accept V7 request/result
- validate
- persist
- create event/outcome objects

### Phase 2
- add actionability gating
- add expected-R gating
- add timing observability

### Phase 3
- add optional timing gating
- expand event/outcome summaries
- harden review/analytics surfaces

### Phase 4
- runtime rework only after V7 contract family and pipeline are stable

This matches the current priority order.

---

## Final Position

V7 runtime integration should be:

- contract-driven
- atomic at the request/result/event/outcome level
- batch-aware through lineage
- confidence-aware
- expected-R-aware
- advisory-first for timing
- explicit about actionability vs execution eligibility
- incremental rather than rewrite-first

That is the cleanest way to make runtime compatible with the V7 contract family without turning the current effort into a premature runtime rewrite.
