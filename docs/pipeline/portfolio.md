# Pipeline Portfolio

**Intended path:** `docs/v7/pipeline/portfolio.md`

## Purpose

Defines how V7 handles cross-symbol portfolio interaction after single-candidate policy output exists.

It answers:

> Given multiple candidate decisions across symbols, how should V7 reason about exposure, concentration, and cross-symbol competition?

---

## In Scope

- multi-symbol comparison
- exposure concentration
- correlation / cluster pressure
- portfolio-aware suppression or down-ranking
- portfolio interpretation visibility

---

## Out of Scope

- model training
- calibration logic
- hard account risk ledgers
- broker execution plumbing

---

## Core Decision

V7 is designed for a centralized multi-symbol world.
That means portfolio logic is a first-class stage, but it should stay lightweight in first phase.

---

## First-Phase Scope

- target universe up to **60 symbols**
- initial rollout may use a smaller subset
- portfolio layer may:
  - pass
  - suppress
  - down-rank
  - annotate

It should **not** become a full optimizer in first phase.

---

## Inputs

- candidate results from policy stage
- current portfolio context
- exposure state
- symbol cluster / correlation metadata
- portfolio config

---

## Outputs

Portfolio stage should minimally produce:
- pass / suppress decision
- portfolio interpretation
- suppression reason if blocked
- optional ranking metadata

These later surface in:
- `DecisionEvent`
- `TradeOutcome`

---

## Rules

### 1. Portfolio is not the model
Do not push cross-symbol capital logic into the model family in first phase.

### 2. Keep portfolio layer explicit
A blocked trade should say it was portfolio-blocked.

### 3. No hidden veto
Suppression must remain visible downstream.

### 4. Lightweight first phase
Prefer simple concentration and cluster rules before advanced optimization.

---

## Cluster Definition

First-phase cluster families may use:
- approved manual groupings, or
- stable correlation-based groups computed offline and versioned

Do not compute ad hoc runtime clusters without a versioned grouping family.

The cluster family used must be traceable in config or lineage.

---

## Ranking Rule

When multiple candidates compete, first-phase ranking should use:
1. policy-approved actionability
2. expected-R quality
3. confidence as secondary ordering
4. portfolio pressure adjustments
5. deterministic tie-break by symbol order only as last resort

Use suppression instead of down-ranking when:
- a hard portfolio cap is already exceeded, or
- cluster concentration would breach configured limits

---

## Portfolio Context Unavailable Rule

If portfolio context is unavailable:
- degrade explicitly
- default first-phase behavior is **safe non-execution** unless config explicitly allows a lighter fallback

Do not silently assume zero portfolio pressure.

---

## DecisionEvent Mapping

`DecisionEvent.runtime_interpretation.portfolio_blocked = true` when the portfolio stage returns:
- `SUPPRESSED`, or
- `BLOCKED`

Down-ranked but still admissible candidates should not set `portfolio_blocked = true`.

This keeps event semantics explicit.

---

## Recommended First-Phase Controls

- max simultaneous positions
- cluster exposure caps
- symbol concentration caps
- drawdown-state pressure modifiers
- optional per-session ranking limits

---

## Failure / Fallback

If portfolio context is unavailable:
- degrade explicitly
- do not silently assume zero portfolio pressure if that assumption is unsafe

---

## Config Surface

Key config families:
- max open positions
- exposure caps
- cluster grouping rules
- portfolio suppression thresholds
- ranking family

---

## Interfaces

Upstream:
- `pipeline/policy.md`

Downstream:
- `pipeline/risk.md`
- `contracts/decision_event.md`
- `contracts/trade_outcome.md`

---

## Test Requirements

Minimum portfolio tests:
- concentration suppression works
- cluster suppression is visible
- rank vs suppress behavior is deterministic
- `portfolio_blocked` mapping is correct
- portfolio context absence degrades visibly

---

## Final Position

Portfolio logic exists to keep a good single-trade decision from becoming a bad multi-symbol portfolio decision.
It should stay explicit and lightweight in first phase.
