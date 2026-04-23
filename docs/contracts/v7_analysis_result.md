# V7 AnalysisResult Contract

## Purpose

This document defines the **`AnalysisResult`** contract for V7.

`AnalysisResult` is the atomic **engine-to-runtime analysis output** contract.

It answers one question:

> What exact analysis result must the engine return so runtime can interpret, review, persist, and safely act on one evaluated market state?

This document defines **analysis output semantics only**.

It does not define:

- broker order payloads
- database storage schema
- final execution implementation
- training labels
- trade outcome semantics
- promotion policy

Those belong elsewhere.

---

## Core Position

V7 keeps the strong V6 response principle:

- one request
- one result
- one evaluated market state
- one explicit runtime-facing decision surface

But V7 adjusts the result around five rules:

1. **the result belongs to one atomic `AnalysisRequest`**
2. **confidence remains a first-class runtime opening field**
3. **economic quality fields such as `expected_r` are also first-class**
4. **execution guidance and timing remain explicit**
5. **degradation, fallback, and deterministic interaction remain visible**

The result remains a **runtime-usable decision contract**, not a hidden model-internals dump and not a broker execution object.

---

## Request Compatibility Rule

Every valid `AnalysisResult` must correspond to exactly **one** valid `AnalysisRequest`.

That means:

- one `request_id`
- one `symbol`
- one `primary_interval`
- one atomic evaluated market state
- one engine result surface

`AnalysisResult` must never silently combine multiple requests into one atomic result.

If multiple symbols or multiple atomic requests are analyzed together, that belongs to:

- `AnalysisBatchRequest`
- `AnalysisBatchResult`
- `DecisionSession`

not to the atomic `AnalysisResult`.

---

## Role In The System

`AnalysisResult` sits at the engine ↔ runtime boundary.

### Engine owns
- state interpretation
- score generation
- confidence estimation
- economic decision estimation
- action recommendation
- timing and execution guidance
- degradation visibility
- deterministic interaction visibility

### Runtime owns
- validation
- orchestration
- persistence
- execution control
- order placement
- operational hard guards
- final execution or no-execution

`AnalysisResult` must preserve that boundary.

---

## In Scope

`AnalysisResult` defines:

- result identity and request linkage
- status and actionability
- recommended action
- confidence surface
- economic decision surface
- execution guidance
- timing guidance
- uncertainty and quality visibility
- deterministic interaction visibility
- fallback and degradation visibility
- observability metadata
- batch/session lineage

---

## Out of Scope

`AnalysisResult` does **not** define:

- raw model internals as required runtime fields
- full broker order instructions
- portfolio accounting internals
- final position sizing ownership
- trade outcome records
- label records
- evaluation artifacts
- multiprocessing strategy
- GPU execution topology

---

## Atomic Result Rule

A valid V7 `AnalysisResult` is the result of evaluating:

- **one symbol**
- **one primary interval**
- **one atomic request**
- **one engine pass**

This rule stays first-class.

The response may include richer score surfaces and context, but it must remain atomic and audit-friendly.

---

## Top-Level Shape

The semantic shape of `AnalysisResult` should be:

```text
AnalysisResult
├── contract
├── identity
├── request_link
├── status
├── decision
├── scores
├── execution_guidance
├── uncertainty_and_quality
├── deterministic_interaction
├── fallback_and_degradation
├── observability
└── lineage
```

This keeps the result compact, explicit, and compatible with the request contract.

---

## 1. Contract

This section identifies the result as a versioned contract artifact.

### Required fields
- `contract_version`
- `response_schema_version`
- `engine_output_version`

### Purpose
These fields make result semantics, compatibility, and evolution explicit.

### Notes
- `contract_version` tracks the request/response boundary family
- `response_schema_version` tracks result meaning
- `engine_output_version` tracks the engine's own output surface evolution

---

## 2. Identity

This section identifies the result instance and the engine instance that produced it.

### Required fields
- `request_id`
- `engine_name`
- `engine_version`
- `timestamp_utc`

### Recommended fields
- `run_id`
- `trace_id`
- `model_artifact_version`
- `calibration_artifact_version`
- `policy_artifact_version`

### Rules
- `request_id` is mandatory because each result must point back to one request
- identity fields must remain stable for review and replay lineage
- artifact versions should be explicit when available

---

## 3. Request Link

This section makes request/result compatibility explicit.

### Recommended fields
- `symbol`
- `primary_interval`
- `request_contract_version`
- `request_kind_seen`

### Purpose
The result must clearly state which request scope it is answering.

### Rules
- these fields are compatibility and audit echoes, not a second request
- they must match the originating request
- runtime should be able to verify consistency

### Required consistency rules
If present:
- `request_link.symbol == request.scope.symbol`
- `request_link.primary_interval == request.scope.primary_interval`
- `identity.request_id == request.identity.request_id`
- `request_link.request_contract_version == request.contract.contract_version`
- `lineage.analysis_batch_id == request.lineage.analysis_batch_id` when both exist
- `lineage.decision_session_id == request.lineage.decision_session_id` when both exist

### Design note
This section exists so later review does not need to reconstruct basic request linkage from logs only.

---

## 4. Status

This section contains the stable runtime-facing status surface.

### Required fields
- `signal_status`
- `decision_status`
- `is_actionable`

### Allowed concepts

#### `signal_status`
- `SIGNAL`
- `NO_TRADE`
- `FILTERED`
- `DEGRADED`
- `ERROR`

#### `decision_status`
- `VALID`
- `LOW_CONFIDENCE`
- `BLOCKED`
- `DEGRADED`
- `FAILED`

### Purpose
Runtime should not have to infer actionability indirectly from low-level scores alone.

### Rules
- `is_actionable` must be explicit
- `NO_TRADE` is first-class, not an absence of output
- degraded or failed states must remain visible

---

## 5. Decision

This section expresses the primary action recommendation.

### Required fields
- `recommended_action`
- `direction`
- `decision_summary`

### Expected conceptual values

#### `recommended_action`
- `LONG_NOW`
- `SHORT_NOW`
- `NO_TRADE`

#### `direction`
- `LONG`
- `SHORT`
- `NONE`

### Rules
- `recommended_action` is the main action surface
- `direction` exists for compatibility and analytics
- `NO_TRADE` must be explicit
- the decision must correspond to the same request scope identified above

---

## 6. Scores

This section contains the comparative decision surface.

### Required core runtime/economic fields
- `confidence`
- `confidence_kind`
- `expected_r`

### Strongly recommended fields
- `probability`
- `expected_drawdown`
- `risk_reward_estimate`
- `decision_margin`
- `long_score`
- `short_score`
- `no_trade_score`

### Optional richer fields
- `raw_confidence`
- `calibrated_confidence`
- `expected_hold_time`
- `expected_edge`

### Purpose
V7 needs both:
- a **runtime opening field**
- an **economic quality field**

### Rules
- `confidence` remains first-class because runtime may open trades using confidence thresholds
- `expected_r` must also be first-class because economic quality matters
- `confidence` does **not** mean automatic execution by itself
- `decision_margin` should express how clearly the chosen action beat alternatives
- `probability` is supportive, not the only decision scalar

### `confidence_kind`
This field should make the score semantics explicit.

Typical values:
- `RAW`
- `CALIBRATED`
- `POLICY_CONFIDENCE`

Runtime and review layers must know what kind of confidence they are reading.

### Unit rule
`expected_r` and `expected_drawdown` should use explicit **R-multiple** semantics unless another unit convention is explicitly declared.

---

## 7. Execution Guidance

This section contains execution-relevant guidance without transferring execution ownership into the engine.

### Required for actionable directional trades
If:
- `recommended_action` is `LONG_NOW` or `SHORT_NOW`
- and `is_actionable = true`

then the following fields should be present:

- `entry_price`
- `stop_loss`
- `take_profit`
- `time_sensitivity`

### Strongly recommended fields
- `entry_zone`
- `size_multiplier`
- `risk_expression`
- `execution_notes`

### Purpose
Execution guidance is first-class because runtime needs explicit trade-shape information, not just a direction.

### Rules
- this section is guidance, not broker execution ownership
- `size_multiplier` is acceptable; absolute final sizing ownership stays outside the engine
- if `recommended_action = NO_TRADE`, execution fields may be null or omitted where allowed
- timing guidance must be explicit for actionable trades

### Timing concepts
Typical `time_sensitivity` concepts:
- `IMMEDIATE`
- `STANDARD`
- `CAN_WAIT`
- `EXPIRING_SOON`

---

## 8. Uncertainty And Quality

This section captures how trustworthy or fragile the decision is.

### Recommended fields
- `uncertainty_score`
- `uncertainty_type`
- `decision_quality`
- `path_quality_expectation`
- `is_ambiguous`
- `quality_flags`

### Purpose
Confidence alone is not enough.
The result must show whether the decision is clean, noisy, uncertain, or ambiguous.

### Example concepts

#### `uncertainty_type`
- `EPISTEMIC`
- `ALEATORIC`
- `MIXED`
- `UNKNOWN`

#### `decision_quality`
- `HIGH`
- `MEDIUM`
- `LOW`
- `AMBIGUOUS`

### Rules
- ambiguity must remain visible
- uncertainty must not be hidden behind one scalar only
- these fields support safer review and later attribution

---

## 9. Deterministic Interaction

This section makes interaction with deterministic guidance explicit.

### Recommended fields
- `deterministic_alignment`
- `deterministic_warning`
- `deterministic_block`
- `deterministic_disagreement_reason`
- `regime_transition_risk`
- `constraint_level`

### Purpose
If deterministic guidance influenced result usability, that interaction must be visible.

### Rules
- no silent deterministic veto
- no hidden suppression
- alignment or disagreement must be reviewable
- deterministic interaction is context, not secret authority

---

## 10. Fallback And Degradation

This section makes degraded behavior explicit.

### Required fields
- `fallback_used`
- `degraded_reason`

### Strongly recommended fields
- `fallback_reason`
- `fallback_source`
- `runtime_safe_action`
- `is_timeout_fallback`
- `is_schema_fallback`

### Purpose
Runtime must not reverse-engineer degraded behavior from logs alone.

### Rules
- `fallback_used` remains first-class
- degraded decisions must remain reviewable
- `runtime_safe_action` may explicitly suggest safe runtime handling such as:
  - `NO_TRADE`
  - `SKIP`
  - `HOLD`

---

## 11. Observability

This section exposes review and audit metadata.

### Strongly recommended fields
- `analysis_latency_ms`
- `reason_summary`
- `warnings`
- `top_feature_groups`
- `review_tags`
- `contract_strictness_used`

### Optional field
- `decision_payload_reference`

### Purpose
Runtime and later review flows need a short stable explanation surface without depending on a giant opaque blob.

### Rules
- `reason_summary` should remain short and human-readable
- large unstable diagnostics must not become required runtime dependencies
- observability fields are helpful but must stay bounded

---

## 12. Lineage

This section connects the atomic result to broader grouped inference flows.

### Recommended fields
- `analysis_batch_id`
- `decision_session_id`
- `batch_rank` (optional)

### Purpose
These fields support:
- centralized scans
- GPU batch inference audit
- replay grouping
- later event/outcome lineage

### Rules
- identity only
- optional for atomic validity
- must match the originating request lineage where applicable

---

## Actionability Matrix

This matrix defines the minimum runtime interpretation rules.

| Case | `recommended_action` | `is_actionable` | Required execution fields | Runtime default interpretation |
|---|---|---:|---|---|
| Valid long | `LONG_NOW` | true | `entry_price`, `stop_loss`, `take_profit`, `time_sensitivity` | Eligible for execution gates |
| Valid short | `SHORT_NOW` | true | `entry_price`, `stop_loss`, `take_profit`, `time_sensitivity` | Eligible for execution gates |
| Explicit skip | `NO_TRADE` | false | none | Do not open trade |
| Low-confidence block | `LONG_NOW` or `SHORT_NOW` | false | optional | Reviewable, not executable |
| Degraded safe skip | any | false | optional | Use `runtime_safe_action` |
| Error/failure | any | false | none | Reject for execution |

This table is semantic guidance for runtime interpretation.

---

## Required vs Optional

### Required in first V7 result
- `contract.contract_version`
- `contract.response_schema_version`
- `identity.request_id`
- `identity.engine_name`
- `identity.engine_version`
- `identity.timestamp_utc`
- `status.signal_status`
- `status.decision_status`
- `status.is_actionable`
- `decision.recommended_action`
- `decision.direction`
- `decision.decision_summary`
- `scores.confidence`
- `scores.confidence_kind`
- `scores.expected_r`
- `fallback_and_degradation.fallback_used`
- `fallback_and_degradation.degraded_reason`

### Required for actionable directional trades
- `execution_guidance.entry_price`
- `execution_guidance.stop_loss`
- `execution_guidance.take_profit`
- `execution_guidance.time_sensitivity`

### Strongly recommended in first V7 result
- `scores.expected_drawdown`
- `scores.decision_margin`
- `scores.long_score`
- `scores.short_score`
- `scores.no_trade_score`
- `execution_guidance.entry_zone`
- `uncertainty_and_quality.uncertainty_score`
- `uncertainty_and_quality.decision_quality`
- `deterministic_interaction.deterministic_alignment`
- `observability.analysis_latency_ms`
- `observability.reason_summary`
- `lineage.analysis_batch_id`
- `lineage.decision_session_id`

### Optional for later controlled expansion
- richer calibration metadata
- candidate decision lists
- alternative action summaries
- broader market summaries
- specialized diagnostics

---

## What Must Not Be In The Result

To keep the contract disciplined, the following must **not** become required runtime dependencies:

### 1. Multiple-request aggregation
One atomic result must not summarize many requests.

### 2. Opaque giant blobs
Runtime must not depend on unstable diagnostics for normal operation.

### 3. Hidden deterministic veto
Suppression must never be implicit.

### 4. Raw training labels
Inference result is not a label artifact.

### 5. Broker execution internals
No raw broker order plumbing as required core fields.

### 6. Portfolio engine internals
The result may expose guidance or visibility, but not absorb full portfolio accounting logic.

---

## Validation Rules

`AnalysisResult` should be validated before runtime consumes it.

At minimum, validation should check:

- required sections and fields exist
- `request_id` exists and matches an originating request
- `symbol` and `primary_interval` in `request_link`, if present, match the originating request
- `recommended_action` and `direction` are internally consistent
- `is_actionable` is consistent with status and degradation fields
- required execution fields exist for actionable directional trades
- `confidence` and `expected_r` are valid numeric fields
- fallback fields are internally consistent
- contract version is supported

### Missing-section behavior
If a required result section is missing or invalid, runtime should reject the result before execution handling.

---

## Example Semantic Shape

```json
{
  "contract": {
    "contract_version": "v7-0.2",
    "response_schema_version": "result-0.2",
    "engine_output_version": "engine-out-0.2"
  },
  "identity": {
    "request_id": "req_123",
    "run_id": "scan_456",
    "engine_name": "v7",
    "engine_version": "0.2.0",
    "timestamp_utc": "2026-04-05T12:00:01Z",
    "model_artifact_version": "model-0.2",
    "calibration_artifact_version": "calib-0.2",
    "policy_artifact_version": "policy-0.2"
  },
  "request_link": {
    "symbol": "BTCUSDT",
    "primary_interval": "4h",
    "request_contract_version": "v7-0.2",
    "request_kind_seen": "live_scan"
  },
  "status": {
    "signal_status": "SIGNAL",
    "decision_status": "VALID",
    "is_actionable": true
  },
  "decision": {
    "recommended_action": "LONG_NOW",
    "direction": "LONG",
    "decision_summary": "Long setup with acceptable timing and supportive context."
  },
  "scores": {
    "confidence": 0.78,
    "confidence_kind": "CALIBRATED",
    "expected_r": 1.35,
    "expected_drawdown": 0.55,
    "risk_reward_estimate": 2.1,
    "decision_margin": 0.42,
    "long_score": 0.81,
    "short_score": 0.10,
    "no_trade_score": 0.18
  },
  "execution_guidance": {
    "entry_price": 104.0,
    "entry_zone": [103.8, 104.3],
    "stop_loss": 101.5,
    "take_profit": 109.0,
    "time_sensitivity": "STANDARD",
    "size_multiplier": 0.75,
    "risk_expression": "MEDIUM"
  },
  "uncertainty_and_quality": {
    "uncertainty_score": 0.21,
    "uncertainty_type": "EPISTEMIC",
    "decision_quality": "MEDIUM",
    "path_quality_expectation": "CLEAN_ENOUGH",
    "is_ambiguous": false,
    "quality_flags": []
  },
  "deterministic_interaction": {
    "deterministic_alignment": "ALIGNED",
    "deterministic_warning": null,
    "deterministic_block": false,
    "deterministic_disagreement_reason": null,
    "regime_transition_risk": 0.12,
    "constraint_level": "ADVISORY"
  },
  "fallback_and_degradation": {
    "fallback_used": false,
    "degraded_reason": null,
    "fallback_reason": null,
    "fallback_source": null,
    "runtime_safe_action": null,
    "is_timeout_fallback": false,
    "is_schema_fallback": false
  },
  "observability": {
    "analysis_latency_ms": 142.0,
    "reason_summary": "Momentum expansion with acceptable volatility and supportive context.",
    "warnings": [],
    "top_feature_groups": ["momentum", "volatility", "htf_alignment"],
    "review_tags": ["trend", "momentum_breakout"]
  },
  "lineage": {
    "analysis_batch_id": "batch_001",
    "decision_session_id": "session_001"
  }
}
```

This example is semantic guidance, not final transport syntax.

---

## Evolution Rules

V7 result evolution should follow these rules:

1. preserve stable runtime-facing fields whenever possible
2. prefer additive fields over breaking renames
3. bump `contract_version` when boundary semantics change materially
4. bump `response_schema_version` when stable result meaning changes materially
5. treat richer diagnostics as optional until proven stable
6. deprecate explicitly rather than silently removing

A stable result contract must remain evolvable.

---

## Final Position

`AnalysisResult` in V7 should stay simple in principle:

- one atomic result for one atomic request
- explicit request linkage
- explicit status and actionability
- explicit recommended action
- confidence as a first-class runtime field
- expected R as a first-class economic field
- explicit entry, stop, take-profit, and timing guidance
- explicit uncertainty, degradation, and deterministic interaction
- optional batch/session lineage
- no hidden execution-control collapse
- no blob-heavy dependency for normal runtime use

This keeps the strongest V6 response principles while aligning the result with V7’s confidence-aware, economically richer, batch-capable direction.
