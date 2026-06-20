# Alpha Thesis Lifecycle

**Purpose:** Define the alpha thesis lifecycle — how an idea moves from proposal through research, validation, and ultimately becomes a V7 candidate or is rejected.

**Authority:** AlphaForge owns the alpha thesis lifecycle. This document is LOCKED.

---

## States

| State | Meaning | Entry Condition | Exit Condition |
|-------|---------|----------------|----------------|
| PROPOSED | Idea formalized as alpha thesis | Thesis document written with hypothesis and rejection criteria | DATA_READY or REJECTED |
| DATA_READY | Required data is available and validated | Data scope defined, quality checks passed | FEATURED |
| FEATURED | Feature set specified and computed | FeatureSetSpec defined, no leakage detected | SIMULATED |
| SIMULATED | Simulation run complete, labels generated | LabelDataset produced from SimulationOutput | TRAINED or REJECTED |
| TRAINED | Model training complete | Model artifact produced, training metrics recorded | VALIDATED or REJECTED |
| VALIDATED | Walk-forward validation complete | ValidationReport produced, all required checks passed | V7_CANDIDATE, REJECTED, or CONTINUE_RESEARCH |
| V7_CANDIDATE | Packaged for V7 acceptance gates | V7HandoffPackage assembled, all evidence attached | ARCHIVED (after V7 decision) |
| REJECTED | Failed to meet evidence requirements | Rejection criteria triggered | ARCHIVED (after review period) |
| ARCHIVED | Final state | Thesis lifecycle complete | — |

---

## State Transition Rules

### PROPOSED → DATA_READY
**Required:**
- Alpha thesis document complete with hypothesis, expected edge mechanism, required data, required features, risk factors, and rejection criteria.
- Data scope defined: symbols, intervals, timeframe stack, date range.
- All data sources identified and accessible.

### DATA_READY → FEATURED
**Required:**
- Normalized market data available and quality-checked.
- FeatureSetSpec defined per mode.
- Feature leakage policy documented and enforced.
- No future-looking features.

### FEATURED → SIMULATED
**Required:**
- Simulation profile selected per mode.
- Simulation run complete producing SimulationOutput.
- LabelDataset generated from SimulationOutput per [label_contract.md](label_contract.md).
- NO_TRADE comparison computed.

### SIMULATED → TRAINED
**Required:**
- Training/validation/OOS split defined.
- Model training run executed.
- Training metrics recorded.
- Model artifact produced.

### TRAINED → VALIDATED
**Required (ALL must pass):**
- Walk-forward validation across all folds.
- OOS performance metrics computed.
- Cost stress analysis (fee + slippage sensitivity).
- NO_TRADE comparison (edge over doing nothing).
- Regime breakdown (does edge hold across regimes?).
- Symbol stability check (does edge work on multiple symbols?).
- Overfit risk flags assessed.
- Calibration quality checked.

### VALIDATED → V7_CANDIDATE
**Required:**
- Validation verdict is CONTINUE_RESEARCH, CANDIDATE_FOR_V7_GATES, or BASELINE_VALID.
- All required evidence attached.
- V7HandoffPackage assembled per [handoff_to_v7.md](handoff_to_v7.md).
- V7 gate mapping complete.
- Blocked scopes and limitations explicit.

---

## Rejection Rules

An alpha candidate MUST be rejected if ANY of these conditions are true:

1. **NO_TRADE beats directional:** NO_TRADE outperforms both LONG and SHORT after costs.
2. **Non-positive OOS expectancy:** OOS expected return is ≤ 0 after costs.
3. **Cost stress flips edge negative:** Applying worst-case (but plausible) fee/slippage assumptions eliminates the edge.
4. **Single-symbol overfitting:** Edge only works on one symbol without a documented rationale.
5. **Rare-regime overfitting:** Edge only appears in a regime that is untradeable or too rare.
6. **Feature leakage detected:** Any feature uses future information.
7. **Funding impact unknown but required:** Alpha requires perpetual/live trading but funding model is DEFERRED.
8. **Excessive drawdown:** Drawdown exceeds mode-allowed threshold.
9. **Unusable calibration:** Calibration quality is too poor for reliable probability estimates.
10. **Missing lineage:** Report lacks required dataset references, checksums, or provenance.
11. **Missing checksum:** Model artifact has no checksum or validation report reference.
12. **Missing V7 gate mapping:** Handoff package has no V7 gate mapping.

---

## Required Evidence Per State

| State | Required Evidence |
|-------|-------------------|
| PROPOSED | AlphaThesis document |
| DATA_READY | Data quality flags, source manifest |
| FEATURED | FeatureSetSpec, leakage audit |
| SIMULATED | SimulationOutput, LabelDatasetSpec, NO_TRADE comparison |
| TRAINED | ModelArtifact, training metrics |
| VALIDATED | ValidationReport (all sections) |
| V7_CANDIDATE | V7HandoffPackage (complete) |

---

## Mode-Specific Lifecycle Notes

### SCALP (PRIMARY)
- Stricter fee sensitivity requirements (high trade frequency).
- Must demonstrate edge survives realistic slippage.
- NO_TRADE comparison is mandatory (high opportunity cost of overtrading).
- Regime breakdown must cover high-volatility and low-volatility separately.

### AGGRESSIVE_SCALP (PRIMARY)
- Highest fee/slippage sensitivity (very high trade frequency).
- Liquidity/spread limitation caveat required.
- Latency caveat (fast reversals may not be executable).
- Strongest overfit control (high-dimensional feature space risk).
- NO_TRADE comparison is mandatory.

### SWING (SECONDARY_BASELINE)
- Lower fee sensitivity (lower trade frequency).
- Baseline overfit controls sufficient.
- NO_TRADE comparison required but less stringent.
- Threshold recalibration after first walk-forward.

---

## NO_TRADE Comparison Requirement

Every alpha thesis validation MUST include:

- Comparative metrics: LONG vs NO_TRADE, SHORT vs NO_TRADE.
- Cost-adjusted comparison (after fees and slippage).
- The question "Is this alpha better than doing nothing?" must be answerable from the report.
- If NO_TRADE beats both directional actions, the thesis is REJECTED.

---

## Cost Stress Requirement

Every alpha thesis validation MUST include:

- Sensitivity analysis: ±X% on fee assumptions.
- Sensitivity analysis: ±X% on slippage assumptions.
- The question "Does the edge survive plausible cost variation?" must be answerable.
- If edge disappears under moderate cost stress, thesis cannot reach V7_CANDIDATE.

---

## Walk-Forward Requirement

Every alpha thesis MUST undergo walk-forward validation:

- Minimum folds: defined per mode in [validation_contract.md](validation_contract.md).
- OOS period must be genuinely out-of-sample (no information leakage).
- Purge/embargo policy must be documented.
- Walk-forward results must be reported per fold and aggregated.

---

## Related Docs

- [ai_summary.md](ai_summary.md)
- [discovery_authority.md](discovery_authority.md)
- [data_contract.md](data_contract.md)
- [feature_contract.md](feature_contract.md)
- [label_contract.md](label_contract.md)
- [report_contracts.md](report_contracts.md)
- [validation_contract.md](validation_contract.md)
- [handoff_to_v7.md](handoff_to_v7.md)
- [decision_log.md](decision_log.md)

## Related Contracts

- [../../contracts/schemas/alphaforge/alpha_thesis.schema.json](../../contracts/schemas/alphaforge/alpha_thesis.schema.json)
- [../../contracts/schemas/alphaforge/alpha_candidate.schema.json](../../contracts/schemas/alphaforge/alpha_candidate.schema.json)

## Forbidden Assumptions

- An alpha is not "working" just because it was trained.
- Rejection is a normal outcome, not a failure of the process.
- VALIDATED does not mean promotion-ready — V7 decides.

## Open Holds

- SCALP and AGGRESSIVE_SCALP thresholds cannot be locked without empirical evidence.
- Funding DEFERRED blocks perpetual/live lifecycle stages.
