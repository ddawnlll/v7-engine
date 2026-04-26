# Pipeline Policy

**Intended path:** `docs/v7/pipeline/policy.md`

## Purpose

Defines how V7 converts calibrated decision surfaces into a normalized engine decision.

It answers:

> Given calibrated scores and economic signals, how should V7 decide between `LONG_NOW`, `SHORT_NOW`, and `NO_TRADE`?

---

## In Scope

- decision policy logic
- actionability policy
- long / short / no-trade selection
- economic gating at engine-policy level
- timing guidance derivation

---

## Out of Scope

- portfolio exposure management
- hard risk controls
- broker execution logic
- account-level operational gating

---

## Core Decision

Policy is the stage that turns calibrated surfaces into:
- `recommended_action`
- `is_actionable`
- confidence-facing result fields
- expected-R-facing result fields
- execution guidance
- timing guidance

Runtime then decides whether execution is operationally allowed.

---

## Inputs

- calibrated multi-view score surfaces (fused surfaces, not averaged interval outputs)
- confidence
- expected R
- expected drawdown
- decision margins
- timing-supporting fields (e.g., 1h refinement data, which influences timing and entry readiness more than primary direction in phase one)
- policy config

---

## Outputs

Policy should produce a normalized decision surface matching `AnalysisResult`, including:

- `recommended_action`
- `is_actionable`
- `confidence`
- `expected_r`
- `expected_drawdown`
- `entry_price`
- `stop_loss`
- `take_profit`
- `time_sensitivity`
- optional advisory timing:
  - `entry_readiness`
  - `entry_valid_for_bars`

---

## Rules

### 1. Confidence matters, but is not enough
Confidence remains first-class.
It is not the only decision scalar.

### 2. No-trade is first-class
No-trade must be explicitly selected, not inferred from weak long/short scores.

### 3. Economic gating is policy-owned
Expected R and related economic surfaces belong here before runtime execution gates.

### 4. Timing extension is advisory-first
`entry_readiness` and `entry_valid_for_bars` are produced at the policy stage from calibrated score surfaces, entry-zone geometry, and timing heuristics.
They are not first-phase primary learned targets.

### 5. Keep the action family compact
First phase action family:
- `LONG_NOW`
- `SHORT_NOW`
- `NO_TRADE`

---

## Tie-Break Rule

First-phase decision rule:
1. both actionability gates must pass:
   - confidence gate
   - economic gate
2. if both directional actions fail, select `NO_TRADE`
3. if one directional action passes and beats `NO_TRADE` by the configured margin, select it
4. if long/short are too close or neither beats `NO_TRADE` cleanly, select `NO_TRADE`

This keeps `NO_TRADE` a positive decision rather than a weak fallback.

---

## `entry_readiness` Rule

First-phase `entry_readiness` is policy-derived, not a standalone model target.

It should use:
- entry-zone distance
- time sensitivity
- margin decay signals if configured
- simple bounded heuristics

Do not turn policy into a complex timing optimizer.

---

## Failure / Fallback

If policy cannot safely produce a clean actionable decision:
- emit no-trade or degraded-safe behavior
- preserve fallback visibility
- do not silently emit confident but structurally incomplete actions

---

## Config Surface

Key config families:
- minimum confidence
- minimum expected R
- drawdown limits at policy stage
- no-trade thresholds
- timing extension enablement
- timing heuristic thresholds

---

## Interfaces

Upstream:
- `pipeline/calibration.md`

Downstream:
- `pipeline/portfolio.md`
- `pipeline/risk.md`
- `contracts/analysis_result.md`

---

## Test Requirements

Minimum policy tests:
- long vs short vs no-trade selection
- confidence-only is insufficient when economic gate fails
- no-trade selected explicitly
- fallback behavior visible
- timing extension fields bounded and legal

---

## Final Position

Policy is where learned scores become a normalized decision.
It must stay explicit, compact, and auditable.
