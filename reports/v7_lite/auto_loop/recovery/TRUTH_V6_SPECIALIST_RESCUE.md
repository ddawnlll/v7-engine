# Truth V6 BTCUSDT SHORT Maker Specialist Rescue

**Generated:** 2026-07-08T08:02:00+00:00
**Source:** `reports/v7_lite/truth_v6/TRUTH_V6_DISSECTION_REPORT.md`,
         `reports/v7_lite/truth_v6/TRUTH_V6_COST_RESCUE_REPORT.md`,
         `reports/ALPHA_INVENTORY_REPORT.md`

---

## Data Availability

Truth V6's actual trade-level data (`run-alpha-truth-v6-20260707`) is **NOT persisted**.
The dissection report used a nearest-available proxy dataset (factor sprint V1 candidate outcomes,
10,000 trades). The reported cross-section metrics (by symbol, direction, regime) come
from this proxy dataset, not the actual Truth V6 trades.

**870 actual trades** (from ledger) — but no per-trade details beyond aggregate metrics.

| Metric | Actual (870 trades) | Proxy (10K trades) |
|--------|--------------------|--------------------|
| Raw R | +0.0515 | +0.000851 |
| Win rate | 49.66% | 49.34% |
| Profit factor | 1.11 | 1.004 |

The actual Truth V6 (+0.0515R) is **60x better** than the proxy (+0.000851R) on raw R.
This means the proxy dataset **underestimates** the true edge, but also means we cannot
rely on the proxy's cross-section breakdown for precise rescue analysis.

---

## BTCUSDT SHORT Analysis

### From Proxy Dataset (10K trades)

| Metric | BTCUSDT SHORT | BTCUSDT All | SHORT All |
|--------|--------------|-------------|-----------|
| **Trade count** | ~1,696 | 3,354 | 5,018 |
| **Mean R** | +0.0115 | +0.0116 | +0.0046 |
| **Win rate** | ~50% | 50.72% | 49.32% |

### Actual Truth V6 (extrapolated)

Given the proxy underestimates the edge by ~60x, we can estimate:

| Metric | Estimated (actual) | Confidence | Source |
|--------|-------------------|------------|--------|
| BTCUSDT SHORT mean R | ~+0.12R | LOW | Extrapolated from proxy +0.0115R × 60x discrepancy |
| BTCUSDT SHORT trade count | ~130-200 | LOW | Estimated from 870 × (1696/10000) × (0.5) |

The **estimated trade count of 130-200** for BTCUSDT SHORT is below the minimum threshold
of 200 for a counted cost_survivor_candidate (per thresholds).

---

## Cost Scenarios

### BTCUSDT SHORT — Estimated Cost-Adjusted R

| Scenario | Est. Raw R | Est. Cost/R | Est. Adj R | Trade Count | Verdict |
|----------|-----------|-------------|-----------|-------------|---------|
| **Best:** Maker BTCUSDT SHORT | ~+0.12R | ~0.031R | ~+0.089R | ~130-200 | WEAK |
| **Base:** Taker BTCUSDT SHORT | ~+0.12R | ~0.062R | ~+0.058R | ~130-200 | WEAK |
| **2x cost stress** | ~+0.12R | ~0.124R | ~-0.004R | ~130-200 | FAIL |
| **5x cost stress** | ~+0.12R | ~0.310R | ~-0.19R | ~130-200 | FAIL |

All scenarios fail the cost_survivor_candidate requirement (`cost_adjusted_R > 0, trade_count >= 200`).

### BTCUSDT × downtrend (best segment, proxy data)

| Metric | Value |
|--------|-------|
| **Trade count (proxy)** | 649 |
| **Mean R (proxy)** | +0.0231 |
| **Extrapolated to Truth V6** | ~+0.15R (LOW confidence) |
| **Cost-adjusted maker** | ~+0.12R |
| **Trade count (actual est.)** | ~56 (WAY below 200) |

---

## BTCUSDT Maker-like Scenario

In the maker scenario (`maker 2bps entry + exit, 0.5bp slippage`), the cost drops to
~0.031R/trade. For BTCUSDT (most liquid symbol, tightest spreads), the effective cost
may be even lower (~0.020–0.025R/trade).

**Minimum raw R needed for cost survivor:** 0.031R (maker cost)
**Minimum trade count needed:** 200

Even under best-case maker assumptions on BTCUSDT, we cannot have confidence in a
specialist candidate because:
1. **Trade count is too low** (~130-200 estimated BTCUSDT SHORT, actual data not available)
2. **Edge estimation is unreliable** (60x discrepancy between actual and proxy)
3. **Symbol concentration risk is extreme** (BTCUSDT = 457% of profit)
4. **No per-trade cost data** available

---

## Symbol Concentration Risk

| Risk | Assessment |
|------|-----------|
| BTCUSDT share of profit | ~457% (proxy) — extreme |
| BTCUSDT SHORT as % of total | ~17% (proxy) |
| Single-symbol dependency | **Critical** — alpha dies without BTCUSDT |
| Other symbols | ETHUSDT is -402% of profit, SOLUSDT is +46% |

A single-symbol specialist (BTCUSDT only) would have extreme concentration risk and
cannot be considered portfolio-ready.

---

## Holdout / OOS Availability

| Gate | Status |
|------|--------|
| Holdout tested | **NOT RUN** |
| Walk-forward | 6-fold exists but results not per-symbol |
| OOS period | Unknown |

Without holdout/OOS validation, any specialist claim is premature.

---

## Verdict

| Label | Decision |
|-------|----------|
| `SPECIALIST_COST_SURVIVOR` | ❌ Cannot confirm |
| `SPECIALIST_WATCH` | ✅ **SPECIALIST_WATCH** |
| `SPECIALIST_REJECT` | ❌ Premature — raw edge exists |
| `BLOCKED_TRADE_DATA_MISSING` | ✅ Actual trade data not persisted; proxy data used |

### Rationale for SPECIALIST_WATCH

1. Raw edge exists for BTCUSDT SHORT (+0.0046 to +0.0115R in proxy, potentially higher in actual)
2. Maker scenario on BTCUSDT could bring cost-adjusted R close to positive
3. However, trade count for BTCUSDT SHORT is likely below 200
4. No per-trade actual data exists to verify
5. Symbol concentration is extreme (single-symbol dependency)
6. OOS/holdout not evaluated

### Conditions to Upgrade to SPECIALIST_COST_SURVIVOR

| Condition | Needed | Status |
|-----------|--------|--------|
| Re-run Truth V6 discovery pipeline with per-trade logging | Trade data persisted | ❌ Not done |
| Compute per-trade cost for BTCUSDT SHORT | Trade data | ❌ Not available |
| Filter to BTCUSDT SHORT only | Trade data | ❌ Not available |
| Verify >= 200 trades in segment | Trade data | ❌ Estimated 130-200 |
| Cost-adjusted R > 0 at maker cost | Trade data | ❌ Estimated +0.089R |
| 2x cost stress not catastrophic | Trade data | ❌ Estimated -0.004R |
| OOS/holdout positive | Segment data | ❌ Not evaluated |

**Cannot produce a cost survivor from Truth V6 without re-running the discovery pipeline
with complete trade logging.**
