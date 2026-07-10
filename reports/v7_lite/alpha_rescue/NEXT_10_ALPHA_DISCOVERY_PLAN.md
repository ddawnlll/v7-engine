# Next 10 Alpha Discovery Plan

**Generated:** 2026-07-08
**Current state:** 3 raw-positive, 0 cost-survivors, 0 promoted
**Target:** 10 raw-positive, 3 cost-survivors, 1 promotion candidate

---

## Strategy

Not "invent 10 new alphas." The plan is failure-driven:

1. **Invert 6 misdeclared factors** (immediate, high-probability gains)
2. **Re-simulate 33 proxy-only entries** on central engine
3. **Regime/symbol filter 8 segment rescue candidates**
4. **Cost-optimize via confidence percentile + maker execution**
5. **Combine top 3 approaches into 1 champion candidate**

---

## Proposed Experiments

### Experiment 1: ret_1h_rank — Inverted Direction
```
experiment_id: EXP-RET-1H-INVERT
derived_from_failed_alpha: ret_1h_rank (all horizons)
hypothesis: Factor is actually a REVERSAL signal, not momentum.
  Declared direction was wrong. Inverted direction will produce positive R.
cluster: momentum
mutation_type: invert_signal
expected edge source: Mean reversion at 1h horizon
required data: Existing factor sprint data + central simulation
test mode: SCALP 1h
expected trade count: ~80K
cost-risk: Low (already tested, just flipping sign)
baseline to beat: Original ret_1h_rank R (-0.15 to -0.84R) → should be positive
promotion condition: cost-adjusted R > 0.10R with > 1,000 trades
reject condition: cost-adjusted R < 0 after inversion
```

### Experiment 2: ret_4h_rank — Inverted Direction
```
experiment_id: EXP-RET-4H-INVERT
derived_from_failed_alpha: ret_4h_rank
hypothesis: Same reversal effect at 4h horizon
mutation_type: invert_signal
expected trade count: ~80K
promotion condition: cost-adjusted R > 0.08R
reject condition: R < 0
```

### Experiment 3: ret_12h_rank — Inverted Direction
```
experiment_id: EXP-RET-12H-INVERT
mutation_type: invert_signal
promotion condition: cost-adjusted R > 0.06R
```

### Experiment 4: volume_zscore — Inverted Direction
```
experiment_id: EXP-VOL-ZSCORE-INVERT
derived_from_failed_alpha: volume_zscore
hypothesis: High volume predicts LOW future returns (contrarian), not HIGH
cluster: volume
mutation_type: invert_signal
expected trade count: ~30K
promotion condition: cost-adjusted R > 0.08R
reject condition: R < 0
```

### Experiment 5: trend_pullback_ema — Inverted Direction
```
experiment_id: EXP-TREND-PB-INVERT
derived_from_failed_alpha: trend_pullback_ema
hypothesis: EMA pullback LONG is wrong direction. SHORT after EMA pullback works.
cluster: trend
mutation_type: invert_signal
expected trade count: ~40K
promotion condition: cost-adjusted R > 0.06R
```

### Experiment 6: Truth V6 — BTCUSDT × SHORT × Maker
```
experiment_id: EXP-TRUTH-V6-BTC-SHORT-COST
derived_from_failed_alpha: Discovery Pipeline V6
hypothesis: Truth V6 edge is concentrated in BTCUSDT SHORT trades.
  Maker execution + BTCUSDT-only + SHORT-only will achieve cost survival.
cluster: discovery_pipeline
mutation_type: symbol_whitelist + direction_filter + maker_execution
expected trade count: ~200-400 (after filters)
promotion condition: cost-adjusted R > 0.10R with > 200 trades
reject condition: cost-adjusted R < 0 or < 200 trades
```

### Experiment 7: Truth V6 — Confidence Percentile Filter
```
experiment_id: EXP-TRUTH-V6-CONFIDENCE-TOP25
derived_from_failed_alpha: Discovery Pipeline V6
hypothesis: Top quartile by model confidence has R > 0.10R after costs
mutation_type: confidence_threshold
expected trade count: ~200 (top 25% of 870)
promotion condition: cost-adjusted R > 0.10R
```

### Experiment 8: BB Position v2 — Corrected Features
```
experiment_id: EXP-BB-POS-V2-CORRECTED
derived_from_failed_alpha: BB Position Mean-Reversion v1 (CONTAMINATED)
hypothesis: After fixing the convolve bug, the corrected v2 will preserve
  the mean-reversion edge (though likely weaker).
cluster: mean_reversion
mutation_type: retest (corrected pipeline)
expected trade count: ~3,000-5,000
promotion condition: cost-adjusted R > 0.05R
reject condition: R < 0
```

### Experiment 9: Operation SCALP 0.05 — Regime-Gated
```
experiment_id: EXP-SCALP-005-REGIME-GATED
derived_from_failed_alpha: SCALP Baseline (Operation 0.05, taker)
hypothesis: Adding a regime gate (no LONG in uptrend, no SHORT in downtrend)
  improves the baseline by filtering counter-trend entries.
mutation_type: regime_gate
expected trade count: ~3,000
promotion condition: cost-adjusted R > 0.05R
reject condition: R < 0 or trade count < 500
```

### Experiment 10: Factor Sprint Proxy — Central Simulation Re-run
```
experiment_id: EXP-FACTOR-SPRINT-CENTRAL-SIM
derived_from_failed_alpha: All 33 proxy R entries
hypothesis: Proxy simulation was inaccurate. Central simulation bridge will
  produce different (potentially better) R for these entries.
mutation_type: retest (central sim bridge)
expected trade count: Varies by factor
promotion condition: At least 1 entry with cost-adjusted R > 0.05R
reject condition: All 33 entries remain negative after central sim
```

---

## Expected Outcomes

| Experiment | Success Probability | Expected R | Confidence |
|------------|-------------------|------------|------------|
| 1. ret_1h inverted | 50% | +0.02 to +0.06R | MEDIUM |
| 2. ret_4h inverted | 45% | +0.01 to +0.05R | MEDIUM |
| 3. ret_12h inverted | 40% | +0.01 to +0.04R | MEDIUM |
| 4. volume_zscore inverted | 40% | +0.01 to +0.03R | LOW |
| 5. trend_pullback inverted | 35% | +0.005 to +0.03R | LOW |
| 6. Truth V6 BTC SHORT cost | 30% | +0.05 to +0.12R | MEDIUM |
| 7. Truth V6 conf filter | 25% | +0.05 to +0.15R | LOW |
| 8. BB Position v2 | 30% | +0.003 to +0.02R | LOW |
| 9. Op Scalp regime-gated | 20% | 0.00 to +0.03R | LOW |
| 10. Central sim re-run | 30% | at least 1 positive | LOW |

### Projected Results

| Target | Current | After 10 experiments | Confidence |
|--------|---------|---------------------|------------|
| Raw-positive candidates | 3 | **5-8** | MEDIUM |
| Cost-surviving candidates | 0 | **1-2** | LOW |
| Promotion candidates | 0 | **0-1** | LOW |
| Usable features/filters | 0 | **3-5** | HIGH |

**Likely reachable:** 5-8 raw-positive, 1 cost-survivor, 0 promotion candidates.
**Unlikely without new discovery:** 3 cost-survivors, 1 promotion candidate.
