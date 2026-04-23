# V7 DecisionEvent Contract — Timing Extension Revision

## Purpose

This document defines the revised **`DecisionEvent`** contract for V7.

`DecisionEvent` is the atomic **system-level normalized decision record** created **after** one `AnalysisRequest` has been evaluated into one `AnalysisResult`.

This revision keeps the previous V7 `DecisionEvent` direction and adds support for the revised `AnalysisResult` timing extension:

- `entry_readiness`
- `entry_valid_for_bars`
- optional timing observability echoes

It answers one question:

> After one atomic request is evaluated into one atomic result, what is the canonical event object the rest of the system should persist, compare, review, and later link to execution and outcomes?

---

## Core Position

V7 keeps the strong event principle:

- request and result are not enough by themselves
- the system needs one normalized event object
- that event must be stable, replay-compatible, and linkable to later execution and outcome records

This revision preserves:

1. `DecisionEvent` is not emitted by the model
2. `DecisionEvent` belongs to one atomic request/result pair
3. runtime interpretation is explicit
4. V7 request/result naming stays aligned
5. batch/session lineage remains first-class
6. the event remains small enough to stay stable

And adds:

7. **small timing-readiness echoes from result may be recorded for audit and later evaluation**

---

## Ownership Rule

### Engine owns
- `AnalysisResult`

### Runtime / lifecycle layer owns
- `DecisionEvent`

`DecisionEvent` remains a system lifecycle object, not an engine output object.

---

## Position In The Flow

`AnalysisRequest`
→ `AnalysisResult`
→ `DecisionEvent`
→ optional execution / no-execution path
→ `TradeOutcome`

The event still records what was known and decided at decision time, before hindsight or final outcome knowledge exists.

---

## Request/Result Compatibility Rule

Every valid `DecisionEvent` must correspond to exactly:

- one valid `AnalysisRequest`
- one valid `AnalysisResult`
- one evaluated market state
- one normalized system interpretation

This remains unchanged.

---

## Top-Level Shape

```text
DecisionEvent
├── contract
├── identity
├── lineage
├── scope
├── request_summary
├── decision_summary
├── runtime_interpretation
├── execution_linkage
├── outcome_linkage
├── observability
└── optional_extended_metadata
```

The timing update affects:
- `decision_summary`
- `runtime_interpretation`
- `observability`

---

## 1. Contract

### Required fields
- `event_schema_version`
- `contract_version`
- `request_contract_version`
- `response_schema_version`

### Recommended fields
- `state_schema_version_seen`
- `snapshot_builder_version_seen`

No structural change.

---

## 2. Identity

### Required fields
- `decision_event_id`
- `request_id`
- `timestamp_utc`

### Recommended fields
- `run_id`
- `trace_id`
- `comparison_group_id`

### Canonical location of `comparison_group_id`

`comparison_group_id` is canonically an **identity-level grouping field**.

If later lineage-level comparison metadata is added, identity remains the source of truth for the event’s comparison grouping.

---

## 3. Lineage

### Required fields
- `engine_name`
- `engine_version`
- `request_kind`
- `analysis_batch_id` (nullable)
- `decision_session_id` (nullable)

### Strongly recommended fields
- `model_artifact_version`
- `calibration_artifact_version`
- `policy_artifact_version`

### Optional fields
- `portfolio_artifact_version`
- `risk_policy_version`
- `candidate_source`
- `replay_mode`
- `deterministic_annotation_version`
- `batch_rank`

No structural change.

---

## 4. Scope

### Required fields
- `symbol`
- `primary_interval`
- `analysis_mode`

### Optional fields
- `exchange`
- `market_type`

No structural change.

---

## 5. Request Summary

### Recommended fields
- `request_timestamp_utc`
- `state_timestamp_utc`
- `state_window_length`
- `state_schema_version_seen`
- `snapshot_builder_version_seen`
- `state_views_seen`
- `stale_flag`
- `snapshot_validity`
- `data_source`
- `htf_bias`
- `regime_label`
- `regime_confidence`
- `risk_flags`
- `paper_or_live_mode`
- `engine_budget_hint`

No structural change.

---

## 6. Decision Summary

This section stores the normalized meaning of the result.

### Required fields
- `signal_status`
- `decision_status`
- `is_actionable`
- `recommended_action`
- `direction`

### Strongly recommended fields
- `confidence`
- `confidence_kind`
- `expected_r`
- `expected_drawdown`
- `decision_margin`
- `long_score`
- `short_score`
- `no_trade_score`
- `reason_summary`

### Timing echo fields
- `entry_price_seen`
- `stop_loss_seen`
- `take_profit_seen`
- `time_sensitivity_seen`
- `entry_readiness_seen`
- `entry_valid_for_bars_seen`

### Optional timing field
- `entry_expiry_utc_seen`

### Purpose
This remains the event’s operational core, now with small timing-readiness echoes from the result.

### Rules
- use V7 result semantics
- `expected_r` stays preferred over `expected_return`
- timing echoes are summaries of what the result said at decision time
- timing echoes must not be re-inferred later from hindsight

---

## 7. Runtime Interpretation

### Recommended fields
- `runtime_actionability`
- `deterministic_alignment`
- `deterministic_block`
- `fallback_used`
- `degraded_reason`
- `runtime_safe_action`
- `policy_passed`
- `portfolio_blocked`
- `risk_blocked`
- `suppression_reason`
- `should_persist_as_signal`
- `should_surface_to_review`

### Timing-related optional fields
- `entry_timing_observed`
- `entry_timing_used_for_gate`
- `entry_timing_gate_reason`

### Purpose
The event should show not only what the result said, but whether runtime used or ignored the timing extension.

### Rules
- timing use must be explicit if runtime operationalizes it
- in the first rollout, `entry_timing_used_for_gate` will usually be false
- no silent timing-based suppression

---

## 8. Execution Linkage

### Recommended fields
- `execution_path`
- `execution_decision`
- `order_group_id`
- `paper_trade_id`
- `position_id`
- `execution_reference_ids`

No structural change.

---

## 9. Outcome Linkage

### Recommended fields
- `trade_outcome_id`
- `outcome_status`
- `label_status`
- `outcome_horizon_family`
- `outcome_ready_timestamp_utc`

No structural change.

---

## 10. Observability

### Strongly recommended fields
- `analysis_latency_ms`
- `warnings`
- `quality_flags`
- `uncertainty_type`
- `decision_quality`
- `regime_transition_risk`
- `review_tags`
- `payload_references`

### Timing observability fields
- `timing_extension_present`
- `timing_review_tags`

### Purpose
These fields make it easy to review how often timing information appeared and whether it was useful.

### Rules
- keep observability compact
- do not turn the event into a debug blob
- timing review tags should remain small and human-usable

### `timing_review_tags` convention

Suggested initial values:
- `ready_now`
- `wait_preferred`
- `chasing_entry`
- `expiring_setup`
- `missed_setup`

These are review-facing conventions, not hard runtime enums.

---

## Request/Result/Event Consistency Rules

The event must preserve consistency with the originating request and result.

### Required consistency
- `identity.request_id == request.identity.request_id == result.identity.request_id`
- `scope.symbol == request.scope.symbol`
- `scope.primary_interval == request.scope.primary_interval`
- `scope.analysis_mode == request.scope.analysis_mode`
- `decision_summary.recommended_action == result.decision.recommended_action`
- `decision_summary.direction == result.decision.direction`
- `decision_summary.is_actionable == result.status.is_actionable`
- `decision_summary.confidence == result.scores.confidence` when surfaced
- `decision_summary.expected_r == result.scores.expected_r` when surfaced
- `decision_summary.entry_readiness_seen == result.execution_guidance.entry_readiness` when surfaced
- `decision_summary.entry_valid_for_bars_seen == result.execution_guidance.entry_valid_for_bars` when surfaced
- `decision_summary.time_sensitivity_seen == result.execution_guidance.time_sensitivity` when surfaced
- `lineage.analysis_batch_id == request.lineage.analysis_batch_id == result.lineage.analysis_batch_id` when present
- `lineage.decision_session_id == request.lineage.decision_session_id == result.lineage.decision_session_id` when present

### Allowed transformation
The event may:
- summarize
- normalize
- classify
- add runtime interpretation
- add linkage fields

The event may **not** silently rewrite engine decision meaning.

---

## Required vs Optional

### Required in first V7 event contract
- `contract.event_schema_version`
- `contract.contract_version`
- `contract.request_contract_version`
- `contract.response_schema_version`
- `identity.decision_event_id`
- `identity.request_id`
- `identity.timestamp_utc`
- `lineage.engine_name`
- `lineage.engine_version`
- `lineage.request_kind`
- `scope.symbol`
- `scope.primary_interval`
- `scope.analysis_mode`
- `decision_summary.signal_status`
- `decision_summary.decision_status`
- `decision_summary.is_actionable`
- `decision_summary.recommended_action`
- `decision_summary.direction`

### Strongly recommended in first V7 event contract
- `request_summary.stale_flag`
- `request_summary.regime_label`
- `decision_summary.confidence`
- `decision_summary.confidence_kind`
- `decision_summary.expected_r`
- `decision_summary.reason_summary`
- `decision_summary.time_sensitivity_seen`
- `decision_summary.entry_readiness_seen`
- `decision_summary.entry_valid_for_bars_seen`
- `runtime_interpretation.deterministic_alignment`
- `runtime_interpretation.fallback_used`
- `runtime_interpretation.policy_passed`
- `execution_linkage.execution_path`
- `outcome_linkage.outcome_status`
- `observability.analysis_latency_ms`
- `observability.timing_extension_present`
- `lineage.analysis_batch_id`
- `lineage.decision_session_id`

### Optional for later evolution
- `decision_summary.entry_expiry_utc_seen`
- `runtime_interpretation.entry_timing_used_for_gate`
- `runtime_interpretation.entry_timing_gate_reason`
- richer execution references
- richer outcome references
- specialist metadata

---

## Validation Rules

`DecisionEvent` should be validated before it is persisted or published.

At minimum, validation must check:

- required sections and fields exist
- request lineage is resolvable
- result-derived decision fields are internally consistent
- `execution_path` and `execution_decision` do not contradict `decision_summary.is_actionable`
- `fallback_used` and degraded interpretation fields are internally consistent
- deterministic block/alignment fields do not contradict visible actionability
- outcome linkage fields use legal state transitions
- batch/session lineage is consistent with originating request/result when present
- timing echoes, if present, match originating result fields

---

## Example Semantic Shape

```json
{
  "contract": {
    "event_schema_version": "decision-event-0.3",
    "contract_version": "v7-0.3",
    "request_contract_version": "v7-0.2",
    "response_schema_version": "result-0.3",
    "state_schema_version_seen": "state-0.2",
    "snapshot_builder_version_seen": "snapshot-0.2"
  },
  "identity": {
    "decision_event_id": "de_123",
    "request_id": "req_123",
    "run_id": "scan_456",
    "trace_id": "trace_999",
    "comparison_group_id": "cmp_abc",
    "timestamp_utc": "2026-04-05T12:00:01Z"
  },
  "lineage": {
    "engine_name": "v7",
    "engine_version": "0.3.0",
    "request_kind": "live_scan",
    "analysis_batch_id": "batch_001",
    "decision_session_id": "session_001",
    "model_artifact_version": "model-0.3",
    "calibration_artifact_version": "calib-0.3",
    "policy_artifact_version": "policy-0.3"
  },
  "scope": {
    "symbol": "BTCUSDT",
    "primary_interval": "4h",
    "analysis_mode": "live",
    "exchange": "BINANCE",
    "market_type": "PERP"
  },
  "request_summary": {
    "request_timestamp_utc": "2026-04-05T12:00:00Z",
    "state_timestamp_utc": "2026-04-05T12:00:00Z",
    "state_window_length": 256,
    "state_schema_version_seen": "state-0.2",
    "snapshot_builder_version_seen": "snapshot-0.2",
    "state_views_seen": {
      "primary": "4h",
      "higher_timeframe": "1d"
    },
    "stale_flag": false,
    "snapshot_validity": "VALID",
    "data_source": "fresh_exchange",
    "htf_bias": "BULLISH",
    "regime_label": "TRENDING",
    "regime_confidence": 0.82,
    "risk_flags": [],
    "paper_or_live_mode": "PAPER",
    "engine_budget_hint": "low_latency_live"
  },
  "decision_summary": {
    "signal_status": "SIGNAL",
    "decision_status": "VALID",
    "is_actionable": true,
    "recommended_action": "LONG_NOW",
    "direction": "LONG",
    "confidence": 0.78,
    "confidence_kind": "CALIBRATED",
    "expected_r": 1.35,
    "expected_drawdown": 0.55,
    "decision_margin": 0.42,
    "long_score": 0.81,
    "short_score": 0.10,
    "no_trade_score": 0.18,
    "reason_summary": "Momentum expansion with acceptable risk and supportive context.",
    "entry_price_seen": 104.0,
    "stop_loss_seen": 101.5,
    "take_profit_seen": 109.0,
    "time_sensitivity_seen": "EXPIRING_SOON",
    "entry_readiness_seen": "CHASING",
    "entry_valid_for_bars_seen": 1
  },
  "runtime_interpretation": {
    "runtime_actionability": "ACTIONABLE",
    "deterministic_alignment": "ALIGNED",
    "deterministic_block": false,
    "fallback_used": false,
    "degraded_reason": null,
    "runtime_safe_action": null,
    "policy_passed": true,
    "portfolio_blocked": false,
    "risk_blocked": false,
    "suppression_reason": null,
    "should_persist_as_signal": true,
    "should_surface_to_review": true,
    "entry_timing_observed": true,
    "entry_timing_used_for_gate": false,
    "entry_timing_gate_reason": null
  },
  "execution_linkage": {
    "execution_path": "PAPER_EXECUTED",
    "execution_decision": "EXECUTED",
    "order_group_id": "ordgrp_1",
    "paper_trade_id": "paper_123",
    "position_id": null,
    "execution_reference_ids": []
  },
  "outcome_linkage": {
    "trade_outcome_id": null,
    "outcome_status": "PENDING",
    "label_status": "NOT_LABELED",
    "outcome_horizon_family": "short_medium",
    "outcome_ready_timestamp_utc": null
  },
  "observability": {
    "analysis_latency_ms": 142.0,
    "warnings": [],
    "quality_flags": [],
    "uncertainty_type": "EPISTEMIC",
    "decision_quality": "MEDIUM",
    "regime_transition_risk": 0.12,
    "review_tags": ["trend", "momentum_breakout"],
    "payload_references": {},
    "timing_extension_present": true,
    "timing_review_tags": ["chasing_entry"]
  },
  "optional_extended_metadata": {}
}
```

This example is semantic guidance, not final transport syntax.

---

## Final Position

`DecisionEvent` remains the object that turns inference from a transient engine call into a system-level fact.

This revision keeps that role intact while making one more thing visible:

- what the result said about **current entry quality**
- whether runtime merely observed it or used it operationally

That is enough to support later timing analysis without turning the event into a heavy execution-planning object.
