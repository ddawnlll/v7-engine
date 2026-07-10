# Cost Rescue Candidates

**Generated:** 2026-07-08

---

## Overview

No alpha in the inventory survives the base taker cost model (0.062R/trade).
This report evaluates whether any alpha can be cost-rescued through execution
optimization, not cost model mutation.

**Hard rule:** The cost model is not mutated. We evaluate whether EXISTING alphas
can be executed cheaper.

---

## Cost Structure (from simulation/docs/cost_model.md)

| Component | Value |
|-----------|-------|
| taker_fee_bps | 4.0 (0.04%) |
| maker_fee_bps | 2.0 (0.02%) |
| slippage_bps | 1.0 (0.01%) |
| Round trip (taker) | 10 bps ≈ 0.062R/trade |
| Round trip (maker) | 5 bps ≈ 0.031R/trade |
| Maker savings | +0.0124-0.0210R/trade (measured) |

---

## Candidate 1: Discovery Pipeline V6

| Metric | Raw | Taker Cost | Maker Cost |
|--------|-----|------------|------------|
| R/trade | +0.0515 | -0.0105 | +0.0205 |
| Trades | 870 | 870 | 870 |

**Rescue levers:**
- ✅ Maker execution: +0.0205R (still below 0.10R threshold)
- ✅ High-confidence subset: if top-quartile has +0.6466R (from 12K proxy data),
     selecting top 25% confidence would drastically improve cost-adjusted R
- ✅ Symbol whitelist: BTCUSDT only. If BTCUSDT carries all profit,
     cost savings per trade on a liquid symbol are higher
- ❌ Wider targets: would reduce trade frequency, increase hold time,
     may improve R/trade but at the cost of fewer trades

**Decision:** COST_RESCUE_MEDIUM — achievable with maker + confidence filter
but unlikely to reach +0.10R without additional edge improvement.

---

## Candidate 2: SCALP 1h Direction v01

| Metric | Raw | Taker Cost | Maker Cost |
|--------|-----|------------|------------|
| R/trade | +0.0076 | -0.0544 | -0.0234 |
| Trades | 31,752 | 31,752 | 31,752 |

**Rescue levers:**
- ✅ Confidence percentile filter (top 10% only): 3,175 trades, potential R much higher
- ✅ Maker execution: reduces cost gap significantly
- ❌ Even with best levers, the raw edge is too thin (0.0076R)

**Decision:** COST_RESCUE_LOW — raw edge is 8× too small for cost rescue.

---

## Candidate 3: BB Position Mean-Reversion v1 (CONTAMINATED)

| Metric | Raw | Taker Cost |
|--------|-----|------------|
| R/trade | +0.0043 | -0.0577 |
| Trades | 4,552 | 4,552 |

**Decision:** COST_RESCUE_NOT_WORTH_IT — contaminated AND positive only due
to future leakage. Do not attempt rescue.

---

## Cost Rescue Levers Summary

| Lever | Expected Gain | Complexity | Notes |
|-------|--------------|------------|-------|
| Maker execution | +0.012 to +0.021R | LOW | Already measured, works |
| Symbol whitelist | +0.01 to +0.03R | LOW | BTCUSDT-only filtering |
| Confidence filter | +0.02 to +0.10R | LOW | Top-quartile only |
| Regime filter | +0.01 to +0.03R | LOW | Non-uptrend + SHORT |
| Wider targets | +0.01 to +0.05R | MEDIUM | Changes profile |
| Longer hold | +0.01 to +0.03R | MEDIUM | Changes profile |
| Volume filter | +0.005 to +0.02R | LOW | High-volume only |
| Session filter | +0.005 to +0.02R | LOW | Liquid hours only |

**Combined best case (all levers):** ~+0.12 to +0.20R improvement.
This means a raw alpha needs at minimum -0.05R after best levers to potentially
reach +0.10R. No current alpha meets this threshold at base cost.

---

## Verdict

No alpha is cost-rescuable to +0.10R with the current toolkit.

**The cost gap is not an execution problem — it is an edge magnitude problem.**
The best raw alpha (+0.0515R) needs to be 3-5× more powerful before cost rescue
becomes feasible. New alpha discovery is required, not cost optimization.
