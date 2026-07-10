# Truth V6 Confidence Percentile Rescue

**Generated:** 2026-07-08T08:06:00+00:00
**Status:** BLOCKED_SCORE_MISSING

---

## Issue

Truth V6 actual trade-level data is **NOT persisted**. The discovery pipeline
(`run-alpha-truth-v6-20260707`) was run without per-trade logging, so no
`profit_score`, `confidence`, or per-trade metadata is available.

The dissection report used a proxy dataset (10K factor sprint candidate outcomes),
which has distribution metrics but:
1. The proxy dataset has mean R = +0.000851 (60x worse than actual Truth V6 +0.0515R)
2. Percentile splits from proxy data cannot be extrapolated to actual Truth V6
3. No confidence/profit_score field exists in the ledger

## What's Needed

| Requirement | Status |
|-------------|--------|
| Per-trade R values | ❌ Not persisted |
| Per-trade confidence/profit_score | ❌ Never computed |
| Per-trade cost model input | ❌ Not available |
| Re-run discovery pipeline with logging | Needed |
| Re-run with central simulation | Central sim bridge not built |

## Proxy-Only Distribution (for reference only)

From the proxy dataset (10K trades, mean R = +0.000851):

| Percentile | R Value |
|------------|---------|
| p10 | -0.6422 |
| p25 | -0.3351 |
| p50 | -0.0069 |
| p75 | +0.3362 |
| p90 | +0.6549 |
| p99 | +1.1788 |

These values are NOT representative of actual Truth V6 and cannot be used for
cost-survival analysis.

## Verdict

**BLOCKED_SCORE_MISSING** — Actual Truth V6 trade data not persisted.
Required field: per-trade `net_R` and `profit_score` from re-run with logging.
