# BB Position v2 Reality Check

**Generated:** 2026-07-08T08:44:00+00:00

---

## Investigation Results

### v1 Source

| Field | Value |
|-------|-------|
| **Alpha ID** | `scalp_bb_position_mean_reversion_v1` |
| **Source file** | `alphaforge/docs/discovered_alphas/SCALP_bb_position_mean_reversion_v1.json` |
| **Run ID** | `run-scalp-bb-v1-20260705` |
| **Ledger entry** | `alphaforge_report/alpha_ledger.json` (entry 0) |

### v1 Contamination Reason

The ledger states:
> CONTAMINATED: `_rolling_mean` used `np.convolve(mode='same')` leaking future data

**Current code audit:** The current `_rolling_mean` function in
`alphaforge/src/alphaforge/features/pipeline.py` (line 857) uses:
```python
kernel = np.ones(window, dtype=np.float64) / window
result = np.convolve(arr, kernel, mode='full')[:n]
result[:window - 1] = np.nan
```

This is **causal** — `result[t]` uses `arr[t-window+1 .. t]` only. The pipeline was
**already fixed** (from `mode='same'` to `mode='full'[:n]`) at some point after the
contamination was detected.

### v2 Status

| Check | Result |
|-------|--------|
| **v2 exists in ledger?** | ✅ Placeholder entry at `alphaforge_report/alpha_ledger.json` index 1 |
| **v2 has artifacts?** | ❌ No JSON, no CSV, no model file |
| **v2 has run data?** | ❌ `net_R_per_trade: null`, `trade_count: null` |
| **v2 source code?** | ❌ Only the v1 JSON exists |
| **v2 pipeline fix present?** | ✅ The pipeline was fixed (mode='full'[:n]) — applies to v1 re-run |

**v2 is a PHANTOM placeholder.** It was added to the ledger as an intent to re-run,
but the re-run was never executed.

### What "v2" Actually Means

"v2 (corrected)" means: re-run the v1 configuration on the now-fixed pipeline.
There is no separate code, model, or artifact for v2. The ledger entry is a bookmark
for work that hasn't been done.

### Required Re-run Command

```bash
PYTHONPATH=alphaforge/src:v7/src:.

python -m alphaforge.discover \
    --mode SCALP \
    --panel-cache cache/factor_sprint \
    --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT \
    --confidence-threshold 0.55 \
    --folds 6 \
    --output reports/discovery/bb_position_v2_replay.json
```

Since the v1 alpha was from the XGBoost pipeline (not a factor sprint), the discovery
pipeline re-run would produce a new model trained on fixed features. Expected outcome:

| Metric | v1 (contaminated) | v2 (expected clean) |
|--------|-------------------|---------------------|
| Raw R | +0.0043 | ~0.000 to +0.002 |
| Cost-adjusted R | Unknown (G3 pass claimed) | ~-0.060R (negative) |
| Trade count | 4,552 | ~3,000-5,000 |

**Expected clean R is near zero or negative.** The original edge was 97.3% dependent on
bb_position, and the contamination (future leakage through mode='same') would have
inflated the apparent edge significantly.

### Verdict

| Label | Decision |
|-------|----------|
| V2_EXISTS_READY_FOR_RETEST | ❌ v2 is a phantom placeholder |
| V2_EXISTS_BUT_NOT_SIMULATED | ❌ Same — no code/artifact exists |
| **V2_MISSING_PHANTOM** | ✅ **v2 is a phantom — only a ledger intent** |
| V2_BLOCKED_SOURCE_MISSING | ❌ Source pipeline exists and works (verified via synthetic test) |

### Recommendation

1. **Delete the v2 ledger placeholder** — it has no data and misrepresents the state
2. **Re-run v1 on fixed pipeline** to get actual clean metrics
3. **Expected clean R ~0.000** — BB position alone cannot survive costs in crypto
4. **Accept the result** even if it shows the alpha was entirely contamination-driven

### Cleanup Actions

| Action | Command/Detail |
|--------|---------------|
| Remove v2 ledger entry | Edit `alphaforge_report/alpha_ledger.json`, remove entry with alpha_id `scalp_bb_position_mean_reversion_v2` |
| Remove v2 from inventory | The ALPHA_INVENTORY_FULL.csv was auto-generated from the ledger; re-generate after cleanup |
| Note on v1 | Keep v1 as CONTAMINATED with evidence of the lookup bug |
