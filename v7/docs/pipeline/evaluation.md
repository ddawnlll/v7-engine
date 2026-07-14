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

- **AlphaForge handoff packages** (V7HandoffPackage) — AlphaForge delivers evidence packages; V7 gates evaluate them. See [../../../contracts/mappings/alphaforge_to_v7.md](../../../contracts/mappings/alphaforge_to_v7.md)
- trained model artifacts (per mode) — from AlphaForge ModelArtifact metadata
- calibration artifacts (per mode) — from AlphaForge CalibrationCandidate
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

### Holdout Protocol

When a holdout tail is reserved (via ``--holdout-cutoff`` in the CLI),
the following rules apply:

1. **Cutoff semantics:** Data at or after the cutoff date is held out.
   The model never sees holdout rows during walk-forward validation or
   final training.
2. **Off-by-one bar:** The cutoff is treated as **inclusive** — bars
   whose open time is >= the cutoff timestamp are held out.  This
   ensures forward-looking leakage is impossible at the boundary bar.
3. **One-shot evaluation:** The holdout set is evaluated once after
   training completes.  No re-tuning, no threshold adjustment, no
   iteration against holdout outcomes.  If a holdout evaluation suggests
   candidate improvement, a new candidate with a fresh holdout reservation
   (new timestamp cutoff) must be created — the original holdout may not
   be re-consumed.
4. **Minimum size:** If fewer than 100 rows fall after the cutoff, the
   holdout reservation is skipped (insufficient statistical power).
   This threshold is configurable in ``compute_holdout_split()``.
5. **Single-use enforcement (future):** A ledger entry in
   ``ResearchRunIndex`` recording which holdout reservation was consumed
   by which candidate is planned but not yet implemented.  See issue #306
   for the follow-up scope.

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
| G1 | RESEARCH_BACKTEST | Initial research backtest with cost-honest labels and no-trade quality | Walk-forward OOS backtest with unified cost model; all metric families computed; PBO/deflated-Sharpe computed from real MHT functions (not fallback identity) | Positive expectancy R; no-trade quality meets per-mode threshold; PBO risk LOW or MEDIUM; deflated Sharpe > 0; MHT computed for real (fail-closed against fallback identity) |
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

**Owner Review Status (P0.7C, updated 2026-07-13):** SWING, SCALP, and AGGRESSIVE_SCALP thresholds are all **LOCKED_INITIAL_BASELINE** — owner-reviewed conservative baselines. They are *not* permanent empirical truth and must be recalibrated after each mode's first full walk-forward/backtest evidence on the canonical 5-symbol (v0.30B LOCKED baseline) / full-feature (--features all) dataset. Locking is what makes the deterministic V7-Lite readiness gate (`v7/lite/readiness_gate.py`) able to evaluate G0-G6 as real PASS/FAIL for these modes instead of leaving them permanently un-scoreable.

**SCALP/AGGRESSIVE_SCALP lock note (2026-07-13):** These two modes' thresholds were promoted HOLD → LOCKED_INITIAL_BASELINE by owner decision so the deterministic readiness gate has real numbers to check SCALP/AGGRESSIVE_SCALP against — the numeric values below were already documented as placeholders and are unchanged by this lock; only their status changed. They remain baseline-conservative and pending recalibration after the first full 5-symbol / full-feature walk-forward run for each mode. This does not constitute empirical validation and does not authorize paper/live promotion — G1-G10 evidence is still required per mode.

**Mode Priority Note (P0.7E):** SCALP and AGGRESSIVE_SCALP are **PRIMARY** business/research modes. Their LOCKED_INITIAL_BASELINE status (as of 2026-07-13) means "conservative baseline is now checkable, empirical evidence is still required to keep it locked" — not "already validated." SWING is **SECONDARY_BASELINE** / control mode. Its LOCKED_INITIAL_BASELINE status means "safer initial baseline anchor" — not "highest product priority." AlphaForge must produce primary research reports for SCALP and AGGRESSIVE_SCALP, and a secondary baseline report for SWING. All three modes require AlphaForge research before promotion eligibility can be determined.

**Lock Semantics:**
- **LOCKED_INITIAL_BASELINE:** Owner-reviewed conservative baseline. Implementation can proceed, including deterministic gate evaluation (`v7/lite/readiness_gate.py`). Values subject to recalibration after each mode's first full walk-forward evidence on the canonical 5-symbol (v0.30B LOCKED baseline) / full-feature (--features all) dataset. Does NOT imply the mode has passed any gate yet, and does NOT imply highest business priority — see Mode Priority Note above.
- **HOLD:** Do not implement live/promotion threshold logic for this mode beyond research. HOLD means "empirical evidence required" — this reflects research difficulty (fee, slippage, latency, overfit risks), not low business priority. As of 2026-07-13 no mode's thresholds are HOLD; all three carry LOCKED_INITIAL_BASELINE pending recalibration.
- **RESEARCH_ONLY:** Mode may be researched, but not promoted to paper/tiny-live/live until empirical evidence and owner review exist.

| Threshold | SWING | SCALP | AGGRESSIVE_SCALP |
|-----------|-------|-------|------------------|
| Minimum OOS window | 12 months (6 folds × 2mo) **[LOCKED_INITIAL_BASELINE]** | 12 months (6 folds × 2mo) **[LOCKED_INITIAL_BASELINE]** | 6 months (6 folds × 1mo) **[LOCKED_INITIAL_BASELINE]** |
| Minimum trades/events | ≥ 200 **[LOCKED_INITIAL_BASELINE]** | ≥ 500 **[LOCKED_INITIAL_BASELINE]** | ≥ 300 **[LOCKED_INITIAL_BASELINE]** |
| Minimum expectancy R | ≥ 0.15R **[LOCKED_INITIAL_BASELINE]** | ≥ 0.05R **[LOCKED_INITIAL_BASELINE]** | ≥ 0.03R **[LOCKED_INITIAL_BASELINE]** |
| Max drawdown limit | ≤ 25% **[LOCKED_INITIAL_BASELINE]** | ≤ 15% **[LOCKED_INITIAL_BASELINE]** | ≤ 10% **[LOCKED_INITIAL_BASELINE]** |
| Min no-trade quality | CORRECT_NO_TRADE ≥ 60%; SAVED_LOSS ≥ 0.20R per event **[LOCKED_INITIAL_BASELINE]** | CORRECT_NO_TRADE ≥ 55%; SAVED_LOSS ≥ 0.10R per event **[LOCKED_INITIAL_BASELINE]** | CORRECT_NO_TRADE ≥ 50%; SAVED_LOSS ≥ 0.05R per event **[LOCKED_INITIAL_BASELINE]** |
| Calibration requirement | Reliability error within ±10% per bucket **[LOCKED_INITIAL_BASELINE]** | Reliability error within ±10% per bucket **[LOCKED_INITIAL_BASELINE]** | Reliability error within ±15% per bucket **[LOCKED_INITIAL_BASELINE]** |
| Cost stress requirement | Edge survives taker × 1.5 multiplier stress **[LOCKED_INITIAL_BASELINE]** | Edge survives taker × 2.0 multiplier stress; cost-adjusted expectancy ≥ 0.10R **[LOCKED_INITIAL_BASELINE]** | Edge survives taker × 2.5 multiplier stress **[LOCKED_INITIAL_BASELINE]** |
| Shadow duration | ≥ 4 weeks **[LOCKED_INITIAL_BASELINE]** | ≥ 3 weeks **[LOCKED_INITIAL_BASELINE]** | ≥ 2 weeks **[LOCKED_INITIAL_BASELINE]** |
| Paper duration | ≥ 4 weeks **[LOCKED_INITIAL_BASELINE]** | ≥ 4 weeks **[LOCKED_INITIAL_BASELINE]** | ≥ 3 weeks **[LOCKED_INITIAL_BASELINE]** |
| Tiny live limit | Max 0.5% account risk per trade; max 5% daily loss; max 10% cumulative **[LOCKED_INITIAL_BASELINE]** | Max 0.25% account risk per trade; max 3% daily loss; max 7% cumulative **[LOCKED_INITIAL_BASELINE]** | Max 0.1% account risk per trade; max 2% daily loss; max 5% cumulative **[LOCKED_INITIAL_BASELINE]** |
| Owner review status | **LOCKED_INITIAL_BASELINE** — implementation-ready | **LOCKED_INITIAL_BASELINE** (2026-07-13) — implementation-ready, pending first full-dataset recalibration | **LOCKED_INITIAL_BASELINE** (2026-07-13) — implementation-ready, pending first full-dataset recalibration |

### SWING Baseline Rationale (Per Threshold)

| Threshold | Value | Rationale | Recalibration Trigger |
|-----------|-------|-----------|----------------------|
| Minimum OOS window | 12 months (6 folds × 2mo) | 12-month OOS coverage captures at least one full market cycle including regime transitions; 2-month validation windows balance recency vs statistical power | After first 12-month walk-forward completes |
| Minimum trades/events | ≥ 200 | 200 trades produces expectancy confidence interval width of ~0.14R at typical SWING variance — sufficient to reject zero-expectancy null | After first walk-forward: if variance higher than expected, increase threshold |
| Minimum expectancy R | ≥ 0.15R | Conservative net-expectancy floor after costs; below 0.15R the edge-to-noise ratio is too low for reliable promotion | After first walk-forward: recalibrate based on realized cost-adjusted distribution |
| Max drawdown limit | ≤ 25% | 25% drawdown allows for regime transitions while preventing catastrophic capital impairment; aligned with Kelly-fraction risk sizing | After first multi-regime walk-forward: tighten if drawdown recovery periods exceed 6 months |
| Min no-trade quality | CORRECT_NO_TRADE ≥ 60%; SAVED_LOSS ≥ 0.20R | SWING has LOW no-trade tendency — high correctness threshold ensures NO_TRADE is deliberate, not lazy | After first evaluation: adjust if MISSED_OPPORTUNITY rate exceeds 25% |
| Calibration requirement | ±10% per bucket | 10% reliability error ensures probability/expected-R surfaces are trustworthy enough for policy dual-gate decisions | After first calibration run: tighten to ±8% if model shows stable calibration |
| Cost stress requirement | taker × 1.5 | 1.5× multiplier provides margin above taker baseline; conservative enough to catch hidden cost sensitivity without being so strict it blocks viable edge | After first cost stress run: if edge survives 2.0×, raise stress multiplier |
| Shadow duration | ≥ 4 weeks | 4-week shadow captures ~20-30 SWING trades at typical 4h frequency — sufficient to detect material backtest-shadow divergence | Always 4-week minimum; extend if first shadow period shows high variance |
| Paper duration | ≥ 4 weeks | Matches shadow duration; ensures paper outcomes are statistically comparable to shadow and backtest baselines | Always 4-week minimum; extend if paper-shadow divergence detected |
| Tiny live limit | 0.5% risk/trade; 5% daily; 10% cumulative | Conservative progressive limits: per-trade risk small enough to survive 20 consecutive losses, daily cap prevents single-day spiral, cumulative cap limits total tiny-live exposure | After first tiny-live period: adjust based on realized vs expected loss distribution |

**SWING Recalibration Policy:** All SWING LOCKED_INITIAL_BASELINE thresholds must be recalibrated after the first SWING walk-forward/backtest evidence is available. Recalibration is an owner-reviewed decision, not an automated process. Thresholds do not automatically promote to LOCKED without owner review of the first empirical evidence.

### SCALP / AGGRESSIVE_SCALP Baseline Rationale (Per Threshold)

| Threshold | SCALP Value | AGGRESSIVE_SCALP Value | Rationale | Recalibration Trigger |
|-----------|-------------|-------------------------|-----------|----------------------|
| Minimum OOS window | 12 months (6 folds × 2mo) | 6 months (6 folds × 1mo) | SCALP (1h) needs the same regime-cycle coverage as SWING; AGGRESSIVE_SCALP (15m/5m) generates enough events in half the calendar time to reach its trade-count floor | After first full-dataset walk-forward for each mode completes |
| Minimum trades/events | ≥ 500 | ≥ 300 | Higher-frequency modes require more events for the same expectancy confidence-interval width, offset by shorter OOS windows generating more events/month | After first walk-forward: if variance higher than expected, increase threshold |
| Minimum expectancy R | ≥ 0.05R | ≥ 0.03R | Lower per-trade R floor than SWING is intentional — SCALP/AGGRESSIVE_SCALP compensate with trade frequency; too high a floor here would reject viable high-frequency edges | After first walk-forward: recalibrate based on realized cost-adjusted distribution |
| Max drawdown limit | ≤ 15% | ≤ 10% | Tighter than SWING because higher trade frequency compounds drawdown faster; AGGRESSIVE_SCALP tightest given shortest holding periods | After first multi-regime walk-forward: tighten if recovery periods exceed 3 months |
| Min no-trade quality | CORRECT_NO_TRADE ≥ 55%; SAVED_LOSS ≥ 0.10R | CORRECT_NO_TRADE ≥ 50%; SAVED_LOSS ≥ 0.05R | Higher-frequency modes naturally produce more NO_TRADE noise; thresholds are relaxed vs SWING but still reject a lazy/collapsed classifier | After first evaluation: adjust if MISSED_OPPORTUNITY rate exceeds 25% |
| Calibration requirement | ±10% per bucket | ±15% per bucket | AGGRESSIVE_SCALP's noisier microstructure features justify a looser reliability bound than SCALP/SWING | After first calibration run: tighten if model shows stable calibration |
| Cost stress requirement | taker × 2.0; cost-adjusted expectancy ≥ 0.10R | taker × 2.5 | Higher trade frequency means cost sensitivity compounds faster — SCALP/AGGRESSIVE_SCALP require a harsher stress multiplier than SWING's 1.5× | After first cost stress run: if edge survives further stress, raise multiplier |
| Shadow duration | ≥ 3 weeks | ≥ 2 weeks | Higher event frequency reaches statistically comparable trade counts faster than SWING's 4 weeks | Always minimum; extend if first shadow period shows high variance |
| Paper duration | ≥ 4 weeks | ≥ 3 weeks | Matches shadow duration reasoning; ensures paper outcomes are statistically comparable to shadow/backtest | Always minimum; extend if paper-shadow divergence detected |
| Tiny live limit | 0.25% risk/trade; 3% daily; 7% cumulative | 0.1% risk/trade; 2% daily; 5% cumulative | Progressively tighter than SWING given higher trade frequency and shorter holding periods compound risk faster | After first tiny-live period: adjust based on realized vs expected loss distribution |

**SCALP/AGGRESSIVE_SCALP Recalibration Policy:** These LOCKED_INITIAL_BASELINE thresholds were promoted from HOLD placeholders by owner decision (2026-07-13) specifically so the deterministic V7-Lite readiness gate (`v7/lite/readiness_gate.py`) can evaluate G0-G6 as real PASS/FAIL. They must be recalibrated after each mode's first full 5-symbol / full-feature walk-forward/backtest evidence — same policy as SWING. Locking the threshold values does **not** mean either mode has passed any gate; as of 2026-07-13 no full-dataset SCALP/AGGRESSIVE_SCALP run has been scored against them (see `v7/docs/roadmap.md`).

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

## Layer Metric Ownership

**Critical decision — added 2026-07-02 after FREEZE_AND_REDESIGN RCA.**

Each layer owns distinct metrics. A metric that belongs to one layer must NOT be used to evaluate another layer. This was the root cause of the AlphaForge profitability confusion — trade-level metrics (Sharpe, win rate, PF) were applied to AlphaForge, which is a signal provider, not a trader.

| Layer | Owns These Metrics | Does NOT Own |
|-------|-------------------|-------------|
| **Simulation** | Outcome truth: realized R (gross/net), MFE/MAE, stop/target/horizon, cost decomposition, funding outcome | Model accuracy, signal quality, trade profitability, execution quality |
| **AlphaForge** | Signal quality: **IC** (Information Coefficient), **Rank IC**, calibration error (ECE/MCE), signal stability across folds, regime consistency of signal, MHT survival, incremental information share | Win rate, profit factor, Sharpe ratio, drawdown — these are V7's metrics |
| **V7** | Trade outcomes: net R, Sharpe, profit factor, max drawdown, risk-adjusted return, regret, no-trade quality, mode-level P&L | Execution quality, signal quality (consumes AlphaForge signal but does NOT replace it) |
| **Runtime** | Execution quality: slippage vs benchmark, fill rate, latency, realized vs simulated cost divergence, order book impact | Model accuracy, backtest profitability, signal IC |

### Enforcement

1. **AlphaForge validation reports MUST NOT list Sharpe, win rate, or profit factor as primary success metrics.** These are V7-level trade outcomes. AlphaForge reports IC, Rank IC, calibration error, and signal stability.
2. **V7 evaluation MUST NOT use classification accuracy as a proxy for economic performance.** Accuracy is a diagnostic for AlphaForge's calibration health, not a trade outcome predictor.
3. **Simulation MUST NOT be judged by model performance.** Simulation is the truth source — it is correct by definition. Discrepancies between simulation and live outcomes belong to the Runtime layer.
4. **Runtime MUST NOT use backtest profitability as an execution quality metric.** Backtest assumes perfect fills. Runtime measures the gap between simulated and realized outcomes.

### Why This Was Wrong Before

The original `ai_summary__v7_alphaforge_xgb.md` (625KB combined doc, May 2026) defined AlphaForge as a "classifier" and listed trade-level artifacts ("v7_alphaforge_xgb_swing_classifier"). The authority lock (P0.8B, June 2026) correctly separated layer authorities in the architecture docs but never corrected the metric ownership. The code (`train.py`) continued to train a classifier, report accuracy, and compute trade-level metrics — all of which belong to V7, not AlphaForge.

This is now corrected. All docs and code must align to the table above.

---

## Final Position

Evaluation is where V7 proves that its profitability claims are real. Hybrid modeling is useful only if classification, regression, calibration, regime awareness, and policy together improve economic evidence — independently per mode scope.
