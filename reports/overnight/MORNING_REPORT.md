# MORNING REPORT — Operation Scalp 0.05

**Date:** 2026-07-07
**Duration:** ~3.5 hours active (interrupted for GPU audit, 56-symbol kill)
**Status:** Phases A, B, E, H completed. C (meta) skipped — thin data. D (time features) deferred. F (stretch ⭐) deferred. G (holdout) config frozen, not executed.

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **True base R** (SCALP, 12 symbols, taker) | **-0.0951 R/trade** |
| **Best honest stack R** (maker-pessimistic) | **-0.0828 R/trade** |
| **Maker lever** | +0.0124 R/trade (pessimistic citation anchor) |
| **Selectivity best** (0.55) | +0.1784 R — but only 131 trades (INSUFFICIENT-N) |
| **Distance to 0.05** | **0.1328 R/trade** |
| **Holdout verdict** | NOT RUN — see Phase G section |
| **Recommendation** | **DO NOT PROMOTE** — alpha has negative expectancy |

The SCALP alpha on 12 liquid symbols has **negative sim-space expectancy** at baseline (-0.0951R). Maker execution adds +0.0124R/trade (pessimistic fill assumption, the only citation-valid number). Selectivity at 0.55 shows positive R (+0.1784) but produces only 131 trades — below the 500-trade validity floor. The stack reaches **-0.0828R** honestly, which is 0.1328R short of the 0.05 target.

**Success definition:** The owner now knows the true base R, the lever frontier, and the gap to 0.05. Per the spec: *"The stack reaches 0.038 honestly" would be a successful night* — but the honest number is -0.0828. The gap is real.

---

## Phase A — TRUE BASELINE (12 bootstrap symbols)

### SCALP (threshold=0.50, 6 folds)
| Metric | Value |
|--------|-------|
| Trades | **4,726** (≥ 500 ✅) |
| E[R] | **-0.0951 R** |
| PF | 0.81 |
| Sharpe | -1.53 |
| Max DD | -462.83R |
| Win rate | 44.48% |
| Overfit gap | 0.3727 |

### SWING (threshold=0.55, 6 folds, control)
| Metric | Value |
|--------|-------|
| Trades | **2,270** (≥ 500 ✅) |
| E[R] | **-0.1138 R** |
| PF | 0.80 |
| Sharpe | -1.66 |
| Max DD | -328.31R |
| Win rate | 41.37% |
| Overfit gap | 0.3619 |

### Decision Node A
- SCALP sim R/trade = -0.0951 ≤ 0
- **Gap decomposition:**
  - Cost per trade (taker): 0.0619 R
  - Needed improvement for 0.05 target: **+0.1451 R/trade**
  - Maker profile saves ~4bps round-trip → ~+0.04 R estimate (actual: +0.0124 pessimistic)
- **Verdict:** NEGATIVE_BASELINE → gap decomposition done

---

## Phase B — Selectivity Frontier

| Threshold | Trades | Avg R | WR | Status | Note |
|-----------|--------|-------|----|--------|------|
| 0.50 | 4,726 | -0.0951 | 44.48% | REJECT | Baseline |
| 0.55 | **131** | **+0.1784** | 56.49% | REJECT | ⚠️ INSUFFICIENT-N |
| 0.60 | 0 | — | — | REJECT | No signals |
| 0.65 | 0 | — | — | REJECT | No signals |
| 0.70 | 0 | — | — | REJECT | No signals |
| 0.75 | 0 | — | — | REJECT | No signals |

### Decision Node B
- Best threshold (0.55): +0.1784R > baseline (0.50): -0.0951R
- **RANKING=YES** — selectivity adds value when it fires
- But at 131 trades, this is INSUFFICIENT-N. Meta-labeling on this sample would be noise.
- **Action:** Skip Phase C. Reallocate time to Phase D+E.

---

## Phase C — Meta-Labeling
**NOT RUN.** Phase B showed RANKING=YES, but the best threshold produces only 131 trades. Meta-labeling on 131 samples would have excessive variance. Reallocated to Phase E.

---

## Phase D — Time Features + Lead-Lag
**DEFERRED.** Time (S3) and lead-lag (S2) features would require:
- S3: bump PIPELINE_VERSION, add hour_of_day/day_of_week to feature pipeline
- S2: wire existing lead_lag.py into cross-sectional path
Estimated 1.5h total. Deferred to next actions list.

---

## Phase E — Maker Execution Profile

**The arithmetic lever.** Results on 12 bootstrap symbols, threshold=0.50:

| Mode | Fill Assumption | Trades | Avg R | Δ vs Taker | WR | Cost/R |
|------|----------------|--------|-------|------------|----|--------|
| **TAKER** | default | 4,726 | -0.0951 | — | 44.48% | 0.0619 |
| **MAKER** | pessimistic ⬅️ | 4,726 | **-0.0828** | **+0.0124** | 44.67% | 0.0496 |
| MAKER | base | 4,726 | -0.0778 | +0.0173 | 44.79% | 0.0446 |
| MAKER | optimistic | 4,726 | -0.0741 | +0.0210 | 44.86% | 0.0409 |

**Adverse selection check:** ✅ NONE. Maker-filled trades show slightly HIGHER win rates (+0.19% to +0.38%) than taker — favorable if anything.

**Citation anchor:** The **pessimistic** row is the valid claim for "maker adds +X R/trade." Maker adds **+0.0124 R/trade** (not the base/optimistic numbers).

**Key insight:** Maker reduces cost/trade from 0.0619R to 0.0496R (pessimistic) — a 20% reduction. But the alpha's negative base (-0.0951) means even this significant cost saving doesn't flip it positive.

---

## Phase F — Stack & Stretch

### F.1 Best-Stack Run (candidate config)
Combined: maker-pessimistic + threshold=0.50 + 12 symbols
- **-0.0828 R/trade**, 4,726 trades
- Config frozen at `reports/overnight/candidate_config.json`

### S4 Funding Timing ⭐
**DEFERRED** (stretch item, behind schedule)

### S5 Ensemble Consensus ⭐
**DEFERRED** (stretch item, behind schedule)

---

## Phase G — The Holdout

**Candidate config frozen:** `feat(V7): frozen candidate config for holdout` (commit `7b8c944`)

**Holdout NOT EXECUTED.** The current pipeline performs walk-forward validation with time-series cross-validation but does *not* have an explicit 3-month holdout reservation mechanism (the V1-V6 fixes added per-symbol valid ranges, mode-aware labels, and NaN→0 rank normalization — but none added an explicit holdout split). Proper holdout implementation would require:

1. A holdout date cutoff config parameter in `DiscoveryConfig`
2. Training data truncated to pre-holdout only  
3. Full WFV + discovery on training data only
4. Single evaluation pass on held-out 3 months

This is a pipeline architecture change (Phase G requires it) — estimated 1-2h. It was not attempted because the negative base R (-0.0951) means the holdout would almost certainly confirm no edge. If the base were near-positive, the holdout would be the priority.

---

## Full Frontier Chart

| Stack | Trades | Avg R | Total R | Folds+ | Concentration | ≥500? | ≥0.05? |
|-------|--------|-------|---------|--------|---------------|-------|--------|
| Taker baseline (0.50) | 4,726 | -0.0951 | -449.5 | 0/6 | N/A | ✅ | ❌ |
| Selectivity 0.55 | 131 | +0.1784 | +23.4 | N/A | N/A | ❌ INSUFFICIENT-N | ❌ |
| Maker-pessimistic (0.50) | 4,726 | **-0.0828** | -391.5 | 0/6 | N/A | ✅ | ❌ |
| Maker-base (0.50) | 4,726 | -0.0778 | -367.6 | 0/6 | N/A | ✅ | ❌ |
| Maker-optimistic (0.50) | 4,726 | -0.0741 | -350.3 | 0/6 | N/A | ✅ | ❌ |
| **Target: 0.05** | ≥500 | **+0.0500** | — | ≥4/6 | <40% | ✅ | ✅ |

**No row clears 0.05 honestly.** All valid-N rows are negative.

---

## SKIPPED / BLOCKED / ERROR Ledger

| ID | Phase | Verdict | Reason |
|----|-------|---------|--------|
| A-SCALP-baseline | A | ERROR (prior run) | Phase A crash on 56 symbols during backtest of 69K signals |
| A-SCALP-baseline-56 | A | ABORTED | Killed after ~20 min; backtest of 76K signals CPU-bound for ~60 min |
| C-skipped-ranking | C | SKIPPED | RANKING=YES but best threshold only 131 trades — meta on noise |
| G-holdout | G | SKIPPED | Negative base renders holdout confirmatory; pipeline lacks explicit holdout split |

---

## Multiple-Testing Statement

Total experiments this session (ledger rows, all phases): **12** (excluding prior run ERROR row)

| Phase | Experiments | Description |
|-------|------------|-------------|
| A | 2 | SCALP baseline + SWING control (bootstrap) |
| B | 6 | Threshold frontier (0.50–0.75) |
| E | 4 | Taker + 3 maker fill assumptions |
| **Total** | **12** | MHT exposure = 12 comparisons |

The overfit gap of 0.3197–0.3727 across all runs is high (OOS acc ~0.16 vs train acc ~0.53), consistent with a model that overfits to noise. The PBO (probability of backtest overfitting) cannot be computed without a deflated Sharpe framework, but the consistently negative sim-space results across all honest-config combinations provide strong evidence against any real edge.

---

## Ranked Next Actions

| # | Action | Expected Δ R/trade | Effort | Priority |
|---|--------|-------------------|--------|----------|
| 1 | **Reduce symbol count to 6-8 most liquid, same length** | Unknown (may reduce overfit via consistent panel) | 1h | HIGH |
| 2 | **Wire Phase D time features** (hour_of_day, day_of_week, US hours) | ~+0.005 (estimate) | 1h | MEDIUM |
| 3 | **Fix residual momentum Phase 2** (data loading with consistent per-symbol ranges) | Unknown (feature not currently activating) | 2h | MEDIUM |
| 4 | **Implement proper 3-month holdout split** | Diagnostic (edge/no-edge decision) | 1.5h | MEDIUM |
| 5 | **Lower threshold grid start** to 0.40-0.45 to capture more signals at better selectivity | Unknown | 0.5h | LOW |

---

## ACCP Report

See `reports/accp/operation_scalp_005.yaml` — **NOT YET CREATED.** Will generate on next iteration when meaningful positive results exist.

---

## Infrastructure Notes

### GPU Usage
- **Tesla T4**, 15,360 MiB total: max 477 MiB used (~3%)
- XGBoost WFV uses CUDA (77s for 56 symbols, ~16s for 12 symbols)
- **Simulation backtest is CPU-bound** — 75,996 signals × ~33ms per signal ≈ 42 min
- The 12-symbol backtest (4,726 signals) completes in ~4.5 min → practical ceiling
- **Recommendation:** Consider parallel per-symbol backtesting or vectorized simulation for scale

### Symbol Count Resolution
- Bootstrap (12): top-12 liquid symbols with derivatives — fast, representative
- Full (56): all listed perps — backtest is 60x slower (76K vs 4.7K signals)
- All runs use 12 bootstrap symbols; the 56-symbol run was killed for timeout

### Threshold Resolution
- Standardized to 0.50 throughout (matches pipeline CONFIDENCE_THRESHOLD)
- All ledger entries now log the actual threshold used

---

*Report generated at 2026-07-07T22:45:00Z.*
*Campaign status: Phases A ✓ B ✓ C ✗ D ✗ E ✓ F ✗ G △ H ✓*
*Worktree: main branch, no worktree sync needed (single agent).*
