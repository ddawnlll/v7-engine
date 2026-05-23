# Phase 1 — Contracts & Hybrid Validation (Planned)

**Status:** Planned  
**Owner:** Contracts / interface track  
**Last updated:** 2026-05-23  
**Delivery status:** Not started

---

## 1. Purpose

Implement the four V7 lifecycle contracts as typed runtime surfaces and make the hybrid model outputs explicit and validateable.

This phase prevents later stages from passing ad hoc dicts or hiding required score surfaces.

---

## 2. Stable Contract Family

Implement:

- `AnalysisRequest`
- `AnalysisResult`
- `DecisionEvent`
- `TradeOutcome`

Request/result are engine-facing. Event/outcome are system-facing.

---

## 3. Workstream A — Typed Contract Objects

### `AnalysisRequest`

Minimum fields:

- `request_id`
- `contract_version`
- `symbol`
- `model_scope` (SWING | SCALP | AGGRESSIVE_SCALP)
- `requested_trade_mode` (maps to model_scope)
- `primary_interval` (per mode: 4h/1h/15m)
- `context_intervals` (per mode: 1d/4h/1h)
- `refinement_intervals` (per mode: 1h/15m/5m)
- `state_timestamp_utc`
- `feature_schema_version`
- `label_horizon_family`
- `simulation_profile_version` (mode-specific)
- `runtime_context`
- degradation / missingness flags where relevant

### `AnalysisResult`

Must support hybrid output surfaces:

- `result_id`
- `request_id`
- `contract_version`
- `response_schema_version`
- `model_scope`
- `artifact_id`
- `calibration_artifact_id`
- `recommended_action`
- `is_actionable`
- `action_probabilities`
  - `LONG_NOW`
  - `SHORT_NOW`
  - `NO_TRADE`
- `confidence`
- `confidence_kind`
- `expected_r_by_action`
  - `LONG_NOW`
  - `SHORT_NOW`
- `expected_drawdown_r_by_action` where available
- `expected_cost_adjusted_r_by_action` where available
- `policy_gate_status`
- `policy_reason_codes`
- `entry_readiness`
- `entry_valid_for_bars`
- `degradation_flags`

### `DecisionEvent`

Must snapshot final decision and supporting hybrid surfaces:

- request/result lineage
- model/calibration/policy artifact lineage
- action probabilities observed
- expected-R surfaces observed
- policy gates observed
- portfolio/risk suppression state
- runtime interpretation

### `TradeOutcome`

Must support later comparison between:

- projected probabilities
- projected expected R
- realized outcome R
- realized exit reason
- no-trade / missed-opportunity / saved-loss evidence

### Acceptance Criteria

- [ ] all four typed objects exist.
- [ ] hybrid output fields are explicit.
- [ ] required vs optional fields are clear.
- [ ] version fields are represented explicitly.

---

## 4. Workstream B — Contract Validation

Validators must check:

- required field presence
- enum legality
- numeric bounds
- probabilities sum within configured tolerance
- no negative or impossible probability values
- expected-R values are numeric or explicitly unavailable
- `model_scope` compatibility
- artifact/calibration/policy bundle compatibility
- timing extension bounds
- actionability vs execution eligibility separation

### Timing validation defaults

- `entry_valid_for_bars` integer range: `0–5`
- `entry_readiness` legal enum only
- `entry_expiry_utc`, if present, parses as UTC

### Hybrid validation defaults

- `recommended_action` must be in `LONG_NOW`, `SHORT_NOW`, `NO_TRADE`.
- `action_probabilities` must include all three actions.
- If a directional action is actionable, its expected-R surface must be present unless result is explicitly degraded.
- Raw confidence must never be mislabeled as calibrated confidence.

### Acceptance Criteria

- [ ] invalid objects fail before downstream use.
- [ ] scope mismatch fails or routes to documented degraded-safe behavior.
- [ ] invalid hybrid surfaces cannot silently pass.

---

## 5. Workstream C — Serialization / Round-Trip

Implement:

```python
obj.to_dict()
ContractType.from_dict(payload)
```

Version compatibility rule:

- major contract-family mismatch fails
- same-family newer minor versions may load only if active required fields exist
- unknown optional fields are preserved or explicitly ignored, never reinterpreted silently

### Acceptance Criteria

- [ ] request/result/event/outcome round-trip safely.
- [ ] unknown or unsupported versions fail clearly.
- [ ] hybrid fields survive round-trip.

---

## 6. Workstream D — Test Coverage

Minimum tests:

- required/optional field tests
- hybrid `AnalysisResult` shape tests
- action probability validation tests
- expected-R availability tests
- confidence kind tests
- request/result/event/outcome linkage tests
- scope-compatible artifact bundle tests
- timing field validation tests
- serialization round-trip tests

---

## 7. Pre-Run Audit

Before Phase 2:

- [ ] no active V7 flow depends on unvalidated dict payloads
- [ ] all hybrid result fields have defined names and types
- [ ] scope mismatch cannot silently fall through to another artifact
- [ ] raw vs calibrated confidence distinction is test-covered

---

## 8. Definition of Done

- [ ] typed contract objects exist.
- [ ] validators exist for all four contracts.
- [ ] hybrid result validation exists.
- [ ] serialization works.
- [ ] tests pass.

---

## 9. What Phase 2 Inherits

Phase 2 inherits trusted typed objects that can carry simulation lineage and later hybrid model outputs without schema guessing.
