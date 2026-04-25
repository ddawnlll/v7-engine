# Pipeline Monitoring

**Intended path:** `docs/v7/pipeline/monitoring.md`

## Purpose

Defines how V7 monitors post-training and post-deployment quality.

It answers:

> After artifacts are trained and runtime is active, what signals should V7 track to detect drift, degradation, and contract-family health issues?

---

## In Scope

- result quality monitoring
- calibration drift monitoring
- no-trade / action mix monitoring
- contract-family health monitoring
- batch/session visibility
- timing extension observability
- feature drift
- baseline updates

---

## Out of Scope

- alert transport implementation
- dashboard UI design
- broker monitoring specifics
- scheduler internals

---

## Core Decision

Monitoring must observe both:
- model quality surfaces
- system lifecycle surfaces

That means monitoring should track not only scores, but also:
- degradation
- fallback
- execution suppression
- outcome readiness
- contract validity

---

## Inputs

- `AnalysisResult`
- `DecisionEvent`
- `TradeOutcome`
- calibration artifacts
- runtime logs / metrics
- monitoring config

---

## Outputs

Monitoring should produce:

- health signals
- drift indicators
- degradation alerts
- coverage summaries
- symbol/regime dashboards
- timing extension usefulness summaries

---

## Rules

### 1. Monitor the contract family, not just the model
A healthy model with broken lifecycle plumbing is still a broken system.

### 2. Calibration drift matters
Confidence usage in runtime requires monitoring of confidence reliability.

### 3. No-trade distribution matters
A large shift in no-trade frequency may signal model or state drift.

### 4. Degradation must be visible
Fallback and degraded-result usage should be measurable.

### 5. Timing extension is initially observability-first
Track:
- frequency of `entry_readiness` states
- later outcome quality by timing state
- whether timing gating is active

---

## Baseline Update Policy

Monitoring baselines should reference:
1. the currently promoted artifact family
2. the previous promoted artifact family for regression comparison
3. optional longer historical aggregate baselines for trend context

When promotion occurs:
- the promoted artifact becomes the new primary monitoring baseline
- the previous promoted artifact remains retained according to baseline-retention config

This keeps drift interpretation stable.

---

## Feature Drift Ownership

Monitoring owns feature-drift observation.

Minimum first-phase feature drift families:
- feature distribution shift
- missingness-rate shift
- HTF-availability shift
- symbol mix shift

Recommended metrics may include PSI-like or distribution-shift families, but the exact metric family remains config-driven.

---

## Timing Extension Decision Rule

The timing extension may move from observability-only to gating-enabled only when:
- timing states show stable predictive usefulness across multiple evaluation windows
- `CHASING` or `MISSED` states repeatedly correspond to materially worse outcomes
- the evidence crosses the configured promotion threshold for timing gating

Until then:
- `entry_timing_used_for_gate` should remain false in normal operation

---

## Outcome Finality Lag Rule

Monitoring should track outcome finality lag as:
- median lag
- tail lag
- unresolved fraction by horizon family

If lag exceeds configured thresholds:
- raise a data-quality / pipeline-health signal
- do not silently treat missing outcomes as stable absence

Whether this blocks training is controlled by training/evaluation config, not hardcoded here.

---

## Coverage Thresholds

Monitoring should track:
- symbol coverage
- regime coverage

Coverage thresholds must be config-driven.
Below-threshold coverage should emit:
- warning signals
- slice incompleteness markers
- optional promotion-blocking evidence if evaluation policy requires it

---

## Recommended Monitoring Families

Minimum first-phase families:
- request/result validation failure rate
- fallback / degraded rate
- confidence distribution
- expected-R distribution
- no-trade rate
- actionability vs execution-eligibility gap
- symbol coverage
- regime coverage
- timing-extension distribution
- outcome finality lag
- feature drift

---

## Alert Thresholds

Thresholds belong in config.
Alert transport is outside scope.

Bridge rule:
- monitoring defines what threshold crossing means
- deployment/runtime alerting systems define how that threshold is delivered

This keeps threshold semantics useful without forcing transport design into this document.

---

## Failure / Fallback

If monitoring coverage is incomplete:
- preserve that explicitly
- do not silently report false stability

---

## Config Surface

Key config families:
- monitoring windows
- drift thresholds
- alert thresholds
- timing observability enablement
- slice definitions
- baseline retention rules
- feature-drift thresholds
- outcome-lag thresholds

---

## Interfaces

Upstream:
- `contracts/analysis_result.md`
- `contracts/decision_event.md`
- `contracts/trade_outcome.md`

Downstream:
- alerting systems
- evaluation baselines
- promotion reviews

---

## Test Requirements

Minimum monitoring tests:
- drift calculations stable
- degraded/fallback counting correct
- actionability vs execution-eligibility gap measurable
- timing extension aggregation works
- outcome lag metrics correct
- feature drift aggregation works
- baseline replacement logic works

---

## Final Position

Monitoring is how V7 stays trustworthy after deployment.
It must track both economic quality and lifecycle integrity.
