# Phase 9 — Deployment Safety & Release Readiness (Planned)

**Status:** Planned  
**Owner:** Release / runtime safety track  
**Last updated:** 2026-05-23  
**Delivery status:** Not started

---

## 1. Purpose

Turn a functioning and measured V7 hybrid system into a release-ready system with safety gates, rollback, kill switch, and controlled rollout modes.

Good evaluation is not the same as safe operational authority.

---

## 2. Stable Rules

- Release eligibility is per `model_scope`.
- Candidate artifact, evaluation-promotable artifact, and live-eligible authority are distinct.
- Shadow is required for first live-eligible release unless explicitly waived.
- Hybrid artifact bundles must rollback as compatible bundles.
- Timing remains advisory-first unless Phase 8 evidence and config approve gating.

---

## 3. Workstream A — Rollout Modes

Implement:

- replay-only
- paper
- shadow
- live-eligible

Release authority rule:

- one named release owner
- one named runtime/control reviewer
- shadow waiver requires both approvals plus written rationale in release record

### Acceptance Criteria

- [ ] rollout modes are distinguishable in code/config.
- [ ] first live-eligible path requires shadow unless waived.
- [ ] execution authority changes by mode are explicit.

---

## 4. Workstream B — Hybrid Bundle Rollback

Active release authority is a scope-compatible bundle:

```python
model_scope
action_classifier_artifact
expected_r_long_regressor_artifact
expected_r_short_regressor_artifact
optional_risk_regressor_artifacts
calibration_artifact
expected_r_reliability_artifact
policy_artifact
feature_schema_version
label_interpretation_version
simulation_profile_version
```

Rollback must restore a compatible bundle. Do not permit partial activation of incompatible classifier/regressor/calibration/policy combinations.

### Acceptance Criteria

- [ ] rollback restores complete hybrid bundle.
- [ ] incompatible partial activation is rejected.
- [ ] rollback lineage is preserved.

---

## 5. Workstream C — Kill Switch & Execution Disable

While kill switch is active:

- requests may still be built
- results may still be recorded if policy allows
- `DecisionEvent` creation remains available
- execution is blocked
- `TradeOutcome` remains compatible with non-execution or unavailable execution outcome

### Acceptance Criteria

- [ ] kill switch blocks execution.
- [ ] lifecycle recording remains intact.
- [ ] non-execution outcome semantics remain valid.

---

## 6. Workstream D — Live-Eligibility Gate

Live eligibility requires:

```python
evaluation_pass = True
hybrid_surface_quality_pass = True
monitoring_baseline_ready = True
fallback_policy_ready = True
kill_switch_ready = True
rollback_ready = True
bundle_compatibility_pass = True
```

Hybrid-specific checks:

- calibrated confidence is present or explicitly downgraded by policy
- expected-R reliability is above configured minimum or policy downgrades expected-R use
- no classifier/regressor artifact mismatch
- no stale calibration artifact
- no stale expected-R reliability artifact

Timing gate default:

```python
entry_timing_gate_enabled = False
```

### Acceptance Criteria

- [ ] live-eligibility gate is executable.
- [ ] hybrid artifact consistency is enforced.
- [ ] release gate distinguishes evaluation promotion from live authority.

---

## 7. Workstream E — Test Coverage

Minimum tests:

- paper mode
- shadow mode
- live-eligibility rejection
- kill switch
- rollback
- dependency-compatible hybrid rollback
- incomplete candidate rejected from live eligibility
- stale calibration rejected or downgraded
- stale expected-R reliability rejected or downgraded
- timing hard-gate disabled by default
- kill-switch lifecycle recording behavior

---

## 8. Pre-Deploy Audit

Before first live-eligible release attempt:

- [ ] kill switch operational end to end
- [ ] rollback operational end to end
- [ ] evaluation gate passed on real candidate evidence
- [ ] hybrid-surface quality gate passed
- [ ] monitoring baseline designated and retained
- [ ] release authority named and documented
- [ ] live eligibility distinct from candidate promotion
- [ ] rollback bundle compatibility preserved

---

## 9. Definition of Done

- [ ] rollout mode controls exist.
- [ ] live-eligibility gate exists.
- [ ] kill switch works.
- [ ] hybrid rollback bundle compatibility is enforced.
- [ ] release authority is documented and test-backed.
- [ ] tests pass.

---

## 10. What Comes After Phase 9

After Phase 9, V7 can expand carefully:

- broader symbol-universe activation
- additional scopes
- specialist/model-family experiments
- timing-gate promotion if evidence supports it
- advanced portfolio/risk only after first safe live-eligible slice

Post-Phase 9 expansion must not create a new contract family automatically.
