# BB Position v2 Clean Revalidation

**Generated:** 2026-07-08T08:05:00+00:00
**Source:** `alphaforge/src/alphaforge/features/pipeline.py` (lines 857-882),
         `alphaforge/docs/discovered_alphas/SCALP_bb_position_mean_reversion_v1.json`,
         `alphaforge_report/alpha_ledger.json`,
         `reports/bb_position_audit.json`

---

## Critical Finding: Pipeline Already Fixed

The contamination claim against BB Position v1 was:
> `_rolling_mean` used `np.convolve(mode='same')` leaking future data

However, the current `_rolling_mean` function (in `alphaforge/src/alphaforge/features/pipeline.py`,
line 857) uses:

```python
kernel = np.ones(window, dtype=np.float64) / window
result = np.convolve(arr, kernel, mode='full')[:n]
result[:window - 1] = np.nan
```

This is **causal** — `result[t]` uses `arr[t-window+1 .. t]` only, which is correct.
The `mode='full'[:n]` pattern is equivalent to a trailing window. The function was
**already fixed** (from `mode='same'` to `mode='full'[:n]`) at some point after
the contamination was detected.

**Therefore:** The v1 alpha was contaminated when run with the OLD `mode='same'` code,
but the pipeline has since been corrected. Re-running the same v1 configuration on
the current pipeline would produce clean, non-contaminated results. There is no
need for a separate "v2" — re-running v1 with the fixed pipeline is sufficient.

---

## Current Status Check

| Criterion | Status |
|-----------|--------|
| **v2 exists as code** | ❌ No — v2 is a ledger placeholder only |
| **v2 exists as artifact** | ❌ No — no JSON file, no CSV, no model |
| **v2 re-validation run** | ❌ Not run |
| **Pipeline is fixed** | ✅ Fixed (`mode='full'[:n]` is causal) |
| **v1 source data available** | ✅ Yes (Binance real, 4 symbols, 118K bars) |
| **Feature computation safe** | ✅ Causal verified via code inspection |
| **Future leakage** | ✅ None — close[t-window+1..t] only |
| **Central sim run exists** | ❌ No — v1 used XGBoost model, not central sim |
| **Raw R (v1 actual)** | +0.0043 (4,552 trades) — NOTE: may have been inflated by contamination |
| **Cost-adjusted R (v1)** | Not directly available (G3 reported PASS with 10bps cost) |
| **Trade count (v1)** | 4,552 |
| **Baseline BB comparison** | Not run for standalone BB strategy |
| **OOS status** | Walk-forward 6-fold PASS (G2), holdout NOT RUN |

---

## Impact of Contamination

The v1 alpha had `_rolling_mean` using `mode='same'`, which means for a window of 20:
- `result[t]` used `arr[t-9 .. t+10]` (centered window, asymmetric)
- This leaks up to 10 bars of future data into each feature value
- In a time-series trading model, this creates an **illegal edge** (the model "sees" future price movements through future bar data)

The margin of contamination depends on:
1. How many features use `_rolling_mean` with BBands computation
2. Whether the BBands are the primary signal
3. The size of the contamination window (10 bars = 10 hours of future leakage)

Since bb_position has 97.3% feature dominance, the contamination is severe — nearly
the entire alpha edge came from looking into the future.

**Raw R +0.0043 is likely INFLATED by contamination.** A clean re-run would likely
produce a lower (possibly negative) R.

---

## Expected Clean R

Based on the walk-forward and CI data in the v1 handoff:

| Metric | Contaminated (v1) | Expected Clean | Source |
|--------|------------------|----------------|--------|
| Raw R | +0.0043 | ~+0.000 to +0.002 | Model without future edge |
| Trade count | 4,552 | ~3,000-4,500 | Similar (model fires at same times) |
| Cost-adjusted R | "PASS" (unknown) | **Likely negative** | Edge drops below cost |
| Win rate | ~50% | ~48-50% | Near-random |

**The clean re-run is unlikely to produce a cost survivor.** The BB position strategy
is a mean-reversion strategy on Bollinger Bands — a well-known approach with near-zero
edge in crypto markets after costs.

---

## Decision

| Label | Decision |
|-------|----------|
| **CLEAN_RETEST_PASS** | ❌ Cannot confirm — re-run needed |
| **CLEAN_RETEST_WATCH** | ✅ **WATCH** — pipeline is fixed, re-run is feasible |
| **CLEAN_RETEST_FAIL** | ❌ Premature — cost impact not quantified |
| **BLOCKED_V2_MISSING** | ✅ v2 is a placeholder; v1 re-run with fixed pipeline = de facto v2 |

### Recommendation

1. **Delete the v2 placeholder** from ledger (it has no data)
2. **Re-run v1 with current (fixed) pipeline** — this is the de facto v2
3. **Expected outcome**: R drops from +0.0043 to ~0.000, cost-adjusted R negative
4. **Do not expect a cost survivor** from BB Position strategy
5. **Move to failure-driven discovery** if cost survivors are the goal

### Conditions to Upgrade to CLEAN_RETEST_PASS

| Condition | Needed | Status |
|-----------|--------|--------|
| Pipeline fixed | Verify `mode='full'[:n]` | ✅ DONE |
| Re-run model training | Training pipeline + data | ❌ Not done in this run |
| Compute central sim R | Central sim bridge | ❌ Not built |
| Raw R > 0 (clean) | Re-run | ❌ Not done |
| Cost-adjusted R > 0 | Re-run | ❌ Not done |
| OOS positive | Re-run | ❌ Not done |
