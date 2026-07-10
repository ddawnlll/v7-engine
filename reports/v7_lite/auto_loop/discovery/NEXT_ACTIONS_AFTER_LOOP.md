# Next Actions After Loop

**Generated:** 2026-07-08T08:10:00+00:00
**Loop Phase:** COMPLETE
**Raw positive created:** 0
**Cost survivors created:** 0

---

## Summary

This loop did NOT improve any alpha count metric. The honest assessment is:

| Metric | Before | After | Delta | Target |
|--------|--------|-------|-------|--------|
| Raw-positive alphas | 3 | 3 | 0 | 5+ |
| Cost-survivor candidates | 0 | 0 | 0 | 1+ |
| Promotion candidates | 0 | 0 | 0 | 0-1 |
| Retest-required count | 87 | 87 | 0 | Reduce |
| Blocked tasks | 0 | 4 | +4 | 0 |

---

## Blockers Preventing Progress

### Blocker #1: Cost Dominance (HARD BLOCKER)

| Detail | Value |
|--------|-------|
| **Cost per trade** | ~0.062R |
| **Best raw alpha** | +0.0515R (Truth V6) |
| **Best factor IC** | 0.035 (volume_zscore) |
| **Gap** | All factors need IC > 0.10 to survive costs |

No factor or alpha in the entire inventory has sufficient edge to survive the cost model.
This is the primary HARD BLOCKER for creating cost survivors.

**Possible mitigations:**
- Maker execution (reduces cost to ~0.031R)
- High-ATR regime filtering (cost/R is lower when ATR is high)
- Symbol whitelist to most liquid pairs (BTCUSDT only, reduces slippage)

### Blocker #2: Central Simulation Bridge Not Built

| Detail | Value |
|--------|-------|
| **Proxy entries needing retest** | 33 |
| **Current sim** | Standalone fast_simulator with TOTAL_COST_RATE = 0.0012 |
| **Target sim** | `simulation/engine/engine.py` with full cost model |
| **Effort** | ~150-250 lines of Python (adapter + CLI) |
| **Blocker type** | ENGINEERING — not analysis |

### Blocker #3: Trade Data Not Persisted

| Detail | Value |
|--------|-------|
| **Affected alpha** | Truth V6 (Discovery Pipeline V6) |
| **Available data** | Aggregate metrics only (total R = +0.0515, 870 trades) |
| **Missing data** | Per-trade R, symbol, direction, timestamp, ATR at entry, confidence |
| **Effort to fix** | Re-run discovery pipeline with logging enabled |
| **Blocker type** | INFRASTRUCTURE — needs pipeline execution |

---

## Priority Actions

### P0: Re-run Truth V6 with per-trade logging (4-6 hours)

```text
What: Re-run discovery_pipeline_v6 with complete trade logging
Why: Unlocks experiments 6 and 7 (best chance at cost survivor)
Deliverable: Per-trade CSV with R, symbol, direction, timestamp, ATR, confidence
Expected cost survivor: BTCUSDT SHORT maker, ~130-200 trades, ~+0.089R
Risk: Trade count may still be below 200 threshold
```

### P1: Build central simulation bridge (2-4 hours)

```text
What: Implement alphaforge/factors/central_sim_bridge.py + CLI
Why: Unlocks experiments 9, 10 and enables all future factor re-simulations
Deliverable: batch converter + CLI runner
Risk: Central sim may produce same or worse results as fast_simulator
```

### P2: Re-run BB Position v1 with fixed pipeline (1-2 hours)

```text
What: Re-run the XGBoost training pipeline with current (fixed) features
Why: Confirms or rejects experiment 8 conclusively
Expected clean R: ~0.000 to +0.002 (likely negative after costs)
Risk: Confirms the v1 edge was entirely from contamination
```

---

## Forbidden Next Actions

- ❌ Claim revenue readiness
- ❌ Build live executor
- ❌ Mutate cost model
- ❌ Mutate risk limits
- ❌ Claim 60%+ overall readiness (blocked by hard cap: 0 cost-adjusted positives)
- ❌ Let LLM mutate full configs
- ❌ Delete or overwrite existing reports
- ❌ Random alpha mining
- ❌ Hidden OOS optimization

---

## What Would Break the Logjam

A **single** cost-surviving alpha requires:

```text
raw_edge > cost_per_trade
raw_edge > 0.062R (taker) or 0.031R (maker)
```

The only candidates that might achieve this:

| Candidate | Raw R | Estimated | Trade Count | Likelihood |
|-----------|-------|-----------|-------------|------------|
| Truth V6 BTCUSDT SHORT maker | +0.0515 | ~+0.12R (extrapolated) | ~150 | MEDIUM |
| Truth V6 top 25% confidence | +0.0515 | ~+0.15R | ~200 | LOW |
| Direction-corrected ret_*_rank | -0.55 to -0.84 | ~+0.00 to +0.02 | 80K+ | VERY LOW (IC too weak) |

**None are guaranteed. All require infrastructure work outside this loop.**
