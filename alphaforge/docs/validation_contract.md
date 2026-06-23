# AlphaForge Validation Contract

**Purpose:** Define the walk-forward validation standard, split policy, required checks, overfit detection rules, MHT/data-snooping controls, and V7 gate alignment for AlphaForge alpha candidates.

**Authority:** AlphaForge owns validation design and execution. This document is LOCKED.

**P0.8E note:** Regime taxonomy aligned to V7 canonical (TREND_UP/TREND_DOWN/RANGE/TRANSITION). Walk-forward fold minimum corrected to 6 for all modes. MHT/data-snooping controls added. Symbol stability made quantitative (40%/60% limits). Cost stress now requires spread and funding deferred block. Calibration reliability mapped to G6.

---

## ValidationReport

**Schema:** [validation_report.schema.json](../../contracts/schemas/alphaforge/validation_report.schema.json)

Every alpha candidate that reaches TRAINED state must produce a ValidationReport before advancing to VALIDATED state.

---

## Split Policy

### Train / Validation / OOS

| Split | Purpose | Minimum % |
|-------|---------|-----------|
| Train | Model fitting | ~60% |
| Validation | Hyperparameter tuning, early stopping | ~20% |
| OOS (Out of Sample) | Final evaluation | ~20% |

**Rules:**
- OOS data must be chronologically AFTER all training and validation data.
- NO shuffling across time boundaries.
- Purge window between splits: minimum N bars (mode-dependent).
- Embargo policy: no training sample within M bars of any test sample.

### Purge Windows by Mode

| Mode | Purge Bars | Rationale |
|------|-----------|-----------|
| SCALP | 100 bars (5m) | Short holding, but feature windows may overlap |
| AGGRESSIVE_SCALP | 200 bars (5m) | Higher dimensionality → higher leakage risk |
| SWING | 20 bars (4h) | Longer holding, wider bar spacing |

---

## Walk-Forward Folds

### Configuration

| Parameter | SCALP | AGGRESSIVE_SCALP | SWING |
|-----------|-------|-----------------|-------|
| Minimum folds | 6 | 6 | 6 |
| Train window (bars) | ~5000 | ~5000 | ~2000 |
| Test window (bars) | ~1000 | ~1000 | ~500 |
| Anchored vs rolling | Rolling | Rolling | Anchored or Rolling |

Anchored: Train window expands forward. Rolling: Train window of fixed size rolls forward.

**P0.8E correction:** All modes require minimum 6 walk-forward folds, aligned to V7 canonical G2: WALK_FORWARD_OOS requirement. Previous per-mode variation (5/5/3) was AlphaForge-invented and did not match V7 evaluation.md.

### Required Output Per Fold

- Train metrics
- Validation metrics
- OOS metrics
- Fold-specific regime breakdown
- Fold-specific cost stress

---

## OOS Summary

The aggregate OOS summary must include:

| Metric | Description |
|--------|-------------|
| OOS Sharpe ratio | Risk-adjusted return on OOS period |
| OOS win rate | % of trades with positive R |
| OOS expectancy | Average R per trade |
| OOS max drawdown | Maximum peak-to-trough in R |
| OOS profit factor | Gross gain / gross loss |
| OOS trades count | Number of decision points |
| OOS stability | Variance of metrics across folds |

---

## Symbol Stability

Alpha candidates must demonstrate stability across symbols with **quantitative concentration limits:**

| Limit | Threshold | Description |
|-------|-----------|-------------|
| Max single symbol concentration | **40%** | No single symbol may contribute >40% of total edge |
| Max cluster concentration | **60%** | No correlated cluster may contribute >60% of total edge |
| Minimum symbols tested | ≥2 (if available) | If only 1 symbol available, flag as LIMITATION |
| Cross-symbol metric variance | Must be reported | Variance of OOS expectancy across symbols |

**P0.8E:** Symbol stability limits are now quantitative (40%/60%) aligned to V7 canonical G5: SYMBOL_STABILITY. Previous qualitative-only assessment was insufficient.

- If only one symbol is available, this is a LIMITATION and must be flagged.
- Cross-symbol metric variance must be reported.
- If edge only works on one symbol without rationale → REJECT.

---

## Regime Breakdown

Performance must be broken down by market regime using the **V7 canonical regime taxonomy** from `v7/docs/pipeline/evaluation.md`:

| Regime | Definition |
|--------|------------|
| TREND_UP | Sustained upward price movement with directional conviction |
| TREND_DOWN | Sustained downward price movement with directional conviction |
| RANGE | Price oscillating within a bounded channel without clear direction |
| TRANSITION | Regime shift in progress — elevated uncertainty, changing volatility |

**P0.8E correction:** Previous AlphaForge-invented regime names (HIGH_VOL_UP, HIGH_VOL_DOWN, LOW_VOL_RANGE, LOW_VOL_TREND, NORMAL) replaced with V7 canonical taxonomy. All schemas, fixtures, and reports must use TREND_UP/TREND_DOWN/RANGE/TRANSITION.

**Requirement:** If edge only exists in one regime, the report must state this explicitly. If that regime is rare or untradeable → REJECT.

---

## Cost Stress

Every validation must include cost stress:

### Required Components

| Component | Status | Description |
|-----------|--------|-------------|
| Fee | REQUIRED | Baseline fee assumption (e.g., 0.04% per trade) |
| Slippage | REQUIRED | Baseline slippage assumption |
| Spread / Spread Proxy | REQUIRED | Bid-ask spread estimate or proxy |
| Funding | DEFERRED_BLOCK | Placeholder required; must block live promotion if not implemented |

### Fee Sensitivity
- Baseline fee assumption (e.g., 0.04% per trade).
- Stress scenarios: 1.5×, 2×, 3× baseline fee.
- For each: does the edge survive?

### Slippage Sensitivity
- Baseline slippage assumption.
- Stress scenarios: 1.5×, 2×, 3× baseline slippage.
- For each: does the edge survive?

### Spread Sensitivity
- Baseline spread assumption or proxy (e.g., tick size × multiplier).
- Stress scenarios: 1.5×, 2× baseline spread.
- For each: does the edge survive?

### Funding Deferred Block
- If funding model is DEFERRED, a `funding_deferred_block` must be present.
- This block explicitly states that live/perpetual promotion is blocked until funding is implemented.
- A report without this block when funding is DEFERRED is structurally invalid.

### SCALP Reference Minimum
- Cost-adjusted OOS expectancy for SCALP must meet **≥0.10R** after cost stress (aligned to V7 G3: COST_STRESS).

### Combined Stress
- Fee, slippage, and spread stressed simultaneously.
- Worst plausible case.

### Break-Even Cost
- The maximum cost (fee + slippage + spread) at which the edge breaks even.
- If break-even cost is below realistic minimum → REJECT.

---

## Overfit Risk Flags

The validation report must assess these overfit indicators:

| Flag | Detection Method |
|------|-----------------|
| Train/OOS gap | Large gap between train and OOS metrics |
| Fold instability | High variance of OOS metrics across folds |
| Feature count / sample ratio | Too many features relative to samples |
| Top feature dominance | One or two features drive all performance |
| Calibration degradation | Calibration gets worse in OOS |
| Purge violation | Any evidence of train-test leakage |

If multiple flags fire → strong overfit risk → cannot be V7_CANDIDATE.

---

## MHT / Data-Snooping Controls

**P0.8E addition.** Every validation report must include multiple hypothesis testing (MHT) and data-snooping controls. A report that silently omits how many hypotheses/features/theses were tested is structurally incomplete.

### Required Fields

| Field | Description |
|-------|-------------|
| `tested_hypothesis_count` | Total number of hypotheses/theses/feature-sets tested across this research run |
| `correction_method` | Method applied: FDR, Bonferroni, Deflated_Sharpe, PBO, or `NONE_APPLIED` |
| `corrected_significance` | Significance after correction (null if NONE_APPLIED) |
| `false_discovery_control` | Whether FDR or equivalent is active |
| `deflated_sharpe_or_equivalent` | Deflated Sharpe ratio or PBO risk assessment result |
| `pbo_or_backtest_overfit_risk` | Probability of Backtest Overfit assessment |
| `trial_count_disclosure` | How many trial configurations were tested |
| `rejected_candidate_count` | How many candidates were rejected during research |
| `data_snooping_risk_flag` | Overall risk flag: LOW, MEDIUM, HIGH, CRITICAL |

### Allowed Methods

| Method | Description |
|--------|-------------|
| FDR | False Discovery Rate (Benjamini-Hochberg) |
| Bonferroni | Bonferroni correction |
| Deflated_Sharpe | Deflated Sharpe ratio (Harvey-Liu) |
| PBO | Probability of Backtest Overfit (Bailey-Lopez de Prado) |
| NONE_APPLIED | Must carry a blocking hold if no method was applied |

### Blocking Rule

If `correction_method` is `NONE_APPLIED`:
- `data_snooping_risk_flag` must be HIGH or CRITICAL.
- A `blocking_hold` must be present explaining why MHT was not run.
- The report cannot claim robust edge without data-snooping control.
- This is a blocking condition for CANDIDATE_FOR_V7_GATES verdict.

---

## Calibration Reliability (G6)

**P0.8E:** Calibration reliability is mapped to V7 canonical G6: CALIBRATION_RELIABILITY (not a standalone AlphaForge concept). The CalibrationCandidate schema defines the required metrics (ECE, MCE, confidence bins). The validation report references the calibration candidate but the calibration assessment itself lives in the CalibrationCandidate artifact.

### Required Alignment

- Calibration assessment must use reliability error per confidence bucket.
- Predicted-vs-realized R bucket alignment must be reported.
- Calibration status (CALIBRATED/UNCALIBRATED/UNRELIABLE) maps to G6 pass/fail.
- Calibration degradation across folds is an overfit risk flag.

---

## Minimum Evidence Requirements by Mode

### SCALP (PRIMARY)
- **6 walk-forward folds** (P0.8E: aligned to V7 G2 canonical minimum)
- 2+ symbols (if available)
- Full cost stress (3 levels each for fee and slippage, 2 levels for spread)
- SCALP reference: cost-adjusted OOS expectancy ≥0.10R after cost stress
- Funding deferred block required
- Regime breakdown across all 4 canonical regimes (TREND_UP/DOWN/RANGE/TRANSITION)
- NO_TRADE comparison
- Overfit risk assessment
- **MHT/data-snooping control (P0.8E)**

### AGGRESSIVE_SCALP (PRIMARY)
- **6 walk-forward folds** (P0.8E: aligned to V7 G2 canonical minimum)
- 2+ symbols (if available)
- Full cost stress (3 levels each for fee, slippage, and spread)
- Liquidity/spread analysis
- Latency caveat documented
- Funding deferred block required
- Regime breakdown across all 4 canonical regimes
- NO_TRADE comparison
- Strongest overfit controls
- **MHT/data-snooping control (P0.8E — critical at 15m frequency)**

### SWING (SECONDARY_BASELINE)
- **6 walk-forward folds** (P0.8E: aligned to V7 G2 canonical minimum)
- 1+ symbol (limitation must be flagged if only 1)
- Standard cost stress (2 levels each for fee, slippage, spread)
- Funding deferred block required
- Regime breakdown across all 4 canonical regimes
- NO_TRADE comparison
- Standard overfit controls
- **MHT/data-snooping control (P0.8E)**

---

## Validation Verdicts

| Verdict | Criteria |
|---------|----------|
| PASS | All checks pass; OOS edge confirmed; cost stress survives |
| PASS_WITH_LIMITATIONS | Edge confirmed but with known limitations (single symbol, narrow regime, etc.) |
| FAIL_OVERFIT | OOS metrics significantly worse than train |
| FAIL_COST | Edge destroyed by realistic costs |
| FAIL_REGIME | Edge only in narrow/rare regimes |
| FAIL_OOS | Non-positive OOS expectancy |
| INCONCLUSIVE | Insufficient data for reliable conclusion |

---

## Related Docs

- [ai_summary.md](ai_summary.md)
- [alpha_thesis_lifecycle.md](alpha_thesis_lifecycle.md)
- [report_contracts.md](report_contracts.md)
- [model_artifact_contract.md](model_artifact_contract.md)
- [handoff_to_v7.md](handoff_to_v7.md)

## Related Contracts

- [../../contracts/schemas/alphaforge/validation_report.schema.json](../../contracts/schemas/alphaforge/validation_report.schema.json)

## Forbidden Assumptions

- Backtest pass ≠ live promotion evidence.
- Validation does NOT authorize trading.
- A single-symbol validation is a limitation, not a confirmation.

## Open Holds

- Exact purge/embargo parameters to be tuned per mode during implementation.
- Funding DEFERRED limits perpetual validation scenarios.
