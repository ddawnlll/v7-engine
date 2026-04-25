# Pipeline Risk

**Intended path:** `docs/v7/pipeline/risk.md`

## Purpose

Defines hard and soft risk controls applied after policy and portfolio stages.

It answers:

> Given a candidate decision, what risk rules may block, degrade, or allow execution eligibility?

---

## In Scope

- hard risk guards
- soft risk guards
- cooldowns
- exposure hard stops
- risk interpretation visibility

---

## Out of Scope

- model scoring
- calibration logic
- portfolio ranking logic
- broker fill accounting

---

## Core Decision

Risk is a separate stage from:
- model
- calibration
- policy
- portfolio

This separation matters because:
- a trade can be economically attractive
- yet still not be operationally safe

---

## Inputs

- candidate decision
- portfolio interpretation
- account/exposure state
- risk config

---

## Outputs

Risk stage should minimally produce:
- pass / block / degrade
- risk interpretation
- explicit block reason
- cooldown or exposure reason where relevant

---

## Rules

### 1. No hidden risk veto
If risk blocks a decision, downstream records must show that.

### 2. Hard guards stay hard
Do not let soft model enthusiasm override hard operational limits.

### 3. Keep risk readable
First phase should prefer small explicit rules over complex dynamic systems.

### 4. Separate engine actionability from operational safety
A decision may be actionable yet not executable.

---

## Stage Order

First-phase order:
1. policy
2. portfolio
3. risk
4. runtime execution eligibility

If both portfolio and risk would block:
- preserve both signals if available
- treat risk as the final hard gate
- set the primary suppression reason to risk when the block is risk-hard

This keeps `portfolio_blocked` and `risk_blocked` compatible downstream.

---

## Recommended First-Phase Controls

- global kill switch
- cooldown after loss / major event
- exposure hard limits
- duplicate-position protection
- stale-result safety handling
- degraded-result safe action rules

---

## Hard Guard Families

At minimum, config must define:
- max gross exposure
- max per-symbol exposure
- max cluster exposure
- stale-result rejection threshold
- duplicate-position rules
- cooldown trigger family

This document does not hardcode final numeric values, but these guard families must exist.

---

## Cooldown Rule

First-phase cooldown should be configurable by:
- triggering event family
- cooldown duration in bars or minutes
- scope:
  - global
  - symbol-local
  - direction-local

Default examples belong in config, not here.

---

## Duplicate Position Protection

First-phase duplicate protection should at least detect:
- same symbol, same direction, existing open position
- same symbol, same direction, already accepted decision in the same batch/session where policy forbids duplication

The exact duplicate family must be config-driven and explicit.

---

## Failure / Fallback

If risk context is unavailable:
- degrade explicitly
- prefer safe non-execution behavior when required by policy

---

## Config Surface

Key config families:
- kill-switch settings
- cooldown rules
- exposure hard limits
- degraded-result handling
- duplicate protection rules

These integrate with `docs/v7/runtime/runtime_integration.md` and `docs/v7/configuration.md`.

---

## Interfaces

Upstream:
- `pipeline/portfolio.md`
- `runtime/runtime_integration.md`

Downstream:
- `contracts/decision_event.md`
- `contracts/trade_outcome.md`
- runtime execution eligibility

---

## Test Requirements

Minimum risk tests:
- hard block visibility
- cooldown behavior
- duplicate protection
- degraded-result safe handling
- actionability vs execution-eligibility separation
- portfolio-before-risk ordering is preserved

---

## Final Position

Risk is the final safety layer before execution eligibility.
It must stay explicit, conservative, and auditable.
