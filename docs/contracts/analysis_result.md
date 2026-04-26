# V7 AnalysisResult Contract — Timing Extension Revision

## Purpose

This document defines the revised **`AnalysisResult`** contract for V7.

`AnalysisResult` is the atomic **engine-to-runtime analysis output** contract.

It answers one question:

> What exact analysis result must the engine return so runtime can interpret, review, persist, and safely act on one evaluated market state?

This revision keeps the existing V7 response direction and adds a small, explicit **entry-timing surface** so the system can distinguish:

- a good directional thesis with a good current entry
- a good directional thesis with a weak or late current entry
- a setup that is still alive but expiring
- a setup that is no longer meaningfully enterable

This document defines **analysis output semantics only**.

---

## Core Position

V7 keeps the strong response principle:

- one request
- one result
- one evaluated market state
- one explicit runtime-facing decision surface

This revision preserves:

1. **the result belongs to one atomic `AnalysisRequest`**
2. **confidence remains a first-class runtime opening field**
3. **economic quality fields such as `expected_r` remain first-class**
4. **execution guidance and timing remain explicit**
5. **degradation, fallback, and deterministic interaction remain visible**

And adds one more principle:

6. **current entry readiness should be explicit without turning the result into a complex execution planner**

The result remains a **runtime-usable decision contract**, not a broker execution object.

---

## Request Compatibility Rule

Every valid `AnalysisResult` must correspond to exactly **one** valid `AnalysisRequest`.

That means:

- one `request_id`
- one `symbol`
- one `primary_interval`
- one atomic evaluated market state (which may include fused multi-view state like 1h and 1d)
- one engine result surface (a fused unified decision, not an average of separate interval-specific results)

If multiple atomic requests are analyzed together, that belongs to:

- `AnalysisBatchRequest`
- `AnalysisBatchResult`
- `DecisionSession`

not to the atomic `AnalysisResult`.

This remains aligned with the V7 request contract’s atomic rule and interval-aware-but-still-atomic scope.

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

The engine may say:
- this is a valid long thesis
- this is still enterable
- this is already chasing
- this setup is expiring

But runtime still owns the final execution decision.

---

## Top-Level Shape

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

The new timing extension lives inside `execution_guidance`.

---

## 1. Contract

### Required fields
- `contract_version`
- `response_schema_version`
- `engine_output_version`

No change from the prior V7 result revision.

---

## 2. Identity

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

No change from the prior V7 result revision.

---

## 3. Request Link

### Recommended fields
- `symbol`
- `primary_interval`
- `request_contract_version`
- `request_kind_seen`

### Required consistency rules
If present:
- `request_link.symbol == request.scope.symbol`
- `request_link.primary_interval == request.scope.primary_interval`
- `identity.request_id == request.identity.request_id`
- `request_link.request_contract_version == request.contract.contract_version`
- `lineage.analysis_batch_id == request.lineage.analysis_batch_id` when both exist
- `lineage.decision_session_id == request.lineage.decision_session_id` when both exist

No change from the prior V7 result revision.

---

## 4. Status

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

No change from the prior V7 result revision.

---

## 5. Decision

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

No change from the prior V7 result revision.

---

## 6. Scores

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

### Rules
- `confidence` remains first-class because runtime may open trades using confidence thresholds
- `expected_r` remains first-class because economic quality matters
- `confidence` does **not** mean automatic execution by itself
- `probability` is supportive, not the only decision scalar

No change from the prior V7 result revision.

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
- `entry_readiness`
- `entry_valid_for_bars`
- `size_multiplier`
- `risk_expression`
- `execution_notes`

### Optional timing field
- `entry_expiry_utc`

### Purpose

Execution guidance is first-class because runtime needs explicit trade-shape information, not just a direction.

This revision adds a **small timing surface**. The goal is **not** to predict a perfect oracle entry timestamp. The goal is to tell runtime and review systems whether the trade is:

- currently enterable
- better to wait on
- already chasing
- expiring
- likely missed

### Rules
- this section is guidance, not broker execution ownership
- `size_multiplier` is acceptable; absolute final sizing ownership stays outside the engine
- if `recommended_action = NO_TRADE`, execution fields may be null or omitted where allowed
- timing guidance must be explicit for actionable trades
- timing fields should remain small and bounded, not a full execution planner

### Timing concepts

#### `time_sensitivity`
- `IMMEDIATE`
- `STANDARD`
- `CAN_WAIT`
- `EXPIRING_SOON`

#### `entry_readiness`
- `READY_NOW`
- `WAIT`
- `CHASING`
- `EXPIRING`
- `MISSED`
- `NOT_APPLICABLE`

*Note: In first-phase V7, 1h refinement context primarily influences entry timing, time sensitivity, and `entry_readiness` fields, rather than acting as a separate primary decision family.*

### `entry_valid_for_bars`

This field expresses how many future analysis bars the current entry thesis is expected to remain valid for, under the engine’s current view.

Examples:
- `0` = valid only now or effectively expiring now
- `1` = likely valid through one more analysis step
- `2` = likely valid through two more analysis steps

This is a bounded advisory field, not a guarantee.

### Bound convention for `entry_valid_for_bars`

First V7 convention:
- legal range: **0 to 5**
- values above `5` should not be emitted in the first contract version
- if the engine believes the setup is valid for longer than that, cap it at `5`

This keeps the field compact and comparable across strategies.

### Design rule for timing extension

The timing extension should remain **advisory-first** in the first rollout.

That means:
- it should be visible in the contract
- it should be persisted and reviewed
- runtime may log and inspect it
- runtime does **not** have to hard-gate on it immediately

This keeps complexity controlled while still making the signal measurable.

---

## 8. Uncertainty And Quality

### Recommended fields
- `uncertainty_score`
- `uncertainty_type`
- `decision_quality`
- `path_quality_expectation`
- `is_ambiguous`
- `quality_flags`

No structural change from the prior V7 result revision.

---

## 9. Deterministic Interaction

### Recommended fields
- `deterministic_alignment`
- `deterministic_warning`
- `deterministic_block`
- `deterministic_disagreement_reason`
- `regime_transition_risk`
- `constraint_level`

No structural change from the prior V7 result revision.

---

## 10. Fallback And Degradation

### Required fields
- `fallback_used`
- `degraded_reason`

### Strongly recommended fields
- `fallback_reason`
- `fallback_source`
- `runtime_safe_action`
- `is_timeout_fallback`
- `is_schema_fallback`

No structural change from the prior V7 result revision.

---

## 11. Observability

### Strongly recommended fields
- `analysis_latency_ms`
- `reason_summary`
- `warnings`
- `top_feature_groups`
- `review_tags`
- `contract_strictness_used`

### Optional field
- `decision_payload_reference`

### `contract_strictness_used`

This field records which contract-validation or boundary strictness mode the engine/result pipeline assumed when producing the result.

Suggested values:
- `STRICT`
- `DEGRADED_ALLOWED`
- `SHADOW_RELAXED`

Meaning:
- `STRICT` = full contract expectations assumed
- `DEGRADED_ALLOWED` = degraded but still legal result path allowed
- `SHADOW_RELAXED` = non-production comparison or shadow path with looser non-core expectations

This helps review systems understand whether the result came from a strict production path or a relaxed comparison path.

---

## 12. Lineage

### Recommended fields
- `analysis_batch_id`
- `decision_session_id`
- `batch_rank` (optional)

No structural change from the prior V7 result revision.

---

## Actionability Matrix

| Case | `recommended_action` | `is_actionable` | `entry_readiness` | Required execution fields | Runtime default interpretation |
|---|---|---:|---|---|---|
| Valid long | `LONG_NOW` | true | `READY_NOW`, `WAIT`, `CHASING`, or `EXPIRING` | `entry_price`, `stop_loss`, `take_profit`, `time_sensitivity` | Eligible for execution gates |
| Valid short | `SHORT_NOW` | true | `READY_NOW`, `WAIT`, `CHASING`, or `EXPIRING` | `entry_price`, `stop_loss`, `take_profit`, `time_sensitivity` | Eligible for execution gates |
| Explicit skip | `NO_TRADE` | false | `NOT_APPLICABLE` | none | Do not open trade |
| Low-confidence block | `LONG_NOW` or `SHORT_NOW` | false | optional | optional | Reviewable, not executable |
| Degraded safe skip | any | false | optional | optional | Use `runtime_safe_action` |
| Error/failure | any | false | optional | none | Reject for execution |

This matrix is semantic guidance for runtime interpretation.

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
- `execution_guidance.entry_zone`
- `execution_guidance.entry_readiness`
- `execution_guidance.entry_valid_for_bars`
- `scores.expected_drawdown`
- `scores.decision_margin`
- `scores.long_score`
- `scores.short_score`
- `scores.no_trade_score`
- `uncertainty_and_quality.uncertainty_score`
- `uncertainty_and_quality.decision_quality`
- `deterministic_interaction.deterministic_alignment`
- `observability.analysis_latency_ms`
- `observability.reason_summary`
- `lineage.analysis_batch_id`
- `lineage.decision_session_id`

### Optional for later controlled expansion
- `execution_guidance.entry_expiry_utc`
- richer calibration metadata
- candidate decision lists
- alternative action summaries
- broader market summaries
- specialized diagnostics

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
- `entry_valid_for_bars`, if present, is an integer in the range `0..5`
- `entry_readiness`, if present, is a legal enum value
- fallback fields are internally consistent
- contract version is supported

---

## Example Semantic Shape

```json
{
  "contract": {
    "contract_version": "v7-0.3",
    "response_schema_version": "result-0.3",
    "engine_output_version": "engine-out-0.3"
  },
  "identity": {
    "request_id": "req_123",
    "run_id": "scan_456",
    "engine_name": "v7",
    "engine_version": "0.3.0",
    "timestamp_utc": "2026-04-05T12:00:01Z",
    "model_artifact_version": "model-0.3",
    "calibration_artifact_version": "calib-0.3",
    "policy_artifact_version": "policy-0.3"
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
    "time_sensitivity": "EXPIRING_SOON",
    "entry_readiness": "CHASING",
    "entry_valid_for_bars": 1,
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

## Runtime Impact And Required Changes

Yes — this revision creates **some additional runtime load**, but it should be **small and manageable** if rollout stays advisory-first.

### What increases

Runtime now has to:

1. **validate two extra timing fields**
   - `entry_readiness`
   - `entry_valid_for_bars`

2. **persist two extra fields**
   - in event/outcome lineage or downstream review surfaces

3. **surface these fields in logs/review tooling**
   - so the team can measure whether they are useful

4. **optionally incorporate them later into execution gating**
   - but only after evidence exists

### What should not happen immediately

Runtime should **not** immediately become a complex timing planner.

Do not add:
- best-entry search logic
- oracle timing backfills in runtime
- large action-family branching
- heavy extra control flow based on many timing states

### Recommended runtime changes

#### Phase 1 — Contract acceptance
- update result validators for:
  - `entry_readiness`
  - `entry_valid_for_bars`
- update persistence schemas
- update logging/review serialization
- no hard execution gating yet

#### Phase 2 — Observability only
- record these fields in `DecisionEvent` or related review surfaces
- compare:
  - `READY_NOW` vs later outcome quality
  - `CHASING` vs later regret
  - `EXPIRING` vs missed-opportunity patterns

#### Phase 3 — Optional gating
Only after evidence exists, allow runtime to use these in the execution eligibility layer.

Examples:
- suppress execution when `entry_readiness = MISSED`
- weaken execution when `entry_readiness = CHASING`
- require `entry_valid_for_bars > 0` for certain strategies

### Suggested config additions

If runtime later uses these fields operationally, add config-driven controls such as:

- `enable_entry_timing_observability`
- `enable_entry_readiness_gate`
- `blocked_entry_readiness_states`
- `min_entry_valid_for_bars`
- `entry_timing_gate_mode`

These should go through the existing unified config system, not be hardcoded.

### Net runtime cost assessment

#### Low cost
- validation
- persistence
- logging
- analytics

#### Medium cost
- optional gating logic
- review tooling updates

#### High cost only if you over-expand it
- oracle-like timing planner
- heavy multi-step action families
- runtime-side entry optimization

So the real answer is:

**yes, runtime load increases slightly**
but
**no, it does not have to become a major runtime burden if the feature stays small and advisory-first**

---

## Final Position

`AnalysisResult` in this revision should stay simple in principle:

- one atomic result for one atomic request
- confidence as a first-class runtime field
- expected R as a first-class economic field
- explicit entry, stop, take-profit, and timing guidance
- small explicit timing extension:
  - `entry_readiness`
  - `entry_valid_for_bars`
- advisory-first rollout
- no hidden execution-control collapse
- no blob-heavy dependency for normal runtime use

This keeps the strongest V7 response principles while making current entry quality more visible without turning the contract into a complex execution planner.
