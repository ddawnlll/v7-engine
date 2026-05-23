# Runtime Fallback Policy

## Purpose

Defines what kinds of fallback and degraded behavior are allowed in V7 runtime.

It answers:

> When inputs, artifacts, or runtime context are incomplete or unavailable, what may the system safely do, and what must remain explicit?

This is a boundary and safety document.

---

## Core Position

Fallbacks are allowed.
Hidden fallbacks are forbidden.

Every fallback must be:
- explicit
- observable
- testable
- attributable to a config/governed policy

---

## In Scope

- request-side degradation
- result-side degradation handling
- calibration fallback
- policy/runtime safe action behavior
- event/outcome recording for degraded paths

---

## Out of Scope

- broker retry internals
- infrastructure alert routing
- long-term deployment scheduling

---

## Fallback Taxonomy

V7 should distinguish at least these families:

### 1. Request degradation
Examples:
- missing HTF context
- partial canonical state
- stale data

### 2. Artifact degradation
Examples:
- missing calibration artifact
- stale policy artifact
- unavailable portfolio context family
- missing `model_scope` artifact
- incompatible or non-scope-compatible artifact
- `scope_mismatch` between request, artifact, calibration, or policy

### 3. Runtime context degradation
Examples:
- incomplete account state
- incomplete exposure state
- monitoring/telemetry lag

### 4. Execution eligibility degradation
Examples:
- exchange state uncertain
- duplicate-position state uncertain
- kill-switch state unclear

These should not be conflated.

---

## Evaluation Order vs Fallback Severity

These are different concepts.

### Operational evaluation order
First-phase runtime order remains:
1. request / state quality
2. model / calibration / policy interpretation
3. portfolio interpretation
4. risk interpretation
5. execution safety

### Fallback severity priority
When multiple fallback families are active, the most conservative effective safe action wins.

Default severity order:
1. hard execution safety uncertainty
2. risk uncertainty
3. portfolio uncertainty
4. calibration / artifact uncertainty
5. request quality degradation

This does not change pipeline order.
It defines which uncertainty dominates the final safe behavior.

---

## Allowed Fallback Behavior

### Request side
Allowed:
- continue with explicit `degradation_context`
- preserve quality flags
- mark stale / partial state

Not allowed:
- silently pretending degraded state is normal state

### Calibration side
Allowed:
- use explicit raw-confidence fallback only if policy allows it
- surface `confidence_kind` accordingly

Not allowed:
- silently passing raw confidence as calibrated confidence

### Policy / result side
Allowed:
- emit safe no-trade or degraded-safe interpretation
- emit `runtime_safe_action`

Not allowed:
- silently forcing directional action from incomplete surfaces
- silently falling back from one `model_scope` to another without explicit configured authority and visible safe behavior

A missing or incompatible `model_scope` artifact is an explicit fallback/failure condition. If configured fallback exists, it must be visible and safe, usually `NO_TRADE` or `SKIP`.

### Runtime side
Allowed:
- block execution
- skip execution
- persist reviewable event
- create pending outcome where relevant

Not allowed:
- execute on an unsafe fallback path without explicit authority

---

## Preferred Safe Actions

First-phase runtime safe actions:
- `NO_TRADE`
- `SKIP`
- `HOLD`

### `HOLD` meaning
`HOLD` means:
- do not open a new position because of the degraded decision
- do not mutate an already-managed existing position because of the degraded decision
- preserve the existing managed state until normal control resumes or a separate explicit position-management rule applies

`HOLD` is not the same as “take new risk.”
It is a conservative continuity action.

---

## Event / Outcome Recording Rule

If fallback or degradation affected behavior:
- `DecisionEvent` must record it
- `TradeOutcome` must remain compatible with it later

Fallback history must not live only in logs.

### Minimum DecisionEvent field mapping
- `fallback_used`
- `degraded_reason`
- `runtime_safe_action`
- `suppression_reason` when fallback caused suppression
- `runtime_actionability` downgraded if applicable

### Outcome linkage rule
If fallback prevented normal execution, the later `TradeOutcome` must remain compatible with:
- non-execution
- blocked execution
- replay-only evaluation
- pending or unavailable real outcome

---

## Artifact Staleness Rule

Artifact staleness must be config-governed.
The policy must define at least:
- staleness unit:
  - wall-clock age
  - bar age
  - release/version age
- allowed stale-use modes:
  - allowed
  - allowed with downgrade
  - forbidden

Do not hardcode one universal staleness meaning across all artifact families.

---

## Minimum Runtime Rules

### Rule 1
Invalid input is not the same as no-trade.

### Rule 2
Degraded input is not the same as normal input.

### Rule 3
Missing artifact is not the same as low confidence.

### Rule 4
If the system is unsure whether execution is safe, safe non-execution is the default unless explicit policy says otherwise.

---

## Failure / Fallback Examples

### Example A — Missing 1d context
Allowed:
- request proceeds with explicit degradation
- result may still be produced
- runtime may keep it reviewable
- execution policy may still block if configured

### Example B — Missing calibration artifact
Allowed:
- raw-confidence fallback only if explicitly configured
- result surfaces raw confidence honestly
- runtime may downgrade to review-only

### Example C — Portfolio context unavailable
Allowed:
- degrade explicitly
- default safe non-execution unless lighter fallback is explicitly approved

### Example D — Exchange health uncertain
Allowed:
- no execution
- keep event
- later outcome may remain skip / pending / unavailable

---

## Test Requirements

Minimum fallback tests:
- degraded request remains explicit
- missing calibration stays visible
- runtime safe action is emitted when required
- execution is blocked on unsafe fallback paths
- event/outcome preserve fallback lineage
- `HOLD` does not open or mutate positions implicitly
- severity priority picks the more conservative safe action

---

## Final Position

V7 is allowed to degrade.
It is not allowed to degrade invisibly.

Fallback policy exists to make degraded behavior safe, explicit, and measurable.
