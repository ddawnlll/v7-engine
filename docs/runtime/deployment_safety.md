# Runtime Deployment Safety

## Purpose

Defines the minimum deployment and release safety rules for V7 runtime.

It answers:

> Before V7 is allowed to influence real execution, what safety gates, rollout modes, and rollback controls must exist?

This is a runtime release-safety document.

---

## Core Position

Deployment safety comes after:
- contract correctness
- simulation correctness
- evaluation correctness

Do not use deployment complexity to compensate for weak contract or truth-layer discipline.

---

## In Scope

- rollout modes
- promotion safety gates
- paper / shadow / live progression
- rollback rules
- kill switch expectations
- monitoring prerequisites

---

## Out of Scope

- CI/CD implementation details
- infrastructure vendor specifics
- alert transport design
- exchange onboarding details

---

## Rollout Modes

V7 should support these conceptual modes:

### 1. Replay-only
Used for:
- simulation verification
- offline evaluation
- regression testing

### 2. Paper
Used for:
- live-ish operational validation
- event/outcome lifecycle validation
- actionability vs execution-eligibility review

### 3. Shadow
Used when:
- V7 observes live state
- records decisions
- does not control execution authority directly

Shadow is optional for general experimentation.
For the **first live-eligible release family**, shadow should be treated as required unless explicit release authority waives it.

### 4. Live-eligible
Only after:
- contract family works
- evaluation passes
- monitoring is in place
- rollback exists
- kill switch exists

---

## Minimum Deployment Gates

Before a V7 candidate is live-eligible, all of these should be true:

- request/result/event/outcome contract flow is valid
- runtime-hosted simulation engine / simulated-truth layer is in use
- candidate clears evaluation gate
- confidence surface is calibrated or explicitly treated as uncalibrated
- no-trade quality is reviewed
- fallback policy is configured
- runtime safe actions are defined
- monitoring baselines exist
- rollback path is tested
- kill switch is operational

---

## Monitoring Baseline Rule

A monitoring baseline means:
- one promoted reference artifact family is designated as the primary baseline
- one previous promoted baseline is retained for regression comparison
- baseline windows and retention rules are config-governed

“Monitoring baselines exist” does not mean vague historical averages only.
It means there is a named promoted reference family.

---

## Promotion vs Live Eligibility

These are related but not identical.

### Evaluation promotion gate
Answers:
- is this artifact family good enough to become the new promoted reference candidate?

### Live-eligibility gate
Answers:
- even if promoted, is it operationally safe to influence live execution?

A model family may be:
- evaluation-promoted but only paper-eligible
- evaluation-promoted and shadow-eligible
- evaluation-promoted and live-eligible

Eligibility is per `model_scope`: `SWING` live eligibility does not imply `SCALP` live eligibility, and `SCALP` live eligibility does not imply `AGGRESSIVE_SCALP` live eligibility.

Do not collapse evaluation promotion and live eligibility into one gate.

---

## Promotion Rule

A candidate may become:
- paper-eligible
- shadow-eligible
- live-eligible

These are not the same thing.

Recommended order:
1. replay
2. paper
3. shadow
4. live-eligible

Do not skip straight from offline success to live authority unless explicit release authority allows it.

---

## Kill Switch Rules

V7 must support at least:
- global kill switch
- symbol-local or strategy-local disable where practical
- execution disable without losing request/result/event recording
- safe behavior under kill-switch activation

Kill switch activation should:
- block execution
- preserve event visibility
- emit monitoring-visible kill-switch state

Kill switch activation must not look like an unexplained drop in activity.

---

## Rollback Rules

Rollback must be able to revert compatible artifact bundles per `model_scope`:
- promoted model family
- promoted calibration family
- promoted policy family where relevant

### Dependency rule
Rollback must preserve dependency compatibility.
If a model family rollback requires its matching calibration family, they must roll back together.

Rollback changes forward authority, not past records.

---

## Monitoring Preconditions

Before live-eligible deployment:
- fallback/degraded rates are visible
- confidence / expected-R distributions are visible
- no-trade rate is visible
- actionability vs execution-eligibility gap is visible
- outcome finality lag is visible
- baseline comparisons exist
- kill-switch state is visible in monitoring

If these are missing, deployment safety is incomplete.

---

## Timing Extension Safety Rule

The timing extension:
- `entry_readiness`
- `entry_valid_for_bars`

should remain observability-first by default.

It must not become a hard live gate unless:
- monitoring evidence exists
- evaluation supports the change
- the gating mode is config-enabled

---

## Safe First Live Shape

The first live-eligible V7 should be able to do all of these safely:

- validate request/result linkage
- create decision events
- block unsafe execution
- preserve fallback visibility
- update trade outcomes
- support rollback
- support kill switch
- surface monitoring signals

If it cannot do these, it is not ready for live authority.

---

## Release Authority Note

Where this document says “explicit release authority,” the minimum expectation is:
- a documented release policy in repo process or ops practice
- not an undocumented operator judgment in chat only

This avoids dangling references to undefined higher-level policy.

---

## Config Surface

Deployment safety should be governed by config families such as:
- rollout mode
- promotion gate family
- kill-switch settings
- rollback authority
- live-eligibility toggles
- timing-gate enablement
- degraded-result live behavior
- baseline retention rules

---

## Test Requirements

Minimum deployment-safety tests:
- kill switch blocks execution
- rollback changes active authority
- rollback preserves dependency compatibility
- paper mode preserves lifecycle records
- degraded paths do not execute unsafely
- live-eligibility gate rejects incomplete candidates

---

## Final Position

Deployment safety is how V7 earns the right to influence real trading.

It is not a substitute for correctness.
It is the protective shell around correctness.
