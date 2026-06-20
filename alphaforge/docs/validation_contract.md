# AlphaForge Validation Contract

**Purpose:** Define the walk-forward validation standard, split policy, required checks, and overfit detection rules for AlphaForge alpha candidates.

**Authority:** AlphaForge owns validation design and execution. This document is LOCKED.

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
| Minimum folds | 5 | 5 | 3 |
| Train window (bars) | ~5000 | ~5000 | ~2000 |
| Test window (bars) | ~1000 | ~1000 | ~500 |
| Anchored vs rolling | Rolling | Rolling | Anchored or Rolling |

Anchored: Train window expands forward. Rolling: Train window of fixed size rolls forward.

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

Alpha candidates must demonstrate stability across symbols:

- Minimum symbols tested: defined per mode.
- If only one symbol is available, this is a LIMITATION and must be flagged.
- Cross-symbol metric variance must be reported.
- If edge only works on one symbol without rationale → REJECT.

---

## Regime Breakdown

Performance must be broken down by market regime:

| Regime | Definition |
|--------|------------|
| HIGH_VOL_UP | High volatility, upward trend |
| HIGH_VOL_DOWN | High volatility, downward trend |
| LOW_VOL_RANGE | Low volatility, ranging |
| LOW_VOL_TREND | Low volatility, trending |
| NORMAL | Neither extreme |

**Requirement:** If edge only exists in one regime, the report must state this explicitly. If that regime is rare or untradeable → REJECT.

---

## Cost Stress

Every validation must include cost stress:

### Fee Sensitivity
- Baseline fee assumption (e.g., 0.04% per trade).
- Stress scenarios: 1.5×, 2×, 3× baseline fee.
- For each: does the edge survive?

### Slippage Sensitivity
- Baseline slippage assumption.
- Stress scenarios: 1.5×, 2×, 3× baseline slippage.
- For each: does the edge survive?

### Combined Stress
- Both fee and slippage stressed simultaneously.
- Worst plausible case.

### Break-Even Cost
- The maximum cost (fee + slippage) at which the edge breaks even.
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

## Minimum Evidence Requirements by Mode

### SCALP (PRIMARY)
- 5+ walk-forward folds
- 2+ symbols (if available)
- Full cost stress (3 levels each for fee and slippage)
- Regime breakdown across 4+ regimes
- NO_TRADE comparison
- Overfit risk assessment

### AGGRESSIVE_SCALP (PRIMARY)
- 5+ walk-forward folds
- 2+ symbols (if available)
- Full cost stress (3 levels each)
- Liquidity/spread analysis
- Latency caveat documented
- Regime breakdown across 4+ regimes
- NO_TRADE comparison
- Strongest overfit controls

### SWING (SECONDARY_BASELINE)
- 3+ walk-forward folds
- 1+ symbol (limitation must be flagged if only 1)
- Standard cost stress (2 levels)
- Regime breakdown across 3+ regimes
- NO_TRADE comparison
- Standard overfit controls

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
