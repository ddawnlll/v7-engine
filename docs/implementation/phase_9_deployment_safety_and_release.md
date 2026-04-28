
# Phase 9 — Deployment Safety & Release Readiness (Planned)

**Status:** Planned
**Owner:** Release / runtime safety track
**Last updated:** 2026-04-24
**Delivery status:** Not started

---

## 1. Purpose

This phase turns a functioning and measured V7 system into a release-ready system with safety gates, rollback, and controlled rollout modes.

It solves the problem that good evaluation is not the same as safe operational authority.

---

## 2. What Carried Over / What Must Stay Stable

The following are already implemented / must remain stable:

- [x] contract family exists
- [x] runtime lifecycle exists
- [x] evaluation and monitoring evidence exist from Phase 8
- [x] fallback and deployment-safety docs define the target behavior

This phase builds on top of these. Do not regress them.

---

## 3. Background & Motivation

Without this phase:
- live eligibility stays ambiguous
- rollback may exist only in theory
- kill switch may not be proven
- promoted models may not be operationally safe

This phase closes that gap.

---

## 4. Current Failure State / Known Blockers

The current state has the following known issues:

- `paper / shadow / live progression` = may not yet be enforced
- `kill switch` = may not yet be proven in flow
- `rollback` = may not yet preserve dependency compatibility
- `live-eligibility gate` = may not yet exist as executable logic
- `release authority` = may still be manual and under-specified

---

## 5. Workstream A — Rollout Modes

**Status:** New

### Problem / Goal

Implement the controlled progression from replay to paper to shadow to live-eligible.

Release eligibility is per `model_scope`; do not infer `SCALP` safety from `SWING` success or `AGGRESSIVE_SCALP` safety from `SCALP` success.

### Release authority rule

First implementation default:
- one named release owner
- one named runtime/control reviewer
- shadow waiver requires both approvals plus written rationale in release record

This replaces vague “higher-level release policy” wording with a concrete minimum rule.

### Implementation Tasks

- [ ] Implement rollout mode config/control surface
- [ ] Implement paper mode guarantees
- [ ] Implement shadow mode guarantees
- [ ] Implement live-eligibility gating surface

### Acceptance Criteria

- [ ] replay, paper, shadow, and live-eligible are distinguishable in code/config
- [ ] first live-eligible path requires shadow unless explicit release authority waives it
- [ ] execution authority changes by mode are explicit

---

## 6. Workstream B — Kill Switch & Rollback

**Status:** New

### Problem / Goal

Guarantee that unsafe runtime authority can be stopped and reverted.

### Rollback bundle rule

Active release authority is a **scope-compatible bundle**:
- `model_scope`
- model artifact family
- calibration artifact family
- policy artifact family

Rollback must restore a compatible bundle.
Do not permit partial activation of incompatible model/calibration/policy combinations.

### Kill-switch lifecycle rule

While kill switch is active:
- requests may still be built
- results may still be recorded if policy allows
- `DecisionEvent` creation must remain available
- execution must be blocked
- `TradeOutcome` must remain compatible with non-execution or unavailable execution outcome

### Implementation Tasks

- [ ] Implement global kill switch
- [ ] Implement execution disable without losing lifecycle visibility
- [ ] Implement rollback of active promoted authority
- [ ] Preserve dependency-compatible rollback across model/calibration/policy bundles

### Acceptance Criteria

- [ ] kill switch blocks execution
- [ ] lifecycle recording remains intact during kill-switch activation
- [ ] rollback changes forward active authority safely
- [ ] rollback preserves dependency compatibility

---

## 7. Workstream C — Release Gate & Safety Audit

**Status:** New

### Problem / Goal

Make live authority conditional on explicit gates rather than intuition.

#### 7.1 Release gate inputs

```python
evaluation_pass = True
monitoring_baseline_ready = True
fallback_policy_ready = True
kill_switch_ready = True
rollback_ready = True
```

**Rationale:**
- release readiness must be testable
- live eligibility is stricter than candidate or paper eligibility

#### 7.2 Timing extension gate

```python
entry_timing_gate_enabled = False
```

### Acceptance Criteria

- [ ] live-eligibility gate is explicit and executable
- [ ] release gate distinguishes evaluation promotion from live authority
- [ ] timing extension remains observability-first unless evidence and config allow escalation

---

## 8. Workstream D — Test Coverage

**Status:** New
**Required before:** first live-eligible release attempt

### 8.1 Rollout tests

- [ ] paper mode test
- [ ] shadow mode test
- [ ] live-eligibility rejection test

### 8.2 Safety control tests

- [ ] kill-switch test
- [ ] rollback test
- [ ] dependency-compatible rollback test

### 8.3 Gate tests

- [ ] incomplete candidate rejected from live eligibility
- [ ] baseline requirement enforced
- [ ] timing extension hard-gate remains disabled by default
- [ ] kill-switch lifecycle-recording behavior remains intact

---

## 9. Workstream E — Pre-Run / Pre-Deploy Audit Checklist

**Status:** New
**Must complete before:** first live-eligible release attempt

### 9.1 Safety audit

- [ ] verify kill switch is operational end to end
- [ ] verify rollback path is operational end to end

### 9.2 Evidence audit

- [ ] verify evaluation gate passed on real candidate evidence
- [ ] verify monitoring baseline is designated and retained

### 9.3 Release audit

- [ ] verify release authority is named and documented
- [ ] verify live eligibility is distinct from candidate promotion
- [ ] verify rollback bundle compatibility is preserved

---

## 10. Combined Implementation Order

1. Complete Workstream A — Rollout Modes
2. Implement Workstream B — Kill Switch & Rollback
3. Apply Workstream C — Release Gate & Safety Audit
4. Run Workstream E — Pre-Deploy Audit
5. Implement Workstream D — Test Coverage
6. Execute deployment-safety suite
7. Evaluate results against acceptance criteria

### Acceptance Criteria for First Combined Run

- [ ] rollout modes behave distinctly
- [ ] kill switch and rollback work
- [ ] live-eligibility gate rejects incomplete candidates
- [ ] release safety is test-backed rather than assumed

---

## 11. Definition of Done

### 11.1 Gate layer

- [x] deployment-safety semantics are documented
- [ ] rollout mode controls exist
- [ ] live-eligibility gate exists

### 11.2 Safety layer

- [ ] kill switch exists and works
- [ ] rollback exists and works
- [ ] dependency-compatible rollback is enforced

### 11.3 Candidate health

- [ ] paper / shadow / live distinctions are explicit
- [ ] release authority is documented and test-backed
- [ ] monitoring baseline designation/retention is wired into release flow

### 11.4 Test layer

- [ ] rollout tests pass
- [ ] safety-control tests pass
- [ ] gate tests pass

---

## 12. What Comes After Phase 9

### 12.1 Capability expansion themes

- safe live-eligible V7 slice
- evidence-backed promotion discipline
- operational safety controls
- stable baseline for later optimization

### 12.2 Phase Boundary

- Post-Phase 9 work is optimization, expansion, and productization.
- Phase 9 is the prerequisite.
- Do not start advanced expansion work until Phase 9 definition of done is fully satisfied.

---

## 13. Compact Mental Model

### 13.1 Phase Relationships

- Phase 7: runtime lifecycle became real
- Phase 8: evidence and drift became measurable
- Phase 9: safe authority becomes possible
- Post-Phase 9: optimization starts

### 13.2 Key Takeaway

A system that cannot be stopped safely is not ready for live authority.
Phase 9 is the final proof that V7 is not only smart enough to act, but safe enough to be allowed to act.
