# BB Position v2 Revalidation Report — Issue #312

**Generated:** 2026-07-13T09:47:02Z
**Author:** Hermes Agent (autonomous execution)

---

## VERDICT: KIRMIZI (REJECT)

**The BB position mean-reversion mechanism hypothesis is NOT supported by the evidence.**

The edge is too weak (+0.0121R per active trade), rapidly destroyed by even normal costs (break-even multiplier: 1.23x), and concentrated in < 2% exposure with 97% low-confidence rate. Models 5-6 are degenerate (< 10 trades). Per MECHANISM_HYPOTHESES.md, this means **the entire alpha pipeline needs fundamental redesign** — no current alpha candidates survive mechanism testing.

---

## 1. Protocol Summary

| Field | Value |
|-------|-------|
| **Issue** | #312 — BB Position v2 Revalidation |
| **Mechanism** | Price mean-reverts near Bollinger Band extremes in ranging/low-volatility regimes |
| **Feature** | `bb_position` (normalized distance from SMA within bands) + `bb_width`, `range_breakout_N` |
| **Pipeline Version** | 0.3.1 (corrected trailing-window features — confirmed) |
| **Mode** | SCALP (primary business/research priority) |
| **Symbols** | BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT (pre-registered, fixed) |
| **Validation** | 6-fold anchored expanding walk-forward |
| **Data** | Real 1h OHLCV (2023-09-01 to 2026-05-31), cached factor_sprint panel |
| **Cost Model** | Fee-only (8 bps round trip) — funding_cost_r = 0.0 per audit |

---

## 2. Audit Notes (Pre-execution)

### 2.1 PIPELINE_VERSION
**Confirmed:** 0.3.1 at `alphaforge/src/alphaforge/features/pipeline.py:118`. The corrected trailing-window bb_position features are active. No override found in the execution path.

### 2.2 Data Lake Status
**No 56-symbol data lake available on the remote host (vast.ai: 1.208.108.242:33346).** The `data/raw/` directory contains only `.gitkeep`. Execution used the cached factor_sprint panel (`cache/factor_sprint/`) which has 20 symbols, 1h data, 2023-01-01 to 2026-05-31. Only the 4 pre-registered symbols were selected. This is a limitation — results may differ on a larger, more diverse symbol set.

### 2.3 Funding Cost Status
**Funding cost is NOT active in the WFV execution path (train.py walk_forward_validate).**
- Issues #304/#315 are marked CLOSED on GitHub but the funding_rate wiring in the actual WFV label generation path is still zero.
- Label generation (`_generate_simple_labels_numba` in train.py:444) uses only a flat round-trip cost (8 bps taker fee) — no funding cost.
- `compute_oos_metrics()` in the WFV path is called with `fee_pct=0.0` and default `funding_pct=0.0`.
- `_map_config_to_profile()` in `simulation_adapter.py:99` has a comment: `funding_rate: SimulationProfile defaults to 0.0; override via config when available` — but no override is visible in the WFV code path.

**Implication:** Results shown below are fee-only. Real trading costs (slippage + funding) would reduce the already-small edge further. The KIRMIZI verdict would not change with active funding costs — the edge is already destroyed at 1.5x baseline cost.

---

## 3. Per-Fold Walk-Forward Results

| Fold | Train | Val | Active Trades | Long | Short | Net R/trade | Val Acc | Low Conf% |
|------|-------|-----|--------------|------|-------|-------------|---------|-----------|
| 1    | 10,401 | 5,201 | 153 | 100 | 53 | +0.017607 | 0.2442 | 97.0% |
| 2    | 24,269 | 5,201 | 247 | 111 | 136 | +0.010900 | 0.1509 | 94.0% |
| 3    | 38,137 | 5,201 | 71 | 43 | 28 | +0.007874 | 0.1388 | 96.9% |
| 4    | 52,005 | 5,201 | 39 | 34 | 5 | +0.003687 | 0.1769 | 98.5% |
| 5    | 65,873 | 5,201 | 3 | 3 | 0 | +0.020224 | 0.1769 | 98.5% |
| 6    | 79,741 | 5,201 | 8 | 3 | 5 | +0.022130 | 0.1156 | 99.1% |
| **All** | — | — | **521** | **294** | **227** | **+0.012144** | **0.1672** | **97.4%** |

### Key Observations

1. **Accuracy is near-random for 3-class task**: 16.7% vs 33.3% baseline (random guess). The model is overwhelmingly predicting NO_TRADE.

2. **Extreme NO_TRADE bias**: 97.4% of validation samples are flagged as low-confidence and forced to NO_TRADE. The model only trades 1.7% of the time.

3. **Exposure collapse in later folds**: Folds 5-6 are degenerate — 3 and 8 trades respectively out of 5,201 validation samples. The model found essentially no signal in recent data.

4. **Fold 4-6 signal shift**: After fold 2, the model shifts from relatively balanced long/short (111/136) to heavily long-biased fold 4 (34/5). This non-stationarity is a pattern-break signal.

5. **Overfit gap is severe**: Train accuracy (46.1%) vs validation accuracy (16.7%) = 29.4% gap. PBO risk rated **HIGH**.

---

## 4. Aggregate Metrics

| Metric | Value | Threshold | Verdict |
|--------|-------|-----------|---------|
| Net Expectancy R / trade | +0.012144 | ≥0.05 (CONTINUE_RESEARCH) | FAIL |
| Gross Expectancy R / trade | +0.012144 | — | — |
| Total Gross R (all folds) | +6.33 | — | — |
| Total Net R | +6.33 | — | — |
| Active Trades | 521 | ≥100 | PASS |
| Folds completed | 6 | ≥6 | PASS |
| Accuracy | 16.72% | — | — |
| Overfit Gap | 0.2936 | <0.10 (LOW RISK) | HIGH PBO |
| Exposure | 1.67% | — | — |
| Inter-fold Consistency | 4.57 | — | — |

---

## 5. Cost Stress Results

| Multiplier | Stressed Net R/trade | Edge Survives? |
|------------|---------------------|----------------|
| 1.0x (baseline) | +0.012144 | No (too weak) |
| 1.5x | -0.014523 | No |
| 2.0x | -0.041189 | No |
| 3.0x | -0.094523 | No |
| **Combined survive** | — | **NO** |
| Break-even multiplier | 1.23x | — |

**Cost stress verdict: FAIL_EDGE_DESTROYED_BY_COSTS**

The edge is destroyed at 1.5x baseline costs — barely above normal operating costs. Baseline cost in R is 0.0533/trade (from SCALP mode stop_mult=1.5, 4bps taker fee). The net edge of 0.0121 is 23% of baseline cost. A 23% increase in costs eliminates all edge.

---

## 6. Null Test Comparison

| Metric | Null Test | This Result |
|--------|-----------|-------------|
| Baseline | -0.1675 (TEMIZ, cost_adj_R) | +0.012144 |
| Z-score vs null | — | **10.57** |
| >3-sigma | No (null) | **Yes** |
| >2-sigma | No (null) | **Yes** |

The net expectancy R (+0.012) is statistically distinguishable from the null distribution (TEMIZ z=10.57), but the magnitude is economically irrelevant. The edge exists as a statistical artifact but is too small to be actionable after costs.

---

## 7. Verdict Computation

Using evidence-gated thresholds from `empirical.py` (LOCKED_INITIAL_BASELINE):

| Criterion | Required | Actual | Result |
|-----------|----------|--------|--------|
| Active trades ≥ 100 | 100 | 521 | ✅ PASS |
| Folds ≥ 6 | 6 | 6 | ✅ PASS |
| Net expectancy R > 0 | >0 | +0.012 | ✅ PASS (barely) |
| Net expectancy R ≥ 0.05 (CONTINUE_RESEARCH) | 0.05 | 0.012 | ❌ FAIL |
| Net expectancy R ≥ 0.10 (BASELINE_VALID) | 0.10 | 0.012 | ❌ FAIL |
| Cost stress survives | Yes | No | ❌ FAIL |
| Z-score vs null > 2σ | >2σ | 10.57σ | ✅ PASS |

**Final Verdict: KIRMIZI (REJECT)**

Rationale: Edge destroyed by cost stress. The positive net R of +0.012 exists but is economically insignificant — consumed by the smallest cost increase. The model's 97% low-confidence rate and 1.7% exposure make it practically unusable. Per MECHANISM_HYPOTHESES.md section "If BB v2 fails": **"entire alpha pipeline needs fundamental redesign."**

---

## 8. Comparison with BB Position v1 (Contaminated)

| Metric | BB v1 (leaked) | BB v2 (corrected) | Delta |
|--------|----------------|-------------------|-------|
| Pipeline version | Pre-0.3.0 | 0.3.1 | Fixed |
| Net R/trade | +0.0043 | +0.0121 | +181% (!) |
| Active Trades | 4552 | 521 | -89% |
| Low-conf rate | N/A | 97.4% | — |

**Note:** The v1 result of +0.0043R over 4552 trades was contaminated by lookahead. The v2 result shows a paradoxically **higher** per-trade net R (0.012 vs 0.004) but with 89% fewer trades. The corrected features produce a higher-quality but much rarer signal — which is actually worse for a mean-reversion strategy that needs frequent entries.

The v1 "edge" was partly a volume illusion (more trades × tiny edge = more total R). The v2 corrected pipeline shows the real bb_position signal is too sparse to be useful.

---

## 9. Implications for V7 Roadmap

Per MECHANISM_HYPOTHESES.md's explicit conclusion:

> "If BB v2 fails: entire alpha pipeline needs fundamental redesign"

**What this means concretely:**

1. **No surviving alpha candidates.** After the mining-vs-mechanism purge, BB Position was the sole survivor. Its rejection means there are zero mechanism-validated alpha signals in the pipeline.

2. **bb_position alone is insufficient.** Even with corrected features, the mean-reversion signal from a single technical indicator does not produce actionable edge. The mechanism hypothesis is not supported.

3. **Funding cost gap must be addressed.** The fact that funding cost wiring is still inactive (despite #304/#315 being CLOSED) means all current training results are on a partial cost model. A KIRMIZI verdict on fee-only costs would only get worse with funding active.

4. **Recommendation per MECHANISM_HYPOTHESES.md:** Do NOT open new mining/discovery work here. This is a repo-owner decision whether to redesign the alpha pipeline, change the data source, or adopt a fundamentally different approach (e.g., regime-aware combined-signal instead of single-feature mechanism testing).

---

## 10. Files Changed

| File | Action |
|------|--------|
| `scripts/revalidate_bb_position_v2.py` | NEW — glue script for this revalidation |
| `reports/v7_lite/mechanism/bb_position_v2_result.json` | NEW — raw result data |
| `reports/v7_lite/mechanism/BB_POSITION_V2_REVALIDATION.md` | NEW — this report |
| `reports/accp/issue-312.yaml` | NEW — ACCP completion report |
| `v7/docs/roadmap.md` | PATCHED — updated lock status |
