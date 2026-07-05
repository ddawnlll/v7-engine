# AlphaForge Report Contracts

**Purpose:** Define the format, required sections, and verdict system for AlphaForge research reports.

**Authority:** AlphaForge owns report formats and verdict assignment (within its scope). V7 owns final acceptance. This document is LOCKED.

---

## Report Hierarchy

```
AlphaForgeResearchReport (aggregate, cross-mode)
├── ModeResearchReport (SCALP)        ← primary_research_report
├── ModeResearchReport (AGGRESSIVE_SCALP) ← primary_research_report
└── ModeResearchReport (SWING)        ← secondary_baseline_report
```

---

## AlphaForgeResearchReport

**Schema:** [alphaforge_research_report.schema.json](../../contracts/schemas/alphaforge/alphaforge_research_report.schema.json)

**Purpose:** Aggregate cross-mode synthesis. Contains all mode reports, promoted/rejected candidates, and global limitations.

**Required sections:**
1. **Header:** alphaforge_report_id, run_id, created_at
2. **Mode Reports:** Array of ModeResearchReport references
3. **Promoted Candidates:** Array of AlphaCandidate IDs promoted to CANDIDATE_FOR_V7_GATES
4. **Rejected Candidates:** Array of rejected AlphaCandidate IDs with rejection reasons
5. **Global Limitations:** Cross-mode limitations and caveats
6. **V7 Handoff Packages:** Array of V7HandoffPackage references

---

## ModeResearchReport

**Schema:** [mode_research_report.schema.json](../../contracts/schemas/alphaforge/mode_research_report.schema.json)

**Purpose:** Per-mode research report with verdict.

**Required sections:**

### 1. Header
- report_id, mode, mode_priority, report_type
- created_at, run_id reference

### 2. Data Scope
- Symbols covered
- Date range
- Primary/secondary timeframes
- Data quality summary

### 3. Feature Set References
- FeatureSetSpec IDs used
- Feature count per group
- Leakage audit summary

### 4. Label Dataset References
- LabelDatasetSpec IDs used
- Simulation profiles used
- Label distribution (LONG/SHORT/NO_TRADE/AMBIGUOUS)
- Funding status

### 5. Alpha Theses
- Array of alpha thesis summaries
- Status per thesis
- Evidence quality per thesis

### 6. Validation Summary
- Walk-forward fold count and configuration
- OOS performance metrics
- Symbol stability assessment
- Overfit risk assessment

### 7. Metrics
**Layer-appropriate metrics (corrected 2026-07-02):** AlphaForge reports signal quality, not trade outcomes. Win rate, Sharpe, profit factor belong to V7. See `v7/docs/pipeline/evaluation.md` Layer Metric Ownership section.

**Primary AlphaForge metrics:**
- Per-fold IC (Information Coefficient) and Rank IC
- Calibration error (ECE/MCE) per fold
- Signal stability: IC variance across folds
- Regime consistency: IC breakdown by regime
- MHT survival: PBO, deflated Sharpe, corrected significance

**Reported for V7 consumption (not AlphaForge success metrics):**
- Edge magnitude (expected return per trade)
- Win rate
- Sharpe, profit factor, drawdown

### 8. Cost Stress
- Fee sensitivity analysis (±X%)
- Slippage sensitivity analysis (±X%)
- Combined stress scenarios
- Break-even cost threshold

### 9. NO_TRADE Comparison
- LONG vs NO_TRADE comparison
- SHORT vs NO_TRADE comparison
- Is the alpha better than doing nothing?

### 10. Regime Breakdown
- Performance per volatility regime
- Performance per volume regime
- Performance per market session
- Any regimes where edge disappears?

### 11. Verdict
One of the allowed verdicts (see below).

### 12. Blocked Scopes
- Features/theses that could not be researched
- Reasons for blocking

### 13. Limitations
- Known limitations of this report
- Data quality caveats
- Model limitations

---

## Verdict System

### Verdicts by Report Type

**primary_research_report** (SCALP, AGGRESSIVE_SCALP):

| Verdict | Meaning |
|---------|---------|
| REJECT | Alpha does not meet evidence requirements. Do not continue. |
| CONTINUE_RESEARCH | Promising but needs more work. Not ready for V7. |
| CANDIDATE_FOR_V7_GATES | Ready for V7 acceptance evaluation. |

**secondary_baseline_report** (SWING):

| Verdict | Meaning |
|---------|---------|
| REJECT | Does not meet baseline requirements. |
| BASELINE_WEAK | Meets some baseline criteria but has known weaknesses. |
| BASELINE_VALID | Meets all baseline criteria. |
| CANDIDATE_FOR_V7_GATES | Exceeds baseline. Ready for V7 acceptance evaluation. |

---

## Report Rules

### Reports are NOT trade commands
- A report verdict of CANDIDATE_FOR_V7_GATES does NOT authorize live trading.
- V7 acceptance gates are the sole authority for trade authorization.
- Reports are evidence packages, not execution orders.

### Reports must be rejectable
- Every report must carry enough evidence that a reviewer can independently decide to reject.
- If a report cannot justify its verdict from its own data, it is incomplete.

### Reports must include NO_TRADE comparison
- Every ModeResearchReport must answer: "Is this alpha better than doing nothing?"
- If the answer is "no" or "unclear," the verdict must reflect this.

### Reports must include cost stress
- Fee and slippage assumptions must be stressed.
- If edge disappears under moderate stress, this must be reported.

---

## SCALP Primary Research Report

**Report type:** `primary_research_report`
**Allowed verdicts:** REJECT, CONTINUE_RESEARCH, CANDIDATE_FOR_V7_GATES
**Required cautions:**
- Fee sensitivity (high trade frequency → high fee impact)
- Slippage sensitivity (short holding periods → high slippage impact)
- NO_TRADE comparison (high opportunity cost of overtrading)
- Overfit risk (high dimensionality relative to sample)
- Regime breakdown (must cover high-vol and low-vol separately)

## AGGRESSIVE_SCALP Primary Research Report

**Report type:** `primary_research_report`
**Allowed verdicts:** REJECT, CONTINUE_RESEARCH, CANDIDATE_FOR_V7_GATES
**Required cautions:**
- Higher fee/slippage sensitivity than SCALP
- Liquidity/spread limitation (aggressive entries may not fill)
- Latency caveat (fast reversals may not be executable at reported prices)
- Fast reversal risk
- Strong overfit control (highest dimensionality)

## SWING Secondary Baseline Report

**Report type:** `secondary_baseline_report`
**Allowed verdicts:** REJECT, BASELINE_WEAK, BASELINE_VALID, CANDIDATE_FOR_V7_GATES
**Required cautions:**
- Secondary baseline only — does not override primary research priority
- Threshold recalibration after first walk-forward
- Standard overfit controls sufficient

---

## Related Docs

- [ai_summary.md](ai_summary.md)
- [alpha_thesis_lifecycle.md](alpha_thesis_lifecycle.md)
- [validation_contract.md](validation_contract.md)
- [model_artifact_contract.md](model_artifact_contract.md)
- [handoff_to_v7.md](handoff_to_v7.md)

## Related Contracts

- [../../contracts/schemas/alphaforge/mode_research_report.schema.json](../../contracts/schemas/alphaforge/mode_research_report.schema.json)
- [../../contracts/schemas/alphaforge/alphaforge_research_report.schema.json](../../contracts/schemas/alphaforge/alphaforge_research_report.schema.json)
- [../../contracts/fixtures/alphaforge/](../../contracts/fixtures/alphaforge/) — minimal fixtures

## Forbidden Assumptions

- CANDIDATE_FOR_V7_GATES does NOT mean V7 will accept.
- A report is not a trade authorization.
- Baseline validation for SWING does not make SWING a primary product.

## Open Holds

- SCALP/AGGRESSIVE_SCALP verdicts limited to CONTINUE_RESEARCH until empirical evidence exists.
- SWING BASELINE_VALID requires first walk-forward to confirm.
