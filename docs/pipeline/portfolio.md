# Pipeline Portfolio

**Intended path:** `docs/v7/pipeline/portfolio.md`

## Purpose

Defines how V7 handles cross-symbol portfolio interaction after single-candidate policy output exists.

It answers:

> Given multiple candidate decisions across symbols, how should V7 reason about exposure, concentration, and cross-symbol competition?

---

## Core Decision

V7 is designed for a centralized multi-symbol world.

Portfolio logic is first-class but lightweight in first phase. It is not the model and not a full optimizer.

---

## First-Phase Scope

- target universe up to 60 symbols
- initial rollout may use a smaller subset
- portfolio layer may pass, suppress, down-rank, or annotate
- portfolio layer should not become a full optimizer in first phase

---

## Inputs

- policy-approved candidate results
- action probabilities
- expected R by action
- confidence
- current portfolio context
- exposure state
- symbol cluster/correlation metadata
- portfolio config

---

## Outputs

Portfolio stage produces:

- pass / suppress / down-rank / annotate
- portfolio interpretation
- suppression reason if blocked
- ranking metadata where relevant
- portfolio pressure score where configured

---

## Ranking Rule

When multiple candidates compete, first-phase ranking should use:

1. policy-approved actionability
2. expected-R quality
3. cost-adjusted expectancy
4. confidence as secondary ordering
5. portfolio pressure adjustments
6. deterministic tie-break by symbol order only as last resort

Use suppression instead of down-ranking when:

- a hard portfolio cap is exceeded
- cluster concentration would breach configured limits
- portfolio context is degraded and config requires safe non-execution

---

## Rules

1. Portfolio is not the model.
2. Portfolio suppression must be visible.
3. Portfolio should not hide risk vetoes.
4. Lightweight first phase.
5. Regression expected-R can inform ranking, but cannot override hard caps.

---

## Cluster Definition

First-phase cluster families may use:

- approved manual groupings
- stable correlation-based groups computed offline and versioned

Do not compute ad hoc runtime clusters without a versioned grouping family.

---

## Portfolio Context Unavailable Rule

If portfolio context is unavailable:

- degrade explicitly
- default first-phase behavior is safe non-execution unless config explicitly allows lighter fallback

Do not silently assume zero portfolio pressure.

---

## DecisionEvent Mapping

Set `DecisionEvent.runtime_interpretation.portfolio_blocked = true` when the portfolio stage returns:

- `SUPPRESSED`
- `BLOCKED`

Down-ranked but still admissible candidates should not set `portfolio_blocked = true`.

---

## Recommended Controls

- max simultaneous positions
- cluster exposure caps
- symbol concentration caps
- drawdown-state pressure modifiers
- optional per-session ranking limits
- duplicate candidate suppression before risk gate where configured

---

## Config Surface

Key config families:

- max open positions
- exposure caps
- cluster grouping rules
- portfolio suppression thresholds
- ranking family
- portfolio context fallback behavior

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

Minimum tests:

- concentration suppression works
- cluster suppression is visible
- rank vs suppress is deterministic
- expected-R influences ranking only within allowed caps
- `portfolio_blocked` mapping is correct
- unavailable context degrades visibly

---

## Final Position

Portfolio logic keeps individually good trades from becoming collectively bad exposure. It uses expected economic quality, but it must remain explicit and lightweight in first phase.
