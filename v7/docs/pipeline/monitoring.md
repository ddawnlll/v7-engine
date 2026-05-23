# Pipeline Monitoring — Mode-Aware

**Intended path:** `docs/v7/pipeline/monitoring.md`

## Purpose

Defines how V7 monitors post-training and post-deployment quality — **per mode scope**.

It answers:

> After hybrid artifacts are trained and runtime is active, what should V7 track to detect drift, degradation, and lifecycle health issues per mode?

---

## Core Decision

Monitoring must observe both:

- model quality surfaces (per mode)
- system lifecycle surfaces

For V7 hybrid modeling, monitoring also tracks:

- action probability drift (per mode)
- expected-R drift (per mode)
- regression reliability drift (per mode)
- calibration drift (per mode)
- no-trade/action mix drift (per mode)
- **mode distribution** (which modes are active, coverage balance)

---

## Inputs

- `AnalysisResult` (mode-scoped)
- `DecisionEvent` (mode-scoped)
- `TradeOutcome`
- calibration artifacts (per mode)
- model artifact metadata (per mode)
- runtime logs / metrics
- monitoring config

---

## Outputs

Monitoring produces (**per mode**):

- health signals
- drift indicators
- degradation alerts
- coverage summaries
- symbol/regime dashboards
- timing extension usefulness summaries
- regression reliability summaries
- **mode distribution and cross-mode comparisons**

---

## Recommended Monitoring Families

Minimum first-phase families (tracked **per mode**):

- request/result validation failure rate
- fallback/degraded rate
- calibrated confidence distribution
- action probability distribution
- expected-R distribution
- expected adverse-pressure distribution
- no-trade rate
- long/short/no-trade action mix
- actionability vs execution-eligibility gap
- symbol and regime coverage
- interval-view coverage integrity
- refinement availability rate (per mode)
- timing-extension distribution
- outcome finality lag
- feature drift
- regression reliability drift
- **mode activity balance**

---

## Calibration Drift

Monitor:

- reliability error
- confidence bucket realized quality
- no-trade confidence quality
- per-symbol and per-regime reliability breakdowns

Confidence used in runtime requires reliability evidence.

---

## Regression Drift

Monitor:

- predicted expected-R bucket vs realized average R
- expected-R sign quality
- adverse-pressure prediction quality
- cost-adjusted expectancy bucket quality
- error distribution by symbol/regime

If regression reliability degrades, policy may need to raise economic gates, ignore affected heads, or degrade to no-trade depending on config.

---

## Feature Drift

Monitoring owns feature-drift observation.

Minimum families:

- continuous feature distribution shift
- missingness-rate shift
- HTF availability shift
- 1h refinement availability shift
- symbol mix shift

---

## Timing Extension Decision Rule

Timing extension may move from observability-only to gating-enabled only when:

- timing states show stable predictive usefulness across multiple windows
- `CHASING` or `MISSED` states repeatedly correspond to worse outcomes
- evidence crosses configured promotion threshold

Until then, `entry_timing_used_for_gate` should remain false in normal operation.

---

## Outcome Finality Lag

Track:

- median lag
- tail lag
- unresolved fraction by horizon family

If lag exceeds thresholds:

- raise data-quality/pipeline-health signal
- do not treat missing outcomes as stable absence

---

## Baseline Update Policy

Monitoring baselines reference:

1. current promoted artifact family
2. previous promoted artifact family
3. optional longer historical aggregate baselines

When promotion occurs, the promoted artifact becomes the new primary monitoring baseline.

---

## Rules

1. Monitor the contract family, not just the model.
2. Calibration drift matters.
3. Regression drift matters.
4. No-trade distribution matters.
5. Degradation must be visible.
6. Timing extension is initially observability-first.

---

## Config Surface

Key config families:

- monitoring windows
- drift thresholds
- alert thresholds
- regression reliability thresholds
- timing observability enablement
- slice definitions
- baseline retention
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

Minimum tests:

- drift calculations stable
- degraded/fallback counting correct
- expected-R distribution aggregation works
- regression reliability aggregation works
- actionability vs execution-eligibility gap measurable
- timing extension aggregation works
- outcome lag metrics correct
- baseline replacement logic works

---

## Final Position

Monitoring is how V7 stays trustworthy after deployment. A hybrid model must monitor both decision probabilities and economic estimates, not just final actions.
