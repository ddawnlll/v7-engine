# Phase 7 — Portfolio, Risk & Runtime Integration (Planned)

**Status:** Planned  
**Owner:** Runtime / controls track  
**Last updated:** 2026-05-23  
**Delivery status:** Not started

---

## 1. Purpose

Integrate hybrid policy outputs into runtime lifecycle, portfolio interpretation, risk gates, `DecisionEvent`, and `TradeOutcome` flows.

A valid `AnalysisResult` is economically actionable, but runtime still decides whether execution is operationally eligible.

---

## 2. Stable Rules

- Runtime builds requests and validates results.
- Engine produces the hybrid decision surface.
- Portfolio and risk are separate explicit stages.
- Runtime persists lifecycle records.
- No hidden fallback, hidden veto, or hidden score mutation.

---

## 3. Workstream A — Portfolio & Risk Controls

Portfolio consumes:

- recommended action
- action probabilities
- confidence
- expected-R by action
- expected drawdown/adverse estimates
- portfolio context
- cluster/concentration config

Risk consumes:

- portfolio-interpreted candidate
- account/exposure state
- risk config
- degradation state

Combined block rule:

If both portfolio and risk block:

- `portfolio_blocked = true`
- `risk_blocked = true`
- primary suppression reason is risk if the risk block is hard
- portfolio block remains secondary context

### Acceptance Criteria

- [ ] portfolio suppression is explicit.
- [ ] risk blocks are explicit.
- [ ] expected-R/probability context is preserved through suppression.

---

## 4. Workstream B — Runtime Request/Result Flow

Runtime must:

- build valid `AnalysisRequest`
- route by `requested_trade_mode` / `model_scope`
- load scope-compatible model/calibration/policy bundle
- reject invalid `AnalysisResult`
- preserve actionability vs execution eligibility
- surface fallback/degradation visibly
- consume runtime simulation engine for paper forward simulation and historical replay

### Hybrid result validation before consumption

Runtime rejects or degrades when:

- action probabilities are missing or invalid
- expected-R is required for the chosen direction but missing
- confidence kind is misrepresented
- artifact/calibration/policy bundle is scope-incompatible
- policy gate status is missing

### Acceptance Criteria

- [ ] runtime builds valid requests.
- [ ] runtime validates hybrid results.
- [ ] actionability and execution eligibility are distinct.

---

## 5. Workstream C — Event & Outcome Lifecycle

`DecisionEvent` must persist:

- requested scope
- artifact bundle lineage
- action probabilities
- expected-R surfaces
- expected-R reliability state
- policy gates
- portfolio/risk interpretation
- degradation/fallback state

`TradeOutcome` must later allow:

- realized R comparison
- projected-vs-realized R error
- projected confidence bucket review
- no-trade missed-opportunity/saved-loss review

Outcome states:

```text
PENDING → RESOLVED | PARTIALLY_RESOLVED | INVALIDATED | UNAVAILABLE
```

### Acceptance Criteria

- [ ] `DecisionEvent` is created after valid normalized result.
- [ ] `TradeOutcome` can be created pending and updated later.
- [ ] hybrid surfaces survive into lifecycle records.

---

## 6. Workstream D — Test Coverage

Minimum tests:

- portfolio suppression
- risk block
- dual portfolio+risk block propagation
- request builder
- hybrid result validation rejection
- scope mismatch fallback
- actionability vs execution-eligibility split
- event materialization
- outcome pending → update
- fallback/suppression propagation matrix

---

## 7. Pre-Run Audit

Before Phase 8:

- [ ] runtime does not bypass result validation
- [ ] fallback signals are visible in event creation
- [ ] portfolio/risk blocks can be distinguished downstream
- [ ] timing extension remains advisory by default
- [ ] hybrid surfaces are persisted for evaluation

---

## 8. Definition of Done

- [ ] portfolio interpretation exists.
- [ ] risk interpretation exists.
- [ ] request builder exists.
- [ ] hybrid result validator exists.
- [ ] lifecycle records persist hybrid surfaces.
- [ ] tests pass.

---

## 9. What Phase 8 Inherits

Phase 8 inherits runtime-consumable hybrid decisions, explicit suppression, and lifecycle records that preserve projected probabilities and expected-R estimates for evaluation.
