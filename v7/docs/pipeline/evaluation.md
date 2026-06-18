# Pipeline Evaluation — Mode-Aware, Regime-Aware

**Intended path:** `docs/v7/pipeline/evaluation.md`

## Purpose

Defines how V7 measures model and system quality — **per mode scope with regime breakdowns**.

It answers:

> Given hybrid model artifacts, calibrated outputs, policy behavior, and outcomes (per mode), how should V7 decide whether quality is improving or regressing?

---

## Core Decision

V7 evaluation is **economic-quality-first** and **mode-aware**.
The system is not judged only by:

- accuracy
- confidence
- hit rate

It is judged by:

- realized R (per mode)
- expectancy
- regret
- no-trade quality
- calibration quality
- regression reliability
- path quality
- symbol/regime stability
- safety behavior
- **mode comparison quality**

---

## Inputs

- trained model artifacts (per mode)
- calibration artifacts (per mode)
- policy behavior (per mode, including regime modifiers)
- replay outcomes
- paper/live outcomes where available
- `DecisionEvent`
- `TradeOutcome`
- evaluation config

---

## Outputs

Evaluation produces (**per mode scope**):

- global quality metrics
- walk-forward summaries
- classification metrics
- regression metrics
- economic metrics
- no-trade quality metrics
- calibration metrics
- symbol breakdowns
- regime breakdowns
- promotion/non-promotion support

---

## Walk-Forward Family

First-phase defaults (per mode):

- 6 folds
- minimum train window: 12 months
- validation window: 2 months
- optional holdout tail: 1 month

Dataset owns fold construction. Evaluation owns fold consumption and interpretation.

---

## Metric Families

### Economic metrics (per mode)

- realized R
- net expectancy
- profit factor
- max drawdown
- average trade R
- cost-adjusted R
- regret distribution
- saved-loss / missed-opportunity quality

### Classification metrics (per mode)

- action accuracy where meaningful
- precision/recall by action
- no-trade classification quality
- confusion matrix for `LONG_NOW`, `SHORT_NOW`, `NO_TRADE`
- action probability bucket quality

### Regression metrics (per mode)

- MAE/RMSE for expected R heads
- sign correctness for expected R
- predicted-R bucket vs realized-R average
- adverse-pressure error
- cost-adjusted expectancy error
- symbol/regime regression breakdowns

### Calibration metrics (per mode)

- reliability error
- confidence bucket behavior
- no-trade calibration quality
- forward-period stability

### Regime-aware metrics

- realized-R by regime bucket
- no-trade quality by regime
- action distribution by regime
- decision margin by regime
- regime stability: consistency of metrics across consecutive same-regime windows

---

## No-Trade Quality

No-trade quality must measure:

- correct skip
- saved loss
- missed opportunity
- over-suppression
- under-suppression

A model that avoids all trades may look safe but is not automatically good.

---

## Ablation Requirement

First-phase evaluation should include:

- **per-mode ablation:** SWING only, SCALP only, AGGRESSIVE_SCALP only
- interval-view ablation per mode:
  - primary only
  - primary + context
  - primary + context + refinement
- classifier-only policy vs hybrid policy (per mode)
- probability gate only vs probability + expected-R gate

Refinement intervals must prove value through evidence, not assumption.

---

## Promotion Gate (Per Mode)

Promotion must never rely on a single scalar.

Minimum gate families:

- realized-R quality threshold
- no-trade quality threshold
- calibration quality threshold
- regression reliability threshold
- symbol/regime stability threshold
- no critical safety regression
- no unacceptable portfolio/risk suppression regression

Threshold values live in config.

---

## Mode-Specific Promotion Gate Sequence

Each mode must pass these gates sequentially. No gate may be skipped. Promotion is **per mode** — SWING promotion does not imply SCALP or AGGRESSIVE_SCALP readiness.

### Gate Definitions

| Gate | Name | Meaning | Required Evidence | Exit Criteria |
|------|------|---------|-------------------|---------------|
| G0 | DOC_READY | Mode has complete docs, contracts, labels, model outputs, and risk rules | All authority docs for the mode are written and internally consistent | Design lock review passed |
| G1 | RESEARCH_BACKTEST | Initial research backtest with cost-honest labels and no-trade quality | Walk-forward OOS backtest with unified cost model; all metric families computed | Positive expectancy R; no-trade quality meets per-mode threshold |
| G2 | WALK_FORWARD_OOS | Walk-forward out-of-sample evidence across multiple folds | 6 folds minimum; 12-month train, 2-month validation per fold; per-fold consistency metrics | Median fold expectancy meets mode threshold; no fold catastrophically negative |
| G3 | COST_STRESS | Fee, slippage, spread, and funding stress where applicable | Cost model applied at taker rates (conservative); slippage volatility-adjusted; funding stress if perps | Edge survives cost stress; cost-adjusted expectancy meets mode minimum (SCALP REQUIRED: ≥ 0.10R) |
| G4 | REGIME_BREAKDOWN | Performance evaluated per TREND_UP, TREND_DOWN, RANGE, TRANSITION | Per-regime metrics: realized R, no-trade quality, action distribution, decision margin | No single regime hides catastrophic loss; TRANSITION regime does not dominate negative outcomes |
| G5 | SYMBOL_STABILITY | No single symbol or cluster explains majority of edge | Per-symbol breakdown: contribution to total expectancy; cluster contribution analysis | No single symbol > 40% of total edge; no single cluster > 60% of total edge |
| G6 | CALIBRATION_RELIABILITY | Probability and expected-R surfaces calibrated enough for policy gates | Reliability error per confidence bucket; predicted-vs-realized R bucket alignment | Reliability error within acceptable bounds; regression sign correctness above threshold |
| G7 | SHADOW | Live-market observation without order placement | Real-time market data; shadow events generated; shadow-vs-backtest comparison report | Shadow outcomes statistically consistent with backtest expectations; no material divergence |
| G8 | PAPER | Paper trading with runtime lifecycle and outcome reconciliation | Paper forward simulation via runtime-hosted simulation engine; full trade lifecycle tracked | Paper outcomes consistent with shadow and backtest; execution eligibility gates function correctly |
| G9 | TINY_LIVE | Small real-capital live validation with strict kill switches | Real orders placed with minimum size; kill switches active; daily loss limits enforced | Live outcomes consistent with paper/shadow; no kill-switch violations; no unexpected cost divergence |
| G10 | LIVE | Production-eligible mode after independent promotion | All prior gates passed; deployment safety gates active; rollback plan documented | Mode is production-eligible; independent of other modes' readiness |

### Mode-Specific Promotion Thresholds

Where exact values are documented in existing authority docs, those values are cited. Values marked **LOCK_CANDIDATE** are conservative defaults requiring owner review before implementation.

| Threshold | SWING | SCALP | AGGRESSIVE_SCALP |
|-----------|-------|-------|------------------|
| Minimum OOS window | 12 months (6 folds × 2mo) | 12 months (6 folds × 2mo) | 6 months (6 folds × 1mo) **[LOCK_CANDIDATE]** |
| Minimum trades/events | ≥ 200 **[LOCK_CANDIDATE]** | ≥ 500 **[LOCK_CANDIDATE]** | ≥ 300 **[LOCK_CANDIDATE]** |
| Minimum expectancy R | ≥ 0.15R **[LOCK_CANDIDATE]** | ≥ 0.05R **[LOCK_CANDIDATE]** | ≥ 0.03R **[LOCK_CANDIDATE]** |
| Max drawdown limit | ≤ 25% **[LOCK_CANDIDATE]** | ≤ 15% **[LOCK_CANDIDATE]** | ≤ 10% **[LOCK_CANDIDATE]** |
| Min no-trade quality | CORRECT_NO_TRADE ≥ 60%; SAVED_LOSS ≥ 0.20R per event | CORRECT_NO_TRADE ≥ 55%; SAVED_LOSS ≥ 0.10R per event | CORRECT_NO_TRADE ≥ 50%; SAVED_LOSS ≥ 0.05R per event |
| Calibration requirement | Reliability error within ±10% per bucket **[LOCK_CANDIDATE]** | Reliability error within ±10% per bucket **[LOCK_CANDIDATE]** | Reliability error within ±15% per bucket **[LOCK_CANDIDATE]** |
| Cost stress requirement | Edge survives taker × 1.5 multiplier stress **[LOCK_CANDIDATE]** | Edge survives taker × 2.0 multiplier stress; cost-adjusted expectancy ≥ 0.10R | Edge survives taker × 2.5 multiplier stress **[LOCK_CANDIDATE]** |
| Shadow duration | ≥ 4 weeks **[LOCK_CANDIDATE]** | ≥ 3 weeks **[LOCK_CANDIDATE]** | ≥ 2 weeks **[LOCK_CANDIDATE]** |
| Paper duration | ≥ 4 weeks **[LOCK_CANDIDATE]** | ≥ 4 weeks **[LOCK_CANDIDATE]** | ≥ 3 weeks **[LOCK_CANDIDATE]** |
| Tiny live limit | Max 0.5% account risk per trade; max 5% daily loss; max 10% cumulative **[LOCK_CANDIDATE]** | Max 0.25% account risk per trade; max 3% daily loss; max 7% cumulative **[LOCK_CANDIDATE]** | Max 0.1% account risk per trade; max 2% daily loss; max 5% cumulative **[LOCK_CANDIDATE]** |
| Owner review required | Yes — all LOCK_CANDIDATE values | Yes — all LOCK_CANDIDATE values | Yes — all LOCK_CANDIDATE values |

### Rejection Rules

1. **Reject if profitability only appears before costs** — cost-honest labels must show edge survives G3.
2. **Reject if edge disappears under slippage stress** — apply taker-fee multiplier stress at G3.
3. **Reject if one symbol or cluster dominates results** — G5 symbol stability gate.
4. **Reject if regime breakdown shows unacceptable hidden fragility** — any single regime with catastrophic loss triggers G4 rejection.
5. **Reject if NO_TRADE quality is poor** — CORRECT_NO_TRADE rate below mode threshold or excessive MISSED_OPPORTUNITY.
6. **Reject if calibration is not trustworthy enough for policy thresholds** — G6 reliability error above acceptable bounds.
7. **Reject if paper/shadow diverges materially from backtest expectations** — G7/G8 statistical consistency check.
8. **Reject if tiny-live outcomes diverge from paper/shadow** — G9 consistency check.

### Alpha Thesis Validation Gate

Each alpha thesis must be validated independently before being attached to a promoted mode.

- **Alpha thesis validation is not the same as mode promotion.** An alpha passing validation is necessary but not sufficient for mode promotion.
- **Mode promotion requires alpha evidence plus policy/risk/cost/portfolio acceptance.** The full G0-G10 gate sequence applies.
- Rejected alpha theses are archived with rejection reason and do not block mode promotion — but they cannot be used as promotion evidence.
- Alpha validation follows its own walk-forward protocol (see `alpha_thesis_validation_plan.md`) with independent baselines.

---

## Replay vs Live Evidence Rule

Replay-only evidence may justify:

- candidate continuation
- deeper review
- paper deployment

Live-eligible authority should not rely on replay alone when release policy requires paper/live evidence.

---

## Baseline Policy

Evaluation compares candidates against:

1. current promoted baseline model family (per mode)
2. last accepted evaluation baseline for the same evaluation family

When a candidate is promoted, it becomes the new promoted baseline and the previous baseline is retained according to artifact policy.

---

## Failure / Fallback

If a slice is incomplete:

- mark incomplete
- preserve reason
- do not treat it as normal evidence

If regression evidence is missing or unreliable:

- degrade the affected evaluation family explicitly
- do not pretend the hybrid model is fully evaluated

---

## Config Surface

Key config families:

- evaluation family
- walk-forward windows
- promotion thresholds
- regression reliability thresholds
- minimum coverage rules
- slice breakdown rules
- baseline retention
- replay vs live evidence policy

---

## Interfaces

Upstream:

- `pipeline/model.md`
- `pipeline/calibration.md`
- `pipeline/policy.md`
- `contracts/trade_outcome.md`

Downstream:

- promotion decisions
- monitoring baselines
- roadmap decisions

---

## Test Requirements

Minimum tests:

- walk-forward split integrity
- economic metric correctness
- classification metric correctness
- regression metric correctness
- calibration metric correctness
- no-trade metric correctness
- symbol/regime slicing reproducibility
- incomplete slice handling
- baseline replacement logic
- **regime-aware metric correctness**
- **per-mode metric isolation**

---

## Final Position

Evaluation is where V7 proves that its profitability claims are real. Hybrid modeling is useful only if classification, regression, calibration, regime awareness, and policy together improve economic evidence — independently per mode scope.
