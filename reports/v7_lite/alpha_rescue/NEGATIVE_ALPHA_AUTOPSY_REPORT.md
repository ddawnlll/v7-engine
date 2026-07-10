# Negative Alpha Autopsy Report — V7-Lite / AlphaForge

**Generated:** 2026-07-08
**Source:** `reports/ALPHA_INVENTORY_FULL.csv`, `alphaforge_report/alpha_ledger.json`, `reports/alphaforge/factor_sprint/`
**Total entries analyzed:** 170
**Unique concepts:** ~25

---

## Executive Summary

Of 170 tested alpha entries (representing ~25 unique concepts), the vast majority are negative. This report classifies every entry into rescue/reject buckets and produces a concrete plan to move from 3 raw-positive candidates toward 10.

### Key Numbers

| Metric | Value |
|--------|-------|
| Total alpha entries | 170 |
| Positive raw R | 3 |
| Negative raw R | 110 |
| Unknown R (IC-only) | 57 |
| Cost-adjusted positive | 0 |
| Promotion-ready | 0 |
| Contaminated | 1 |

---

## Classification Breakdown

| Classification | Count | % of Total |
|----------------|-------|------------|
| RETEST_REQUIRED | 87 | 51.2% |
| INVERSION_CANDIDATE | 36 | 21.2% |
| FEATURE_ONLY | 18 | 10.6% |
| SEGMENT_RESCUE_CANDIDATE | 9 | 5.3% |
| BASELINE_DUPLICATE | 9 | 5.3% |
| REJECT_FOREVER | 5 | 2.9% |
| NOISE_NEAR_ZERO | 3 | 1.8% |
| PROMISING_RAW_POSITIVE | 2 | 1.2% |
| CONTAMINATED_REJECT | 1 | 0.6% |

### Key Finding

**51.2% are RETEST_REQUIRED** — these are factor sprint IC-only entries that were never simulated through the central simulation engine. They have IC evidence but no official R. Running them through the central simulation bridge (once built) is the single highest-impact action to increase the pipeline of evaluated alpha candidates.

---

## Cluster Analysis

| Cluster | Count | Best R | Worst R | Cost Survivors |
|---------|-------|--------|---------|----------------|
| momentum | 32 | +0.0076 | -0.8394 | 0 |
| mean_reversion | 24 | +0.0043 | -0.7290 | 0 |
| volatility | 20 | -0.1293 | -1.3535 | 0 |
| BTC_dependency | 12 | -0.3611 | -1.4790 | 0 |
| breakout | 16 | -0.1221 | -1.0195 | 0 |
| volume | 14 | -0.1449 | -1.2782 | 0 |
| trend | 8 | -0.1033 | -0.1509 | 0 |
| spread_microstructure | 8 | -0.1101 | -0.1549 | 0 |
| regime | 6 | -0.2439 | -0.7489 | 0 |
| discovery_pipeline | 5 | +0.0515 | -0.1138 | 0 |
| XGBoost | 2 | +0.0043 | +0.0076 | 0 |

**No cluster has a cost survivor.** Every concept family is net negative after costs.

---

## Primary Loss Buckets

Based on the data:

1. **Cost dominance** (all entries with trade_count > 1000): Costs at ~0.062R/trade exceed the gross edge in every case. Even the best raw alpha (+0.0515R) fails cost-adjusted.
2. **Direction misalignment** (36 of 48 IC factor/horizon pairs): 6 of 12 factors in the FACTOR_REGISTRY have wrong declared direction. The `ret_*_rank` factors are actually reversal signals, not momentum.
3. **Selection bias** (170-way multiple testing): The best raw alpha (+0.0515R) is consistent with the expected maximum from 170 random trials.
4. **Proxy-only simulation** (33 proxy R entries): These used a standalone simulator, not the central engine. Their R values are labeled PROXY and should not be treated as official.

---

## Truth V6 Status

Discovery Pipeline V6 (+0.0515R, 870 trades) is the best honest alpha. It fails cost-adjusted survival. Per the TRUTH_V6_DISSECTION_REPORT from this repo, the edge is:
- **Carried by a small subset** (BTCUSDT carries 457% of profit)
- **Cost-negative** at base taker model (-0.01R adjusted)
- **Deflated Sharpe failure** (obs 0.79, expected max from 170 trials ≈ 3.17)
- **Verdict: WATCH** — not rejectable but not promotable

---

## Files

| File | Description |
|------|-------------|
| `ALPHA_RESCUE_MATRIX.csv` | Full 170-row classification matrix |
| `ALPHA_RESCUE_MATRIX.json` | JSON version of same |
| `INVERSION_CANDIDATES.md` | 36 inversion candidates analyzed |
| `SEGMENT_RESCUE_CANDIDATES.md` | 9 segment rescue candidates |
| `COST_RESCUE_CANDIDATES.md` | Cost rescue analysis |
| `REJECT_FOREVER_LIST.md` | Permanently rejected alphas |
| `ALPHA_CLUSTER_MAP.md` | Cluster grouping |
| `NEXT_10_ALPHA_DISCOVERY_PLAN.md` | Plan for 10 new positive candidates |
